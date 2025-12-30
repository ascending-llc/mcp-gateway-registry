import asyncio
import time
from typing import Dict, Optional, Any, Tuple, Union
from auth.oauth.oauth_service import get_oauth_service
from services.oauth.service import get_config_service
from schemas.enums import ConnectionState
from services.oauth.connection_service import get_connection_service

from registry.utils.log import logger


class MCPService:
    """MCP main service"""

    def __init__(self):
        self._config_service = None
        self._connection_service = None
        self._oauth_service = None
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize all services"""
        async with self._lock:
            if self._initialized:
                return
            try:
                self._config_service = await get_config_service()
                self._connection_service = await get_connection_service()
                self._oauth_service = await get_oauth_service()
                self._initialized = True
                logger.info("MCP service initialized successfully")

            except Exception as e:
                logger.error(f"Failed to initialize MCP service: {e}", exc_info=True)
                raise

    # ==================== Configuration Service Methods ====================

    async def get_server_config(self, server_name: str) -> Optional[Any]:
        """Get server configuration"""
        await self.ensure_initialized()
        if self._config_service:
            return self._config_service.get_server_config(server_name)
        return None

    async def get_all_configs(self) -> Dict[str, Any]:
        """Get all server configurations"""
        await self.ensure_initialized()
        if self._config_service:
            return self._config_service.get_all_configs()
        return {}

    async def is_oauth_server(self, server_name: str) -> bool:
        """Check if server requires OAuth"""
        await self.ensure_initialized()
        if self._config_service:
            return self._config_service.is_oauth_server(server_name)
        return False

    async def validate_server_config(self, server_name: str) -> Tuple[bool, Optional[str]]:
        """Validate server configuration"""
        await self.ensure_initialized()
        if self._config_service:
            return self._config_service.validate_config(server_name)
        return False, "Config service not initialized"

    async def reload_configs(self) -> bool:
        """Reload configurations"""
        await self.ensure_initialized()
        if self._config_service:
            return await self._config_service.reload_configs()
        return False

    # ==================== Connection Service Methods ====================

    async def get_connection_state(
            self,
            user_id: str,
            server_name: str
    ) -> Optional[str]:
        """Get connection state"""
        await self.ensure_initialized()
        if self._connection_service:
            connection = await self._connection_service.get_connection(user_id, server_name)
            return connection.connection_state.value if connection else None
        return None

    async def update_connection_state(
            self,
            user_id: str,
            server_name: str,
            state: str,
            details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update connection state"""
        await self.ensure_initialized()
        if not self._connection_service:
            return
        try:
            connection_state = ConnectionState(state)
        except ValueError:
            logger.error(f"Invalid connection state: {state}")
            return

        await self._connection_service.update_connection_state(
            user_id, server_name, connection_state, details
        )

    async def create_user_connection(
            self,
            user_id: str,
            server_name: str,
            initial_state: str = "connecting",
            details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create user connection"""
        await self.ensure_initialized()
        if not self._connection_service:
            return False
        try:
            connection_state = ConnectionState(initial_state)
        except ValueError:
            logger.error(f"Invalid initial state: {initial_state}")
            return False

        connection = await self._connection_service.create_user_connection(
            user_id, server_name, connection_state, details
        )
        return connection is not None

    async def disconnect_user_connection(self, user_id: str, server_name: str) -> bool:
        """Disconnect user connection"""
        await self.ensure_initialized()
        if self._connection_service:
            return await self._connection_service.disconnect_user_connection(user_id, server_name)
        return False

    async def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        await self.ensure_initialized()
        if self._connection_service:
            return await self._connection_service.get_connection_stats()
        return {}

    # ==================== OAuth Service Methods ====================

    async def initiate_oauth_flow(
            self,
            user_id: str,
            server_name: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Initialize OAuth flow"""
        await self.ensure_initialized()
        if self._oauth_service:
            return await self._oauth_service.initiate_oauth_flow(user_id, server_name)
        return None, None, "OAuth service not initialized"

    async def complete_oauth_flow(
            self,
            flow_id: str,
            authorization_code: str,
            state: str
    ) -> Tuple[bool, Optional[str]]:
        """Complete OAuth flow"""
        await self.ensure_initialized()
        if self._oauth_service:
            return await self._oauth_service.complete_oauth_flow(flow_id, authorization_code, state)
        return False, "OAuth service not initialized"

    async def get_oauth_tokens(self, user_id: str, server_name: str) -> Optional[Any]:
        """Get OAuth tokens"""
        await self.ensure_initialized()
        if self._oauth_service:
            return await self._oauth_service.get_tokens(user_id, server_name)
        return None

    async def get_oauth_tokens_by_flow_id(self, flow_id: str) -> Optional[Any]:
        """Get OAuth tokens by flow ID"""
        await self.ensure_initialized()
        if self._oauth_service:
            return await self._oauth_service.get_tokens_by_flow_id(flow_id)
        return None

    async def get_oauth_flow_status(self, flow_id: str) -> Dict[str, Any]:
        """Get OAuth flow status"""
        await self.ensure_initialized()
        if self._oauth_service:
            return await self._oauth_service.get_flow_status(flow_id)
        return {"status": "error", "error": "OAuth service not initialized"}

    async def cancel_oauth_flow(self, user_id: str, server_name: str) -> Tuple[bool, Optional[str]]:
        """Cancel OAuth flow"""
        await self.ensure_initialized()
        if self._oauth_service:
            return await self._oauth_service.cancel_oauth_flow(user_id, server_name)
        return False, "OAuth service not initialized"

    async def cleanup_user_oauth_tokens(self, user_id: str, server_name: str) -> bool:
        """Cleanup user OAuth tokens"""
        await self.ensure_initialized()
        if self._oauth_service:
            return await self._oauth_service.cleanup_user_tokens(user_id, server_name)
        return False

    async def refresh_oauth_tokens(self, user_id: str, server_name: str) -> Tuple[bool, Optional[str]]:
        """Refresh OAuth tokens"""
        await self.ensure_initialized()
        if self._oauth_service:
            return await self._oauth_service.refresh_tokens(user_id, server_name)
        return False, "OAuth service not initialized"

    # ==================== Combined Methods ====================

    async def connect_to_server(
            self,
            user_id: str,
            server_name: str
    ) -> Tuple[bool, Optional[str]]:
        """Connect to MCP server"""
        await self.ensure_initialized()

        try:
            # Validate server configuration
            is_valid, error = await self.validate_server_config(server_name)
            if not is_valid:
                return False, error

            # Check if OAuth is required
            if await self.is_oauth_server(server_name):
                # Check if tokens already exist
                tokens = await self.get_oauth_tokens(user_id, server_name)
                if tokens:
                    # Tokens exist, create connection
                    await self.create_user_connection(
                        user_id, server_name, "connected",
                        {"oauth_tokens": True})
                    return True, None
                else:
                    # OAuth authorization required
                    flow_id, auth_url, error = await self.initiate_oauth_flow(user_id, server_name)
                    if error:
                        return False, error
                    return False, f"OAuth required: {auth_url}"
            else:
                # Non-OAuth server, create connection directly
                await self.create_user_connection(user_id, server_name, "connected")
                return True, None

        except Exception as e:
            logger.error(f"Failed to connect to server: {e}", exc_info=True)
            return False, str(e)

    async def disconnect_from_server(self, user_id: str, server_name: str) -> bool:
        """Disconnect from MCP server"""
        await self.ensure_initialized()

        try:
            # Disconnect
            disconnected = await self.disconnect_user_connection(user_id, server_name)

            # If OAuth server, cleanup tokens
            if await self.is_oauth_server(server_name):
                await self.cleanup_user_oauth_tokens(user_id, server_name)
            return disconnected

        except Exception as e:
            logger.error(f"Failed to disconnect from server: {e}", exc_info=True)
            return False

    async def get_server_status(
            self,
            user_id: str,
            server_name: str
    ) -> Dict[str, Any]:
        """Get server status"""
        await self.ensure_initialized()

        try:
            # Get configuration
            config = await self.get_server_config(server_name)
            if not config:
                return {"error": f"Server '{server_name}' not found"}

            # Get connection state
            connection_state = await self.get_connection_state(user_id, server_name)

            # Get OAuth status
            oauth_status = None
            if await self.is_oauth_server(server_name):
                tokens = await self.get_oauth_tokens(user_id, server_name)
                oauth_status = {
                    "has_tokens": tokens is not None,
                    "tokens_valid": tokens is not None and (
                            not tokens.expires_at or tokens.expires_at > time.time()
                    )
                }

            return {
                "server_name": server_name,
                "config": {
                    "type": config.type,
                    "requires_oauth": config.requires_oauth,
                    "description": config.description
                },
                "connection_state": connection_state or "disconnected",
                "oauth_status": oauth_status,
                "timestamp": time.time()
            }

        except Exception as e:
            logger.error(f"Failed to get server status: {e}", exc_info=True)
            return {"error": str(e)}

    async def cleanup_resources(self) -> Dict[str, Union[int, str]]:
        """Cleanup all resources"""
        await self.ensure_initialized()

        try:
            result = {}

            # Cleanup stale connections
            if self._connection_service:
                stale_connections = await self._connection_service.cleanup_stale_connections()
                result["stale_connections"] = stale_connections

            # Cleanup expired OAuth flows
            if self._oauth_service:
                expired_flows = await self._oauth_service.cleanup_expired_flows()
                result["expired_flows"] = expired_flows

            # Cleanup expired tokens
            if self._oauth_service:
                expired_tokens = await self._oauth_service.cleanup_expired_tokens()
                result["expired_tokens"] = expired_tokens

            return result

        except Exception as e:
            logger.error(f"Failed to cleanup resources: {e}", exc_info=True)
            return {"error": str(e)}

    # ==================== Helper Methods ====================

    async def ensure_initialized(self) -> None:
        """Ensure services are initialized"""
        if not self._initialized:
            await self.initialize()


_mcp_service_instance: Optional[MCPService] = None


async def get_mcp_service() -> MCPService:
    """Get MCP service instance"""
    global _mcp_service_instance
    if _mcp_service_instance is None:
        _mcp_service_instance = MCPService()
        await _mcp_service_instance.initialize()
    return _mcp_service_instance
