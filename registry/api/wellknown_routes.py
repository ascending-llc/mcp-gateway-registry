import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from ..core.config import settings
from ..services.server_service import server_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/mcp-servers")
async def get_wellknown_mcp_servers(
    request: Request,
    user_context: Optional[dict] = None
) -> JSONResponse:
    """
    Main endpoint handler for /.well-known/mcp-servers
    Returns JSON with all discoverable MCP servers
    """
    # Step 1: Check if discovery is enabled
    if not settings.enable_wellknown_discovery:
        raise HTTPException(status_code=404, detail="Well-known discovery is disabled")

    # Step 2: Get all servers from server_service
    all_servers = server_service.get_all_servers()

    # Step 3: Filter based on discoverability and permissions
    discoverable_servers = []
    for server_path, server_info in all_servers.items():
        # For now, include all enabled servers
        # TODO: Add discoverability flag to server configs if needed
        if server_service.is_service_enabled(server_path):
            formatted_server = _format_server_discovery(server_info, request)
            discoverable_servers.append(formatted_server)

    # Step 4: Format response
    response_data = {
        "version": "1.0",
        "servers": discoverable_servers,
        "registry": {
            "name": "Enterprise MCP Gateway",
            "description": "Centralized MCP server registry for enterprise tools",
            "version": "1.0.0",
            "contact": {
                "url": str(request.base_url).rstrip('/'),
                "support": "mcp-support@company.com"
            }
        }
    }

    # Step 5: Return JSONResponse with cache headers
    headers = {
        "Cache-Control": f"public, max-age={settings.wellknown_cache_ttl}",
        "Content-Type": "application/json"
    }

    logger.info(f"Returned {len(discoverable_servers)} servers for well-known discovery")
    return JSONResponse(content=response_data, headers=headers)


def _format_server_discovery(server_info: dict, request: Request) -> dict:
    """Format individual server for discovery response"""
    server_path = server_info.get("path", "")
    server_name = server_info.get("server_name", server_path)
    description = server_info.get("description", "MCP Server")

    # Generate dynamic URL based on request host
    server_url = _get_server_url(server_path, request)

    # Get transport type from config
    transport_type = _get_transport_type(server_info)

    # Get authentication requirements
    auth_info = _get_authentication_info(server_info)

    # Get first 5 tools as preview
    tools_preview = _get_tools_preview(server_info, max_tools=5)

    return {
        "name": server_name,
        "description": description,
        "url": server_url,
        "transport": transport_type,
        "authentication": auth_info,
        "capabilities": ["tools", "resources"],
        "health_status": "healthy",  # TODO: Get actual health status
        "tools_preview": tools_preview
    }


def _get_server_url(server_path: str, request: Request) -> str:
    """Generate full URL for MCP server based on request host"""
    # Get host from request headers
    host = request.headers.get("host", "localhost:7860")

    # Get protocol (http/https) from X-Forwarded-Proto or scheme
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)

    # Clean up server path (remove leading and trailing slashes)
    clean_path = server_path.strip('/')

    # Return formatted URL
    return f"{proto}://{host}/{clean_path}/mcp"


def _get_transport_type(server_config: dict) -> str:
    """Determine transport type (sse or streamable-http)"""
    # Check server configuration for transport setting
    # Default to "streamable-http" if not specified
    return server_config.get("transport", "streamable-http")


def _get_authentication_info(server_info: dict) -> dict:
    """Extract authentication requirements for server"""
    auth_type = server_info.get("auth_type", "oauth")
    auth_provider = server_info.get("auth_provider", "default")
    server_name = server_info.get("server_name", "unknown")

    # Map auth types to standard formats
    if auth_type == "oauth":
        return {
            "type": "oauth2",
            "required": True,
            "authorization_url": "/auth/oauth/authorize",
            "provider": auth_provider,
            "scopes": ["mcp:read", f"{auth_provider}:read"]
        }
    elif auth_type == "api-key":
        return {
            "type": "api-key",
            "required": True,
            "header": "X-API-Key"
        }
    else:
        # Default to OAuth2 for unknown types
        return {
            "type": "oauth2",
            "required": True,
            "authorization_url": "/auth/oauth/authorize",
            "scopes": ["mcp:read", f"{server_name.lower()}:read"]
        }


def _get_tools_preview(server_info: dict, max_tools: int = 5) -> list:
    """Get limited list of tools for discovery preview"""
    # Extract tools from server_info
    tools = server_info.get("tool_list", [])

    # Return first N tools with name and description
    preview_tools = []
    for tool in tools[:max_tools]:
        if isinstance(tool, dict):
            preview_tools.append({
                "name": tool.get("name", "unknown"),
                "description": tool.get("description", "No description available")
            })
        elif isinstance(tool, str):
            # Handle case where tools are just strings
            preview_tools.append({
                "name": tool,
                "description": "No description available"
            })

    return preview_tools