import logging
from typing import Any

from ...schemas.enums import ConnectionState
from ..server_service import ServerServiceV1
from .mcp_service import MCPService
from .status_resolver import ConnectionStateContext, ConnectionStatusResolver

logger = logging.getLogger(__name__)


async def get_servers_connection_status(
    user_id: str,
    servers: list[Any],
    mcp_service: MCPService,
    status_resolver: ConnectionStatusResolver,
) -> dict[str, dict[str, Any]]:
    """
    Get connection status for multiple servers.

    """
    if not servers:
        return {}

    # Retrieve application-level and user-level connections
    app_connections = mcp_service.connection_service.app_connections
    user_connections = mcp_service.connection_service.get_user_connections(user_id)

    # Retrieve statuses
    connection_status = {}
    for server in servers:
        server_name = server.serverName
        server_id = str(server.id)

        requires_oauth = server.config.get("requiresOAuth", False)
        idle_timeout_seconds = server.config.get("idleTimeout", 900)
        try:
            # Retrieve the connection
            connection = app_connections.get(server_id) or user_connections.get(server_id)

            # Build the context
            context = ConnectionStateContext(
                user_id=user_id,
                server_name=server_name,
                server_id=server_id,
                server_config=server.config,
                connection=connection,
                is_oauth_server=requires_oauth,
                idle_timeout=idle_timeout_seconds,
            )

            # Resolve the status
            server_status = await status_resolver.resolve_status(context)
            connection_status[server_id] = server_status

        except Exception as e:
            logger.error(f"Failed to retrieve connection status for {server_name}: {e}", exc_info=True)
            connection_status[server_id] = {
                "connection_state": ConnectionState.ERROR.value,
                "requires_oauth": requires_oauth,
                "error": f"Failed to retrieve connection status: {str(e)}",
            }

    return connection_status


async def get_single_server_connection_status(
    user_id: str,
    server_id: str,
    mcp_service: MCPService,
    server_service: ServerServiceV1,
    status_resolver: ConnectionStatusResolver,
) -> dict[str, Any]:
    """
    Get connection status for a single server.
    """
    server_docs = await server_service.get_server_by_id(server_id)
    if not server_docs or not server_docs.config:
        raise ValueError(f"Server '{server_id}' not found")

    app_connections = mcp_service.connection_service.app_connections
    user_connections = mcp_service.connection_service.get_user_connections(user_id)

    # Determine if it is an OAuth server.
    requires_oauth = server_docs.config.get("requires_oauth", False) or server_docs.config.get("requiresOAuth", False)

    # Connection idle time
    if requires_oauth:
        idle_timeout_seconds = 3600  # Default OAuth connection timeout: 1 hour
    else:
        timeout_ms = server_docs.config.get("timeout", 60000)  # Default: 60 seconds
        idle_timeout_seconds = timeout_ms / 1000.0

    connection = app_connections.get(server_id) or user_connections.get(server_id)
    context = ConnectionStateContext(
        user_id=user_id,
        server_name=server_docs.serverName,
        server_id=server_id,
        server_config=server_docs.config,
        connection=connection,
        is_oauth_server=requires_oauth,
        idle_timeout=idle_timeout_seconds,
    )
    server_status = await status_resolver.resolve_status(context)
    return server_status
