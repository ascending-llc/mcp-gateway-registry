import asyncio
import time
from typing import Dict, Any, Optional, List, Set
from registry.utils.log import logger
from registry.models.oauth_models import OAuthTokens
from .tracker import OAuthReconnectionTracker
from registry.schemas.enums import ConnectionState
from registry.services.server_service_v1 import server_service_v1


class OAuthReconnectionManager:
    """
    OAuth Reconnection Manager

    Manages reconnection attempts for OAuth-enabled MCP servers
    """

    # Default connection timeout (10 seconds)
    DEFAULT_CONNECTION_TIMEOUT_MS = 10_000

    def __init__(
            self,
            mcp_service: Any,  # MCPService instance
            oauth_service: Any,  # OAuthService instance
            tracker: Optional[OAuthReconnectionTracker] = None,
            connection_timeout_ms: Optional[int] = None
    ):
        """
        Initialize reconnection manager
        
        Args:
            mcp_service: MCP service instance providing connection methods
            oauth_service: OAuth service instance providing token methods
            tracker: Reconnection tracker, optional
            connection_timeout_ms: Connection timeout in milliseconds, optional
        """
        self.mcp_service = mcp_service
        self.oauth_service = oauth_service
        self.tracker = tracker or OAuthReconnectionTracker()
        self.connection_timeout_ms = connection_timeout_ms or self.DEFAULT_CONNECTION_TIMEOUT_MS

        logger.debug(f"Initialized with timeout: {self.connection_timeout_ms}ms")

    def is_reconnecting(self, user_id: str, server_name: str) -> bool:
        """
        Check if server is currently reconnecting
        
        Notes: isReconnecting()
        """
        # Clean up if timed out, then return whether still reconnecting
        self.tracker.cleanup_if_timed_out(user_id, server_name)
        return self.tracker.is_still_reconnecting(user_id, server_name)

    async def reconnect_servers(self, user_id: str) -> Dict[str, bool]:
        """
        Reconnect all OAuth servers for user
        
        Notes: reconnectServers()
        
        Returns:
            Dict[str, bool]: server_name -> reconnection success status
        """
        logger.info(f"Starting reconnection for user: {user_id}")

        # 1. Get servers to reconnect
        servers_to_reconnect = await self._get_servers_to_reconnect(user_id)

        if not servers_to_reconnect:
            logger.info(f"No servers to reconnect for user: {user_id}")
            return {}

        logger.info(f"Found {len(servers_to_reconnect)} servers to reconnect: "
                    f"{list(servers_to_reconnect)}")

        # 2. Mark servers as actively reconnecting
        for server_name in servers_to_reconnect:
            self.tracker.set_active(user_id, server_name)

        # 3. Try to reconnect servers (sequentially like TypeScript version)
        results = {}
        for server_name in servers_to_reconnect:
            success = await self.try_reconnect_server(user_id, server_name)
            results[server_name] = success

        logger.info(f"Reconnection completed for user: {user_id}, "
            f"successful: {sum(1 for r in results.values() if r)}, "
            f"failed: {sum(1 for r in results.values() if not r)}")
        return results

    async def try_reconnect_server(
            self,
            user_id: str,
            server_name: str,
            force_new: bool = False
    ) -> bool:
        """
        Try to reconnect single server
        
        Notes: tryReconnect()
        
        Args:
            user_id: User ID
            server_name: Server name
            force_new: Whether to force new connection
            
        Returns:
            bool: Whether reconnection was successful
        """
        log_prefix = f"[tryReconnectOAuthMCPServer][User: {user_id}][{server_name}]"

        logger.info(f"{log_prefix} Attempting reconnection")

        # Mark as actively reconnecting
        self.tracker.set_active(user_id, server_name)

        try:
            # Get server configuration
            config = await self._get_server_config(user_id, server_name)
            if not config:
                logger.warn(f"{log_prefix} No configuration found")
                self._cleanup_on_failed_reconnect(user_id, server_name)
                return False

            # Get connection timeout from config
            connection_timeout = config.get("init_timeout", self.connection_timeout_ms)

            # Try to get user connection (this will use existing tokens and refresh if needed)
            connection = await self.mcp_service.connection_service.get_connection(
                user_id=user_id,
                server_name=server_name
            )

            # Check if connection is valid
            if connection and await self._is_connection_valid(connection):
                logger.info(f"{log_prefix} Successfully reconnected")
                self.clear_reconnection(user_id, server_name)
                return True
            else:
                logger.warn(f"{log_prefix} Failed to reconnect")
                self._cleanup_on_failed_reconnect(user_id, server_name)
                return False

        except Exception as error:
            logger.warn(f"{log_prefix} Failed to reconnect: {error}")
            self._cleanup_on_failed_reconnect(user_id, server_name)
            return False

    def clear_reconnection(self, user_id: str, server_name: str) -> None:
        """
        Clear reconnection status
        
        Notes: clearReconnection()
        """
        self.tracker.remove_failed(user_id, server_name)
        self.tracker.remove_active(user_id, server_name)
        logger.info(f"Cleared reconnection: user={user_id}, server={server_name}")

    async def can_reconnect(self, user_id: str, server_name: str) -> bool:
        """
        Check if server can be reconnected
        
        Notes: canReconnect()
        """
        # 1. If server is marked as failed, don't reconnect
        if self.tracker.is_failed(user_id, server_name):
            logger.info(f"Server marked as failed: "
                        f"user={user_id}, server={server_name}")
            return False

        # 2. If server is actively reconnecting, don't reconnect
        if self.tracker.is_active(user_id, server_name):
            logger.info(f"Server already reconnecting: "
                        f"user={user_id}, server={server_name}")
            return False

        # 3. If server is already connected, don't reconnect
        if await self._is_server_connected(user_id, server_name):
            logger.info(f"Server already connected: "
                        f"user={user_id}, server={server_name}")
            return False

        # 4. If server has no tokens, don't reconnect
        tokens = await self._get_user_tokens(user_id, server_name)
        if not tokens:
            logger.info(f"No tokens found: "
                        f"user={user_id}, server={server_name}")
            return False

        # 5. If token has expired, don't reconnect
        if self._is_token_expired(tokens):
            logger.info(f"Token expired: "
                        f"user={user_id}, server={server_name}")
            return False

        # 6. Can reconnect
        logger.info(f"Can reconnect: user={user_id}, server={server_name}")
        return True

    async def get_reconnection_status(
            self,
            user_id: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get reconnection status for user
        
        Python-specific: TypeScript doesn't have this method
        """
        status = {}

        # Get all OAuth servers
        oauth_servers = await self._get_oauth_servers()

        for server_name in oauth_servers:
            server_status = {
                "can_reconnect": await self.can_reconnect(user_id, server_name),
                "is_failed": self.tracker.is_failed(user_id, server_name),
                "is_active": self.tracker.is_active(user_id, server_name),
                "is_still_reconnecting": self.tracker.is_still_reconnecting(user_id, server_name),
                "is_connected": await self._is_server_connected(user_id, server_name),
                "has_token": bool(await self._get_user_tokens(user_id, server_name)),
            }

            status[server_name] = server_status

        return status

    # Private methods

    async def _get_servers_to_reconnect(self, user_id: str) -> Set[str]:
        """Get servers that need reconnection"""
        servers_to_reconnect = set()

        # Get all OAuth servers
        oauth_servers = await self._get_oauth_servers()

        for server_name in oauth_servers:
            if await self.can_reconnect(user_id, server_name):
                servers_to_reconnect.add(server_name)

        return servers_to_reconnect

    def _cleanup_on_failed_reconnect(self, user_id: str, server_name: str) -> None:
        """Cleanup on failed reconnection"""
        self.tracker.set_failed(user_id, server_name)
        self.tracker.remove_active(user_id, server_name)

        # Disconnect user connection
        try:
            asyncio.create_task(
                self.mcp_service.connection_service.disconnect_user_connection(
                    user_id, server_name
                )
            )
        except Exception as e:
            logger.error(f"Failed to disconnect user connection: {e}")

    async def _get_oauth_servers(self) -> List[str]:
        """Get all OAuth servers"""
        try:
            servers, _ = await server_service_v1.list_servers(
                page=1,
                per_page=1000,
                status="active"
            )

            oauth_servers = [
                server.serverName
                for server in servers
                if server.config.get("requires_oauth", False)
            ]
            return oauth_servers
        except Exception as e:
            logger.error(f"Failed to get OAuth servers: {e}")
            return []

    async def _get_server_config(
            self,
            user_id: str,
            server_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get server configuration"""
        try:
            server = await server_service_v1.get_server_by_name(server_name)
            if server:
                return server.config
            return None

        except Exception as e:
            logger.error(f"Failed to get server config: "
                         f"user={user_id}, server={server_name}, error={e}")
            return None

    async def _is_server_connected(self, user_id: str, server_name: str) -> bool:
        """Check if server is connected"""
        try:
            connection = await self.mcp_service.connection_service.get_connection(
                user_id, server_name
            )
            if not connection:
                return False
            return await self._is_connection_valid(connection)

        except Exception as e:
            logger.error(f"Failed to check connection status: {e}")
            return False

    async def _is_connection_valid(self, connection: Any) -> bool:
        """Check if connection is valid"""
        try:
            return connection.connection_state == ConnectionState.CONNECTED
        except Exception as e:
            logger.info(f"_is_connection_valid: {e}")
            return False

    async def _get_user_tokens(
            self,
            user_id: str,
            server_name: str
    ) -> Optional[OAuthTokens]:
        """Get user tokens"""
        try:
            tokens = await self.oauth_service.get_tokens(user_id, server_name)
            return tokens
        except Exception as e:
            logger.error(f"Failed to get user tokens: "
                         f"user={user_id}, server={server_name}, error={e}")
            return None

    def _is_token_expired(self, tokens: OAuthTokens) -> bool:
        """Check if token is expired"""
        if not tokens.expires_at:
            return False

        # Add buffer time to avoid edge cases
        current_time = time.time()
        return tokens.expires_at < current_time

    def __str__(self) -> str:
        """String representation"""
        return f"OAuthReconnectionManager(timeout={self.connection_timeout_ms}ms)"


_reconnection_manager_instance: Optional = None


def get_reconnection_manager(
        mcp_service: Any = None,
        oauth_service: Any = None
) -> OAuthReconnectionManager:
    """
    Get reconnection manager instance
    
    Note: This is a simplified singleton pattern for compatibility
    In production, consider using dependency injection
    """
    global _reconnection_manager_instance

    if _reconnection_manager_instance is None:
        if mcp_service is None or oauth_service is None:
            raise RuntimeError(
                "OAuthReconnectionManager not initialized. "
                "Call with mcp_service and oauth_service first."
            )
        _reconnection_manager_instance = OAuthReconnectionManager(
            mcp_service=mcp_service,
            oauth_service=oauth_service
        )
        logger.info("Initialized global OAuthReconnectionManager singleton")

    return _reconnection_manager_instance
