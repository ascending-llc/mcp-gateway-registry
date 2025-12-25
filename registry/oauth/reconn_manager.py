import logging
import asyncio
from typing import Optional
from datetime import datetime
from registry.oauth.flow_manager import FlowStateManager
from registry.oauth.mcp_manager import MCPManager, TokenMethods, User
from registry.oauth.registry import MCPServersRegistry
from registry.oauth.tracker import OAuthReconnectionTracker

logger = logging.getLogger(__name__)

DEFAULT_CONNECTION_TIMEOUT_MS = 10_000  # ms


class OAuthReconnectionManager:
    """
    OAuth重连管理器

    Note: jarvis-api/packages/api/src/mcp/oauth/OAuthReconnectionManager.ts
    """

    _instance: Optional['OAuthReconnectionManager'] = None

    def __init__(
            self,
            flow_manager: FlowStateManager,
            token_methods: TokenMethods,
            mcp_servers_registry: MCPServersRegistry,
            reconnections: Optional[OAuthReconnectionTracker] = None
    ):
        self.flow_manager = flow_manager
        self.token_methods = token_methods
        self.mcp_servers_registry = mcp_servers_registry
        self.reconnections_tracker = reconnections or OAuthReconnectionTracker()
        self.mcp_manager: Optional[MCPManager] = None
        try:
            self.mcp_manager = MCPManager.get_instance()
            pass
        except Exception as e:
            logger.error(e)
            self.mcp_manager = None
            logger.warning("MCPManager not available during OAuthReconnectionManager initialization")

    @classmethod
    def get_instance(cls) -> 'OAuthReconnectionManager':
        """获取单例实例"""
        if cls._instance is None:
            raise RuntimeError("OAuthReconnectionManager not initialized")
        return cls._instance

    @classmethod
    async def create_instance(
            cls,
            flow_manager: 'FlowStateManager',
            token_methods: TokenMethods,
            mcp_servers_registry: MCPServersRegistry,
            reconnections: Optional[OAuthReconnectionTracker] = None
    ) -> 'OAuthReconnectionManager':
        """创建单例实例"""
        if cls._instance is not None:
            raise RuntimeError("OAuthReconnectionManager already initialized")

        manager = cls(flow_manager, token_methods, mcp_servers_registry, reconnections)
        cls._instance = manager
        return manager

    def is_reconnecting(self, user_id: str, server_name: str) -> bool:
        """检查是否正在重连"""
        self.reconnections_tracker.cleanup_if_timed_out(user_id, server_name)
        return self.reconnections_tracker.is_still_reconnecting(user_id, server_name)

    async def reconnect_servers(self, user_id: str) -> None:
        """重连服务器"""
        # 检查MCPManager是否可用
        if self.mcp_manager is None:
            logger.warning(
                '[OAuthReconnectionManager] MCPManager not available, skipping OAuth MCP server reconnection'
            )
            return

        # 1. derive the servers to reconnect
        servers_to_reconnect = []
        oauth_servers = await self.mcp_servers_registry.get_oauth_servers()

        for server_name in oauth_servers:
            can_reconnect = await self._can_reconnect(user_id, server_name)
            if can_reconnect:
                servers_to_reconnect.append(server_name)

        # 2. mark the servers as reconnecting
        for server_name in servers_to_reconnect:
            self.reconnections_tracker.set_active(user_id, server_name)

        # 3. attempt to reconnect the servers
        tasks = []
        for server_name in servers_to_reconnect:
            task = asyncio.create_task(self._try_reconnect(user_id, server_name))
            tasks.append(task)

        # 不等待所有任务完成，让它们在后台运行
        if tasks:
            logger.info(f"Started {len(tasks)} reconnection tasks for user {user_id}")

    def clear_reconnection(self, user_id: str, server_name: str) -> None:
        """清除重连状态"""
        self.reconnections_tracker.remove_failed(user_id, server_name)
        self.reconnections_tracker.remove_active(user_id, server_name)

    async def _try_reconnect(self, user_id: str, server_name: str) -> None:
        """尝试重连"""
        if self.mcp_manager is None:
            return

        log_prefix = f"[tryReconnectOAuthMCPServer][User: {user_id}][{server_name}]"
        logger.info(f"{log_prefix} Attempting reconnection")

        config = await self.mcp_servers_registry.get_server_config(server_name, user_id)

        def cleanup_on_failed_reconnect():
            """失败重连时的清理"""
            self.reconnections_tracker.set_failed(user_id, server_name)
            self.reconnections_tracker.remove_active(user_id, server_name)
            if self.mcp_manager:
                asyncio.create_task(
                    self.mcp_manager.disconnect_user_connection(user_id, server_name)
                )

        try:
            # attempt to get connection (this will use existing tokens and refresh if needed)
            connection_params = {
                'server_name': server_name,
                'user': User(id=user_id),
                'flow_manager': self.flow_manager,
                'token_methods': self.token_methods,
                # don't force new connection, let it reuse existing or create new as needed
                'force_new': False,
                # set a reasonable timeout for reconnection attempts
                'connection_timeout': getattr(config, 'init_timeout',
                                              DEFAULT_CONNECTION_TIMEOUT_MS) if config else DEFAULT_CONNECTION_TIMEOUT_MS,
                # don't trigger OAuth flow during reconnection
                'return_on_oauth': True,
            }

            connection = await self.mcp_manager.get_user_connection(**connection_params)

            if connection and await connection.is_connected():
                logger.info(f"{log_prefix} Successfully reconnected")
                self.clear_reconnection(user_id, server_name)
            else:
                logger.warning(f"{log_prefix} Failed to reconnect")
                if connection:
                    await connection.close()
                cleanup_on_failed_reconnect()

        except Exception as error:
            logger.warning(f"{log_prefix} Failed to reconnect: {error}")
            cleanup_on_failed_reconnect()

    async def _can_reconnect(self, user_id: str, server_name: str) -> bool:
        """检查是否可以重连"""
        if self.mcp_manager is None:
            return False

        #  if the server has failed reconnection, don't attempt to reconnect
        if self.reconnections_tracker.is_failed(user_id, server_name):
            return False

        if self.reconnections_tracker.is_active(user_id, server_name):
            return False

        # if the server is already connected, don't attempt to reconnect
        existing_connections = self.mcp_manager.get_user_connections(user_id)
        if existing_connections and server_name in existing_connections:
            connection = existing_connections.get(server_name)
            if connection and await connection.is_connected():
                return False

        # if the server has no tokens for the user, don't attempt to reconnect
        if self.token_methods.find_token is None:
            return False

        access_token = await self.token_methods.find_token({
            'user_id': user_id,
            'type': 'mcp_oauth',
            'identifier': f'mcp:{server_name}',
        })
        if access_token is None:
            return False

        # if the token has expired, don't attempt to reconnect
        now = datetime.now()
        if hasattr(access_token, 'expires_at') and access_token.expires_at:
            expires_at = access_token.expires_at
            if isinstance(expires_at, str):
                try:
                    expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # 如果无法解析，假设未过期
                    logger.info(f"decode expires_at: {expires_at}")

            if isinstance(expires_at, datetime) and expires_at < now:
                return False

        # …otherwise, we're good to go with the reconnect attempt
        return True
