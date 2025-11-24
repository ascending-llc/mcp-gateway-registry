"""
Simplified Authentication server that validates JWT tokens against Amazon Cognito.
Configuration is passed via headers instead of environment variables.
"""

import argparse
import logging
import os
import boto3
import jwt
import requests
import json
import yaml
import time
import uuid
import hashlib
from jwt.api_jwk import PyJWK
from datetime import datetime
from typing import Dict, Optional, List, Any
from functools import lru_cache
from botocore.exceptions import ClientError
from fastapi import FastAPI, Header, HTTPException, Request, Cookie
from fastapi.responses import JSONResponse, Response, RedirectResponse
import uvicorn
from pydantic import BaseModel
from pathlib import Path
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import secrets
import urllib.parse
import httpx
from string import Template

# Import metrics middleware
from metrics_middleware import add_auth_metrics_middleware

# Import provider factory
from providers.factory import get_auth_provider

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# Configuration for token generation
JWT_ISSUER = "mcp-auth-server"
JWT_AUDIENCE = "mcp-registry"
MAX_TOKEN_LIFETIME_HOURS = 24
DEFAULT_TOKEN_LIFETIME_HOURS = 8

# Rate limiting for token generation (simple in-memory counter)
user_token_generation_counts = {}
MAX_TOKENS_PER_USER_PER_HOUR = int(os.environ.get('MAX_TOKENS_PER_USER_PER_HOUR', '100'))

# Load scopes configuration
def load_scopes_config():
    """Load the scopes configuration from scopes.yml"""
    try:
        # Check for environment variable first (for EFS-mounted config)
        scopes_path = os.environ.get('SCOPES_CONFIG_PATH')
        if scopes_path:
            scopes_file = Path(scopes_path)
        else:
            # Fall back to default location (baked into image)
            scopes_file = Path(__file__).parent / "scopes.yml"

        with open(scopes_file, 'r') as f:
            config = yaml.safe_load(f)
            logger.info(f"Loaded scopes configuration from {scopes_file} with {len(config.get('group_mappings', {}))} group mappings")
            return config
    except Exception as e:
        logger.error(f"Failed to load scopes configuration: {e}")
        return {}

# Global scopes configuration (will be reloaded dynamically)
SCOPES_CONFIG = load_scopes_config()

# Utility functions for GDPR/SOX compliance
def mask_sensitive_id(value: str) -> str:
    """Mask sensitive IDs showing only first and last 4 characters."""
    if not value or len(value) <= 8:
        return "***MASKED***"
    return f"{value[:4]}...{value[-4:]}"

def hash_username(username: str) -> str:
    """Hash username for privacy compliance."""
    if not username:
        return "anonymous"
    return f"user_{hashlib.sha256(username.encode()).hexdigest()[:8]}"

def anonymize_ip(ip_address: str) -> str:
    """Anonymize IP address by masking last octet for IPv4."""
    if not ip_address or ip_address == 'unknown':
        return ip_address
    if '.' in ip_address:  # IPv4
        parts = ip_address.split('.')
        if len(parts) == 4:
            return f"{'.'.join(parts[:3])}.xxx"
    elif ':' in ip_address:  # IPv6
        # Mask last segment
        parts = ip_address.split(':')
        if len(parts) > 1:
            parts[-1] = 'xxxx'
            return ':'.join(parts)
    return ip_address

def mask_token(token: str) -> str:
    """Mask JWT token showing only last 4 characters."""
    if not token:
        return "***EMPTY***"
    if len(token) > 20:
        return f"...{token[-4:]}"
    return "***MASKED***"

def mask_headers(headers: dict) -> dict:
    """Mask sensitive headers for logging compliance."""
    masked = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if key_lower in ['x-authorization', 'authorization', 'cookie']:
            if 'bearer' in str(value).lower():
                # Extract token part and mask it
                parts = str(value).split(' ', 1)
                if len(parts) == 2:
                    masked[key] = f"Bearer {mask_token(parts[1])}"
                else:
                    masked[key] = mask_token(value)
            else:
                masked[key] = "***MASKED***"
        elif key_lower in ['x-user-pool-id', 'x-client-id']:
            masked[key] = mask_sensitive_id(value)
        else:
            masked[key] = value
    return masked

def map_groups_to_scopes(groups: List[str]) -> List[str]:
    """
    Map identity provider groups to MCP scopes using the group_mappings from scopes.yml configuration.
    
    Args:
        groups: List of group names from identity provider (Cognito, Keycloak, etc.)
        
    Returns:
        List of MCP scopes
    """
    scopes = []
    group_mappings = SCOPES_CONFIG.get('group_mappings', {})
    
    for group in groups:
        if group in group_mappings:
            group_scopes = group_mappings[group]
            scopes.extend(group_scopes)
            logger.debug(f"Mapped group '{group}' to scopes: {group_scopes}")
        else:
            logger.debug(f"No scope mapping found for group: {group}")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_scopes = []
    for scope in scopes:
        if scope not in seen:
            seen.add(scope)
            unique_scopes.append(scope)
    
    logger.info(f"Final mapped scopes: {unique_scopes}")
    return unique_scopes

def validate_session_cookie(cookie_value: str) -> Dict[str, any]:
    """
    Validate session cookie using itsdangerous serializer.
    
    Args:
        cookie_value: The session cookie value
        
    Returns:
        Dict containing validation results matching JWT validation format:
        {
            'valid': True,
            'username': str,
            'scopes': List[str],
            'method': 'session_cookie',
            'groups': List[str]
        }
        
    Raises:
        ValueError: If cookie is invalid or expired
    """
    # Use global signer initialized at startup
    global signer
    if not signer:
        logger.warning("Global signer not configured for session cookie validation")
        raise ValueError("Session cookie validation not configured")
    
    try:
        # Decrypt cookie (max_age=28800 for 8 hours)
        data = signer.loads(cookie_value, max_age=28800)
        
        # Extract user info
        username = data.get('username')
        groups = data.get('groups', [])
        
        # Map groups to scopes
        scopes = map_groups_to_scopes(groups)
        
        logger.info(f"Session cookie validated for user: {hash_username(username)}")
        
        return {
            'valid': True,
            'username': username,
            'scopes': scopes,
            'method': 'session_cookie',
            'groups': groups,
            'client_id': '',  # Not applicable for session
            'data': data  # Include full data for consistency
        }
    except SignatureExpired:
        logger.warning("Session cookie has expired")
        raise ValueError("Session cookie has expired")
    except BadSignature:
        logger.warning("Invalid session cookie signature")
        raise ValueError("Invalid session cookie")
    except Exception as e:
        logger.error(f"Session cookie validation error: {e}")
        raise ValueError(f"Session cookie validation failed: {e}")

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


def _normalize_server_name(name: str) -> str:
    """
    Normalize server name by removing trailing slash for comparison.

    This handles cases where a server is registered with a trailing slash
    but accessed without one (or vice versa).

    Args:
        name: Server name to normalize

    Returns:
        Normalized server name (without trailing slash)
    """
    return name.rstrip('/') if name else name


def _server_names_match(name1: str, name2: str) -> bool:
    """
    Compare two server names, normalizing for trailing slashes.
    Supports wildcard matching with '*'.

    Args:
        name1: First server name (can be '*' for wildcard)
        name2: Second server name

    Returns:
        True if names match (ignoring trailing slashes) or if name1 is '*', False otherwise
    """
    normalized_name1 = _normalize_server_name(name1)
    if normalized_name1 == '*':
        return True
    return normalized_name1 == _normalize_server_name(name2)


def validate_server_tool_access(server_name: str, method: str, tool_name: str, user_scopes: List[str]) -> bool:
    """
    Validate if the user has access to the specified server method/tool based on scopes.
    
    Args:
        server_name: Name of the MCP server
        method: Name of the method being accessed (e.g., 'initialize', 'notifications/initialized', 'tools/list')
        tool_name: Name of the specific tool being accessed (optional, for tools/call)
        user_scopes: List of user scopes from token
        
    Returns:
        True if access is allowed, False otherwise
    """
    try:
        # Verbose logging: Print input parameters
        logger.info(f"=== VALIDATE_SERVER_TOOL_ACCESS START ===")
        logger.info(f"Requested server: '{server_name}'")
        logger.info(f"Requested method: '{method}'")
        logger.info(f"Requested tool: '{tool_name}'")
        logger.info(f"User scopes: {user_scopes}")
        logger.info(f"Available scopes config keys: {list(SCOPES_CONFIG.keys()) if SCOPES_CONFIG else 'None'}")
        
        if not SCOPES_CONFIG:
            logger.warning("No scopes configuration loaded, allowing access")
            logger.info(f"=== VALIDATE_SERVER_TOOL_ACCESS END: ALLOWED (no config) ===")
            return True
            
        # Check each user scope to see if it grants access
        for scope in user_scopes:
            logger.info(f"--- Checking scope: '{scope}' ---")
            scope_config = SCOPES_CONFIG.get(scope, [])
            
            if not scope_config:
                logger.info(f"Scope '{scope}' not found in configuration")
                continue
                
            logger.info(f"Scope '{scope}' config: {scope_config}")
            
            # The scope_config is directly a list of server configurations
            # since the permission type is already encoded in the scope name
            for server_config in scope_config:
                logger.info(f"  Examining server config: {server_config}")
                server_config_name = server_config.get('server')
                logger.info(f"  Server name in config: '{server_config_name}' vs requested: '{server_name}'")

                if _server_names_match(server_config_name, server_name):
                    logger.info(f"  ✓ Server name matches!")
                    
                    # Check methods first
                    allowed_methods = server_config.get('methods', [])
                    logger.info(f"  Allowed methods for server '{server_name}': {allowed_methods}")
                    logger.info(f"  Checking if method '{method}' is in allowed methods...")

                    # Check if all methods are allowed (wildcard support)
                    has_wildcard_methods = 'all' in allowed_methods or '*' in allowed_methods

                    # for all methods except tools/call we are good if the method is allowed
                    # for tools/call we need to do an extra validation to check if the tool
                    # itself is allowed or not
                    if (method in allowed_methods or has_wildcard_methods) and method != 'tools/call':
                        logger.info(f"  ✓ Method '{method}' found in allowed methods!")
                        logger.info(f"Access granted: scope '{scope}' allows access to {server_name}.{method}")
                        logger.info(f"=== VALIDATE_SERVER_TOOL_ACCESS END: GRANTED ===")
                        return True
                    
                    # Check tools if method not found in methods
                    allowed_tools = server_config.get('tools', [])
                    logger.info(f"  Allowed tools for server '{server_name}': {allowed_tools}")

                    # Check if all tools are allowed (wildcard support)
                    has_wildcard_tools = 'all' in allowed_tools or '*' in allowed_tools

                    # For tools/call, check if the specific tool is allowed
                    if method == 'tools/call' and tool_name:
                        logger.info(f"  Checking if tool '{tool_name}' is in allowed tools for tools/call...")
                        if tool_name in allowed_tools or has_wildcard_tools:
                            logger.info(f"  ✓ Tool '{tool_name}' found in allowed tools!")
                            logger.info(f"Access granted: scope '{scope}' allows access to {server_name}.{method} for tool {tool_name}")
                            logger.info(f"=== VALIDATE_SERVER_TOOL_ACCESS END: GRANTED ===")
                            return True
                        else:
                            logger.info(f"  ✗ Tool '{tool_name}' NOT found in allowed tools")
                    else:
                        # For other methods, check if method is in tools list (backward compatibility)
                        logger.info(f"  Checking if method '{method}' is in allowed tools...")
                        if method in allowed_tools or has_wildcard_tools:
                            logger.info(f"  ✓ Method '{method}' found in allowed tools!")
                            logger.info(f"Access granted: scope '{scope}' allows access to {server_name}.{method}")
                            logger.info(f"=== VALIDATE_SERVER_TOOL_ACCESS END: GRANTED ===")
                            return True
                        else:
                            logger.info(f"  ✗ Method '{method}' NOT found in allowed tools")
                else:
                    logger.info(f"  ✗ Server name does not match")
        
        logger.warning(f"Access denied: no scope allows access to {server_name}.{method} (tool: {tool_name}) for user scopes: {user_scopes}")
        logger.info(f"=== VALIDATE_SERVER_TOOL_ACCESS END: DENIED ===")
        return False
        
    except Exception as e:
        logger.error(f"Error validating server/tool access: {e}")
        logger.info(f"=== VALIDATE_SERVER_TOOL_ACCESS END: ERROR ===")
        return False  # Deny access on error

def validate_scope_subset(user_scopes: List[str], requested_scopes: List[str]) -> bool:
    """
    Validate that requested scopes are a subset of user's current scopes.
    
    Args:
        user_scopes: List of scopes the user currently has
        requested_scopes: List of scopes being requested for the token
        
    Returns:
        True if requested scopes are valid (subset of user scopes), False otherwise
    """
    if not requested_scopes:
        return True  # Empty request is valid
    
    user_scope_set = set(user_scopes)
    requested_scope_set = set(requested_scopes)
    
    is_valid = requested_scope_set.issubset(user_scope_set)
    
    if not is_valid:
        invalid_scopes = requested_scope_set - user_scope_set
        logger.warning(f"Invalid scopes requested: {invalid_scopes}")
    
    return is_valid

def check_rate_limit(username: str) -> bool:
    """
    Check if user has exceeded token generation rate limit.
    
    Args:
        username: Username to check
        
    Returns:
        True if under rate limit, False if exceeded
    """
    current_time = int(time.time())
    current_hour = current_time // 3600
    
    # Clean up old entries (older than 1 hour)
    keys_to_remove = []
    for key in user_token_generation_counts.keys():
        stored_hour = int(key.split(':')[1])
        if current_hour - stored_hour > 1:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        del user_token_generation_counts[key]
    
    # Check current hour count
    rate_key = f"{username}:{current_hour}"
    current_count = user_token_generation_counts.get(rate_key, 0)
    
    if current_count >= MAX_TOKENS_PER_USER_PER_HOUR:
        logger.warning(f"Rate limit exceeded for user {hash_username(username)}: {current_count} tokens this hour")
        return False
    
    # Increment counter
    user_token_generation_counts[rate_key] = current_count + 1
    return True

# Create FastAPI app
app = FastAPI(
    title="Simplified Auth Server",
    description="Authentication server for validating JWT tokens against Amazon Cognito with header-based configuration",
    version="0.1.0"
)

# Add metrics collection middleware
add_auth_metrics_middleware(app)

class TokenValidationResponse(BaseModel):
    """Response model for token validation"""
    valid: bool
    scopes: List[str] = []
    error: Optional[str] = None
    method: Optional[str] = None
    client_id: Optional[str] = None
    username: Optional[str] = None

class GenerateTokenRequest(BaseModel):
    """Request model for token generation"""
    user_context: Dict[str, Any]
    requested_scopes: List[str] = []
    expires_in_hours: int = DEFAULT_TOKEN_LIFETIME_HOURS
    description: Optional[str] = None

class GenerateTokenResponse(BaseModel):
    """Response model for token generation"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int
    refresh_expires_in: Optional[int] = None
    scope: str
    issued_at: int
    description: Optional[str] = None

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
            
            logger.info(f"Successfully validated token via boto3 for user {hash_username(result['username'])}")
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

    def validate_self_signed_token(self, access_token: str) -> Dict:
        """
        Validate self-signed JWT token generated by this auth server.
        
        Args:
            access_token: The JWT token to validate
            
        Returns:
            Dict containing validation results
            
        Raises:
            ValueError: If token is invalid
        """
        try:
            # Decode and validate JWT using shared SECRET_KEY
            claims = jwt.decode(
                access_token, 
                SECRET_KEY, 
                algorithms=['HS256'],
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "verify_aud": True
                },
                leeway=30  # 30 second leeway for clock skew
            )
            
            # Validate token_use
            token_use = claims.get('token_use')
            if token_use != 'access':
                raise ValueError(f"Invalid token_use: {token_use}")
            
            # Extract scopes from space-separated string
            scope_string = claims.get('scope', '')
            scopes = scope_string.split() if scope_string else []
            
            logger.info(f"Successfully validated self-signed token for user: {claims.get('sub')}")
            
            return {
                'valid': True,
                'method': 'self_signed',
                'data': claims,
                'client_id': claims.get('client_id', 'user-generated'),
                'username': claims.get('sub', ''),
                'expires_at': claims.get('exp'),
                'scopes': scopes,
                'groups': [],  # Self-signed tokens don't have groups
                'token_type': 'user_generated'
            }
            
        except jwt.ExpiredSignatureError:
            error_msg = "Self-signed token has expired"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        except jwt.InvalidTokenError as e:
            error_msg = f"Invalid self-signed token: {e}"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Self-signed token validation error: {e}"
            logger.error(error_msg)
            raise ValueError(f"Self-signed token validation failed: {e}")

    def validate_token(self, 
                      access_token: str, 
                      user_pool_id: str, 
                      client_id: str,
                      region: str = None) -> Dict:
        """
        Comprehensive token validation with fallback methods.
        Now supports both Cognito tokens and self-signed tokens.
        
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
            
        # First try self-signed token validation (faster)
        try:
            # Quick check if it might be our token by attempting to decode without verification
            unverified_claims = jwt.decode(access_token, options={"verify_signature": False})
            if unverified_claims.get('iss') == JWT_ISSUER:
                logger.debug("Token appears to be self-signed, validating...")
                return self.validate_self_signed_token(access_token)
        except Exception:
            # Not our token or malformed, continue to Cognito validation
            pass
            
        # Try JWT validation with Cognito
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
        # Check for X-Authorization first (custom header used by this gateway)
        # Only if X-Authorization is not present, check standard Authorization header
        authorization = request.headers.get("X-Authorization")
        if not authorization:
            authorization = request.headers.get("Authorization")
        cookie_header = request.headers.get("Cookie", "")
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
        
        # Log request for debugging with anonymized IP
        client_ip = request.client.host if request.client else 'unknown'
        logger.info(f"Validation request from {anonymize_ip(client_ip)}")
        logger.info(f"Request Method: {request.method}")
        
        # Log masked HTTP headers for GDPR/SOX compliance
        all_headers = dict(request.headers)
        masked_headers = mask_headers(all_headers)
        logger.debug(f"HTTP Headers (masked): {json.dumps(masked_headers, indent=2)}")
        
        # Log specific headers for debugging with masked sensitive data
        logger.info(f"Key Headers: Authorization={bool(authorization)}, Cookie={bool(cookie_header)}, "
                    f"User-Pool-Id={mask_sensitive_id(user_pool_id) if user_pool_id else 'None'}, "
                    f"Client-Id={mask_sensitive_id(client_id) if client_id else 'None'}, "
                    f"Region={region}, Original-URL={original_url}")
        logger.info(f"Server Name from URL: {server_name_from_url}")
        
        # Initialize validation result
        validation_result = None
        
        # FIRST: Check for session cookie if present
        if "mcp_gateway_session=" in cookie_header:
            logger.info("Session cookie detected, attempting session validation")
            # Extract cookie value
            cookie_value = None
            for cookie in cookie_header.split(';'):
                if cookie.strip().startswith('mcp_gateway_session='):
                    cookie_value = cookie.strip().split('=', 1)[1]
                    break
            
            if cookie_value:
                try:
                    validation_result = validate_session_cookie(cookie_value)
                    # Log validation result without exposing username
                    safe_result = {k: v for k, v in validation_result.items() if k != 'username'}
                    safe_result['username'] = hash_username(validation_result.get('username', ''))
                    logger.info(f"Session cookie validation result: {safe_result}")
                    logger.info(f"Session cookie validation successful for user: {hash_username(validation_result['username'])}")
                except ValueError as e:
                    logger.warning(f"Session cookie validation failed: {e}")
                    # Fall through to JWT validation
        
        # SECOND: If no valid session cookie, check for JWT token
        if not validation_result:
            # Validate required headers for JWT
            if not authorization or not authorization.startswith("Bearer "):
                logger.warning("Missing or invalid Authorization header and no valid session cookie")
                raise HTTPException(
                    status_code=401,
                    detail="Missing or invalid Authorization header. Expected: Bearer <token> or valid session cookie",
                    headers={"WWW-Authenticate": "Bearer", "Connection": "close"}
                )
            
            # Extract token
            access_token = authorization.split(" ")[1]
            
            # Get authentication provider based on AUTH_PROVIDER environment variable
            try:
                auth_provider = get_auth_provider()
                logger.info(f"Using authentication provider: {auth_provider.__class__.__name__}")
                
                # Provider-specific validation
                if hasattr(auth_provider, 'validate_token'):
                    # For Keycloak, no additional headers needed
                    validation_result = auth_provider.validate_token(access_token)
                    logger.info(f"Token validation successful using {auth_provider.__class__.__name__}")
                else:
                    # Fallback to old validation for compatibility
                    if not user_pool_id:
                        logger.warning("Missing X-User-Pool-Id header for Cognito validation")
                        raise HTTPException(
                            status_code=400,
                            detail="Missing X-User-Pool-Id header",
                            headers={"Connection": "close"}
                        )
                    
                    if not client_id:
                        logger.warning("Missing X-Client-Id header for Cognito validation")
                        raise HTTPException(
                            status_code=400,
                            detail="Missing X-Client-Id header",
                            headers={"Connection": "close"}
                        )
                    
                    # Use old validator for backward compatibility
                    validation_result = validator.validate_token(
                        access_token=access_token,
                        user_pool_id=user_pool_id,
                        client_id=client_id,
                        region=region
                    )
                    
            except Exception as e:
                logger.error(f"Authentication provider error: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Authentication provider configuration error: {str(e)}",
                    headers={"Connection": "close"}
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
        # For providers that use groups (Keycloak, Entra ID, Cognito), map groups to scopes
        user_groups = validation_result.get('groups', [])
        auth_method = validation_result.get('method', '')
        if user_groups and auth_method in ['keycloak', 'entra', 'cognito']:
            # Map IdP groups to scopes using the group mappings
            user_scopes = map_groups_to_scopes(user_groups)
            logger.info(f"Mapped {auth_method} groups {user_groups} to scopes: {user_scopes}")
        else:
            user_scopes = validation_result.get('scopes', [])
        if server_name:
            # For ANY server access, enforce scope validation (fail closed principle)
            # This includes MCP initialization methods that may not have a specific tool

            method = tool_name if tool_name else "initialize"  # Default to initialize if no tool specified
            actual_tool_name = None

            # For tools/call, extract the actual tool name from params
            if method == 'tools/call' and isinstance(request_payload, dict):
                params = request_payload.get('params', {})
                if isinstance(params, dict):
                    actual_tool_name = params.get('name')
                    logger.info(f"Extracted actual tool name for tools/call: '{actual_tool_name}'")

            # Check if user has any scopes - if not, deny access (fail closed)
            if not user_scopes:
                logger.warning(f"Access denied for user {hash_username(validation_result.get('username', ''))} to {server_name}.{method} (tool: {actual_tool_name}) - no scopes configured")
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied to {server_name}.{method} - user has no scopes configured",
                    headers={"Connection": "close"}
                )

            if not validate_server_tool_access(server_name, method, actual_tool_name, user_scopes):
                logger.warning(f"Access denied for user {hash_username(validation_result.get('username', ''))} to {server_name}.{method} (tool: {actual_tool_name})")
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied to {server_name}.{method}",
                    headers={"Connection": "close"}
                )
            logger.info(f"Scope validation passed for {server_name}.{method} (tool: {actual_tool_name})")
        else:
            logger.debug("No server information available, skipping scope validation")
        
        # Prepare JSON response data
        response_data = {
            'valid': True,
            'username': validation_result.get('username') or '',
            'client_id': validation_result.get('client_id') or '',
            'scopes': user_scopes,
            'method': validation_result.get('method') or '',
            'groups': validation_result.get('groups', []),
            'server_name': server_name,
            'tool_name': tool_name
        }
        logger.info(f"Full validation result: {json.dumps(validation_result, indent=2)}")
        logger.info(f"Response data being sent: {json.dumps(response_data, indent=2)}")
        # Create JSON response with headers that nginx can use
        response = JSONResponse(content=response_data, status_code=200)
        
        # Set headers for nginx auth_request_set directives
        response.headers["X-User"] = validation_result.get('username') or ''
        response.headers["X-Username"] = validation_result.get('username') or ''
        response.headers["X-Client-Id"] = validation_result.get('client_id') or ''
        response.headers["X-Scopes"] = ' '.join(user_scopes)
        response.headers["X-Auth-Method"] = validation_result.get('method') or ''
        response.headers["X-Server-Name"] = server_name or ''
        response.headers["X-Tool-Name"] = tool_name or ''
        
        return response
        
    except ValueError as e:
        logger.warning(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=401,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer", "Connection": "close"}
        )
    except HTTPException as e:
        # If it's a 403 HTTPException, re-raise it as is
        if e.status_code == 403:
            raise
        # For other HTTPExceptions, let them fall through to general handler
        logger.error(f"HTTP error during validation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal validation error: {str(e)}",
            headers={"Connection": "close"}
        )
    except Exception as e:
        logger.error(f"Unexpected error during validation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal validation error: {str(e)}",
            headers={"Connection": "close"}
        )
    finally:
        pass

@app.get("/config")
async def get_auth_config():
    """Return the authentication configuration info"""
    try:
        auth_provider = get_auth_provider()
        provider_info = auth_provider.get_provider_info()
        
        if provider_info.get('provider_type') == 'keycloak':
            return {
                "auth_type": "keycloak",
                "description": "Keycloak JWT token validation",
                "required_headers": [
                    "Authorization: Bearer <token>"
                ],
                "optional_headers": [],
                "provider_info": provider_info
            }
        else:
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
                ],
                "provider_info": provider_info
            }
    except Exception as e:
        logger.error(f"Error getting auth config: {e}")
        return {
            "auth_type": "unknown",
            "description": f"Error getting provider config: {e}",
            "error": str(e)
        }

@app.post("/internal/tokens", response_model=GenerateTokenResponse)
async def generate_user_token(
    request: GenerateTokenRequest
):
    """
    Generate a JWT token for a user with specified scopes.
    
    This is an internal API endpoint meant to be called only by the registry service.
    The generated token will have the same or fewer privileges than the user currently has.
    
    Args:
        request: Token generation request containing user context and requested scopes
        internal_api_key: Internal API key for authentication
        
    Returns:
        Generated JWT token with expiration info
        
    Raises:
        HTTPException: If request is invalid or user doesn't have required permissions
    """
    try:
        # Note: No internal API key validation needed since registry already validates user session
        
        # Extract user context
        user_context = request.user_context
        username = user_context.get('username')
        user_scopes = user_context.get('scopes', [])
        
        if not username:
            raise HTTPException(
                status_code=400,
                detail="Username is required in user context",
                headers={"Connection": "close"}
            )
        
        # Check rate limiting
        if not check_rate_limit(username):
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {MAX_TOKENS_PER_USER_PER_HOUR} tokens per hour.",
                headers={"Connection": "close"}
            )
        
        # Validate expiration time
        expires_in_hours = request.expires_in_hours
        if expires_in_hours <= 0 or expires_in_hours > MAX_TOKEN_LIFETIME_HOURS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid expiration time. Must be between 1 and {MAX_TOKEN_LIFETIME_HOURS} hours.",
                headers={"Connection": "close"}
            )
        
        # Use user's current scopes if no specific scopes requested
        requested_scopes = request.requested_scopes if request.requested_scopes else user_scopes
        
        # Validate that requested scopes are subset of user's current scopes
        if not validate_scope_subset(user_scopes, requested_scopes):
            invalid_scopes = set(requested_scopes) - set(user_scopes)
            raise HTTPException(
                status_code=403,
                detail=f"Requested scopes exceed user permissions. Invalid scopes: {list(invalid_scopes)}",
                headers={"Connection": "close"}
            )
        
        # Generate JWT access token
        current_time = int(time.time())
        expires_at = current_time + (expires_in_hours * 3600)

        access_payload = {
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "sub": username,
            "scope": " ".join(requested_scopes),
            "exp": expires_at,
            "iat": current_time,
            "jti": str(uuid.uuid4()),  # Unique token ID
            "token_use": "access",
            "client_id": "user-generated",
            "token_type": "user_generated"
        }

        # Add description if provided
        if request.description:
            access_payload["description"] = request.description

        # Sign the access token using HS256 with shared SECRET_KEY
        access_token = jwt.encode(access_payload, SECRET_KEY, algorithm='HS256')

        # No refresh tokens - users should configure longer token lifetimes in Keycloak if needed
        refresh_token = None
        refresh_expires_in_seconds = 0

        logger.info(f"Generated access token for user '{hash_username(username)}' with scopes: {requested_scopes}, expires in {expires_in_hours} hours (no refresh token - configure longer token lifetime in Keycloak if needed)")

        return GenerateTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in_hours * 3600,
            refresh_expires_in=refresh_expires_in_seconds,
            scope=" ".join(requested_scopes),
            issued_at=current_time,
            description=request.description
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error generating token: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error generating token",
            headers={"Connection": "close"}
        )

@app.post("/internal/reload-scopes")
async def reload_scopes(
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    Reload the scopes.yml configuration file.
    Requires admin authentication via Basic Auth with ADMIN_USER/ADMIN_PASSWORD.
    """
    import base64

    # Check for HTTP Basic Authentication
    if not authorization or not authorization.startswith("Basic "):
        logger.warning("No Basic Auth header found for reload-scopes request")
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"}
        )

    try:
        # Decode Basic Auth credentials
        encoded_credentials = authorization.split(" ")[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
        username, password = decoded_credentials.split(":", 1)
    except (IndexError, ValueError, Exception) as e:
        logger.warning(f"Failed to decode Basic Auth credentials: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication format",
            headers={"WWW-Authenticate": "Basic"}
        )

    # Verify admin credentials from environment
    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not admin_password:
        logger.error("ADMIN_PASSWORD environment variable not set")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error"
        )

    if username != admin_user or password != admin_password:
        logger.warning(f"Failed admin authentication attempt for reload-scopes from {username}")
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"}
        )

    # Reload the scopes configuration
    global SCOPES_CONFIG
    try:
        SCOPES_CONFIG = load_scopes_config()
        logger.info(f"Successfully reloaded scopes configuration by admin '{username}'")

        return JSONResponse(
            status_code=200,
            content={
                "message": "Scopes configuration reloaded successfully",
                "timestamp": datetime.utcnow().isoformat(),
                "group_mappings_count": len(SCOPES_CONFIG.get('group_mappings', {}))
            }
        )
    except Exception as e:
        logger.error(f"Failed to reload scopes configuration: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload scopes: {str(e)}"
        )

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

# Load OAuth2 providers configuration
def load_oauth2_config():
    """Load the OAuth2 providers configuration from oauth2_providers.yml"""
    try:
        oauth2_file = Path(__file__).parent / "oauth2_providers.yml"
        with open(oauth2_file, 'r') as f:
            config = yaml.safe_load(f)
            
        # Substitute environment variables in configuration
        processed_config = substitute_env_vars(config)
        return processed_config
    except Exception as e:
        logger.error(f"Failed to load OAuth2 configuration: {e}")
        return {"providers": {}, "session": {}, "registry": {}}

def auto_derive_cognito_domain(user_pool_id: str) -> str:
    """
    Auto-derive Cognito domain from User Pool ID.
    
    Example: us-east-1_KmP5A3La3 → us-east-1kmp5a3la3
    """
    if not user_pool_id:
        return ""
    
    # Remove underscore and convert to lowercase
    domain = user_pool_id.replace('_', '').lower()
    logger.info(f"Auto-derived Cognito domain '{domain}' from user pool ID '{user_pool_id}'")
    return domain

def substitute_env_vars(config):
    """Recursively substitute environment variables in configuration"""
    if isinstance(config, dict):
        return {k: substitute_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [substitute_env_vars(item) for item in config]
    elif isinstance(config, str) and "${" in config:
        try:
            # Handle special case for auto-derived Cognito domain
            if "COGNITO_DOMAIN:-auto" in config:
                # Check if COGNITO_DOMAIN is set, if not auto-derive from user pool ID
                cognito_domain = os.environ.get('COGNITO_DOMAIN')
                if not cognito_domain:
                    user_pool_id = os.environ.get('COGNITO_USER_POOL_ID', '')
                    cognito_domain = auto_derive_cognito_domain(user_pool_id)
                
                # Replace the template with the derived domain
                config = config.replace('${COGNITO_DOMAIN:-auto}', cognito_domain)
            
            template = Template(config)
            return template.substitute(os.environ)
        except KeyError as e:
            logger.warning(f"Environment variable not found for template {config}: {e}")
            return config
    else:
        return config

# Global OAuth2 configuration
OAUTH2_CONFIG = load_oauth2_config()

# Initialize SECRET_KEY and signer for session management
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    # Generate a secure random key (32 bytes = 256 bits of entropy)
    SECRET_KEY = secrets.token_hex(32)
    logger.warning("No SECRET_KEY environment variable found. Using a randomly generated key. "
                   "While this is more secure than a hardcoded default, it will change on restart. "
                   "Set a permanent SECRET_KEY environment variable for production.")

signer = URLSafeTimedSerializer(SECRET_KEY)

def get_enabled_providers():
    """Get list of enabled OAuth2 providers, filtered by AUTH_PROVIDER env var if set"""
    enabled = []

    # Check if AUTH_PROVIDER env var is set to filter to only one provider
    auth_provider_env = os.getenv("AUTH_PROVIDER")

    # First, collect all enabled providers from YAML
    yaml_enabled_providers = []
    for provider_name, config in OAUTH2_CONFIG.get("providers", {}).items():
        if config.get("enabled", False):
            yaml_enabled_providers.append(provider_name)

    if auth_provider_env:
        logger.info(f"AUTH_PROVIDER is set to '{auth_provider_env}', filtering providers accordingly")

        # Check if the specified provider exists in the config
        if auth_provider_env not in OAUTH2_CONFIG.get("providers", {}):
            logger.error(f"AUTH_PROVIDER '{auth_provider_env}' not found in oauth2_providers.yml configuration")
            return []

        # Check if the specified provider is enabled in YAML
        provider_config = OAUTH2_CONFIG["providers"][auth_provider_env]
        if not provider_config.get("enabled", False):
            logger.warning(f"AUTH_PROVIDER '{auth_provider_env}' is set but this provider is disabled in oauth2_providers.yml")
            logger.warning(f"To fix this, either set AUTH_PROVIDER to one of the enabled providers: {yaml_enabled_providers} or enable '{auth_provider_env}' in oauth2_providers.yml")
            return []

        # Warn about providers being filtered out
        filtered_providers = [p for p in yaml_enabled_providers if p != auth_provider_env]
        if filtered_providers:
            logger.warning(f"AUTH_PROVIDER override: Filtering out enabled providers {filtered_providers} - only showing '{auth_provider_env}'")
            logger.warning(f"To show all enabled providers, remove the AUTH_PROVIDER environment variable")
    else:
        logger.info("AUTH_PROVIDER not set, returning all enabled providers from config")

    for provider_name, config in OAUTH2_CONFIG.get("providers", {}).items():
        if config.get("enabled", False):
            # If AUTH_PROVIDER is set, only include that specific provider
            if auth_provider_env and provider_name != auth_provider_env:
                logger.debug(f"Skipping provider '{provider_name}' due to AUTH_PROVIDER filter")
                continue

            enabled.append({
                "name": provider_name,
                "display_name": config.get("display_name", provider_name.title())
            })
            logger.debug(f"Enabled provider: {provider_name}")

    logger.info(f"Returning {len(enabled)} enabled providers: {[p['name'] for p in enabled]}")
    return enabled

@app.get("/oauth2/providers")
async def get_oauth2_providers():
    """Get list of enabled OAuth2 providers for the login page"""
    try:
        # Debug: log environment variable for troubleshooting
        auth_provider_env = os.getenv("AUTH_PROVIDER")
        logger.info(f"Debug: AUTH_PROVIDER environment variable = '{auth_provider_env}'")

        providers = get_enabled_providers()
        return {"providers": providers}
    except Exception as e:
        logger.error(f"Error getting OAuth2 providers: {e}")
        return {"providers": [], "error": str(e)}

@app.get("/oauth2/login/{provider}")
async def oauth2_login(provider: str, request: Request, redirect_uri: str = None):
    """Initiate OAuth2 login flow"""
    try:
        if provider not in OAUTH2_CONFIG.get("providers", {}):
            raise HTTPException(status_code=404, detail=f"Provider {provider} not found")
        
        provider_config = OAUTH2_CONFIG["providers"][provider]
        if not provider_config.get("enabled", False):
            raise HTTPException(status_code=400, detail=f"Provider {provider} is disabled")
        
        # Generate state parameter for security
        state = secrets.token_urlsafe(32)
        
        # Store state and redirect URI in session for callback validation
        session_data = {
            "state": state,
            "provider": provider,
            "redirect_uri": redirect_uri or OAUTH2_CONFIG.get("registry", {}).get("success_redirect", "/")
        }
        
        # Create temporary session for OAuth2 flow
        temp_session = signer.dumps(session_data)
        
        # Use configured external URL or build dynamically
        auth_server_external_url = os.environ.get('AUTH_SERVER_EXTERNAL_URL')
        if auth_server_external_url:
            # Use configured external URL (recommended for production)
            auth_server_url = auth_server_external_url.rstrip('/')
            logger.info(f"Using configured AUTH_SERVER_EXTERNAL_URL: {auth_server_url}")
        else:
            # Fall back to dynamic construction (for development)
            host = request.headers.get("host", "localhost:8888")
            scheme = "https" if request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https" else "http"
            
            # Special case for localhost to include port
            if "localhost" in host and ":" not in host:
                auth_server_url = f"{scheme}://localhost:8888"
            else:
                auth_server_url = f"{scheme}://{host}"
            
            logger.warning(f"AUTH_SERVER_EXTERNAL_URL not set, using dynamic URL: {auth_server_url}")
        
        callback_uri = f"{auth_server_url}/oauth2/callback/{provider}"
        logger.info(f"OAuth2 callback URI: {callback_uri}")
        
        auth_params = {
            "client_id": provider_config["client_id"],
            "response_type": provider_config["response_type"],
            "scope": " ".join(provider_config["scopes"]),
            "state": state,
            "redirect_uri": callback_uri
        }
        
        auth_url = f"{provider_config['auth_url']}?{urllib.parse.urlencode(auth_params)}"
        
        # Create response with temporary session cookie
        response = RedirectResponse(url=auth_url, status_code=302)
        response.set_cookie(
            key="oauth2_temp_session",
            value=temp_session,
            max_age=600,  # 10 minutes for OAuth2 flow
            httponly=True,
            samesite="lax"
        )
        
        logger.info(f"Initiated OAuth2 login for provider {provider}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating OAuth2 login for {provider}: {e}")
        error_url = OAUTH2_CONFIG.get("registry", {}).get("error_redirect", "/login")
        return RedirectResponse(url=f"{error_url}?error=oauth2_init_failed", status_code=302)

@app.get("/oauth2/callback/{provider}")
async def oauth2_callback(
    provider: str,
    request: Request,
    code: str = None, 
    state: str = None, 
    error: str = None,
    oauth2_temp_session: str = Cookie(None)
):
    """Handle OAuth2 callback and create user session"""
    try:
        if error:
            logger.warning(f"OAuth2 error from {provider}: {error}")
            error_url = OAUTH2_CONFIG.get("registry", {}).get("error_redirect", "/login")
            return RedirectResponse(url=f"{error_url}?error=oauth2_error&details={error}", status_code=302)
        
        if not code or not state or not oauth2_temp_session:
            raise HTTPException(status_code=400, detail="Missing required OAuth2 parameters")
        
        # Validate temporary session
        try:
            temp_session_data = signer.loads(oauth2_temp_session, max_age=600)
        except (SignatureExpired, BadSignature):
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth2 session")
        
        # Validate state parameter
        if state != temp_session_data.get("state"):
            raise HTTPException(status_code=400, detail="Invalid state parameter")
        
        # Validate provider
        if provider != temp_session_data.get("provider"):
            raise HTTPException(status_code=400, detail="Provider mismatch")
        
        provider_config = OAUTH2_CONFIG["providers"][provider]
        
        # Exchange authorization code for access token
        # Use configured external URL or build dynamically
        auth_server_external_url = os.environ.get('AUTH_SERVER_EXTERNAL_URL')
        if auth_server_external_url:
            # Use configured external URL (recommended for production)
            auth_server_url = auth_server_external_url.rstrip('/')
            logger.info(f"Using configured AUTH_SERVER_EXTERNAL_URL for token exchange: {auth_server_url}")
        else:
            # Fall back to dynamic construction (for development)
            host = request.headers.get("host", "localhost:8888")
            scheme = "https" if request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https" else "http"
            
            # Special case for localhost to include port
            if "localhost" in host and ":" not in host:
                auth_server_url = f"{scheme}://localhost:8888"
            else:
                auth_server_url = f"{scheme}://{host}"
            
            logger.warning(f"AUTH_SERVER_EXTERNAL_URL not set, using dynamic URL for token exchange: {auth_server_url}")
            
        token_data = await exchange_code_for_token(provider, code, provider_config, auth_server_url)
        logger.info(f"Token data keys: {list(token_data.keys())}")
        
        # For Cognito and Keycloak, try to extract user info from JWT tokens
        if provider in ["cognito", "keycloak"]:
            try:
                if provider == "cognito":
                    # Extract Cognito configuration from environment
                    user_pool_id = os.environ.get('COGNITO_USER_POOL_ID')
                    client_id = provider_config["client_id"]
                    region = os.environ.get('AWS_REGION', 'us-east-1')

                    if user_pool_id and client_id:
                        # Use our existing token validation to get groups from JWT
                        validator = SimplifiedCognitoValidator(region)
                        token_validation = validator.validate_token(
                            token_data["access_token"],
                            user_pool_id,
                            client_id,
                            region
                        )

                        logger.info(f"Token validation result: {token_validation}")

                        # Extract user info from token validation
                        mapped_user = {
                            "username": token_validation.get("username"),
                            "email": token_validation.get("username"),  # Cognito username is usually email
                            "name": token_validation.get("username"),
                            "groups": token_validation.get("groups", [])
                        }
                        logger.info(f"User extracted from JWT token: {mapped_user}")
                    else:
                        logger.warning("Missing Cognito configuration for JWT validation, falling back to userInfo")
                        raise ValueError("Missing Cognito config")
                elif provider == "keycloak":
                    # For Keycloak, decode the ID token to get user information
                    if "id_token" in token_data:
                        import jwt
                        # Decode without verification for now (we trust the token since we just got it)
                        id_token_claims = jwt.decode(token_data["id_token"], options={"verify_signature": False})
                        logger.info(f"ID token claims: {id_token_claims}")

                        # Extract user info from ID token claims
                        mapped_user = {
                            "username": id_token_claims.get("preferred_username") or id_token_claims.get("sub"),
                            "email": id_token_claims.get("email"),
                            "name": id_token_claims.get("name") or id_token_claims.get("given_name"),
                            "groups": id_token_claims.get("groups", [])
                        }
                        logger.info(f"User extracted from Keycloak ID token: {mapped_user}")
                    else:
                        logger.warning("No ID token found in Keycloak response, falling back to userInfo")
                        raise ValueError("Missing ID token")
                    
            except Exception as e:
                logger.warning(f"JWT token validation failed: {e}, falling back to userInfo endpoint")
                # Fallback to userInfo endpoint
                user_info = await get_user_info(token_data["access_token"], provider_config)
                logger.info(f"Raw user info from {provider}: {user_info}")
                mapped_user = map_user_info(user_info, provider_config)
                logger.info(f"Mapped user info from userInfo: {mapped_user}")
        elif provider == "entra":
            # For Entra ID, prioritize ID token claims over userinfo endpoint
            try:
                if "id_token" in token_data:
                    import jwt
                    # Decode without verification (we trust the token since we just got it from Microsoft)
                    id_token_claims = jwt.decode(token_data["id_token"], options={"verify_signature": False})
                    logger.info(f"Entra ID token claims: {id_token_claims}")

                    # Extract user info from ID token claims
                    # Entra ID can return groups as either 'groups' or 'roles' depending on configuration
                    groups = id_token_claims.get("groups", [])
                    if not groups:
                        groups = id_token_claims.get("roles", [])

                    mapped_user = {
                        "username": id_token_claims.get("preferred_username") or id_token_claims.get("email") or id_token_claims.get("upn") or id_token_claims.get("sub"),
                        "email": id_token_claims.get("email") or id_token_claims.get("preferred_username"),
                        "name": id_token_claims.get("name") or id_token_claims.get("given_name"),
                        "groups": groups
                    }
                    logger.info(f"User extracted from Entra ID token: {mapped_user}")
                else:
                    logger.warning("No ID token found in Entra response, falling back to userInfo")
                    raise ValueError("Missing ID token")

            except Exception as e:
                logger.warning(f"Entra ID token parsing failed: {e}, falling back to userInfo endpoint")
                # Fallback to userInfo endpoint
                user_info = await get_user_info(token_data["access_token"], provider_config)
                logger.info(f"Raw user info from {provider}: {user_info}")
                mapped_user = map_user_info(user_info, provider_config)
                logger.info(f"Mapped user info from userInfo: {mapped_user}")
        else:
            # For other providers, use userInfo endpoint
            user_info = await get_user_info(token_data["access_token"], provider_config)
            logger.info(f"Raw user info from {provider}: {user_info}")
            mapped_user = map_user_info(user_info, provider_config)
            logger.info(f"Mapped user info: {mapped_user}")
        
        # Create session cookie compatible with registry
        session_data = {
            "username": mapped_user["username"],
            "email": mapped_user.get("email"),
            "name": mapped_user.get("name"),
            "groups": mapped_user.get("groups", []),
            "provider": provider,
            "auth_method": "oauth2"
        }
        
        registry_session = signer.dumps(session_data)
        
        # Redirect to registry with session cookie
        redirect_url = temp_session_data.get("redirect_uri", OAUTH2_CONFIG.get("registry", {}).get("success_redirect", "/"))
        response = RedirectResponse(url=redirect_url, status_code=302)
        
        # Set registry-compatible session cookie
        response.set_cookie(
            key="mcp_gateway_session",  # Same as registry SESSION_COOKIE_NAME
            value=registry_session,
            max_age=OAUTH2_CONFIG.get("session", {}).get("max_age_seconds", 28800),
            httponly=OAUTH2_CONFIG.get("session", {}).get("httponly", True),
            samesite=OAUTH2_CONFIG.get("session", {}).get("samesite", "lax"),
            secure=OAUTH2_CONFIG.get("session", {}).get("secure", False)
        )
        
        # Clear temporary OAuth2 session
        response.delete_cookie("oauth2_temp_session")
        
        logger.info(f"Successfully authenticated user {hash_username(mapped_user['username'])} via {provider}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in OAuth2 callback for {provider}: {e}")
        error_url = OAUTH2_CONFIG.get("registry", {}).get("error_redirect", "/login")
        return RedirectResponse(url=f"{error_url}?error=oauth2_callback_failed", status_code=302)
    
async def exchange_code_for_token(provider: str, code: str, provider_config: dict, auth_server_url: str = None) -> dict:
    """Exchange authorization code for access token"""
    if auth_server_url is None:
        auth_server_url = os.environ.get('AUTH_SERVER_URL', 'http://localhost:8888')
        
    async with httpx.AsyncClient() as client:
        token_data = {
            "grant_type": provider_config["grant_type"],
            "client_id": provider_config["client_id"],
            "client_secret": provider_config["client_secret"],
            "code": code,
            "redirect_uri": f"{auth_server_url}/oauth2/callback/{provider}"
        }
        
        headers = {"Accept": "application/json"}
        if provider == "github":
            headers["Accept"] = "application/json"
        
        response = await client.post(
            provider_config["token_url"],
            data=token_data,
            headers=headers
        )
        response.raise_for_status()
        return response.json()

async def get_user_info(access_token: str, provider_config: dict) -> dict:
    """Get user information from OAuth2 provider"""
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = await client.get(
            provider_config["user_info_url"],
            headers=headers
        )
        response.raise_for_status()
        return response.json()

def map_user_info(user_info: dict, provider_config: dict) -> dict:
    """Map provider-specific user info to our standard format"""
    mapped = {
        "username": user_info.get(provider_config["username_claim"]),
        "email": user_info.get(provider_config["email_claim"]),
        "name": user_info.get(provider_config["name_claim"]),
        "groups": []
    }
    
    # Handle groups if provider supports them
    groups_claim = provider_config.get("groups_claim")
    logger.info(f"Looking for groups using claim: {groups_claim}")
    logger.info(f"Available claims in user_info: {list(user_info.keys())}")
    
    if groups_claim and groups_claim in user_info:
        groups = user_info[groups_claim]
        if isinstance(groups, list):
            mapped["groups"] = groups
        elif isinstance(groups, str):
            mapped["groups"] = [groups]
        logger.info(f"Found groups via {groups_claim}: {mapped['groups']}")
    else:
        # Try alternative group claims for Cognito
        for possible_group_claim in ["cognito:groups", "groups", "custom:groups"]:
            if possible_group_claim in user_info:
                groups = user_info[possible_group_claim]
                if isinstance(groups, list):
                    mapped["groups"] = groups
                elif isinstance(groups, str):
                    mapped["groups"] = [groups]
                logger.info(f"Found groups via alternative claim {possible_group_claim}: {mapped['groups']}")
                break
        
        if not mapped["groups"]:
            logger.warning(f"No groups found in user_info. Available fields: {list(user_info.keys())}")
    
    return mapped

@app.get("/oauth2/logout/{provider}")
async def oauth2_logout(provider: str, request: Request, redirect_uri: str = None):
    """Initiate OAuth2 logout flow to clear provider session"""
    try:
        if provider not in OAUTH2_CONFIG.get("providers", {}):
            raise HTTPException(status_code=404, detail=f"Provider {provider} not found")
        
        provider_config = OAUTH2_CONFIG["providers"][provider]
        logout_url = provider_config.get("logout_url")
        
        if not logout_url:
            # If provider doesn't support logout URL, just redirect
            redirect_url = redirect_uri or OAUTH2_CONFIG.get("registry", {}).get("success_redirect", "/login")
            return RedirectResponse(url=redirect_url, status_code=302)
        
        # For Cognito, we need to construct the full redirect URI
        full_redirect_uri = redirect_uri or "/logout"
        if not full_redirect_uri.startswith("http"):
            # Make it a full URL - extract registry URL from request's referer or use environment
            registry_base = os.environ.get('REGISTRY_URL')
            if not registry_base:
                # Try to derive from the request
                referer = request.headers.get("referer", "")
                if referer:
                    from urllib.parse import urlparse
                    parsed = urlparse(referer)
                    registry_base = f"{parsed.scheme}://{parsed.netloc}"
                else:
                    registry_base = "http://localhost"
            
            full_redirect_uri = f"{registry_base.rstrip('/')}{full_redirect_uri}"
        
        # Build logout URL with correct parameters for Cognito
        logout_params = {
            "client_id": provider_config["client_id"],
            "logout_uri": full_redirect_uri
        }
        
        logout_redirect_url = f"{logout_url}?{urllib.parse.urlencode(logout_params)}"
        
        logger.info(f"Redirecting to {provider} logout: {logout_redirect_url}")
        return RedirectResponse(url=logout_redirect_url, status_code=302)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating logout for {provider}: {e}")
        # Fallback to local redirect
        redirect_url = redirect_uri or OAUTH2_CONFIG.get("registry", {}).get("success_redirect", "/login")
        return RedirectResponse(url=redirect_url, status_code=302)