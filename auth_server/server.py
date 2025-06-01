"""
Simplified Authentication server that validates JWT tokens against Amazon Cognito.
Configuration is passed via headers instead of environment variables.
"""

import argparse
import logging
import boto3
import jwt
import requests
import json
import yaml
from jwt.api_jwk import PyJWK
from datetime import datetime
from typing import Dict, Optional, List
from functools import lru_cache
from botocore.exceptions import ClientError
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
import uvicorn
from pydantic import BaseModel
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="[%(asctime)s] p%(process)s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
# Load scopes configuration
def load_scopes_config():
    """Load the scopes configuration from scopes.yml"""
    try:
        scopes_file = Path(__file__).parent / "scopes.yml"
        with open(scopes_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load scopes configuration: {e}")
        return {}

# Global scopes configuration
SCOPES_CONFIG = load_scopes_config()

def parse_server_and_tool_from_url(original_url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse server name and tool name from the original URL and request payload.
    
    Args:
        original_url: The original URL from X-Original-URL header
        
    Returns:
        Tuple of (server_name, tool_name) or (None, None) if parsing fails
    """
    try:
        # Extract path from URL (remove query parameters and fragments)
        from urllib.parse import urlparse
        parsed_url = urlparse(original_url)
        path = parsed_url.path.strip('/')
        
        # The path should be in format: /server_name/...
        # Extract the first path component as server name
        path_parts = path.split('/') if path else []
        server_name = path_parts[0] if path_parts else None
        
        logger.debug(f"Parsed server name '{server_name}' from URL path: {path}")
        return server_name, None  # Tool name would need to be extracted from request payload
        
    except Exception as e:
        logger.error(f"Failed to parse server/tool from URL {original_url}: {e}")
        return None, None

def validate_server_tool_access(server_name: str, tool_name: str, user_scopes: List[str]) -> bool:
    """
    Validate if the user has access to the specified server and tool based on scopes.
    
    Args:
        server_name: Name of the MCP server
        tool_name: Name of the tool being accessed
        user_scopes: List of user scopes from token
        
    Returns:
        True if access is allowed, False otherwise
    """
    try:
        if not SCOPES_CONFIG:
            logger.warning("No scopes configuration loaded, allowing access")
            return True
            
        # Check each user scope to see if it grants access
        for scope in user_scopes:
            scope_config = SCOPES_CONFIG.get(scope, {})
            
            # Check both 'read' and 'execute' permissions
            for permission_type in ['read', 'execute']:
                servers = scope_config.get(permission_type, [])
                
                for server_config in servers:
                    if server_config.get('server') == server_name:
                        allowed_tools = server_config.get('tools', [])
                        if tool_name in allowed_tools:
                            logger.debug(f"Access granted: scope '{scope}' allows {permission_type} access to {server_name}.{tool_name}")
                            return True
        
        logger.warning(f"Access denied: no scope allows access to {server_name}.{tool_name} for user scopes: {user_scopes}")
        return False
        
    except Exception as e:
        logger.error(f"Error validating server/tool access: {e}")
        return False  # Deny access on error

# Create FastAPI app
app = FastAPI(
    title="Simplified Auth Server",
    description="Authentication server for validating JWT tokens against Amazon Cognito with header-based configuration",
    version="0.1.0"
)

class TokenValidationResponse(BaseModel):
    """Response model for token validation"""
    valid: bool
    scopes: List[str] = []
    error: Optional[str] = None
    method: Optional[str] = None
    client_id: Optional[str] = None
    username: Optional[str] = None

class SimplifiedCognitoValidator:
    """
    Simplified Cognito token validator that doesn't rely on environment variables
    """
    
    def __init__(self, region: str = "us-east-1"):
        """
        Initialize with minimal configuration
        
        Args:
            region: Default AWS region
        """
        self.default_region = region
        self._cognito_clients = {}  # Cache boto3 clients by region
        self._jwks_cache = {}  # Cache JWKS by user pool
        
    def _get_cognito_client(self, region: str):
        """Get or create boto3 cognito client for region"""
        if region not in self._cognito_clients:
            self._cognito_clients[region] = boto3.client('cognito-idp', region_name=region)
        return self._cognito_clients[region]
    
    def _get_jwks(self, user_pool_id: str, region: str) -> Dict:
        """
        Get JSON Web Key Set (JWKS) from Cognito with caching
        """
        cache_key = f"{region}:{user_pool_id}"
        
        if cache_key not in self._jwks_cache:
            try:
                issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
                jwks_url = f"{issuer}/.well-known/jwks.json"
                
                response = requests.get(jwks_url, timeout=10)
                response.raise_for_status()
                jwks = response.json()
                
                self._jwks_cache[cache_key] = jwks
                logger.debug(f"Retrieved JWKS for {cache_key} with {len(jwks.get('keys', []))} keys")
                
            except Exception as e:
                logger.error(f"Failed to retrieve JWKS from {jwks_url}: {e}")
                raise ValueError(f"Cannot retrieve JWKS: {e}")
        
        return self._jwks_cache[cache_key]

    def validate_jwt_token(self, 
                          access_token: str, 
                          user_pool_id: str, 
                          client_id: str,
                          region: str = None) -> Dict:
        """
        Validate JWT access token
        
        Args:
            access_token: The bearer token to validate
            user_pool_id: Cognito User Pool ID
            client_id: Expected client ID
            region: AWS region (uses default if not provided)
            
        Returns:
            Dict containing token claims if valid
            
        Raises:
            ValueError: If token is invalid
        """
        if not region:
            region = self.default_region
            
        try:
            # Decode header to get key ID
            unverified_header = jwt.get_unverified_header(access_token)
            kid = unverified_header.get('kid')
            
            if not kid:
                raise ValueError("Token missing 'kid' in header")
            
            # Get JWKS and find matching key
            jwks = self._get_jwks(user_pool_id, region)
            signing_key = None
            
            for key in jwks.get('keys', []):
                if key.get('kid') == kid:
                    # Handle different versions of PyJWT
                    try:
                        # For newer versions of PyJWT
                        from jwt.algorithms import RSAAlgorithm
                        signing_key = RSAAlgorithm.from_jwk(key)
                    except (ImportError, AttributeError):
                        try:
                            # For older versions of PyJWT
                            from jwt.algorithms import get_default_algorithms
                            algorithms = get_default_algorithms()
                            signing_key = algorithms['RS256'].from_jwk(key)
                        except (ImportError, AttributeError):
                            # For PyJWT 2.0.0+
                            signing_key = PyJWK.from_jwk(json.dumps(key)).key
                    break
            
            if not signing_key:
                raise ValueError(f"No matching key found for kid: {kid}")
            
            # Set up issuer for validation
            issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
            
            # Validate and decode token
            claims = jwt.decode(
                access_token,
                signing_key,
                algorithms=['RS256'],
                issuer=issuer,
                options={
                    "verify_aud": False,  # M2M tokens might not have audience
                    "verify_exp": True,   # Always check expiration
                    "verify_iat": True,   # Check issued at time
                }
            )
            
            # Additional validations
            token_use = claims.get('token_use')
            if token_use not in ['access', 'id']:  # Allow both access and id tokens
                raise ValueError(f"Invalid token_use: {token_use}")
            
            # For M2M tokens, check client_id
            token_client_id = claims.get('client_id')
            if token_client_id and token_client_id != client_id:
                logger.warning(f"Token issued for different client: {token_client_id} vs expected {client_id}")
                # Don't fail immediately - could be user token with different structure
            
            logger.info(f"Successfully validated JWT token for client/user")
            return claims
            
        except jwt.ExpiredSignatureError:
            error_msg = "Token has expired"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        except jwt.InvalidTokenError as e:
            error_msg = f"Invalid token: {e}"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"JWT validation error: {e}"
            logger.error(error_msg)
            raise ValueError(f"Token validation failed: {e}")

    def validate_with_boto3(self, 
                           access_token: str, 
                           region: str = None) -> Dict:
        """
        Validate token using boto3 GetUser API (works for user tokens)
        
        Args:
            access_token: The bearer token to validate
            region: AWS region
            
        Returns:
            Dict containing user information if valid
            
        Raises:
            ValueError: If token is invalid
        """
        if not region:
            region = self.default_region
            
        try:
            cognito_client = self._get_cognito_client(region)
            response = cognito_client.get_user(AccessToken=access_token)
            
            # Extract user attributes
            user_attributes = {}
            for attr in response.get('UserAttributes', []):
                user_attributes[attr['Name']] = attr['Value']
            
            result = {
                'username': response.get('Username'),
                'user_attributes': user_attributes,
                'user_status': response.get('UserStatus'),
                'token_use': 'access',  # boto3 method implies access token
                'auth_method': 'boto3'
            }
            
            logger.info(f"Successfully validated token via boto3 for user {result['username']}")
            return result
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'NotAuthorizedException':
                error_msg = "Invalid or expired access token"
                logger.warning(f"Cognito error {error_code}: {error_message}")
                raise ValueError(error_msg)
            elif error_code == 'UserNotFoundException':
                error_msg = "User not found"
                logger.warning(f"Cognito error {error_code}: {error_message}")
                raise ValueError(error_msg)
            else:
                logger.error(f"Cognito error {error_code}: {error_message}")
                raise ValueError(f"Token validation failed: {error_message}")
                
        except Exception as e:
            logger.error(f"Boto3 validation error: {e}")
            raise ValueError(f"Token validation failed: {e}")

    def validate_token(self, 
                      access_token: str, 
                      user_pool_id: str, 
                      client_id: str,
                      region: str = None) -> Dict:
        """
        Comprehensive token validation with fallback methods
        
        Args:
            access_token: The bearer token to validate
            user_pool_id: Cognito User Pool ID
            client_id: Expected client ID
            region: AWS region
            
        Returns:
            Dict containing validation results and token information
        """
        if not region:
            region = self.default_region
            
        # Try JWT validation first
        try:
            jwt_claims = self.validate_jwt_token(access_token, user_pool_id, client_id, region)
            
            # Extract scopes and other info
            scopes = []
            if 'scope' in jwt_claims:
                scopes = jwt_claims['scope'].split() if jwt_claims['scope'] else []
            
            return {
                'valid': True,
                'method': 'jwt',
                'data': jwt_claims,
                'client_id': jwt_claims.get('client_id') or '',
                'username': jwt_claims.get('cognito:username') or jwt_claims.get('username') or '',
                'expires_at': jwt_claims.get('exp'),
                'scopes': scopes,
                'groups': jwt_claims.get('cognito:groups', [])
            }
            
        except ValueError as jwt_error:
            logger.debug(f"JWT validation failed: {jwt_error}, trying boto3")
            
            # Try boto3 validation as fallback
            try:
                boto3_data = self.validate_with_boto3(access_token, region)
                
                return {
                    'valid': True,
                    'method': 'boto3',
                    'data': boto3_data,
                    'client_id': '',  # boto3 method doesn't provide client_id
                    'username': boto3_data.get('username') or '',
                    'user_attributes': boto3_data.get('user_attributes', {}),
                    'scopes': [],  # boto3 method doesn't provide scopes
                    'groups': []
                }
                
            except ValueError as boto3_error:
                logger.debug(f"Boto3 validation failed: {boto3_error}")
                raise ValueError(f"All validation methods failed. JWT: {jwt_error}, Boto3: {boto3_error}")

# Create global validator instance
validator = SimplifiedCognitoValidator()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "simplified-auth-server"}

@app.get("/validate")
async def validate_request(request: Request):
    """
    Validate a request by extracting configuration from headers and validating the bearer token.
    
    Expected headers:
    - Authorization: Bearer <token>
    - X-User-Pool-Id: <user_pool_id>
    - X-Client-Id: <client_id>
    - X-Region: <region> (optional, defaults to us-east-1)
    - X-Original-URL: <original_url> (optional, for scope validation)
    
    Returns:
        HTTP 200 with user info headers if valid, HTTP 401/403 if invalid
        
    Raises:
        HTTPException: If the token is missing, invalid, or configuration is incomplete
    """
    
    
    try:
        # Extract headers
        authorization = request.headers.get("Authorization")
        user_pool_id = request.headers.get("X-User-Pool-Id")
        client_id = request.headers.get("X-Client-Id")
        region = request.headers.get("X-Region", "us-east-1")
        original_url = request.headers.get("X-Original-URL")
        body = request.headers.get("X-Body")
        
        # Extract server_name from original_url early for logging
        server_name_from_url = None
        if original_url:
            try:
                from urllib.parse import urlparse
                parsed_url = urlparse(original_url)
                path = parsed_url.path.strip('/')
                path_parts = path.split('/') if path else []
                server_name_from_url = path_parts[0] if path_parts else None
                logger.info(f"Extracted server_name '{server_name_from_url}' from original_url: {original_url}")
            except Exception as e:
                logger.warning(f"Failed to extract server_name from original_url {original_url}: {e}")
        
        # Read request body
        request_payload = None
        try:
            if body:
                payload_text = body #.decode('utf-8')
                logger.info(f"Raw Request Payload ({len(payload_text)} chars): {payload_text[:1000]}...")
                request_payload = json.loads(payload_text)
                logger.info(f"JSON RPC Request Payload: {json.dumps(request_payload, indent=2)}")
            else:
                logger.info(f"No request body provided, skipping payload parsing")
        except UnicodeDecodeError as e:
            logger.warning(f"Could not decode body as UTF-8: {e}")
        except json.JSONDecodeError as e:
            logger.warning(f"Could not parse JSON RPC payload: {e}")
        except Exception as e:
            logger.error(f"Error reading request payload: {type(e).__name__}: {e}")
        
        # Log request for debugging
        logger.info(f"Validation request from {request.client.host if request.client else 'unknown'}")
        logger.info(f"Request Method: {request.method}")
        
        # Log all HTTP headers present
        all_headers = dict(request.headers)
        logger.info(f"All HTTP Headers: {json.dumps(all_headers, indent=2)}")
        
        # Log specific headers for debugging
        logger.info(f"Key Headers: Authorization={bool(authorization)}, "
                    f"User-Pool-Id={user_pool_id}, Client-Id={client_id}, Region={region}, "
                    f"Original-URL={original_url}")
        logger.info(f"Server Name from URL: {server_name_from_url}")
        
        # Validate required headers
        if not authorization or not authorization.startswith("Bearer "):
            logger.warning("Missing or invalid Authorization header")
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid Authorization header. Expected: Bearer <token>",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        if not user_pool_id:
            logger.warning("Missing X-User-Pool-Id header")
            raise HTTPException(
                status_code=400,
                detail="Missing X-User-Pool-Id header"
            )
        
        if not client_id:
            logger.warning("Missing X-Client-Id header")
            raise HTTPException(
                status_code=400,
                detail="Missing X-Client-Id header"
            )
        
        # Extract token
        access_token = authorization.split(" ")[1]
        
        # Validate the token
        validation_result = validator.validate_token(
            access_token=access_token,
            user_pool_id=user_pool_id,
            client_id=client_id,
            region=region
        )
        
        logger.info(f"Token validation successful using method: {validation_result['method']}")
        
        # Parse server and tool information from original URL if available
        server_name = server_name_from_url  # Use the server_name we extracted earlier
        tool_name = None
        
        if original_url and request_payload:
            # We already extracted server_name above, now just get tool_name from URL parsing
            _, tool_name = parse_server_and_tool_from_url(original_url)
            logger.debug(f"Parsed from original URL: server='{server_name}', tool='{tool_name}'")
            
            # Try to extract tool name from request payload if not found in URL
            if server_name and not tool_name and request_payload:
                try:
                    # Look for tool name in JSON-RPC 2.0 format and other MCP patterns
                    if isinstance(request_payload, dict):
                        # JSON-RPC 2.0 format: method field contains the tool name
                        tool_name = request_payload.get('method')
                        
                        # If not found in method, check other common patterns
                        if not tool_name:
                            tool_name = request_payload.get('tool') or request_payload.get('name')
                            
                        # Check for nested tool reference in params
                        if not tool_name and 'params' in request_payload:
                            params = request_payload['params']
                            if isinstance(params, dict):
                                tool_name = params.get('name') or params.get('tool') or params.get('method')
                        
                        logger.info(f"Extracted tool name from JSON-RPC payload: '{tool_name}'")
                    else:
                        logger.warning(f"Payload is not a dictionary: {type(request_payload)}")
                except Exception as e:
                    logger.error(f"Error processing request payload for tool extraction: {e}")
        
        # Validate scope-based access if we have server/tool information
        user_scopes = validation_result.get('scopes', [])
        if request_payload and server_name and tool_name and user_scopes:
            if not validate_server_tool_access(server_name, tool_name, user_scopes):
                logger.warning(f"Access denied for user {validation_result.get('username')} to {server_name}.{tool_name}")
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied to {server_name}.{tool_name}"
                )
            logger.info(f"Scope validation passed for {server_name}.{tool_name}")
        elif server_name or tool_name:
            logger.debug(f"Partial server/tool info available (server='{server_name}', tool='{tool_name}'), skipping scope validation")
        else:
            logger.debug("No server/tool information available, skipping scope validation")
        
        # Prepare JSON response data
        response_data = {
            'valid': True,
            'username': validation_result.get('username') or '',
            'client_id': validation_result.get('client_id') or '',
            'scopes': validation_result.get('scopes', []),
            'method': validation_result.get('method') or '',
            'groups': validation_result.get('groups', []),
            'server_name': server_name,
            'tool_name': tool_name
        }
        logger.info(f"Full validation result: {json.dumps(validation_result, indent=2)}")
        # Create JSON response with headers that nginx can use
        response = JSONResponse(content=response_data, status_code=200)
        
        # Set headers for nginx auth_request_set directives
        response.headers["X-User"] = validation_result.get('username') or ''
        response.headers["X-Username"] = validation_result.get('username') or ''
        response.headers["X-Client-Id"] = validation_result.get('client_id') or ''
        response.headers["X-Scopes"] = ' '.join(validation_result.get('scopes', []))
        response.headers["X-Auth-Method"] = validation_result.get('method') or ''
        response.headers["X-Server-Name"] = server_name or ''
        response.headers["X-Tool-Name"] = tool_name or ''
        
        return response
        
    except ValueError as e:
        logger.warning(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        logger.error(f"Unexpected error during validation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal validation error: {str(e)}"
        )
    finally:
        pass

@app.get("/config")
async def get_auth_config():
    """Return the authentication configuration info"""
    return {
        "auth_type": "cognito",
        "description": "Header-based Cognito token validation",
        "required_headers": [
            "Authorization: Bearer <token>",
            "X-User-Pool-Id: <pool_id>",
            "X-Client-Id: <client_id>"
        ],
        "optional_headers": [
            "X-Region: <region> (default: us-east-1)"
        ]
    }

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Simplified Auth Server")

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for the server to listen on (default: 0.0.0.0)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8888,
        help="Port for the server to listen on (default: 8888)",
    )

    parser.add_argument(
        "--region",
        type=str,
        default="us-east-1",
        help="Default AWS region (default: us-east-1)",
    )

    return parser.parse_args()

def main():
    """Run the server"""
    args = parse_arguments()
    
    # Update global validator with default region
    global validator
    validator = SimplifiedCognitoValidator(region=args.region)
    
    logger.info(f"Starting simplified auth server on {args.host}:{args.port}")
    logger.info(f"Default region: {args.region}")
    
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()