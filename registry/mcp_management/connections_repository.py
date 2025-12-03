"""
Connections Repository for managing MCP connections.

Thread-safe storage for MCPConnection objects.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Iterator
from mcp_management.mcp_connection import MCPConnection

logger = logging.getLogger(__name__)


class ConnectionsRepository:
    """
    Repository for storing and managing MCP connections.
    
    Provides thread-safe operations for connection storage and retrieval.
    """
    
    def __init__(self, initial_configs: Optional[Dict[str, Dict[str, Any]]] = None):
        """
        Initialize the connections repository.
        
        Args:
            initial_configs: Optional initial server configurations to pre-create connections
        """
        self._connections: Dict[str, MCPConnection] = {}
        self._lock = asyncio.Lock()
        
        if initial_configs:
            for server_name, config in initial_configs.items():
                self._connections[server_name] = MCPConnection(server_name, config)
    
    async def has(self, server_name: str) -> bool:
        """
        Check if a connection exists for the given server name.
        
        Args:
            server_name: Name of the MCP server
            
        Returns:
            True if connection exists, False otherwise
        """
        async with self._lock:
            return server_name in self._connections
    
    async def get(self, server_name: str) -> Optional[MCPConnection]:
        """
        Get a connection for the given server name.
        
        Args:
            server_name: Name of the MCP server
            
        Returns:
            MCPConnection if found, None otherwise
        """
        async with self._lock:
            return self._connections.get(server_name)
    
    async def set(self, server_name: str, connection: MCPConnection) -> None:
        """
        Set a connection for the given server name.
        
        Args:
            server_name: Name of the MCP server
            connection: MCPConnection object to store
        """
        async with self._lock:
            self._connections[server_name] = connection
            logger.debug(f"Stored connection for server: {server_name}")
    
    async def delete(self, server_name: str) -> bool:
        """
        Delete a connection for the given server name.
        
        Args:
            server_name: Name of the MCP server
            
        Returns:
            True if connection was deleted, False if not found
        """
        async with self._lock:
            if server_name in self._connections:
                connection = self._connections[server_name]
                # Disconnect the connection before removing
                try:
                    await connection.disconnect()
                except Exception as e:
                    logger.warning(f"Error disconnecting {server_name} during deletion: {e}")
                
                del self._connections[server_name]
                logger.debug(f"Deleted connection for server: {server_name}")
                return True
            return False
    
    async def clear(self) -> None:
        """Clear all connections from the repository."""
        async with self._lock:
            # Disconnect all connections
            disconnect_tasks = []
            for server_name, connection in self._connections.items():
                disconnect_tasks.append(connection.disconnect())
                logger.debug(f"Disconnecting {server_name}")
            
            # Wait for all disconnections to complete
            if disconnect_tasks:
                await asyncio.gather(*disconnect_tasks, return_exceptions=True)
            
            self._connections.clear()
            logger.info("Cleared all connections from repository")
    
    async def get_all(self) -> Dict[str, MCPConnection]:
        """
        Get all connections in the repository.
        
        Returns:
            Dictionary of server_name -> MCPConnection
        """
        async with self._lock:
            return self._connections.copy()
    
    async def keys(self) -> List[str]:
        """
        Get all server names in the repository.
        
        Returns:
            List of server names
        """
        async with self._lock:
            return list(self._connections.keys())
    
    async def values(self) -> List[MCPConnection]:
        """
        Get all connections in the repository.
        
        Returns:
            List of MCPConnection objects
        """
        async with self._lock:
            return list(self._connections.values())
    
    async def items(self) -> List[tuple[str, MCPConnection]]:
        """
        Get all server-connection pairs in the repository.
        
        Returns:
            List of (server_name, MCPConnection) tuples
        """
        async with self._lock:
            return list(self._connections.items())
    
    async def size(self) -> int:
        """
        Get the number of connections in the repository.
        
        Returns:
            Number of connections
        """
        async with self._lock:
            return len(self._connections)
    
    async def is_empty(self) -> bool:
        """
        Check if the repository is empty.
        
        Returns:
            True if empty, False otherwise
        """
        async with self._lock:
            return len(self._connections) == 0
    
    async def update_config(self, server_name: str, config: Dict[str, Any]) -> bool:
        """
        Update the configuration for a server and recreate the connection.
        
        Args:
            server_name: Name of the MCP server
            config: New server configuration
            
        Returns:
            True if updated successfully, False if server not found
        """
        async with self._lock:
            if server_name not in self._connections:
                return False
            
            # Get the existing connection
            old_connection = self._connections[server_name]
            
            # Create new connection with new config
            user_id = old_connection.user_id
            oauth_tokens = old_connection.oauth_tokens
            new_connection = MCPConnection(server_name, config, user_id, oauth_tokens)
            
            # Disconnect old connection
            try:
                await old_connection.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting old connection for {server_name}: {e}")
            
            # Store new connection
            self._connections[server_name] = new_connection
            logger.info(f"Updated configuration and connection for server: {server_name}")
            return True
    
    async def get_connection_states(self) -> Dict[str, str]:
        """
        Get the connection state for all servers in the repository.
        
        Returns:
            Dictionary of server_name -> connection_state
        """
        async with self._lock:
            states = {}
            for server_name, connection in self._connections.items():
                states[server_name] = connection.get_connection_state().value
            return states
    
    async def cleanup_idle_connections(self, idle_timeout_seconds: float = 900) -> List[str]:
        """
        Clean up connections that have been idle for too long.
        
        Args:
            idle_timeout_seconds: Timeout in seconds (default 15 minutes)
            
        Returns:
            List of server names that were cleaned up
        """
        cleaned_up = []
        current_time = asyncio.get_event_loop().time()
        
        async with self._lock:
            for server_name, connection in list(self._connections.items()):
                idle_time = current_time - connection.last_activity_time
                if idle_time > idle_timeout_seconds:
                    logger.info(f"Cleaning up idle connection for {server_name} (idle for {idle_time:.1f}s)")
                    try:
                        await connection.disconnect()
                        del self._connections[server_name]
                        cleaned_up.append(server_name)
                    except Exception as e:
                        logger.error(f"Error cleaning up idle connection for {server_name}: {e}")
        
        return cleaned_up
    
    def __aiter__(self) -> Iterator[tuple[str, MCPConnection]]:
        """
        Async iterator over server-connection pairs.
        
        Note: This returns a synchronous iterator that yields copies of the data.
        For true async iteration, use the items() method.
        """
        # Note: This is a simplified implementation that copies data
        # For a true async iterator, we'd need to implement async generator
        # But given our locking strategy, this is simpler
        async def async_generator():
            async with self._lock:
                for server_name, connection in self._connections.items():
                    yield server_name, connection
        
        return async_generator()
