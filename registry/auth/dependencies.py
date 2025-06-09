import secrets
from typing import Annotated
import logging

from fastapi import Depends, HTTPException, status, Cookie
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from ..core.config import settings

logger = logging.getLogger(__name__)

# Initialize session signer
signer = URLSafeTimedSerializer(settings.secret_key)


def get_current_user(
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> str:
    """
    Validate session cookie and return username.
    Now supports both traditional login and OAuth2 sessions.
    """
    if not session:
        logger.info("No session cookie found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        session_data = signer.loads(session, max_age=settings.session_max_age_seconds)
        username = session_data.get("username")
        
        if not username:
            logger.warning("Session cookie exists but no username found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid session format",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Log additional OAuth2 session info if available
        auth_method = session_data.get("auth_method", "traditional")
        provider = session_data.get("provider", "local")
        logger.info(f"Session validated for user {username} (auth: {auth_method}, provider: {provider})")
        
        return username
        
    except SignatureExpired:
        logger.info("Session cookie has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except BadSignature:
        logger.warning("Invalid session cookie signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Unexpected error during session validation: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session validation failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def api_auth(
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> str:
    """
    API authentication that supports both traditional and OAuth2 sessions.
    Returns username for authenticated requests.
    """
    try:
        return get_current_user(session)
    except HTTPException as e:
        # Re-raise with appropriate error response for API endpoints
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API access requires authentication",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise


def web_auth(
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> str:
    """
    Web authentication that redirects to login page for unauthenticated users.
    Used for HTML endpoints that should redirect rather than return 401.
    """
    try:
        return get_current_user(session)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            # For web endpoints, redirect to login instead of returning 401
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                detail="Authentication required",
                headers={"Location": "/login"}
            )
        raise


def create_session_cookie(username: str, auth_method: str = "traditional", provider: str = "local") -> str:
    """Create a signed session cookie for a user."""
    session_data = {
        "username": username,
        "auth_method": auth_method,
        "provider": provider
    }
    return signer.dumps(session_data)


def validate_login_credentials(username: str, password: str) -> bool:
    """Validate traditional login credentials."""
    correct_username = secrets.compare_digest(username, settings.admin_user)
    correct_password = secrets.compare_digest(password, settings.admin_password)
    return correct_username and correct_password 