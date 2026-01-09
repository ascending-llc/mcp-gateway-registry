import time
from typing import Dict, Any, Optional, Tuple
from registry.utils.log import logger
from registry.auth.oauth.flow_state_manager import get_flow_state_manager
from registry.schemas.enums import ConnectionState, OAuthFlowStatus
from registry.auth.oauth.reconnection import get_reconnection_manager
from registry.services.oauth.mcp_service import get_mcp_service


async def check_oauth_flow_status(
        user_id: str,
        server_name: str
) -> Tuple[bool, bool]:
    """
    Check OAuth flow status for user and server
    对应 TypeScript: checkOAuthFlowStatus()
    
    Args:
        user_id: User ID
        server_name: Server name
        
    Returns:
        Tuple[bool, bool]: (has_active_flow, has_failed_flow)
    """
    flow_manager = get_flow_state_manager()

    # Generate flow ID (same format as used during OAuth initiation)
    flow_id = flow_manager.generate_flow_id(user_id, server_name)

    try:
        flow_state = flow_manager.get_flow(flow_id)

        if not flow_state:
            return False, False

        flow_age_seconds = time.time() - flow_state.created_at
        flow_ttl_seconds = flow_manager._flow_ttl  # Default 600 seconds (10 minutes)

        # Check if flow has failed or timed out
        if flow_state.status == OAuthFlowStatus.FAILED or flow_age_seconds > flow_ttl_seconds:
            # Check if it was cancelled
            was_cancelled = flow_state.error and "cancelled" in flow_state.error.lower()

            if was_cancelled:
                logger.info(f"Found cancelled OAuth flow for {server_name}",
                            extra={
                                "flow_id": flow_id,
                                "status": flow_state.status,
                                "error": flow_state.error,
                            })
                return False, False
            else:
                logger.info(f"Found failed OAuth flow for {server_name}",
                            extra={
                                "flow_id": flow_id,
                                "status": flow_state.status,
                                "flow_age": flow_age_seconds,
                                "flow_ttl": flow_ttl_seconds,
                                "timed_out": flow_age_seconds > flow_ttl_seconds,
                                "error": flow_state.error,
                            })
                return False, True

        # Check if flow is pending (active)
        if flow_state.status == OAuthFlowStatus.PENDING:
            logger.info(f"Found active OAuth flow for {server_name}",
                        extra={
                            "flow_id": flow_id,
                            "flow_age": flow_age_seconds,
                            "flow_ttl": flow_ttl_seconds,
                        })
            return True, False
        return False, False

    except Exception as error:
        logger.error(
            f"Error checking OAuth flows for {server_name}: {error}"
        )
        return False, False


async def get_server_connection_status(
        user_id: str,
        server_name: str,
        server_config: Dict[str, Any],
        app_connections: Dict[str, Any],
        user_connections: Dict[str, Any],
        oauth_servers: set
) -> Dict[str, Any]:
    """
    Get connection status for a specific MCP server
    对应 TypeScript: getServerConnectionStatus()
    
    Args:
        user_id: User ID
        server_name: Server name
        server_config: Server configuration dict
        app_connections: Application-level connections
        user_connections: User-level connections
        oauth_servers: Set of OAuth server names
        
    Returns:
        Dict containing requiresOAuth and connectionState
    """

    # Get connection (app-level or user-level)
    connection = app_connections.get(server_name) or user_connections.get(server_name)

    # Check if connection is stale or doesn't exist
    server_updated_at = server_config.get("updated_at")
    is_stale_or_does_not_exist = (
        connection.is_stale(server_updated_at) if connection else True
    )

    # Base connection state
    disconnected_state = ConnectionState.DISCONNECTED.value
    base_connection_state = (
        disconnected_state
        if is_stale_or_does_not_exist
        else (connection.connection_state.value if connection else disconnected_state)
    )

    final_connection_state = base_connection_state

    # Connection state overrides specific to OAuth servers
    if base_connection_state == disconnected_state and server_name in oauth_servers:
        try:
            # Check if server is actively being reconnected
            mcp_service = await get_mcp_service()
            reconnection_manager = get_reconnection_manager(
                mcp_service=mcp_service,
                oauth_service=mcp_service.oauth_service
            )

            if reconnection_manager.is_reconnecting(user_id, server_name):
                final_connection_state = ConnectionState.CONNECTING.value
            else:
                # Check OAuth flow status
                has_active_flow, has_failed_flow = await check_oauth_flow_status(
                    user_id, server_name
                )
                if has_failed_flow:
                    final_connection_state = ConnectionState.ERROR.value
                elif has_active_flow:
                    final_connection_state = ConnectionState.CONNECTING.value

        except Exception as e:
            logger.error(f"Error checking reconnection status: {e}")
    return {"requires_oauth": server_name in oauth_servers,
            "connection_state": final_connection_state, }
