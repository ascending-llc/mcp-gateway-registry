from typing import Dict, Any, List, Optional
from registry.utils.log import logger
from registry.services.oauth.mcp_service import MCPService, get_mcp_service
from registry.services.server_service_v1 import server_service_v1
from registry.services.oauth.flow_helpers import get_server_connection_status as get_server_status_helper
from registry.schemas.enums import ConnectionState


async def get_servers_connection_status(
    user_id: str,
    servers: List[Any],
    mcp_service: Optional[MCPService] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Get connection status for multiple servers.

    """
    if not servers:
        return {}
    
    # Get MCP service instance
    if mcp_service is None:
        mcp_service = await get_mcp_service()
    
    # Get app-level and user-level connections (direct reference, no copy)
    app_connections = mcp_service.connection_service.app_connections
    user_connections = mcp_service.connection_service.get_user_connections(user_id)
    
    # Build server config map and identify OAuth servers
    mcp_config = {}
    oauth_servers = set()
    
    for server in servers:
        server_name = server.serverName
        mcp_config[server_name] = {
            "name": server_name,
            "config": server.config,
            "updated_at": server.updatedAt.timestamp() if server.updatedAt else None,
        }
        if server.config.get("requiresOAuth", False):
            oauth_servers.add(server_name)
    
    # Get status for each server
    connection_status = {}
    for server_name, config_data in mcp_config.items():
        try:
            server_status = await get_server_status_helper(
                user_id=user_id,
                server_name=server_name,
                server_config=config_data,
                app_connections=app_connections,
                user_connections=user_connections,
                oauth_servers=oauth_servers
            )
            connection_status[server_name] = server_status
        except Exception as e:
            logger.error(f"Error getting connection status for {server_name}: {e}", exc_info=True)
            # Set error state if we can't get connection status
            connection_status[server_name] = {
                "connection_state": ConnectionState.ERROR.value,
                "requires_oauth": server_name in oauth_servers,
                "error": f"Failed to get connection status: {str(e)}"
            }
    
    return connection_status


async def get_single_server_connection_status(
    user_id: str,
    server_name: str,
    mcp_service: Optional[MCPService] = None
) -> Dict[str, Any]:
    """
    Get connection status for a single server.
    """
    # Get server configuration
    server_docs = await server_service_v1.get_server_by_name(server_name)
    if not server_docs or not server_docs.config:
        raise ValueError(f"Server '{server_name}' not found")
    
    # Get MCP service instance
    if mcp_service is None:
        mcp_service = await get_mcp_service()
    
    # Get app-level and user-level connections (direct reference, no copy)
    app_connections = mcp_service.connection_service.app_connections
    user_connections = mcp_service.connection_service.get_user_connections(user_id)
    
    # Build server config data
    server_config = {
        "name": server_name,
        "config": server_docs.config,
        "updated_at": server_docs.updatedAt.timestamp() if server_docs.updatedAt else None,
    }
    
    # Determine if this is an OAuth server
    oauth_servers = set()
    if server_docs.config.get("requires_oauth", False):
        oauth_servers.add(server_name)
    
    # Get status using the shared helper
    server_status = await get_server_status_helper(
        user_id=user_id,
        server_name=server_name,
        server_config=server_config,
        app_connections=app_connections,
        user_connections=user_connections,
        oauth_servers=oauth_servers
    )
    
    return server_status
