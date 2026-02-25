"""
Root-level OAuth Authorization endpoint.

This module provides the /authorize endpoint at root level for mcp-remote compatibility.
mcp-remote constructs the authorization URL from the issuer origin (e.g., https://example.com)
instead of the full issuer path (e.g., https://example.com/auth).
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

# Import settings
from ..core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/authorize")
async def authorize_redirect(request: Request):
    """
    Root-level authorize endpoint for mcp-remote compatibility.

    mcp-remote constructs authorize URL from the issuer origin (e.g., https://example.com)
    instead of the full issuer path (e.g., https://example.com/auth).

    This endpoint redirects to the actual authorization endpoint with the correct prefix.
    All query parameters (client_id, redirect_uri, state, scope, etc.) are preserved.

    Flow:
    1. mcp-remote calls: https://example.com/authorize?client_id=...&redirect_uri=...
    2. This endpoint redirects to: https://example.com/auth/oauth2/login/{provider}?client_id=...
    3. User authenticates with the provider (Entra ID, Keycloak, etc.)
    4. Provider redirects to mcp-remote's callback URL
    """
    # Get the current auth provider from settings
    auth_provider = settings.auth_provider

    # Construct the actual authorization endpoint with prefix
    api_prefix = settings.auth_server_api_prefix.rstrip("/") if settings.auth_server_api_prefix else ""
    actual_auth_endpoint = f"{api_prefix}/oauth2/login/{auth_provider}"

    # Preserve all query parameters
    query_params = str(request.url.query) if request.url.query else ""
    redirect_url = f"{actual_auth_endpoint}?{query_params}" if query_params else actual_auth_endpoint

    logger.info(f"Redirecting /authorize to {redirect_url} for provider: {auth_provider}")
    return RedirectResponse(url=redirect_url, status_code=307)  # 307 preserves GET method and query parameters
