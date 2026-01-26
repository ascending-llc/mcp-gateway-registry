import urllib.parse
import logging
from typing import Annotated

from fastapi import APIRouter, Request, Form, HTTPException, status, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx
import base64
import json
import secrets

from ..core.config import settings
from auth_server.core.config import settings as auth_settings
from ..auth.dependencies import create_session_cookie, validate_login_credentials
from packages.models._generated import IUser
from registry.services.user_service import user_service
from itsdangerous import URLSafeTimedSerializer

logger = logging.getLogger(__name__)

router = APIRouter()

# Templates (will be injected via dependency later, but for now keep it simple)
templates = Jinja2Templates(directory=settings.templates_dir)

# JWT / signer configuration
SECRET_KEY = settings.secret_key
signer = URLSafeTimedSerializer(SECRET_KEY)


async def get_oauth2_providers():
    """Fetch available OAuth2 providers from auth server"""
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Fetching OAuth2 providers from {settings.auth_server_url}/oauth2/providers")
            response = await client.get(f"{settings.auth_server_url}/oauth2/providers", timeout=5.0)
            logger.info(f"OAuth2 providers response: status={response.status_code}")
            if response.status_code == 200:
                data = response.json()
                providers = data.get("providers", [])
                logger.info(f"Successfully fetched {len(providers)} OAuth2 providers: {providers}")
                return providers
            else:
                logger.warning(f"Auth server returned non-200 status: {response.status_code}, body: {response.text}")
    except Exception as e:
        logger.warning(f"Failed to fetch OAuth2 providers from auth server: {e}", exc_info=True)
    return []


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, error: str | None = None):
    """Show login form with OAuth2 providers"""
    oauth_providers = await get_oauth2_providers()
    return templates.TemplateResponse(
        "login.html", 
        {
            "request": request, 
            "error": error,
            "oauth_providers": oauth_providers
        }
    )

# OAuth2 login redirect avoid /auth/ route collision with auth server
@router.get("/redirect/{provider}")
async def oauth2_login_redirect(provider: str, request: Request):
    """Redirect to auth server for OAuth2 login"""
    try:
        # Build redirect URL to auth server - use external URL for browser redirects
        registry_client_url = settings.registry_client_url
        auth_external_url = settings.auth_server_external_url
        state_data = {
            "nonce": secrets.token_urlsafe(24),
            "resource": registry_client_url
        }
        client_state = base64.urlsafe_b64encode(
            json.dumps(state_data).encode()
        ).decode().rstrip('=')
        auth_url = f"{auth_external_url}/oauth2/login/{provider}?redirect_uri={registry_client_url}&state={client_state}"
        logger.info(f"request.base_url: {request.base_url}, registry_url: {registry_client_url}, auth_external_url: {auth_external_url}, auth_url: {auth_url}")
        logger.info(f"Redirecting to OAuth2 login for provider {provider}: {auth_url}")
        return RedirectResponse(url=auth_url, status_code=302)
        
    except Exception as e:
        logger.error(f"Error redirecting to OAuth2 login for {provider}: {e}")
        return RedirectResponse(url="/login?error=oauth2_redirect_failed", status_code=302)


@router.get("/redirect")
async def oauth2_callback(request: Request, user_info: str, error: str = None, details: str = None):
    """Handle OAuth2 callback from auth server
    
    This endpoint receives signed user information from the auth server after successful OAuth2 login.
    The user_info parameter contains a cryptographically signed payload that includes:
    - username, email, name
    - idp_id (OID from Entra, sub from Keycloak/Cognito)
    - groups (from IdP)
    - provider and auth_method
    """

    try:
        if error:
            logger.warning(f"OAuth2 callback received error: {error}, details: {details}")
            error_message = "Authentication failed"
            if error == "oauth2_error":
                error_message = f"OAuth2 provider error: {details}"
            elif error == "oauth2_init_failed":
                error_message = "Failed to initiate OAuth2 login"
            elif error == "oauth2_callback_failed":
                error_message = "OAuth2 authentication failed"
            
            return RedirectResponse(
                url=f"/login?error={urllib.parse.quote(error_message)}", 
                status_code=302
            )
    
        try:
            from itsdangerous import SignatureExpired, BadSignature
            # Max age of 60 seconds for the signed data (should be instant redirect)
            userinfo = signer.loads(user_info, max_age=60)
            logger.info(f"OAuth2 callback received signed user info for: {userinfo['username']}")
        except SignatureExpired:
            logger.error("Signed user info has expired (>60 seconds old)")
            return RedirectResponse(
                url="/login?error=oauth2_data_expired", 
                status_code=302
            )
        except BadSignature:
            logger.error("Invalid signature on user info data - possible tampering")
            return RedirectResponse(
                url="/login?error=oauth2_data_invalid", 
                status_code=302
            )
        except Exception as e:
            logger.error(f"Failed to decrypt user info: {e}")
            # Fallback to old base64 decoding for backward compatibility
            try:
                userinfo_json = base64.urlsafe_b64decode(user_info + '=' * (-len(user_info) % 4)).decode()
                userinfo = json.loads(userinfo_json)
                logger.warning("Used legacy base64 decoding for user info (not recommended)")
            except Exception as legacy_error:
                logger.error(f"Failed to decode user info with both methods: {legacy_error}")
                return RedirectResponse(
                    url="/login?error=oauth2_data_decode_failed", 
                    status_code=302
                )
            
        user_obj = await user_service.find_by_source_id(source_id=userinfo.get("idp_id"))
        if not user_obj: 
            logger.warning(f"User {userinfo['username']} not found in registry database")
            return RedirectResponse(
                url="/login?error=User+not+found+in+registry", 
                status_code=302
            )
        
        session_data = {
            **userinfo,
            "user_id": str(user_obj.id),
            "role": user_obj.role
        }
        registry_session = signer.dumps(session_data)
        response = RedirectResponse(url=settings.registry_client_url.rstrip('/'), status_code=302)
        cookie_secure_config = auth_settings.oauth2_config.get("session", {}).get("secure", False)
        x_forwarded_proto = request.headers.get("x-forwarded-proto", "")
        is_https = x_forwarded_proto == "https" or request.url.scheme == "https"
        cookie_secure = cookie_secure_config and is_https   

        cookie_params = {
         "key": "mcp_gateway_session",
         "value": registry_session, 
         "max_age": auth_settings.oauth2_config.get("session", {}).get("max_age_seconds", 28800), 
         "httponly": auth_settings.oauth2_config.get("session", {}).get("httponly", True),
         "samesite": auth_settings.oauth2_config.get("session", {}).get("samesite", "lax"),
         "secure": cookie_secure, 
         "path": "/"
        }

        # Set cookie and redirect back to UI
        response.set_cookie(**cookie_params)
        response.delete_cookie("oauth2_temp_session")
        return response
        
    except Exception as e:
        logger.error(f"Error in OAuth2 callback: {e}")
        return RedirectResponse(url="/login?error=oauth2_callback_error", status_code=302)


@router.post("/login")
async def login_submit(
    request: Request,
    username: Annotated[str, Form()], 
    password: Annotated[str, Form()]
):
    """Handle login form submission - supports both traditional and API calls"""
    logger.info(f"Login attempt for username: {username}")
    
    # Check if this is an API call (React) or traditional form submission
    accept_header = request.headers.get("accept", "")
    is_api_call = "application/json" in accept_header
    
    if validate_login_credentials(username, password):
        session_data = create_session_cookie(username)
        
        if is_api_call:
            # API response for React
            response = JSONResponse(content={"success": True, "message": "Login successful"})
        else:
            # Traditional redirect response
            response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        
        # Security Note: This implementation uses domain cookies for single-tenant deployments
        # where cross-subdomain authentication is required (e.g., auth.domain.com and registry.domain.com).
        # For multi-tenant SaaS deployments with tenant-based subdomains, do NOT use domain cookies
        # as they would allow cross-tenant session sharing. Consider alternative authentication methods
        # such as token-based auth or separate auth domains per tenant.
        cookie_params = {
            "key": settings.session_cookie_name,
            "value": session_data,
            "max_age": settings.session_max_age_seconds,
            "httponly": True,  # Prevents JavaScript access (XSS protection)
            "samesite": "lax",  # CSRF protection
            "secure": settings.session_cookie_secure,  # Only transmit over HTTPS when True
            "path": "/",  # Explicit path for clarity
        }

        # Add domain attribute if configured for cross-subdomain cookie sharing
        if settings.session_cookie_domain:
            cookie_params["domain"] = settings.session_cookie_domain

        response.set_cookie(**cookie_params)
        logger.info(f"User '{username}' logged in successfully.")
        return response
    else:
        logger.info(f"Login failed for user '{username}'.")
        
        if is_api_call:
            # API error response for React
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        else:
            # Traditional redirect with error
            return RedirectResponse(
                url="/login?error=Invalid+username+or+password",
                status_code=status.HTTP_303_SEE_OTHER,
            )





async def logout_handler(
    request: Request,
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None
):
    """Shared logout logic for both GET and POST requests"""
    try:
        # Check if user was logged in via OAuth2
        provider = None
        if session:
            try:
                from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
                serializer = URLSafeTimedSerializer(settings.secret_key)
                session_data = serializer.loads(session, max_age=settings.session_max_age_seconds)
                
                if session_data.get('auth_method') == 'oauth2':
                    provider = session_data.get('provider')
                    logger.info(f"User was authenticated via OAuth2 provider: {provider}")
                    
            except (SignatureExpired, BadSignature, Exception) as e:
                logger.debug(f"Could not decode session for logout: {e}")
        
        # Clear local session cookie
        response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(settings.session_cookie_name)
        
        # If user was logged in via OAuth2, redirect to provider logout
        if provider:
            auth_external_url = settings.auth_server_external_url
            
            # Build redirect URI based on current host
            host = request.headers.get("host", "localhost:7860")
            scheme = "https" if request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https" else "http"
            
            # Handle localhost specially to ensure correct port
            if "localhost" in host and ":" not in host:
                redirect_uri = f"{scheme}://localhost:7860/logout"
            else:
                redirect_uri = f"{scheme}://{host}/logout"
            
            logout_url = f"{auth_external_url}/oauth2/logout/{provider}?redirect_uri={redirect_uri}"
            logger.info(f"Redirecting to {provider} logout: {logout_url}")
            response = RedirectResponse(url=logout_url, status_code=status.HTTP_303_SEE_OTHER)
            response.delete_cookie(settings.session_cookie_name)
        
        logger.info("User logged out.")
        return response
        
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        # Fallback to simple logout
        response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(settings.session_cookie_name)
        return response


@router.get("/logout")
async def logout_get(
    request: Request,
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None
):
    """Handle logout via GET request (for URL navigation)"""
    return await logout_handler(request, session)


@router.post("/logout")
async def logout_post(
    request: Request,
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None
):
    """Handle logout via POST request (for forms)"""
    return await logout_handler(request, session)