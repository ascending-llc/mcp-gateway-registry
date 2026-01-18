"""
OAuth 2.0 Device Flow routes for auth server.

Implements RFC 8628 (OAuth 2.0 Device Authorization Grant).
"""

import os
import time
import secrets
import random
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Form, Request
from fastapi.responses import HTMLResponse

from ..models.device_flow import (
    DeviceCodeResponse,
    DeviceTokenResponse
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Device flow storage (in-memory, will migrate to Redis/MongoDB later)
device_codes_storage = {}  # device_code -> {user_code, status, token, ...}
user_codes_storage = {}    # user_code -> device_code (for quick lookup)

# Device flow configuration
DEVICE_CODE_EXPIRY_SECONDS = 600  # 10 minutes
DEVICE_CODE_POLL_INTERVAL = 5     # Poll every 5 seconds


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
    from ..server import SECRET_KEY, JWT_ISSUER, JWT_AUDIENCE
    import jwt
    
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
    
    access_token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256")
    
    device_data["status"] = "approved"
    device_data["token"] = access_token
    device_data["approved_at"] = current_time
    
    logger.info(f"Device approved for user_code: {user_code}")
    
    return {"status": "approved", "message": "Device verified successfully"}


@router.post("/oauth2/token", response_model=DeviceTokenResponse)
async def device_token(
    grant_type: str = Form(...),
    device_code: str = Form(...),
    client_id: str = Form(...)
):
    """
    OAuth 2.0 Token Endpoint for Device Flow (RFC 8628).
    
    Client polls this endpoint to check if the user has approved the device.
    """
    cleanup_expired_device_codes()
    
    if grant_type != "urn:ietf:params:oauth:grant-type:device_code":
        raise HTTPException(
            status_code=400,
            detail="unsupported_grant_type"
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
