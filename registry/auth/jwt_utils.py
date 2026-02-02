"""
JWT Token Management Utilities

This module provides functions for generating and validating JWT access tokens 
and refresh tokens for the registry authentication system.
"""

import jwt
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from registry.core.config import settings

logger = logging.getLogger(__name__)

# Token expiration defaults
ACCESS_TOKEN_EXPIRES_HOURS = 24  # 1 day
REFRESH_TOKEN_EXPIRES_DAYS = 7   # 7 days


def generate_access_token(
    user_id: str,
    username: str,
    email: str,
    groups: list,
    scopes: list,
    role: str,
    auth_method: str,
    provider: str,
    idp_id: Optional[str] = None,
    expires_hours: int = ACCESS_TOKEN_EXPIRES_HOURS
) -> str:
    """
    Generate a JWT access token for authenticated user.
    
    Args:
        user_id: User's database ID
        username: Username
        email: User's email
        groups: List of user groups
        scopes: List of permission scopes
        role: User role
        auth_method: Authentication method (oauth2, traditional, etc.)
        provider: Auth provider (entra, keycloak, local, etc.)
        idp_id: Identity provider user ID (optional)
        expires_hours: Token expiration in hours (default: 24)
    
    Returns:
        JWT token string
    """
    now = datetime.utcnow()
    exp = now + timedelta(hours=expires_hours)
    
    # Build JWT payload
    payload = {
        # Standard JWT claims
        "sub": username,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        
        # Custom claims
        "user_id": user_id,
        "email": email,
        "groups": groups,
        "scope": " ".join(scopes) if isinstance(scopes, list) else scopes,
        "role": role,
        "auth_method": auth_method,
        "provider": provider,
        "token_type": "access_token",
    }
    
    # Add optional claims
    if idp_id:
        payload["idp_id"] = idp_id
    
    # JWT header
    headers = {
        "kid": settings.JWT_SELF_SIGNED_KID,
        "typ": "JWT",
        "alg": "HS256"
    }
    
    # Generate JWT
    token = jwt.encode(
        payload,
        settings.secret_key,
        algorithm="HS256",
        headers=headers
    )
    
    logger.debug(f"Generated access token for user {username}, expires in {expires_hours}h")
    return token


def generate_refresh_token(
    user_id: str,
    username: str,
    auth_method: str,
    provider: str,
    expires_days: int = REFRESH_TOKEN_EXPIRES_DAYS
) -> str:
    """
    Generate a JWT refresh token.
    
    Refresh tokens contain minimal claims and are used only for refreshing access tokens.
    
    Args:
        user_id: User's database ID
        username: Username
        auth_method: Authentication method
        provider: Auth provider
        expires_days: Token expiration in days (default: 7)
    
    Returns:
        JWT token string
    """
    now = datetime.utcnow()
    exp = now + timedelta(days=expires_days)
    
    payload = {
        # Standard JWT claims
        "sub": username,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        
        # Minimal custom claims
        "user_id": user_id,
        "auth_method": auth_method,
        "provider": provider,
        "token_type": "refresh_token",
    }
    
    headers = {
        "kid": settings.JWT_SELF_SIGNED_KID,
        "typ": "JWT",
        "alg": "HS256"
    }
    
    token = jwt.encode(
        payload,
        settings.secret_key,
        algorithm="HS256",
        headers=headers
    )
    
    logger.debug(f"Generated refresh token for user {username}, expires in {expires_days} days")
    return token


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode an access token.
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded token claims if valid, None otherwise
    """
    try:
        # Verify kid in header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get('kid')
        
        if kid != settings.JWT_SELF_SIGNED_KID:
            logger.debug(f"Invalid kid in token: {kid}")
            return None
        
        # Decode and verify token
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=['HS256'],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_iss": True,
                "verify_aud": True
            },
            leeway=30  # 30 second leeway for clock skew
        )
        
        # Verify token type
        if claims.get("token_type") != "access_token":
            logger.warning(f"Wrong token type: {claims.get('token_type')}")
            return None
        
        logger.debug(f"Access token verified for user: {claims.get('sub')}")
        return claims
        
    except jwt.ExpiredSignatureError:
        logger.debug("Access token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Invalid access token: {e}")
        return None
    except Exception as e:
        logger.error(f"Error verifying access token: {e}")
        return None


def verify_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a refresh token.
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded token claims if valid, None otherwise
    """
    try:
        # Verify kid in header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get('kid')
        
        if kid != settings.JWT_SELF_SIGNED_KID:
            logger.debug(f"Invalid kid in refresh token: {kid}")
            return None
        
        # Decode and verify token
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=['HS256'],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_iss": True,
                "verify_aud": True
            }
        )
        
        # Verify token type
        if claims.get("token_type") != "refresh_token":
            logger.warning(f"Wrong token type in refresh: {claims.get('token_type')}")
            return None
        
        logger.debug(f"Refresh token verified for user: {claims.get('sub')}")
        return claims
        
    except jwt.ExpiredSignatureError:
        logger.debug("Refresh token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Invalid refresh token: {e}")
        return None
    except Exception as e:
        logger.error(f"Error verifying refresh token: {e}")
        return None


def generate_token_pair(
    user_id: str,
    username: str,
    email: str,
    groups: list,
    scopes: list,
    role: str,
    auth_method: str,
    provider: str,
    idp_id: Optional[str] = None
) -> Tuple[str, str]:
    """
    Generate both access and refresh tokens.
    
    Args:
        user_id: User's database ID
        username: Username
        email: User's email
        groups: List of user groups
        scopes: List of permission scopes
        role: User role
        auth_method: Authentication method
        provider: Auth provider
        idp_id: Identity provider user ID (optional)
    
    Returns:
        Tuple of (access_token, refresh_token)
    """
    access_token = generate_access_token(
        user_id=user_id,
        username=username,
        email=email,
        groups=groups,
        scopes=scopes,
        role=role,
        auth_method=auth_method,
        provider=provider,
        idp_id=idp_id
    )
    
    refresh_token = generate_refresh_token(
        user_id=user_id,
        username=username,
        auth_method=auth_method,
        provider=provider
    )
    
    return access_token, refresh_token
