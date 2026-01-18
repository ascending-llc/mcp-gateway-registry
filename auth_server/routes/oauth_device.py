"""
OAuth 2.0 Device Flow and Dynamic Client Registration.

Implements:
- RFC 8628 (OAuth 2.0 Device Authorization Grant)
- RFC 7591 (OAuth 2.0 Dynamic Client Registration)
"""

import os
import time
import secrets
import random
import logging
import jwt
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..models.device_flow import (
    DeviceCodeResponse,
    DeviceTokenResponse
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Device flow storage (in-memory, will migrate to Redis/MongoDB later)
device_codes_storage = {}  # device_code -> {user_code, status, token, ...}
user_codes_storage = {}    # user_code -> device_code (for quick lookup)

# Client registration storage (in-memory, consider using Redis or DB in production)
registered_clients: Dict[str, Dict[str, Any]] = {}

# Authorization code storage for OAuth 2.0 Authorization Code Flow
authorization_codes_storage: Dict[str, Dict[str, Any]] = {}  # code -> {token_data, user_info, client_id, expires_at, used, code_challenge}

# Device flow configuration
DEVICE_CODE_EXPIRY_SECONDS = 600  # 10 minutes
DEVICE_CODE_POLL_INTERVAL = 5     # Poll every 5 seconds


# ============================================================================
# OAuth 2.0 Dynamic Client Registration (RFC 7591)
# ============================================================================

class ClientRegistrationRequest(BaseModel):
    """OAuth 2.0 Dynamic Client Registration Request (RFC 7591)."""
    
    client_name: Optional[str] = Field(None, description="Human-readable name of the client")
    client_uri: Optional[str] = Field(None, description="URL of the client's home page")
    redirect_uris: Optional[List[str]] = Field(None, description="Array of redirection URIs")
    grant_types: Optional[List[str]] = Field(
        default=["authorization_code", "urn:ietf:params:oauth:grant-type:device_code"],
        description="Array of OAuth 2.0 grant types"
    )
    response_types: Optional[List[str]] = Field(
        default=["code"],
        description="Array of OAuth 2.0 response types"
    )
    scope: Optional[str] = Field(None, description="Space-separated list of scopes")
    contacts: Optional[List[str]] = Field(None, description="Array of contact email addresses")
    token_endpoint_auth_method: Optional[str] = Field(
        default="client_secret_post",
        description="Requested authentication method for the token endpoint"
    )


class ClientRegistrationResponse(BaseModel):
    """OAuth 2.0 Dynamic Client Registration Response (RFC 7591)."""
    
    client_id: str = Field(..., description="OAuth 2.0 client identifier")
    client_secret: Optional[str] = Field(None, description="OAuth 2.0 client secret")
    client_id_issued_at: int = Field(..., description="Time at which the client identifier was issued")
    client_secret_expires_at: int = Field(
        default=0,
        description="Time at which the client secret will expire (0 = never expires)"
    )
    client_name: Optional[str] = None
    client_uri: Optional[str] = None
    redirect_uris: Optional[List[str]] = None
    grant_types: List[str] = Field(default_factory=list)
    response_types: List[str] = Field(default_factory=list)
    scope: Optional[str] = None
    token_endpoint_auth_method: str = "client_secret_post"


@router.post("/oauth2/register", response_model=ClientRegistrationResponse)
async def register_client(
    registration: ClientRegistrationRequest,
    request: Request
) -> ClientRegistrationResponse:
    """
    OAuth 2.0 Dynamic Client Registration endpoint (RFC 7591).
    
    Allows MCP clients to dynamically register and obtain client credentials.
    This is required for Claude Desktop and other MCP clients that don't have
    pre-configured client credentials.
    """
    try:
        # Generate client credentials
        client_id = f"mcp-client-{secrets.token_urlsafe(16)}"
        client_secret = secrets.token_urlsafe(32)
        issued_at = int(time.time())
        
        # Build client metadata
        client_metadata = {
            "client_id": client_id,
            "client_secret": client_secret,
            "client_id_issued_at": issued_at,
            "client_secret_expires_at": 0,  # Never expires
            "client_name": registration.client_name or "MCP Client",
            "client_uri": registration.client_uri,
            "redirect_uris": registration.redirect_uris or [],
            "grant_types": registration.grant_types or [
                "authorization_code",
                "urn:ietf:params:oauth:grant-type:device_code"
            ],
            "response_types": registration.response_types or ["code"],
            "scope": registration.scope or "mcp-servers-unrestricted/read mcp-servers-unrestricted/execute",
            "token_endpoint_auth_method": registration.token_endpoint_auth_method or "client_secret_post",
            "contacts": registration.contacts or [],
            "registered_at": issued_at,
            "ip_address": request.client.host if request.client else "unknown"
        }
        
        # Store client in memory
        registered_clients[client_id] = client_metadata
        
        logger.info(
            f"Registered new OAuth client: "
            f"client_id={client_id}, "
            f"name={client_metadata['client_name']}, "
            f"grant_types={client_metadata['grant_types']}"
        )
        
        # Return registration response
        return ClientRegistrationResponse(
            client_id=client_id,
            client_secret=client_secret,
            client_id_issued_at=issued_at,
            client_secret_expires_at=0,
            client_name=client_metadata["client_name"],
            client_uri=client_metadata["client_uri"],
            redirect_uris=client_metadata["redirect_uris"],
            grant_types=client_metadata["grant_types"],
            response_types=client_metadata["response_types"],
            scope=client_metadata["scope"],
            token_endpoint_auth_method=client_metadata["token_endpoint_auth_method"]
        )
        
    except Exception as e:
        logger.error(f"Client registration failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Client registration failed"
        )


def get_client(client_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve registered client by client_id.
    
    Args:
        client_id: OAuth 2.0 client identifier
        
    Returns:
        Client metadata dictionary or None if not found
    """
    return registered_clients.get(client_id)


def validate_client_credentials(client_id: str, client_secret: str) -> bool:
    """
    Validate client credentials.
    
    Args:
        client_id: OAuth 2.0 client identifier
        client_secret: OAuth 2.0 client secret
        
    Returns:
        True if credentials are valid, False otherwise
    """
    client = registered_clients.get(client_id)
    if not client:
        return False
    
    return client.get("client_secret") == client_secret


def list_registered_clients() -> List[Dict[str, Any]]:
    """
    List all registered clients (for admin purposes).
    
    Returns:
        List of client metadata (without secrets)
    """
    return [
        {
            "client_id": client_id,
            "client_name": metadata.get("client_name"),
            "grant_types": metadata.get("grant_types"),
            "registered_at": metadata.get("registered_at"),
            "ip_address": metadata.get("ip_address")
        }
        for client_id, metadata in registered_clients.items()
    ]


# ============================================================================
# OAuth 2.0 Device Flow (RFC 8628)
# ============================================================================

def generate_user_code() -> str:
    """
    Generate readable user code for device flow (e.g., WDJB-MJHT).
    Excludes confusing characters: O, 0, I, 1
    
    Returns:
        8-character code with hyphen separator (XXXX-XXXX)
    """
    import string
    chars = string.ascii_uppercase + string.digits
    # Remove confusing characters
    chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
    code = ''.join(random.choices(chars, k=8))
    return f"{code[:4]}-{code[4:]}"


def cleanup_expired_device_codes():
    """
    Remove expired device codes from in-memory storage.
    Called periodically during device code operations.
    """
    current_time = int(time.time())
    expired_codes = [
        code for code, data in device_codes_storage.items()
        if current_time > data["expires_at"]
    ]
    
    for code in expired_codes:
        user_code = device_codes_storage[code]["user_code"]
        del device_codes_storage[code]
        if user_code in user_codes_storage:
            del user_codes_storage[user_code]
    
    if expired_codes:
        logger.info(f"Cleaned up {len(expired_codes)} expired device codes")


def cleanup_expired_authorization_codes():
    """
    Remove expired authorization codes from in-memory storage.
    Called periodically during authorization code operations.
    """
    current_time = int(time.time())
    expired_codes = [
        code for code, data in authorization_codes_storage.items()
        if current_time > data["expires_at"]
    ]
    
    for code in expired_codes:
        del authorization_codes_storage[code]
    
    if expired_codes:
        logger.info(f"Cleaned up {len(expired_codes)} expired authorization codes")


@router.post("/oauth2/device/code", response_model=DeviceCodeResponse)
async def device_authorization(
    req: Request,
    client_id: str = Form(...),
    scope: Optional[str] = Form(None)
):
    """
    OAuth 2.0 Device Authorization Endpoint (RFC 8628).
    
    Initiates the device flow by generating a device code and user code.
    Accepts application/x-www-form-urlencoded as per RFC 8628.
    """
    cleanup_expired_device_codes()
    
    device_code = secrets.token_urlsafe(32)
    user_code = generate_user_code()
    
    auth_server_url = os.environ.get('AUTH_SERVER_EXTERNAL_URL')
    if not auth_server_url:
        host = req.headers.get("host", "localhost:8888")
        scheme = "https" if req.headers.get("x-forwarded-proto") == "https" or req.url.scheme == "https" else "http"
        auth_server_url = f"{scheme}://{host}"
    
    verification_uri = f"{auth_server_url}/oauth2/device/verify"
    verification_uri_complete = f"{verification_uri}?user_code={user_code}"
    
    current_time = int(time.time())
    expires_at = current_time + DEVICE_CODE_EXPIRY_SECONDS
    
    device_codes_storage[device_code] = {
        "user_code": user_code,
        "client_id": client_id,
        "scope": scope or "",
        "status": "pending",
        "created_at": current_time,
        "expires_at": expires_at,
        "token": None
    }
    
    user_codes_storage[user_code] = device_code
    
    logger.info(f"Generated device code for client_id: {client_id}, user_code: {user_code}")
    
    return DeviceCodeResponse(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verification_uri,
        verification_uri_complete=verification_uri_complete,
        expires_in=DEVICE_CODE_EXPIRY_SECONDS,
        interval=DEVICE_CODE_POLL_INTERVAL
    )


@router.get("/oauth2/device/verify", response_class=HTMLResponse)
async def device_verification_page(user_code: Optional[str] = None):
    """
    Device verification page where users enter their user code.
    """
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Device Verification</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                max-width: 500px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .card {{
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                font-size: 24px;
                margin-bottom: 10px;
            }}
            .subtitle {{
                color: #666;
                margin-bottom: 30px;
            }}
            input[type="text"] {{
                width: 100%;
                padding: 12px;
                font-size: 18px;
                border: 2px solid #ddd;
                border-radius: 4px;
                box-sizing: border-box;
                text-align: center;
                letter-spacing: 2px;
                text-transform: uppercase;
                font-family: monospace;
            }}
            button {{
                width: 100%;
                padding: 12px;
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                cursor: pointer;
                margin-top: 15px;
            }}
            button:hover {{
                background-color: #0056b3;
            }}
            .error {{
                color: #dc3545;
                margin-top: 10px;
                display: none;
            }}
            .success {{
                color: #28a745;
                margin-top: 10px;
                display: none;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Device Verification</h1>
            <p class="subtitle">Enter the code displayed on your device</p>
            
            <form id="verifyForm">
                <input 
                    type="text" 
                    id="user_code" 
                    name="user_code" 
                    placeholder="XXXX-XXXX" 
                    value="{user_code or ''}"
                    required 
                    maxlength="9"
                    pattern="[A-Z0-9]{{4}}-[A-Z0-9]{{4}}"
                />
                <button type="submit">Verify Device</button>
            </form>
            
            <div class="error" id="error"></div>
            <div class="success" id="success"></div>
        </div>
        
        <script>
            document.getElementById('verifyForm').addEventListener('submit', async (e) => {{
                e.preventDefault();
                
                const userCode = document.getElementById('user_code').value;
                const errorDiv = document.getElementById('error');
                const successDiv = document.getElementById('success');
                
                errorDiv.style.display = 'none';
                successDiv.style.display = 'none';
                
                try {{
                    const response = await fetch('/oauth2/device/approve', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{ user_code: userCode }})
                    }});
                    
                    if (response.ok) {{
                        successDiv.textContent = 'Device verified successfully! You can close this window.';
                        successDiv.style.display = 'block';
                        document.getElementById('user_code').disabled = true;
                        document.querySelector('button').disabled = true;
                    }} else {{
                        const data = await response.json();
                        errorDiv.textContent = data.detail || 'Verification failed';
                        errorDiv.style.display = 'block';
                    }}
                }} catch (error) {{
                    errorDiv.textContent = 'Network error. Please try again.';
                    errorDiv.style.display = 'block';
                }}
            }});
            
            // Auto-format input with dash
            document.getElementById('user_code').addEventListener('input', (e) => {{
                let value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
                if (value.length > 4) {{
                    value = value.slice(0, 4) + '-' + value.slice(4, 8);
                }}
                e.target.value = value;
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.post("/oauth2/device/approve")
async def approve_device(user_code: str = Form(...)):
    """
    Approve a device verification request.
    
    This endpoint is called when a user approves a device via the verification page.
    In a real implementation, this would check user authentication and authorization.
    """
    cleanup_expired_device_codes()
    
    device_code = user_codes_storage.get(user_code)
    
    if not device_code:
        raise HTTPException(status_code=404, detail="Invalid or expired user code")
    
    device_data = device_codes_storage.get(device_code)
    
    if not device_data:
        raise HTTPException(status_code=404, detail="Device code not found")
    
    current_time = int(time.time())
    if current_time > device_data["expires_at"]:
        raise HTTPException(status_code=400, detail="Device code expired")
    
    if device_data["status"] == "approved":
        return {"status": "already_approved", "message": "Device already approved"}
    
    # TODO: In production, validate user session and generate proper token
    # For now, generate a simple token
    from ..server import SECRET_KEY, JWT_ISSUER, JWT_AUDIENCE, JWT_SELF_SIGNED_KID
    
    token_payload = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "sub": "device_user",
        "client_id": device_data["client_id"],
        "scope": device_data["scope"],
        "exp": current_time + 3600,  # 1 hour
        "iat": current_time,
        "token_use": "access"
    }
    
    headers = {
        "kid": JWT_SELF_SIGNED_KID,
        "typ": "JWT",
        "alg": "HS256"
    }
    
    access_token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256", headers=headers)
    
    device_data["status"] = "approved"
    device_data["token"] = access_token
    device_data["approved_at"] = current_time
    
    logger.info(f"Device approved for user_code: {user_code}")
    
    return {"status": "approved", "message": "Device verified successfully"}


@router.post("/oauth2/token", response_model=DeviceTokenResponse)
async def device_token(
    grant_type: str = Form(...),
    device_code: str = Form(None),
    client_id: str = Form(...),
    code: str = Form(None),
    code_verifier: str = Form(None),
    redirect_uri: str = Form(None)
):
    """
    OAuth 2.0 Token Endpoint (RFC 6749, RFC 8628).
    
    Supports:
    - Device Flow (RFC 8628): grant_type=urn:ietf:params:oauth:grant-type:device_code
    - Authorization Code Flow (RFC 6749 + PKCE RFC 7636): grant_type=authorization_code
    
    For Device Flow:
        - device_code: Required
        - client_id: Required
        
    For Authorization Code Flow:
        - code: Required authorization code
        - client_id: Required
        - redirect_uri: Required (must match the one used in /oauth2/login)
        - code_verifier: Required for PKCE validation
    """
    
    # Handle Authorization Code Flow (RFC 6749)
    if grant_type == "authorization_code":
        cleanup_expired_authorization_codes()
        
        if not code or not redirect_uri:
            raise HTTPException(
                status_code=400,
                detail="invalid_request: code and redirect_uri are required"
            )
        
        # Retrieve authorization code data
        auth_code_data = authorization_codes_storage.get(code)
        
        if not auth_code_data:
            raise HTTPException(
                status_code=400,
                detail="invalid_grant: authorization code not found or expired"
            )
        
        # Check if already used
        if auth_code_data.get("used"):
            logger.warning(f"Authorization code reuse attempt by client {client_id}")
            # Delete the code to prevent further attempts
            del authorization_codes_storage[code]
            raise HTTPException(
                status_code=400,
                detail="invalid_grant: authorization code already used"
            )
        
        # Validate client_id
        if auth_code_data["client_id"] != client_id:
            raise HTTPException(
                status_code=400,
                detail="invalid_client: client_id mismatch"
            )
        
        # Validate redirect_uri
        if auth_code_data["redirect_uri"] != redirect_uri:
            raise HTTPException(
                status_code=400,
                detail="invalid_grant: redirect_uri mismatch"
            )
        
        # Check expiration
        current_time = int(time.time())
        if current_time > auth_code_data["expires_at"]:
            del authorization_codes_storage[code]
            raise HTTPException(
                status_code=400,
                detail="invalid_grant: authorization code expired"
            )
        
        # Validate PKCE code_verifier if code_challenge was provided
        code_challenge = auth_code_data.get("code_challenge")
        if code_challenge:
            if not code_verifier:
                raise HTTPException(
                    status_code=400,
                    detail="invalid_request: code_verifier required for PKCE"
                )
            
            # Validate code_verifier against code_challenge
            import hashlib
            import base64
            
            code_challenge_method = auth_code_data.get("code_challenge_method", "S256")
            
            if code_challenge_method == "S256":
                # SHA256 hash of code_verifier
                computed_challenge = base64.urlsafe_b64encode(
                    hashlib.sha256(code_verifier.encode()).digest()
                ).decode().rstrip("=")
            elif code_challenge_method == "plain":
                computed_challenge = code_verifier
            else:
                raise HTTPException(
                    status_code=400,
                    detail="invalid_request: unsupported code_challenge_method"
                )
            
            if computed_challenge != code_challenge:
                logger.warning(f"PKCE validation failed for client {client_id}")
                raise HTTPException(
                    status_code=400,
                    detail="invalid_grant: code_verifier validation failed"
                )
            
            logger.info(f"PKCE validation successful for client {client_id}")
        
        # Mark code as used
        auth_code_data["used"] = True
        
        # Generate access token using stored user info
        user_info = auth_code_data["user_info"]
        from ..server import SECRET_KEY, JWT_ISSUER, JWT_AUDIENCE, JWT_SELF_SIGNED_KID
        
        token_payload = {
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "sub": user_info["username"],
            "client_id": client_id,
            "scope": " ".join(user_info.get("groups", [])),  # Map groups to scopes
            "groups": user_info.get("groups", []),
            "exp": current_time + 3600,  # 1 hour
            "iat": current_time,
            "token_use": "access"
        }
        
        headers = {
            "kid": JWT_SELF_SIGNED_KID,
            "typ": "JWT",
            "alg": "HS256"
        }
        
        access_token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256", headers=headers)
        
        # Clean up used authorization code after successful token generation
        del authorization_codes_storage[code]
        
        logger.info(f"Issued access token via authorization code flow for client {client_id}, user {user_info['username']}")
        
        return DeviceTokenResponse(
            access_token=access_token,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(user_info.get("groups", []))
        )
    
    # Handle Device Flow (RFC 8628)
    elif grant_type == "urn:ietf:params:oauth:grant-type:device_code":
        cleanup_expired_device_codes()
        
        if not device_code:
            raise HTTPException(
                status_code=400,
                detail="invalid_request: device_code is required"
            )
        cleanup_expired_device_codes()
        
        if not device_code:
            raise HTTPException(
                status_code=400,
                detail="invalid_request: device_code is required"
            )
        
        device_data = device_codes_storage.get(device_code)
        
        if not device_data:
            raise HTTPException(
                status_code=400,
                detail="invalid_grant"
            )
        
        if device_data["client_id"] != client_id:
            raise HTTPException(
                status_code=400,
                detail="invalid_client"
            )
        
        current_time = int(time.time())
        if current_time > device_data["expires_at"]:
            raise HTTPException(
                status_code=400,
                detail="expired_token"
            )
        
        if device_data["status"] == "pending":
            raise HTTPException(
                status_code=400,
                detail="authorization_pending"
            )
        
        if device_data["status"] == "denied":
            raise HTTPException(
                status_code=400,
                detail="access_denied"
            )
        
        if device_data["status"] == "approved" and device_data["token"]:
            logger.info(f"Token issued for device_code: {device_code}")
            
            return DeviceTokenResponse(
                access_token=device_data["token"],
                token_type="Bearer",
                expires_in=3600,
                scope=device_data["scope"]
            )
        
        raise HTTPException(
            status_code=500,
            detail="server_error"
        )
    
    # Unsupported grant type
    else:
        raise HTTPException(
            status_code=400,
            detail="unsupported_grant_type"
        )
