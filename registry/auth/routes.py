import urllib.parse
import logging
from typing import Annotated

from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
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
            response = await client.get(f"{settings.auth_server_url}/oauth2/providers", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                return data.get("providers", [])
    except Exception as e:
        logger.warning(f"Failed to fetch OAuth2 providers from auth server: {e}")
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
    username: Annotated[str, Form()], 
    password: Annotated[str, Form()]
):
    """Handle traditional login form submission"""
    logger.info(f"Login attempt for username: {username}")
    
    if validate_login_credentials(username, password):
        session_data = create_session_cookie(username)
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
        return RedirectResponse(
            url="/login?error=Invalid+username+or+password",
            status_code=status.HTTP_303_SEE_OTHER,
        )


@router.post("/logout")
async def logout():
    """Handle logout"""
    logger.info("User logged out.")
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(settings.session_cookie_name)
    return response 