from typing import Dict, Any, List, Optional
from registry.utils.log import logger
from registry.services.oauth.mcp_service import MCPService, get_mcp_service
from registry.services.server_service_v1 import server_service_v1
from registry.services.oauth.status_resolver import get_status_resolver, ConnectionStateContext
from registry.schemas.enums import ConnectionState
from registry.auth.oauth.flow_state_manager import get_flow_state_manager
from registry.auth.oauth.reconnection import get_reconnection_manager


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

    if not mcp_service:
        mcp_service = await get_mcp_service()

    # 获取状态解析器
    flow_manager = get_flow_state_manager()
    reconnection_mgr = get_reconnection_manager(
        mcp_service=mcp_service,
        oauth_service=mcp_service.oauth_service
    )

    status_resolver = get_status_resolver(
        flow_state_manager=flow_manager,
        reconnection_manager=reconnection_mgr
    )

    # 获取应用级和用户级连接
    app_connections = mcp_service.connection_service.app_connections
    user_connections = mcp_service.connection_service.get_user_connections(user_id)

    # 获取状态
    connection_status = {}
    for server in servers:
        server_name = server.serverName

        # 确定是否为 OAuth 服务器
        requires_oauth = server.config.get("requiresOAuth", False)

        # 计算 idle_timeout
        if requires_oauth:
            idle_timeout_seconds = 3600  # OAuth 连接默认 1 小时
        else:
            timeout_ms = server.config.get("timeout", 60000)  # 默认 60 秒
            idle_timeout_seconds = timeout_ms / 1000.0

        try:
            # 获取连接
            connection = app_connections.get(server_name) or user_connections.get(server_name)

            # 构建上下文
            context = ConnectionStateContext(
                user_id=user_id,
                server_name=server_name,
                server_config=server.config,
                connection=connection,
                is_oauth_server=requires_oauth,
                idle_timeout=idle_timeout_seconds
            )

            # 解析状态
            server_status = await status_resolver.resolve_status(context)
            connection_status[server_name] = server_status

        except Exception as e:
            logger.error(f"获取连接状态失败 {server_name}: {e}", exc_info=True)
            connection_status[server_name] = {
                "connection_state": ConnectionState.ERROR.value,
                "requires_oauth": requires_oauth,
                "error": f"获取连接状态失败: {str(e)}"
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
    server_docs = await server_service_v1.get_server_by_name(server_name)
    if not server_docs or not server_docs.config:
        raise ValueError(f"server '{server_name}' not found")

    if mcp_service is None:
        mcp_service = await get_mcp_service()

    flow_manager = get_flow_state_manager()
    reconnection_mgr = get_reconnection_manager(
        mcp_service=mcp_service,
        oauth_service=mcp_service.oauth_service
    )

    status_resolver = get_status_resolver(
        flow_state_manager=flow_manager,
        reconnection_manager=reconnection_mgr
    )

    app_connections = mcp_service.connection_service.app_connections
    user_connections = mcp_service.connection_service.get_user_connections(user_id)

    # Determine if it is an OAuth server.
    requires_oauth = server_docs.config.get("requires_oauth", False) or \
                     server_docs.config.get("requiresOAuth", False)

    # Connection idle time
    if requires_oauth:
        idle_timeout_seconds = 3600  # OAuth 连接默认 1 小时
    else:
        timeout_ms = server_docs.config.get("timeout", 60000)  # default: 60s
        idle_timeout_seconds = timeout_ms / 1000.0

    connection = app_connections.get(server_name) or user_connections.get(server_name)
    context = ConnectionStateContext(
        user_id=user_id,
        server_name=server_name,
        server_config=server_docs.config,
        connection=connection,
        is_oauth_server=requires_oauth,
        idle_timeout=idle_timeout_seconds
    )
    server_status = await status_resolver.resolve_status(context)
    return server_status
