from typing import Dict, Any, Optional
from registry.utils.log import logger
from registry.schemas.enums import ConnectionState
from registry.services.oauth.base import MCPConnection, ConnectionStateContext


class ConnectionStatusResolver:
    """Connection Status Resolver"""

    def __init__(
            self,
            flow_state_manager=None,
            reconnection_manager=None
    ):
        """
        Initialize the status resolver

        Args:
            flow_state_manager: OAuth flow state manager
            reconnection_manager: OAuth reconnection manager
        """
        self.flow_state_manager = flow_state_manager
        self.reconnection_manager = reconnection_manager

    async def resolve_status(
            self,
            context: ConnectionStateContext
    ) -> Dict[str, Any]:
        """
        Resolve server connection status - Main entry point

        Corresponds to TypeScript: getServerConnectionStatus()

        Args:
            context: Connection state context

        Returns:
            Dict containing requires_oauth and connection_state
        """
        # 1. Check if the connection is stale or missing
        is_stale_or_missing = self._check_staleness(context)

        # 2. Determine the base connection state
        base_state = self._get_base_connection_state(
            context.connection,
            is_stale_or_missing
        )

        # 3. For OAuth servers and state DISCONNECTED, apply OAuth state overrides
        final_state = base_state
        if context.is_oauth_server and base_state == ConnectionState.DISCONNECTED.value:
            final_state = await self._apply_oauth_overrides(
                context.user_id,
                context.server_name,
                base_state
            )

        return {
            "requires_oauth": context.is_oauth_server,
            "connection_state": final_state,
        }

    def _check_staleness(self, context: ConnectionStateContext) -> bool:
        """
        Check if the connection is stale or missing

        Args:
            context: Connection state context

        Returns:
            bool: Whether it is stale or missing
        """
        if not context.connection:
            return True

        idle_timeout = context.idle_timeout or 3600

        if context.connection.is_stale(max_idle_time=idle_timeout):
            logger.debug(
                f"Connection stale for {context.server_name}, "
                f"idle_timeout={idle_timeout}s"
            )
            return True

        return False

    def _get_base_connection_state(
            self,
            connection: Optional[MCPConnection],
            is_stale_or_missing: bool
    ) -> str:
        """
        Get the base connection state

        Args:
            connection: Connection object
            is_stale_or_missing: Whether it is stale or missing

        Returns:
            str: Connection state value
        """
        disconnected_state = ConnectionState.DISCONNECTED.value

        if is_stale_or_missing:
            return disconnected_state

        return connection.connection_state.value if connection else disconnected_state

    async def _apply_oauth_overrides(
            self,
            user_id: str,
            server_name: str,
            base_state: str
    ) -> str:
        """
        Apply OAuth-specific state overrides

        Only called when the base state is DISCONNECTED

        Args:
            user_id: User ID
            server_name: Server name
            base_state: Base connection state

        Returns:
            str: Final connection state
        """
        try:
            # 1. Check if reconnection is in progress
            if self.reconnection_manager:
                is_reconnecting = self.reconnection_manager.is_reconnecting(
                    user_id,
                    server_name
                )
                if is_reconnecting:
                    logger.debug(f"Server is reconnecting: {server_name}")
                    return ConnectionState.CONNECTING.value

            # 2. Check OAuth flow state
            if self.reconnection_manager:
                oauth_state = await self.reconnection_manager.get_oauth_state_override(
                    user_id,
                    server_name
                )

                if oauth_state == "failed":
                    logger.debug(f"OAuth flow failed for: {server_name}")
                    return ConnectionState.ERROR.value
                elif oauth_state == "active":
                    logger.debug(f"OAuth flow active for: {server_name}")
                    return ConnectionState.CONNECTING.value

        except Exception as e:
            logger.error(
                f"Error applying OAuth overrides for {server_name}: {e}",
                exc_info=True
            )

        return base_state


_status_resolver_instance: Optional[ConnectionStatusResolver] = None


def get_status_resolver(
        flow_state_manager=None,
        reconnection_manager=None
) -> ConnectionStatusResolver:
    global _status_resolver_instance
    if _status_resolver_instance is None:
        _status_resolver_instance = ConnectionStatusResolver(
            flow_state_manager=flow_state_manager,
            reconnection_manager=reconnection_manager
        )
    return _status_resolver_instance
