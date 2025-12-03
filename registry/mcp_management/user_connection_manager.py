"""
User Connection Manager for MCP connections.

Base class for managing user-specific MCP connections with lifecycle management.
Based on jarvis-api TypeScript implementation, adapted to Python.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Set
from mcp_management.connections_repository import ConnectionsRepository
from mcp_management.mcp_connection import MCPConnection

logger = logging.getLogger(__name__)


class UserConnectionManager:
    """
    Abstract base class for managing user-specific MCP connections.
    
    Manages connections per user (user_id -> server_name -> MCPConnection).
    Also manages connection idle timeout and cleanup.
    """
    
    def __init__(self):
        """Initialize the user connection manager."""
        # Connections shared by all users (app-level connections)
        self.app_connections: Optional[ConnectionsRepository] = None
        
        # Connections per user: user_id -> server_name -> MCPConnection
        self.user_connections: Dict[str, Dict[str, MCPConnection]] = {}
        
        # Last activity timestamp per user (not per server)
        self.user_last_activity: Dict[str, float] = {}
        
        # User connection idle timeout (15 minutes in milliseconds)
        self.USER_CONNECTION_IDLE_TIMEOUT = 15 * 60 * 1000  # 15 minutes
        
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        
        logger.debug("Initialized UserConnectionManager")
    
    def _get_log_prefix(self, user_id: Optional[str] = None) -> str:
        """Helper to generate consistent log prefixes."""
        user_part = f"[User: {user_id}]" if user_id else ""
        return f"[MCP]{user_part}"
    
    def update_user_last_activity(self, user_id: str) -> None:
        """Update the last activity timestamp for a user."""
        current_time = asyncio.get_event_loop().time() * 1000  # Convert to milliseconds
        self.user_last_activity[user_id] = current_time
        logger.debug(
            f"{self._get_log_prefix(user_id)} Updated last activity timestamp: {current_time}"
        )
    
    async def get_user_connection(
        self,
        server_name: str,
        user_id: str,
        server_config: Dict[str, Any],
        force_new: bool = False,
        oauth_tokens: Optional[Dict[str, Any]] = None
    ) -> MCPConnection:
        """
        Get or create a connection for a specific user.
        
        Args:
            server_name: Name of the MCP server
            user_id: User ID for user-specific connections
            server_config: Server configuration dictionary
            force_new: Whether to force creation of a new connection
            oauth_tokens: Optional OAuth tokens for authenticated connections
            
        Returns:
            MCPConnection object for the user
        """
        if not user_id:
            raise ValueError("User ID is required for user-specific connections")
        
        # Check if this is an app-level server (should not have user-specific connections)
        if self.app_connections and await self.app_connections.has(server_name):
            raise ValueError(
                f"{self._get_log_prefix(user_id)} Trying to create user-specific connection "
                f"for app-level server '{server_name}'"
            )
        
        async with self._lock:
            # Get or create user's connection map
            if user_id not in self.user_connections:
                self.user_connections[user_id] = {}
            
            user_server_map = self.user_connections[user_id]
            connection = None if force_new else user_server_map.get(server_name)
            current_time = asyncio.get_event_loop().time() * 1000
            
            # Check if user is idle
            last_activity = self.user_last_activity.get(user_id)
            if last_activity and current_time - last_activity > self.USER_CONNECTION_IDLE_TIMEOUT:
                logger.info(
                    f"{self._get_log_prefix(user_id)} User idle for too long. "
                    "Disconnecting all connections."
                )
                # Disconnect all user connections
                try:
                    await self.disconnect_user_connections(user_id)
                except Exception as err:
                    logger.error(
                        f"{self._get_log_prefix(user_id)} Error disconnecting idle connections: {err}"
                    )
                connection = None  # Force creation of a new connection
            elif connection:
                # Check if existing connection is still connected
                if await connection.is_connected():
                    logger.debug(
                        f"{self._get_log_prefix(user_id)}[{server_name}] Reusing active connection"
                    )
                    self.update_user_last_activity(user_id)
                    return connection
                else:
                    # Connection exists but is not connected, remove stale entry
                    logger.warn(
                        f"{self._get_log_prefix(user_id)}[{server_name}] "
                        "Found existing but disconnected connection object. Cleaning up."
                    )
                    self._remove_user_connection(user_id, server_name)
                    connection = None
            
            # If no valid connection exists, create a new one
            if not connection:
                logger.info(
                    f"{self._get_log_prefix(user_id)}[{server_name}] Establishing new connection"
                )
            
            try:
                connection = MCPConnection(
                    server_name=server_name,
                    server_config=server_config,
                    user_id=user_id,
                    oauth_tokens=oauth_tokens
                )
                
                # Connect to the server
                await connection.connect()
                
                if not await connection.is_connected():
                    raise Exception("Failed to establish connection after initialization attempt.")
                
                # Store the connection
                user_server_map[server_name] = connection
                
                logger.info(
                    f"{self._get_log_prefix(user_id)}[{server_name}] Connection successfully established"
                )
                self.update_user_last_activity(user_id)
                return connection
                
            except Exception as error:
                logger.error(
                    f"{self._get_log_prefix(user_id)}[{server_name}] Failed to establish connection: {error}"
                )
                # Ensure cleanup on failure
                if connection:
                    try:
                        await connection.disconnect()
                    except Exception as disconnect_error:
                        logger.error(
                            f"{self._get_log_prefix(user_id)}[{server_name}] "
                            f"Error during cleanup after failed connection: {disconnect_error}"
                        )
                self._remove_user_connection(user_id, server_name)
                raise error
    
    def _remove_user_connection(self, user_id: str, server_name: str) -> None:
        """
        Remove a specific user connection entry (internal method).
        
        Args:
            user_id: User ID
            server_name: Server name
        """
        user_map = self.user_connections.get(user_id)
        if user_map:
            user_map.pop(server_name, None)
            if not user_map:  # If no more connections for this user
                self.user_connections.pop(user_id, None)
                # Only remove user activity timestamp if all connections are gone
                self.user_last_activity.pop(user_id, None)
        
        logger.debug(f"{self._get_log_prefix(user_id)}[{server_name}] Removed connection entry.")
    
    async def disconnect_user_connection(self, user_id: str, server_name: str) -> None:
        """
        Disconnect and remove a specific user connection.
        
        Args:
            user_id: User ID
            server_name: Server name
        """
        async with self._lock:
            user_map = self.user_connections.get(user_id)
            connection = user_map.get(server_name) if user_map else None
            if connection:
                logger.info(f"{self._get_log_prefix(user_id)}[{server_name}] Disconnecting...")
                try:
                    await connection.disconnect()
                except Exception as error:
                    logger.error(
                        f"{self._get_log_prefix(user_id)}[{server_name}] Error during disconnection: {error}"
                    )
                self._remove_user_connection(user_id, server_name)
    
    async def disconnect_user_connections(self, user_id: str) -> None:
        """
        Disconnect and remove all connections for a specific user.
        
        Args:
            user_id: User ID
        """
        async with self._lock:
            user_map = self.user_connections.get(user_id)
            if user_map:
                logger.info(f"{self._get_log_prefix(user_id)} Disconnecting all servers...")
                
                # Collect all disconnect tasks
                disconnect_tasks = []
                user_servers = list(user_map.keys())
                
                for server_name in user_servers:
                    disconnect_tasks.append(
                        self.disconnect_user_connection(user_id, server_name)
                    )
                
                # Wait for all disconnections to complete
                if disconnect_tasks:
                    results = await asyncio.gather(*disconnect_tasks, return_exceptions=True)
                    for server_name, result in zip(user_servers, results):
                        if isinstance(result, Exception):
                            logger.error(
                                f"{self._get_log_prefix(user_id)}[{server_name}] "
                                f"Error during disconnection: {result}"
                            )
                
                logger.info(f"{self._get_log_prefix(user_id)} All connections processed for disconnection.")
    
    def get_user_connections(self, user_id: str) -> Optional[Dict[str, MCPConnection]]:
        """
        Get all connections for a specific user.
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary of server_name -> MCPConnection, or None if user has no connections
        """
        return self.user_connections.get(user_id)
    
    async def check_idle_connections(self, current_user_id: Optional[str] = None) -> List[str]:
        """
        Check for and disconnect idle connections.
        
        Args:
            current_user_id: Optional current user ID to exclude from idle check
            
        Returns:
            List of user IDs that were disconnected due to idle timeout
        """
        disconnected_users = []
        current_time = asyncio.get_event_loop().time() * 1000  # milliseconds
        
        # Make a copy of user IDs to avoid modification during iteration
        user_ids = list(self.user_last_activity.keys())
        
        for user_id in user_ids:
            if current_user_id and current_user_id == user_id:
                continue
            
            last_activity = self.user_last_activity.get(user_id)
            if last_activity and current_time - last_activity > self.USER_CONNECTION_IDLE_TIMEOUT:
                logger.info(
                    f"{self._get_log_prefix(user_id)} User idle for too long. "
                    "Disconnecting all connections..."
                )
                # Disconnect all user connections asynchronously
                try:
                    await self.disconnect_user_connections(user_id)
                    disconnected_users.append(user_id)
                except Exception as err:
                    logger.error(
                        f"{self._get_log_prefix(user_id)} Error disconnecting idle connections: {err}"
                    )
        
        return disconnected_users
    
    async def get_all_user_connections(self) -> Dict[str, Dict[str, MCPConnection]]:
        """
        Get all user connections across all users.
        
        Returns:
            Dictionary of user_id -> server_name -> MCPConnection
        """
        async with self._lock:
            # Return a deep copy to avoid modification
            return {
                user_id: dict(server_map)
                for user_id, server_map in self.user_connections.items()
            }
    
    async def get_connection_states_for_user(self, user_id: str) -> Dict[str, str]:
        """
        Get connection states for all servers connected by a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary of server_name -> connection_state
        """
        user_map = self.user_connections.get(user_id)
        if not user_map:
            return {}
        
        states = {}
        for server_name, connection in user_map.items():
            states[server_name] = connection.get_connection_state().value
        
        return states
    
    async def get_all_connection_states(self) -> Dict[str, Dict[str, str]]:
        """
        Get connection states for all users.
        
        Returns:
            Dictionary of user_id -> server_name -> connection_state
        """
        async with self._lock:
            all_states = {}
            for user_id, user_map in self.user_connections.items():
                user_states = {}
                for server_name, connection in user_map.items():
                    user_states[server_name] = connection.get_connection_state().value
                all_states[user_id] = user_states
            
            return all_states
    
    async def cleanup_all_idle_connections(self) -> List[str]:
        """
        Clean up idle connections for all users.
        
        Returns:
            List of user IDs that were cleaned up
        """
        return await self.check_idle_connections()
