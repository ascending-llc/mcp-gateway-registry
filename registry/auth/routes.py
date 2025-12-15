import urllib.parse
import logging
from typing import Annotated

from fastapi import APIRouter, Request, Form, HTTPException, status, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx

from ..core.config import settings
from .dependencies import create_session_cookie, validate_login_credentials

logger = logging.getLogger(__name__)

router = APIRouter()

# Templates (will be injected via dependency later, but for now keep it simple)
templates = Jinja2Templates(directory=settings.templates_dir)


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


@router.get("/auth/{provider}")
async def oauth2_login_redirect(provider: str, request: Request):
    """Redirect to auth server for OAuth2 login"""
    try:
        # Build redirect URL to auth server - use external URL for browser redirects
        registry_url = str(request.base_url).rstrip('/')
        auth_external_url = settings.auth_server_external_url
        auth_url = f"{auth_external_url}/oauth2/login/{provider}?redirect_uri={registry_url}/"
        logger.info(f"request.base_url: {request.base_url}, registry_url: {registry_url}, auth_external_url: {auth_external_url}, auth_url: {auth_url}")
        logger.info(f"Redirecting to OAuth2 login for provider {provider}: {auth_url}")
        return RedirectResponse(url=auth_url, status_code=302)
        
    except Exception as e:
        logger.error(f"Error redirecting to OAuth2 login for {provider}: {e}")
        return RedirectResponse(url="/login?error=oauth2_redirect_failed", status_code=302)


@router.get("/auth/callback")
async def oauth2_callback(request: Request, error: str = None, details: str = None):
    """Handle OAuth2 callback from auth server"""
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
        
        # If we reach here, the auth server should have set the session cookie
        # Verify the session is valid by checking the cookie
        session_cookie = request.cookies.get(settings.session_cookie_name)
        if session_cookie:
            try:
                from .dependencies import signer
                # Validate session cookie
                session_data = signer.loads(session_cookie, max_age=settings.session_max_age_seconds)
                username = session_data.get("username")
                auth_method = session_data.get("auth_method", "unknown")
                
                logger.info(f"OAuth2 callback successful for user {username} via {auth_method}")
                return RedirectResponse(url="/", status_code=302)
                
            except Exception as e:
                logger.warning(f"Invalid session cookie in OAuth2 callback: {e}")
        
        # If no valid session, redirect to login with error
        logger.warning("OAuth2 callback completed but no valid session found")
        return RedirectResponse(url="/login?error=oauth2_session_invalid", status_code=302)
        
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
        
        response.set_cookie(
            key=settings.session_cookie_name,
            value=session_data,
            max_age=settings.session_max_age_seconds,
            httponly=True,
            samesite="lax",
        )
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


@router.get("/providers")
async def get_providers_api():
    """API endpoint to get available OAuth2 providers for React frontend"""
    providers = await get_oauth2_providers()
    return {"providers": providers}

@router.get("/config")
async def get_auth_config():
    """API endpoint to get auth configuration for React frontend"""
    return {"auth_server_url": settings.auth_server_external_url}
