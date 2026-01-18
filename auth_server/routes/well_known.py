"""
OAuth 2.0 .well-known endpoints for auth server.

Implements RFC 8414 (OAuth 2.0 Authorization Server Metadata) and
OIDC Discovery specifications.

Note: RFC 8705 Protected Resource endpoints are implemented in mcpgw.
"""

import os
import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

# Import provider factory to get JWKS from actual provider
from ..providers.factory import get_auth_provider


def _get_auth_server_url():
    """
    Get required AUTH_SERVER_EXTERNAL_URL environment variable.
    
    Returns:
        Auth server URL string
        
    Raises:
        HTTPException: If AUTH_SERVER_EXTERNAL_URL is not set
    """
    auth_server_url = os.environ.get('AUTH_SERVER_EXTERNAL_URL')
    
    if not auth_server_url:
        logger.error("AUTH_SERVER_EXTERNAL_URL environment variable is not set")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: AUTH_SERVER_EXTERNAL_URL not configured"
        )
    
    return auth_server_url


@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_metadata():
    """
    OAuth 2.0 Authorization Server Metadata (RFC 8414).
    
    Provides metadata about the OAuth 2.0 authorization server to enable
    automatic client configuration and discovery.
    """
    auth_server_url = _get_auth_server_url()
    
    return {
        "issuer": auth_server_url,
        "authorization_endpoint": f"{auth_server_url}/oauth2/login",
        "token_endpoint": f"{auth_server_url}/oauth2/token",
        "device_authorization_endpoint": f"{auth_server_url}/oauth2/device/code",
        "registration_endpoint": f"{auth_server_url}/oauth2/register",
        "jwks_uri": f"{auth_server_url}/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "grant_types_supported": [
            "authorization_code",
            "urn:ietf:params:oauth:grant-type:device_code"
        ],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": [
            "mcp-registry-admin",
            "mcp-servers-unrestricted/read",
            "mcp-servers-unrestricted/execute"
        ],
        "service_documentation": f"{auth_server_url}/docs"
    }


@router.get("/.well-known/openid-configuration")
async def openid_configuration():
    """
    OpenID Connect Discovery endpoint.
    
    Provides OpenID Connect configuration metadata for clients that
    expect OIDC discovery.
    """
    auth_server_url = _get_auth_server_url()
    
    return {
        "issuer": auth_server_url,
        "authorization_endpoint": f"{auth_server_url}/oauth2/login",
        "token_endpoint": f"{auth_server_url}/oauth2/token",
        "device_authorization_endpoint": f"{auth_server_url}/oauth2/device/code",
        "registration_endpoint": f"{auth_server_url}/oauth2/register",
        "userinfo_endpoint": f"{auth_server_url}/oauth2/userinfo",
        "jwks_uri": f"{auth_server_url}/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["HS256", "RS256"],
        "scopes_supported": ["openid", "profile", "email"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "claims_supported": ["sub", "email", "name", "groups"],
        "grant_types_supported": [
            "authorization_code",
            "urn:ietf:params:oauth:grant-type:device_code"
        ]
    }


@router.get("/.well-known/jwks.json")
async def jwks_endpoint():
    """
    JSON Web Key Set (JWKS) endpoint.
    
    Provides public keys for JWT token verification. This endpoint forwards
    the JWKS from the configured authentication provider (Cognito, Keycloak, 
    Entra ID) based on AUTH_PROVIDER environment variable.
    
    For self-signed tokens (HS256), returns empty key set since symmetric 
    keys are not publicly exposed.
    """
    try:
        # Get the configured authentication provider
        auth_provider = get_auth_provider()
        
        # Get JWKS from the provider (Cognito, Keycloak, Entra ID, etc.)
        # Each provider implementation fetches JWKS from their respective endpoints:
        # - Cognito: https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json
        # - Keycloak: {keycloak_url}/realms/{realm}/protocol/openid-connect/certs
        # - Entra ID: https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys
        jwks = auth_provider.get_jwks()
        
        logger.debug(f"Returning JWKS from {auth_provider.__class__.__name__} provider")
        return jwks
        
    except Exception as e:
        logger.error(f"Failed to retrieve JWKS from provider: {e}")
        
        # Fallback: Return empty key set for self-signed tokens
        # HS256 uses symmetric keys (SECRET_KEY), which should not be publicly exposed
        logger.warning("Falling back to empty JWKS (for self-signed HS256 tokens)")
        return {
            "keys": []
        }
