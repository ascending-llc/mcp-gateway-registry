"""
MCP Manager - Centralized manager for MCP server connections and tool execution.

Based on jarvis-api TypeScript implementation, adapted to Python.
Extends UserConnectionManager to handle both app-level and user-specific connections.
"""

import logging
from typing import Dict, Any, Optional, List

from .user_connection_manager import UserConnectionManager
from .mcp_connection import MCPConnection, ConnectionState
from .connections_repository import ConnectionsRepository

logger = logging.getLogger(__name__)


class MCPManager(UserConnectionManager):
    """
    Singleton manager for MCP server connections and tool execution.
    
    Manages both app-level connections (shared) and user-specific connections.
    """
    
    _instance: Optional['MCPManager'] = None
    
    @classmethod
    def get_instance(cls) -> 'MCPManager':
        """Get the singleton instance of MCPManager."""
        if cls._instance is None:
            cls._instance = MCPManager()
        return cls._instance
    
    @classmethod
    async def initialize_instance(cls, server_configs: Dict[str, Dict[str, Any]]) -> 'MCPManager':
        """
        Initialize the singleton MCPManager instance with server configurations.
        
        Args:
            server_configs: Dictionary of server configurations (server_name -> config)
            
        Returns:
            Initialized MCPManager instance
        """
        if cls._instance is not None:
            raise RuntimeError("MCPManager has already been initialized")
        
        instance = cls.get_instance()
        await instance.initialize(server_configs)
        return instance
    
    async def initialize(self, server_configs: Dict[str, Dict[str, Any]]) -> None:
        """
        Initialize the MCPManager by setting up server registry and app connections.
        
        Args:
            server_configs: Dictionary of server configurations (server_name -> config)
        """
        # Create app connections repository with initial configs
        self.app_connections = ConnectionsRepository(server_configs)
        
        # Initialize app connections (connect to all servers)
        logger.info(f"Initializing MCPManager with {len(server_configs)} servers")
        
        # Note: We don't connect immediately to avoid blocking startup
        # Connections will be established on-demand
    
    async def get_connection(
        self,
        server_name: str,
        user_id: Optional[str] = None,
        force_new: bool = False,
        server_config_override: Optional[Dict[str, Any]] = None,
        oauth_tokens: Optional[Dict[str, Any]] = None
    ) -> MCPConnection:
        """
        Retrieve an app-level or user-specific connection.
        
        Args:
            server_name: Name of the MCP server
            user_id: Optional user ID for user-specific connections
            force_new: Whether to force creation of a new connection
            server_config_override: Optional server configuration override
            oauth_tokens: Optional OAuth tokens for authenticated connections
            
        Returns:
            MCPConnection object
        """
        # First, check if we have an app-level connection
        if self.app_connections and await self.app_connections.has(server_name):
            app_connection = await self.app_connections.get(server_name)
            if app_connection and await app_connection.is_connected():
                logger.debug(f"Using app-level connection for {server_name}")
                return app_connection
        
        # If user_id is provided, get or create user-specific connection
        if user_id:
            # Get server configuration (use override if provided)
            if server_config_override:
                server_config = server_config_override
            else:
                # Try to get config from app connections or use default
                if self.app_connections and await self.app_connections.has(server_name):
                    app_connection = await self.app_connections.get(server_name)
                    server_config = app_connection.server_config
                else:
                    # We need a configuration for this server
                    raise ValueError(f"No configuration found for server {server_name}")
            
            return await self.get_user_connection(
                server_name=server_name,
                user_id=user_id,
                server_config=server_config,
                force_new=force_new,
                oauth_tokens=oauth_tokens
            )
        
        # No app connection and no user_id, try to create a generic connection
        if self.app_connections and await self.app_connections.has(server_name):
            app_connection = await self.app_connections.get(server_name)
            # Try to connect if not already connected
            if not await app_connection.is_connected():
                await app_connection.connect()
            return app_connection
        
        raise ValueError(f"No connection found for server {server_name}")
    
    async def get_server_connection_status(
        self,
        server_name: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed connection status for a specific server.
        
        Args:
            server_name: Name of the MCP server
            user_id: Optional user ID for user-specific connections
            
        Returns:
            Dictionary with connection status details
        """
        try:
            # Check if server exists in app connections
            has_app_connection = (
                self.app_connections and 
                await self.app_connections.has(server_name)
            )
            
            if not has_app_connection:
                return {
                    "connection_state": ConnectionState.DISCONNECTED.value,
                    "requires_oauth": False,
                    "server_name": server_name,
                    "error": "Server not found in configuration"
                }
            
            # Get the connection (app-level or user-specific)
            connection = None
            is_app_connection = False
            
            if user_id:
                # Try to get user-specific connection
                user_connections = self.get_user_connections(user_id)
                if user_connections and server_name in user_connections:
                    connection = user_connections[server_name]
                else:
                    # User doesn't have a connection yet
                    connection = await self.app_connections.get(server_name)
                    is_app_connection = True
            else:
                # Use app connection
                connection = await self.app_connections.get(server_name)
                is_app_connection = True
            
            if not connection:
                return {
                    "connection_state": ConnectionState.DISCONNECTED.value,
                    "requires_oauth": False,
                    "server_name": server_name,
                    "error": "Connection not found"
                }
            
            # Check connection state
            connection_state = connection.get_connection_state()
            is_connected = await connection.is_connected() if connection_state == ConnectionState.CONNECTED else False
            
            # Determine actual state
            actual_state = connection_state.value
            if connection_state == ConnectionState.CONNECTED and not is_connected:
                actual_state = ConnectionState.ERROR.value
            
            # Check if OAuth is required
            requires_oauth = connection_state == ConnectionState.REQUIRES_AUTH
            
            return {
                "connection_state": actual_state,
                "requires_oauth": requires_oauth,
                "server_name": server_name,
                "is_app_connection": is_app_connection,
                "user_id": user_id,
                "transport_type": connection.transport_type.value if hasattr(connection, 'transport_type') else "unknown",
                "url": connection.url if hasattr(connection, 'url') else None
            }
            
        except Exception as e:
            logger.error(f"Error getting connection status for {server_name}: {e}")
            return {
                "connection_state": ConnectionState.ERROR.value,
                "requires_oauth": False,
                "server_name": server_name,
                "error": str(e)
            }
    
    async def get_all_connection_status(
        self,
        user_id: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get connection status for all servers.
        
        Args:
            user_id: Optional user ID for user-specific connections
            
        Returns:
            Dictionary mapping server_name -> connection status
        """
        if not self.app_connections:
            return {}
        
        # Get all server names from app connections
        server_names = await self.app_connections.keys()
        
        # Get status for each server
        status_dict = {}
        for server_name in server_names:
            status = await self.get_server_connection_status(server_name, user_id)
            status_dict[server_name] = status
        
        return status_dict
    
    async def list_tools_for_server(
        self,
        server_name: str,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List tools available from a specific MCP server.
        
        Args:
            server_name: Name of the MCP server
            user_id: Optional user ID for user-specific connections
            
        Returns:
            List of tool dictionaries
        """
        try:
            connection = await self.get_connection(server_name, user_id)
            tools = await connection.list_tools()
            return tools
        except Exception as e:
            logger.error(f"Failed to list tools from {server_name}: {e}")
            raise
    
    async def list_resources_for_server(
        self,
        server_name: str,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List resources available from a specific MCP server.
        
        Args:
            server_name: Name of the MCP server
            user_id: Optional user ID for user-specific connections
            
        Returns:
            List of resource dictionaries
        """
        try:
            connection = await self.get_connection(server_name, user_id)
            resources = await connection.list_resources()
            return resources
        except Exception as e:
            logger.error(f"Failed to list resources from {server_name}: {e}")
            raise
    
    async def list_prompts_for_server(
        self,
        server_name: str,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List prompts available from a specific MCP server.
        
        Args:
            server_name: Name of the MCP server
            user_id: Optional user ID for user-specific connections
            
        Returns:
            List of prompt dictionaries
        """
        try:
            connection = await self.get_connection(server_name, user_id)
            prompts = await connection.list_prompts()
            return prompts
        except Exception as e:
            logger.error(f"Failed to list prompts from {server_name}: {e}")
            raise
    
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Call a tool on an MCP server.
        
        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            user_id: Optional user ID for user-specific connections
            
        Returns:
            Tool execution result
        """
        try:
            connection = await self.get_connection(server_name, user_id)
            result = await connection.call_tool(tool_name, arguments)
            
            # Update user activity if user_id is provided
            if user_id:
                self.update_user_last_activity(user_id)
                # Check idle connections
                await self.check_idle_connections(user_id)
            
            return result
        except Exception as e:
            logger.error(f"Failed to call tool {tool_name} on {server_name}: {e}")
            raise
    
    async def update_server_config(
        self,
        server_name: str,
        new_config: Dict[str, Any]
    ) -> bool:
        """
        Update configuration for a server and recreate its connection.
        
        Args:
            server_name: Name of the MCP server
            new_config: New server configuration
            
        Returns:
            True if updated successfully, False otherwise
        """
        if not self.app_connections:
            return False
        
        # Update app connection
        updated = await self.app_connections.update_config(server_name, new_config)
        
        # Also update any user connections for this server
        if updated:
            for user_id, user_map in self.user_connections.items():
                if server_name in user_map:
                    # Disconnect the old user connection
                    old_connection = user_map[server_name]
                    await old_connection.disconnect()
                    
                    # Create new connection with new config
                    new_connection = MCPConnection(
                        server_name=server_name,
                        server_config=new_config,
                        user_id=user_id,
                        oauth_tokens=old_connection.oauth_tokens
                    )
                    
                    # Store the new connection
                    user_map[server_name] = new_connection
        
        return updated
    
    async def cleanup(self) -> None:
        """Clean up all connections and resources."""
        logger.info("Cleaning up MCPManager resources")
        
        # Clean up user connections
        for user_id in list(self.user_connections.keys()):
            await self.disconnect_user_connections(user_id)
        
        # Clean up app connections
        if self.app_connections:
            await self.app_connections.clear()
        
        logger.info("MCPManager cleanup completed")


# Global MCP manager instance
async def get_mcp_manager() -> MCPManager:
    """Get the global MCP manager instance."""
    return MCPManager.get_instance()
