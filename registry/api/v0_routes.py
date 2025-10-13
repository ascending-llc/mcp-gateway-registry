"""
Anthropic MCP Registry API v0 endpoints.

Implements the standard MCP Registry REST API for compatibility with
Anthropic's official registry specification.

Spec: https://raw.githubusercontent.com/modelcontextprotocol/registry/refs/heads/main/docs/reference/api/openapi.yaml
"""

import logging
from typing import Annotated, Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth.dependencies import nginx_proxied_auth
from ..constants import REGISTRY_CONSTANTS
from ..health.service import health_service
from ..schemas.anthropic_schema import ErrorResponse, ServerList, ServerResponse
from ..services.server_service import server_service
from ..services.transform_service import (
    transform_to_server_list,
    transform_to_server_response,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v0", tags=["Anthropic Registry API"])


@router.get(
    "/servers",
    response_model=ServerList,
    summary="List MCP servers",
    description="Returns a paginated list of all registered MCP servers that the authenticated user can access.",
)
async def list_servers(
    cursor: Annotated[Optional[str], Query(description="Pagination cursor")] = None,
    limit: Annotated[
        Optional[int], Query(description="Maximum number of items", ge=1, le=1000)
    ] = None,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
) -> ServerList:
    """
    List all MCP servers with pagination.

    This endpoint respects user permissions - users only see servers they have access to.

    Args:
        cursor: Pagination cursor (opaque string from previous response)
        limit: Max results per page (default: 100, max: 1000)
        user_context: Authenticated user context from enhanced_auth

    Returns:
        ServerList with servers and pagination metadata
    """
    logger.info(
        f"v0 API: Listing servers for user '{user_context['username']}' (cursor={cursor}, limit={limit})"
    )

    # Get servers based on user permissions (same logic as existing /servers endpoint)
    if user_context["is_admin"]:
        # Admin sees all servers
        all_servers = server_service.get_all_servers()
        logger.debug(f"Admin user accessing all {len(all_servers)} servers")
    else:
        # Regular user sees only accessible servers
        all_servers = server_service.get_all_servers_with_permissions(
            user_context["accessible_servers"]
        )
        logger.debug(f"User accessing {len(all_servers)} accessible servers")

    # For v0 API, we don't need UI service filtering - accessible_servers already handles MCP server permissions
    # No additional filtering needed here - the get_all_servers_with_permissions already filtered by accessible_servers
    filtered_servers = []

    for path, server_info in all_servers.items():
        # Add health status and enabled state for transformation
        health_data = health_service._get_service_health_data(path)

        server_info_with_status = server_info.copy()
        server_info_with_status["health_status"] = health_data["status"]
        server_info_with_status["last_checked_iso"] = health_data["last_checked_iso"]
        server_info_with_status["is_enabled"] = server_service.is_service_enabled(path)

        filtered_servers.append(server_info_with_status)

    # Transform to Anthropic format with pagination
    server_list = transform_to_server_list(
        filtered_servers, cursor=cursor, limit=limit or 100
    )

    logger.info(
        f"v0 API: Returning {len(server_list.servers)} servers (hasMore={server_list.metadata.nextCursor is not None})"
    )

    return server_list


@router.get(
    "/servers/{serverName:path}/versions",
    response_model=ServerList,
    summary="List server versions",
    description="Returns all available versions for a specific MCP server.",
    responses={404: {"model": ErrorResponse, "description": "Server not found"}},
)
async def list_server_versions(
    serverName: str,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
) -> ServerList:
    """
    List all versions of a specific server.

    Currently, we only maintain one version per server, so this returns a single-item list.

    Args:
        serverName: URL-encoded server name in reverse-DNS format (e.g., "io.mcpgateway%2Fexample-server")
        user_context: Authenticated user context

    Returns:
        ServerList with single version

    Raises:
        HTTPException: 404 if server not found or user lacks access
    """
    # URL-decode the server name
    decoded_name = unquote(serverName)
    logger.info(
        f"v0 API: Listing versions for server '{decoded_name}' (user='{user_context['username']}')"
    )

    # Extract path from reverse-DNS name
    # Expected format: "io.mcpgateway/example-server"
    namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
    expected_prefix = f"{namespace}/"

    if not decoded_name.startswith(expected_prefix):
        logger.warning(f"Invalid server name format: {decoded_name}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Server not found"
        )

    # Construct initial path for lookup
    lookup_path = "/" + decoded_name.replace(expected_prefix, "")

    # Get server info - try with and without trailing slash
    server_info = server_service.get_server_info(lookup_path)
    if not server_info:
        # Try with trailing slash
        server_info = server_service.get_server_info(lookup_path + "/")

    if not server_info:
        logger.warning(f"Server not found: {lookup_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Server not found"
        )

    # Use the actual path from server_info (has correct trailing slash)
    path = server_info.get("path", lookup_path)

    # Check user permissions - use accessible_servers (MCP scopes) not accessible_services (UI scopes)
    accessible_servers = user_context.get("accessible_servers", [])
    server_name = server_info["server_name"]

    if not user_context["is_admin"]:
        # Check if user can access this server
        if server_name not in accessible_servers:
            logger.warning(
                f"User '{user_context['username']}' attempted to access unauthorized server: {server_name}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Server not found"
            )

    # Add health and status info using the correct path
    health_data = health_service._get_service_health_data(path)

    server_info_with_status = server_info.copy()
    server_info_with_status["health_status"] = health_data["status"]
    server_info_with_status["last_checked_iso"] = health_data["last_checked_iso"]
    server_info_with_status["is_enabled"] = server_service.is_service_enabled(path)

    # Since we only have one version, return a list with one item
    server_list = transform_to_server_list([server_info_with_status])

    logger.info(f"v0 API: Returning version info for {decoded_name}")

    return server_list


@router.get(
    "/servers/{serverName:path}/versions/{version}",
    response_model=ServerResponse,
    summary="Get server version details",
    description="Returns detailed information about a specific version of an MCP server. Use 'latest' to get the most recent version.",
    responses={
        404: {"model": ErrorResponse, "description": "Server or version not found"}
    },
)
async def get_server_version(
    serverName: str,
    version: str,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
) -> ServerResponse:
    """
    Get detailed information about a specific server version.

    Args:
        serverName: URL-encoded server name (e.g., "io.mcpgateway%2Fexample-server")
        version: Version string (e.g., "1.0.0" or "latest")
        user_context: Authenticated user context

    Returns:
        ServerResponse with full server details

    Raises:
        HTTPException: 404 if server not found or user lacks access
    """
    # URL-decode parameters
    decoded_name = unquote(serverName)
    decoded_version = unquote(version)

    logger.info(
        f"v0 API: Getting server '{decoded_name}' version '{decoded_version}' (user='{user_context['username']}')"
    )

    # Extract path from reverse-DNS name
    namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
    expected_prefix = f"{namespace}/"

    if not decoded_name.startswith(expected_prefix):
        logger.warning(f"Invalid server name format: {decoded_name}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Server not found"
        )

    # Construct initial path for lookup
    lookup_path = "/" + decoded_name.replace(expected_prefix, "")

    # Get server info - try with and without trailing slash
    server_info = server_service.get_server_info(lookup_path)
    if not server_info:
        # Try with trailing slash
        server_info = server_service.get_server_info(lookup_path + "/")

    if not server_info:
        logger.warning(f"Server not found: {lookup_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Server not found"
        )

    # Use the actual path from server_info (has correct trailing slash)
    path = server_info.get("path", lookup_path)

    # Check user permissions - use accessible_servers (MCP scopes) not accessible_services (UI scopes)
    accessible_servers = user_context.get("accessible_servers", [])
    server_name = server_info["server_name"]

    if not user_context["is_admin"]:
        if server_name not in accessible_servers:
            logger.warning(
                f"User '{user_context['username']}' attempted to access unauthorized server: {server_name}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Server not found"
            )

    # Currently we only support "latest" or "1.0.0" since we don't version servers
    if decoded_version not in ["latest", "1.0.0"]:
        logger.warning(f"Unsupported version requested: {decoded_version}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {decoded_version} not found",
        )

    # Add health and status info
    health_data = health_service._get_service_health_data(path)

    server_info_with_status = server_info.copy()
    server_info_with_status["health_status"] = health_data["status"]
    server_info_with_status["last_checked_iso"] = health_data["last_checked_iso"]
    server_info_with_status["is_enabled"] = server_service.is_service_enabled(path)

    # Transform to Anthropic format
    server_response = transform_to_server_response(
        server_info_with_status, include_registry_meta=True
    )

    logger.info(f"v0 API: Returning details for {decoded_name} v{decoded_version}")

    return server_response
