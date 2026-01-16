import asyncio
import time
from typing import Dict, Any, Optional, List, Set

from packages.models import MCPServerDocument
from registry.utils.log import logger
from registry.models.oauth_models import OAuthTokens
from .tracker import OAuthReconnectionTracker
from registry.schemas.enums import ConnectionState
from registry.services.server_service_v1 import server_service_v1
from registry.services.oauth.reconnection_lock_service import get_reconnection_lock_service


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

    async def reconnect_servers(
            self,
            user_id: str,
            servers: Optional[list[MCPServerDocument]] = None,
            connection_status: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, bool]:
        """
        Reconnect OAuth servers for user
        
        Args:
            user_id: User ID
            servers: Optional servers list (recommended from list_servers)
            connection_status: Optional connection status dict
        
        Returns:
            Dict[str, bool]: server_name -> reconnection success
        """
        logger.info(f"Starting reconnection for user: {user_id}")

        # Get servers to reconnect
        servers_to_reconnect = await self._get_servers_to_reconnect(
            user_id, servers, connection_status
        )

        if not servers_to_reconnect:
            logger.info(f"No servers to reconnect for user: {user_id}")
            return {}

        logger.info(f"Found {len(servers_to_reconnect)} servers to reconnect: "
                    f"{list(servers_to_reconnect)}")

        # Mark as actively reconnecting
        for server_name in servers_to_reconnect:
            self.tracker.set_active(user_id, server_name)

        # Try to reconnect each server with Redis lock
        results = {}
        for server_name in servers_to_reconnect:
            results[server_name] = await self._try_reconnect_with_lock(user_id, server_name)

        successful = sum(1 for r in results.values() if r)
        failed = len(results) - successful
        logger.info(f"Reconnection completed: {successful} succeeded, {failed} failed")

        return results

    async def try_reconnect_server(self, user_id: str, server_name: str) -> bool:
        """
        Try to reconnect single server
        
        Validates and refreshes OAuth tokens, then updates connection state.
        """
        log_prefix = f"[Reconnect][{user_id}][{server_name}]"
        logger.info(f"{log_prefix} Starting")

        self.tracker.set_active(user_id, server_name)

        try:
            # Validate server config
            config = await self._get_server_config(user_id, server_name)
            if not config:
                logger.warn(f"{log_prefix} No config found")
                self._cleanup_on_failed_reconnect(user_id, server_name)
                return False

            # Ensure tokens are valid (refresh if needed)
            tokens = await self._ensure_valid_tokens(user_id, server_name, log_prefix)
            if not tokens:
                self._cleanup_on_failed_reconnect(user_id, server_name)
                return False

            # Update connection state
            await self._update_connection_state(user_id, server_name)

            logger.info(f"{log_prefix} Success")
            self.clear_reconnection(user_id, server_name)
            return True

        except Exception as error:
            logger.warn(f"{log_prefix} Failed: {error}", exc_info=True)
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
        """Check if server can be reconnected"""
        # Check tracker state
        if self.tracker.is_failed(user_id, server_name):
            return False
        if self.tracker.is_active(user_id, server_name):
            return False

        # Check connection state
        if await self._is_server_connected(user_id, server_name):
            return False

        # Check tokens exist (will refresh in try_reconnect if expired)
        tokens = await self._get_user_tokens(user_id, server_name)
        return tokens is not None

    @DeprecationWarning
    async def get_reconnection_status(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """Get reconnection status for all OAuth servers"""
        oauth_servers = await self._get_oauth_servers()

        status = {}
        for server_name in oauth_servers:
            status[server_name] = {
                "can_reconnect": await self.can_reconnect(user_id, server_name),
                "is_failed": self.tracker.is_failed(user_id, server_name),
                "is_active": self.tracker.is_active(user_id, server_name),
                "is_still_reconnecting": self.tracker.is_still_reconnecting(user_id, server_name),
                "is_connected": await self._is_server_connected(user_id, server_name),
                "has_token": bool(await self._get_user_tokens(user_id, server_name)),
            }

        return status

    # Private methods

    async def _try_reconnect_with_lock(self, user_id: str, server_name: str) -> bool:
        """Try reconnect with Redis lock"""
        lock_service = get_reconnection_lock_service()

        # Check cooldown
        if not lock_service.can_attempt_reconnection(user_id, server_name):
            logger.debug(f"Skip {server_name}: locked or in cooldown")
            return False

        # Acquire lock
        if not lock_service.acquire_lock(user_id, server_name):
            logger.debug(f"Skip {server_name}: failed to acquire lock")
            return False

        try:
            lock_service.set_reconnection_status(user_id, server_name, "in_progress", ttl=60)

            success = await self.try_reconnect_server(user_id, server_name)

            # Update Redis status
            status = "success" if success else "failed"
            ttl = 300 if success else 60
            lock_service.set_reconnection_status(user_id, server_name, status, ttl=ttl)

            return success

        except Exception as e:
            logger.error(f"Error reconnecting {server_name}: {e}")
            lock_service.set_reconnection_status(
                user_id, server_name, "failed", details={"error": str(e)}, ttl=60
            )
            return False

        finally:
            lock_service.release_lock(user_id, server_name)

    async def _ensure_valid_tokens(
            self, user_id: str, server_name: str, log_prefix: str
    ) -> Optional[OAuthTokens]:
        """
        Ensure tokens are valid, refresh if expired
        
        Returns:
            Valid OAuthTokens or None if cannot be validated
        """
        # Get tokens
        tokens = await self._get_user_tokens(user_id, server_name)
        if not tokens:
            logger.warn(f"{log_prefix} No tokens found")
            return None

        # Check if expired
        if not self._is_token_expired(tokens):
            logger.debug(f"{log_prefix} Token still valid")
            return tokens

        # Token expired, try to refresh
        logger.info(f"{log_prefix} Token expired, refreshing...")

        if not tokens.refresh_token:
            logger.warn(f"{log_prefix} No refresh token, cannot refresh")
            return None

        # Refresh tokens
        success, error = await self.oauth_service.refresh_tokens(user_id, server_name)
        if not success:
            logger.warn(f"{log_prefix} Refresh failed: {error}")
            return None

        logger.info(f"{log_prefix} Tokens refreshed")

        # Get refreshed tokens
        new_tokens = await self._get_user_tokens(user_id, server_name)
        if not new_tokens or self._is_token_expired(new_tokens):
            logger.warn(f"{log_prefix} Refreshed token invalid")
            return None

        logger.info(f"{log_prefix} New token valid (expires: {new_tokens.expires_at})")
        return new_tokens

    async def _update_connection_state(self, user_id: str, server_name: str) -> None:
        """Update connection state to CONNECTED"""
        connection = await self.mcp_service.connection_service.get_connection(
            user_id, server_name
        )

        details = {"reconnected": True, "reconnected_at": time.time()}

        if connection:
            await self.mcp_service.connection_service.update_connection_state(
                user_id, server_name, ConnectionState.CONNECTED, details
            )
        else:
            await self.mcp_service.connection_service.create_user_connection(
                user_id, server_name, ConnectionState.CONNECTED, details
            )

    def _should_skip_server(
            self,
            server: Any,
            connection_status: Optional[Dict[str, Dict[str, Any]]]
    ) -> Optional[str]:
        """
        Check if server should be skipped
        
        Returns:
            Reason string if should skip, None otherwise
        """
        # Check OAuth requirement
        if not server.config.get("requiresOAuth", False):
            return "not OAuth server"

        # Check enabled status
        if not server.enabled:
            return "server disabled"

        # Check connection state
        if connection_status:
            status = connection_status.get(server.serverName)
            if status:
                conn_state = status.get("connection_state")
                skip_states = [
                    ConnectionState.CONNECTED.value,
                    ConnectionState.CONNECTING.value,
                    ConnectionState.PENDING_OAUTH.value
                ]
                if conn_state in skip_states:
                    return f"already {conn_state}"

        return None

    async def _get_servers_to_reconnect(
            self,
            user_id: str,
            servers: Optional[list[MCPServerDocument]] = None,
            connection_status: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Set[str]:
        """Get servers that need reconnection"""
        servers_to_reconnect = set()

        if servers:
            logger.debug(f"Filtering {len(servers)} provided servers")

            for server in servers:
                skip_reason = self._should_skip_server(server, connection_status)
                if skip_reason:
                    logger.debug(f"Skip {server.serverName}: {skip_reason}")
                    continue

                if await self.can_reconnect(user_id, server.serverName):
                    servers_to_reconnect.add(server.serverName)
        else:
            # Fallback: query all OAuth servers
            logger.debug("No servers provided, querying OAuth servers")
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

    @DeprecationWarning
    async def _get_oauth_servers(self, total=10000) -> List[str]:
        """Get all active OAuth servers"""
        try:
            servers, _ = await server_service_v1.list_servers(
                page=1, per_page=1000, status="active"
            )
            return [
                s.serverName for s in servers
                if s.config.get("requires_oauth", False)
            ]
        except Exception as e:
            logger.error(f"Failed to get OAuth servers: {e}")
            return []

    async def _get_server_config(self, user_id: str, server_name: str) -> Optional[Dict[str, Any]]:
        """Get server configuration"""
        try:
            server = await server_service_v1.get_server_by_name(server_name)
            return server.config if server else None
        except Exception as e:
            logger.error(f"Failed to get config for {server_name}: {e}")
            return None

    async def _is_server_connected(self, user_id: str, server_name: str) -> bool:
        """Check if server is connected"""
        try:
            connection = await self.mcp_service.connection_service.get_connection(
                user_id, server_name
            )
            return connection and connection.connection_state == ConnectionState.CONNECTED
        except Exception as e:
            logger.error(f"Failed to check connection: {e}")
            return False

    async def _get_user_tokens(self, user_id: str, server_name: str) -> Optional[OAuthTokens]:
        """Get user OAuth tokens"""
        try:
            return await self.oauth_service.get_tokens(user_id, server_name)
        except Exception as e:
            logger.error(f"Failed to get tokens for {user_id}/{server_name}: {e}")
            return None

    def _is_token_expired(self, tokens: OAuthTokens) -> bool:
        """Check if token is expired (with 5 min buffer)"""
        if not tokens.expires_at:
            return False

        buffer_seconds = 300  # 5 minutes
        return tokens.expires_at < (time.time() + buffer_seconds)

    def __str__(self) -> str:
        return f"OAuthReconnectionManager(timeout={self.connection_timeout_ms}ms)"


_reconnection_manager_instance: Optional[OAuthReconnectionManager] = None


def get_reconnection_manager(
        mcp_service: Any = None,
        oauth_service: Any = None
) -> OAuthReconnectionManager:
    """Get or create reconnection manager instance"""
    global _reconnection_manager_instance

    if _reconnection_manager_instance is None:
        if not mcp_service or not oauth_service:
            raise RuntimeError("OAuthReconnectionManager not initialized")

        _reconnection_manager_instance = OAuthReconnectionManager(
            mcp_service=mcp_service,
            oauth_service=oauth_service
        )
        logger.info("Initialized OAuthReconnectionManager")

    return _reconnection_manager_instance
