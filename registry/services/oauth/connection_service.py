import asyncio
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

from registry.schemas.enums import ConnectionState
from registry.services.server_service_v1 import server_service_v1
from registry.utils.log import logger


@dataclass
class MCPConnection:
    """MCP connection"""
    server_name: str
    connection_state: ConnectionState
    last_activity: float = field(default_factory=time.time)
    error_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    
    def is_stale(self, server_updated_at: Optional[float] = None) -> bool:
        """
        Check if connection is stale
        Notes: TypeScript: connection.isStale(config.updatedAt)
        """
        # If server config was updated after connection was created, connection is stale
        if server_updated_at:
            connection_created_at = self.details.get("created_at", self.last_activity)
            if server_updated_at > connection_created_at:
                return True
        
        # Connection is stale if it hasn't been active recently (default 1 hour)
        max_idle_time = 3600  # 1 hour in seconds
        current_time = time.time()
        if current_time - self.last_activity > max_idle_time:
            return True
        return False


class MCPConnectionService:
    """MCP connection service"""

    def __init__(self):
        self.app_connections: Dict[str, MCPConnection] = {}
        self.user_connections: Dict[str, Dict[str, MCPConnection]] = {}  # user_id -> {server_name -> connection}
        self._lock = asyncio.Lock()
        self._max_error_count = 3  # Maximum error count

    async def initialize_app_connections(self) -> None:
        """
        Initialize application-level connections
        """
        async with self._lock:
            try:
                servers, total = await server_service_v1.list_servers(
                    page=1,
                    per_page=1000,
                    status="active"
                )
                logger.info(f"Found {total} active servers in MongoDB")
                
                # 为不需要 OAuth 的服务器创建应用级连接
                for server in servers:
                    # 检查服务器是否需要 OAuth
                    if not server.config.requiresOAuth:
                        self.app_connections[server.serverName] = MCPConnection(
                            server_name=server.serverName,
                            connection_state=ConnectionState.CONNECTED,
                            details={
                                "type": "app_connection",
                                "server_id": str(server.id),
                                "url": server.url,
                                "config": server.config,
                                "created_at": time.time(),
                                "last_health_check": time.time()
                            }
                        )
                        logger.debug(f"Created app connection for non-OAuth server: {server.serverName}")
                    else:
                        logger.debug(f"Skipped OAuth server: {server.serverName}")
                
                logger.info(f"Initialized {len(self.app_connections)} app-level connections from MongoDB")
                
            except Exception as e:
                logger.error(f"Failed to initialize app connections: {e}", exc_info=True)

    def get_user_connections(self, user_id: str) -> Dict[str, MCPConnection]:
        """Get user connections"""
        return self.user_connections.get(user_id, {})

    async def get_connection(
            self,
            user_id: str,
            server_name: str
    ) -> Optional[MCPConnection]:
        """Get connection (application-level or user-level)"""
        # First check application-level connections
        if server_name in self.app_connections:
            return self.app_connections[server_name]

        # Then check user-level connections
        user_conns = self.get_user_connections(user_id)
        if server_name in user_conns:
            return user_conns[server_name]

        return None

    async def update_connection_state(
            self,
            user_id: str,
            server_name: str,
            state: ConnectionState,
            details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update connection state"""
        async with self._lock:
            connection = await self.get_connection(user_id, server_name)
            if connection:
                connection.connection_state = state
                connection.last_activity = time.time()
                if details:
                    connection.details.update(details)

                if state == ConnectionState.ERROR:
                    connection.error_count += 1

                    # If error count exceeds threshold, mark as disconnected
                    if connection.error_count >= self._max_error_count:
                        connection.connection_state = ConnectionState.DISCONNECTED
                        logger.warning(
                            f"Connection {server_name} for user {user_id} "
                            f"disconnected due to {connection.error_count} errors"
                        )
                elif state == ConnectionState.CONNECTED:
                    connection.error_count = 0

    async def create_user_connection(
            self,
            user_id: str,
            server_name: str,
            initial_state: ConnectionState = ConnectionState.CONNECTING,
            details: Optional[Dict[str, Any]] = None
    ) -> MCPConnection:
        """Create user connection"""
        async with self._lock:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = {}

            connection = MCPConnection(
                server_name=server_name,
                connection_state=initial_state,
                details=details or {}
            )
            self.user_connections[user_id][server_name] = connection
            logger.info(f"Created user connection: {user_id}/{server_name}")
            return connection

    async def disconnect_user_connection(self, user_id: str, server_name: str) -> bool:
        """Disconnect user connection"""
        async with self._lock:
            if user_id in self.user_connections and server_name in self.user_connections[user_id]:
                del self.user_connections[user_id][server_name]
                logger.info(f"Disconnected user connection: {user_id}/{server_name}")

                # If user has no other connections, cleanup user entry
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]

                return True
            return False

    async def disconnect_all_user_connections(self, user_id: str) -> int:
        """Disconnect all user connections"""
        async with self._lock:
            if user_id in self.user_connections:
                count = len(self.user_connections[user_id])
                del self.user_connections[user_id]
                logger.info(f"Disconnected all {count} connections for user: {user_id}")
                return count
            return 0

    async def cleanup_stale_connections(self, max_age_seconds: int = 3600) -> int:
        """Cleanup stale connections"""
        async with self._lock:
            cleaned_count = 0
            current_time = time.time()

            # Cleanup user connections
            for user_id in list(self.user_connections.keys()):
                for server_name in list(self.user_connections[user_id].keys()):
                    connection = self.user_connections[user_id][server_name]

                    # Check if connection is stale
                    if current_time - connection.last_activity > max_age_seconds:
                        del self.user_connections[user_id][server_name]
                        cleaned_count += 1
                        logger.debug(f"Cleaned stale connection: {user_id}/{server_name}")

                # If user has no connections, cleanup user entry
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]

            logger.info(f"Cleaned {cleaned_count} stale connections")
            return cleaned_count

    async def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        async with self._lock:
            total_app_connections = len(self.app_connections)
            total_user_connections = sum(len(conns) for conns in self.user_connections.values())
            total_users = len(self.user_connections)

            # Count connection statuses
            status_counts = {
                "connected": 0,
                "disconnected": 0,
                "connecting": 0,
                "error": 0,
                "unknown": 0
            }

            # Count application connection statuses
            for connection in self.app_connections.values():
                status = connection.connection_state.value
                if status in status_counts:
                    status_counts[status] += 1

            # Count user connection statuses
            for user_conns in self.user_connections.values():
                for connection in user_conns.values():
                    status = connection.connection_state.value
                    if status in status_counts:
                        status_counts[status] += 1

            return {
                "total_app_connections": total_app_connections,
                "total_user_connections": total_user_connections,
                "total_users": total_users,
                "status_counts": status_counts
            }


_connection_service_instance: Optional[MCPConnectionService] = None


async def get_connection_service() -> MCPConnectionService:
    """Get connection service instance"""
    global _connection_service_instance
    if _connection_service_instance is None:
        _connection_service_instance = MCPConnectionService()
        await _connection_service_instance.initialize_app_connections()
    return _connection_service_instance
