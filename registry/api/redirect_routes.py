import base64
import json
import logging
import secrets
import urllib.parse
from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import URLSafeTimedSerializer

from auth_server.core.config import settings as auth_settings
from registry.services.user_service import user_service

from ..auth.dependencies import create_session_cookie, validate_login_credentials
from ..core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

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
            logger.warning(f"Auth server returned non-200 status: {response.status_code}, body: {response.text}")
    except Exception as e:
        logger.warning(f"Failed to fetch OAuth2 providers from auth server: {e}", exc_info=True)
    return []

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
        ).decode().rstrip("=")
        auth_url = f"{auth_external_url}/oauth2/login/{provider}?redirect_uri={registry_client_url}&state={client_state}"
        logger.info(f"request.base_url: {request.base_url}, registry_url: {registry_client_url}, auth_external_url: {auth_external_url}, auth_url: {auth_url}")
        logger.info(f"Redirecting to OAuth2 login for provider {provider}: {auth_url}")
        return RedirectResponse(url=auth_url, status_code=302)

    except Exception as e:
        logger.error(f"Error redirecting to OAuth2 login for {provider}: {e}")
        return RedirectResponse(url="/login?error=oauth2_redirect_failed", status_code=302)


@router.get("/redirect")
async def oauth2_callback(request: Request, code: str = None, error: str = None, details: str = None):
    """Handle OAuth2 callback from auth server
    This endpoint receives an authorization code and exchanges it for a JWT access token.
    The user_id has already been resolved by auth_server from MongoDB and included in the JWT.
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
                url=f"{settings.registry_client_url}/login?error={urllib.parse.quote(error_message)}",
                status_code=302
            )

        if not code:
            logger.error("Missing authorization code in OAuth2 callback")
            return RedirectResponse(
                url=f"{settings.registry_client_url}/login?error=oauth2_missing_code",
                status_code=302
            )

        # Exchange authorization code for JWT access token (standard OAuth2 flow)
        try:
            async with httpx.AsyncClient() as client:
                auth_server_url = settings.auth_server_url.rstrip("/")
                registry_redirect_uri = f"{settings.registry_url}/redirect"

                response = await client.post(
                    f"{auth_server_url}/oauth2/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "client_id": settings.registry_app_name,
                        "redirect_uri": registry_redirect_uri
                    },
                    timeout=10.0
                )

                if response.status_code != 200:
                    logger.error(f"Failed to exchange code for token: {response.status_code} - {response.text}")
                    return RedirectResponse(
                        url=f"{settings.registry_client_url}/login?error=oauth2_token_exchange_failed",
                        status_code=302
                    )

                token_response = response.json()
                access_token = token_response.get("access_token")

                if not access_token:
                    logger.error("No access_token returned from auth server")
                    return RedirectResponse(
                        url=f"{settings.registry_client_url}/login?error=oauth2_invalid_response",
                        status_code=302
                    )

                # Decode JWT to extract user information (no signature verification for internal use)
                import jwt as pyjwt
                user_claims = pyjwt.decode(access_token, options={"verify_signature": False})

                # Extract user info from JWT claims
                userinfo = {
                    "user_id": user_claims.get("user_id"),
                    "username": user_claims.get("sub"),
                    "email": user_claims.get("email"),
                    "name": user_claims.get("name"),
                    "groups": user_claims.get("groups", []),
                    "provider": user_claims.get("provider"),
                    "auth_method": "oauth2"
                }

                logger.info(f"OAuth2 callback exchanged code for JWT token: {userinfo['username']}")

        except httpx.TimeoutException:
            logger.error("Timeout exchanging authorization code with auth server")
            return RedirectResponse(
                url=f"{settings.registry_client_url}/login?error=oauth2_timeout",
                status_code=302
            )
        except Exception as e:
            logger.error(f"Failed to exchange authorization code for token: {e}")
            return RedirectResponse(
                url=f"{settings.registry_client_url}/login?error=oauth2_exchange_error",
                status_code=302
            )

        # Validate that user_id was resolved by auth_server
        if not userinfo.get("user_id"):
            logger.warning(f"User {userinfo.get('username')} has no user_id - not found in MongoDB")
            return RedirectResponse(
                url=f"{settings.registry_client_url}/login?error=User+not+found+in+registry",
                status_code=302
            )

        # Look up user object to get role (user_id already provided in JWT)
        user_obj = await user_service.get_user_by_user_id(userinfo.get("user_id"))
        if not user_obj:
            logger.warning(f"User ID {userinfo.get('user_id')} not found in registry database")
            return RedirectResponse(
                url=f"{settings.registry_client_url}/login?error=User+not+found+in+registry",
                status_code=302
            )

        # Session data already contains user_id from auth_server, just add role
        session_data = {
            **userinfo,
            "role": user_obj.role
        }
        registry_session = signer.dumps(session_data)
        response = RedirectResponse(url=settings.registry_client_url.rstrip("/"), status_code=302)
        cookie_secure_config = auth_settings.oauth2_config.get("session", {}).get("secure", False)
        x_forwarded_proto = request.headers.get("x-forwarded-proto", "")
        is_https = x_forwarded_proto == "https" or request.url.scheme == "https"
        cookie_secure = cookie_secure_config and is_https

        cookie_params = {
         "key": "jarvis_registry_session",
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
        return RedirectResponse(url=f"{settings.registry_client_url}/login?error=oauth2_callback_error", status_code=302)


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
    logger.info(f"Login failed for user '{username}'.")

    if is_api_call:
        # API error response for React
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    # Traditional redirect with error
    return RedirectResponse(
        url=f"{settings.registry_client_url}/login?error=Invalid+username+or+password",
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
                from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
                serializer = URLSafeTimedSerializer(settings.secret_key)
                session_data = serializer.loads(session, max_age=settings.session_max_age_seconds)

                if session_data.get("auth_method") == "oauth2":
                    provider = session_data.get("provider")
                    logger.info(f"User was authenticated via OAuth2 provider: {provider}")

            except (SignatureExpired, BadSignature, Exception) as e:
                logger.debug(f"Could not decode session for logout: {e}")

        # Clear local session cookie
        response = RedirectResponse(url=f"{settings.registry_client_url}/login", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(settings.session_cookie_name)

        # If user was logged in via OAuth2, redirect to provider logout
        if provider:
            auth_external_url = settings.auth_server_external_url
            redirect_uri = f"{settings.registry_client_url}/logout"

            logout_url = f"{auth_external_url}/oauth2/logout/{provider}?redirect_uri={redirect_uri}"
            logger.info(f"Redirecting to {provider} logout: {logout_url}")
            response = RedirectResponse(url=logout_url, status_code=status.HTTP_303_SEE_OTHER)
            response.delete_cookie(settings.session_cookie_name)

        logger.info("User logged out.")
        return response

    except Exception as e:
        logger.error(f"Error during logout: {e}")
        # Fallback to simple logout
        response = RedirectResponse(url=f"{settings.registry_client_url}/login", status_code=status.HTTP_303_SEE_OTHER)
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
