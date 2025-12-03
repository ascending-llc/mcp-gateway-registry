"""
MCP Connection implementation for Python.

Based on the jarvis-api TypeScript implementation, adapted to Python MCP SDK.
Supports multiple transport types: stdio, websocket, sse, streamable-http.
"""

import asyncio
import logging
from enum import Enum
from typing import Dict, Any, Optional, List

from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.stdio import stdio_client
from mcp.client.websocket import websocket_client
from mcp.client.session import ClientSession

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    """Connection states for MCP connections."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    REQUIRES_AUTH = "requires_auth"


class TransportType(str, Enum):
    """Supported transport types for MCP connections."""
    STDIO = "stdio"
    WEBSOCKET = "websocket"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"


class MCPOptions(Dict[str, Any]):
    """Type alias for MCP connection options."""
    pass


class MCPConnection:
    """
    Represents a connection to an MCP server.
    
    Manages connection state, transport, and communication with the server.
    """
    
    def __init__(
        self,
        server_name: str,
        server_config: Dict[str, Any],
        user_id: Optional[str] = None,
        oauth_tokens: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize an MCP connection.
        
        Args:
            server_name: Name of the MCP server
            server_config: Server configuration dictionary
            user_id: Optional user ID for user-specific connections
            oauth_tokens: Optional OAuth tokens for authenticated connections
        """
        self.server_name = server_name
        self.server_config = server_config
        self.user_id = user_id
        self.oauth_tokens = oauth_tokens
        
        # Connection state
        self.state: ConnectionState = ConnectionState.DISCONNECTED
        self.transport = None
        self.client: Optional[ClientSession] = None
        self.connect_task: Optional[asyncio.Task] = None
        
        # Configuration
        self.url = server_config.get("url")
        self.command = server_config.get("command")
        self.args = server_config.get("args", [])
        self.env = server_config.get("env", {})
        self.headers = server_config.get("headers", {})
        self.timeout = server_config.get("timeout", 30000)  # 30 seconds default
        self.transport_type = self._determine_transport_type()
        
        # Reconnection
        self.max_reconnect_attempts = 3
        self.reconnect_attempts = 0
        self.is_reconnecting = False
        self.should_stop_reconnecting = False
        
        # Activity tracking
        self.last_activity_time = asyncio.get_event_loop().time()
        
        logger.debug(f"Initialized MCPConnection for {server_name}, transport: {self.transport_type}")
    
    def _determine_transport_type(self) -> TransportType:
        """Determine transport type from configuration."""
        # Check if type is explicitly specified
        if "type" in self.server_config:
            config_type = self.server_config["type"]
            if config_type in ["stdio", "websocket", "sse", "streamable-http"]:
                return TransportType(config_type)
        
        # Infer from URL or command
        if self.command:
            return TransportType.STDIO
        elif self.url:
            url_lower = self.url.lower()
            if url_lower.startswith("ws://") or url_lower.startswith("wss://"):
                return TransportType.WEBSOCKET
            elif "/sse" in url_lower or url_lower.endswith("/sse"):
                return TransportType.SSE
            elif "/mcp" in url_lower or url_lower.endswith("/mcp"):
                return TransportType.STREAMABLE_HTTP
            else:
                # Default to streamable-http for HTTP URLs
                return TransportType.STREAMABLE_HTTP
        
        # Default to streamable-http
        return TransportType.STREAMABLE_HTTP
    
    async def connect(self) -> None:
        """Establish connection to the MCP server."""
        if self.state == ConnectionState.CONNECTED:
            logger.debug(f"Connection to {self.server_name} already established")
            return
        
        if self.connect_task and not self.connect_task.done():
            logger.debug(f"Connection to {self.server_name} already in progress")
            await self.connect_task
            return
        
        self.state = ConnectionState.CONNECTING
        logger.info(f"Connecting to MCP server {self.server_name} using {self.transport_type}")
        
        try:
            # Create client
            self.client = ClientSession(
                name="mcp-gateway-registry",
                version="1.0.0"
            )
            
            # Connect with timeout
            async with asyncio.timeout(self.timeout / 1000):  # Convert to seconds
                if self.transport_type == TransportType.STDIO:
                    # For stdio, transport is a context manager
                    async with stdio_client(
                        command=self.command,
                        args=self.args,
                        env=self.env
                    ) as (read, write):
                        await self.client.connect(read, write)
                elif self.transport_type == TransportType.WEBSOCKET:
                    # For websocket, transport is a context manager
                    async with websocket_client(self.url) as (read, write):
                        await self.client.connect(read, write)
                elif self.transport_type == TransportType.SSE:
                    # Add OAuth tokens to headers if available
                    headers = dict(self.headers)
                    if self.oauth_tokens and self.oauth_tokens.get("access_token"):
                        headers["Authorization"] = f"Bearer {self.oauth_tokens['access_token']}"
                    
                    # For SSE, transport is a context manager
                    async with sse_client(
                        self.url,
                        headers=headers
                    ) as (read, write):
                        await self.client.connect(read, write)
                elif self.transport_type == TransportType.STREAMABLE_HTTP:
                    # Add OAuth tokens to headers if available
                    headers = dict(self.headers)
                    if self.oauth_tokens and self.oauth_tokens.get("access_token"):
                        headers["Authorization"] = f"Bearer {self.oauth_tokens['access_token']}"
                    
                    # For streamable-http, transport is a context manager
                    async with streamablehttp_client(
                        url=self.url,
                        headers=headers
                    ) as (read, write):
                        await self.client.connect(read, write)
                else:
                    raise ValueError(f"Unsupported transport type: {self.transport_type}")
            
            self.state = ConnectionState.CONNECTED
            self.reconnect_attempts = 0
            self.is_reconnecting = False
            self.last_activity_time = asyncio.get_event_loop().time()
            
            logger.info(f"Successfully connected to MCP server {self.server_name}")
            
        except asyncio.TimeoutError:
            self.state = ConnectionState.ERROR
            logger.error(f"Connection timeout for MCP server {self.server_name}")
            raise
        except Exception as e:
            self.state = ConnectionState.ERROR
            logger.error(f"Failed to connect to MCP server {self.server_name}: {e}")
            
            # Check if it's an authentication error
            error_str = str(e).lower()
            if "401" in error_str or "403" in error_str or "authentication" in error_str or "unauthorized" in error_str:
                self.state = ConnectionState.REQUIRES_AUTH
                logger.warning(f"MCP server {self.server_name} requires authentication")
            
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self.state == ConnectionState.DISCONNECTED:
            return
        
        logger.info(f"Disconnecting from MCP server {self.server_name}")
        
        self.should_stop_reconnecting = True
        
        try:
            if self.client:
                await self.client.close()
        except Exception as e:
            logger.warning(f"Error closing client for {self.server_name}: {e}")
        
        self.client = None
        self.transport = None
        self.state = ConnectionState.DISCONNECTED
        
        logger.debug(f"Disconnected from MCP server {self.server_name}")
    
    async def is_connected(self) -> bool:
        """
        Check if the connection is actually connected and responsive.
        
        Returns:
            True if connected and responsive, False otherwise
        """
        if self.state != ConnectionState.CONNECTED or not self.client:
            return False
        
        try:
            # Try to ping the server or list tools to check connection
            await self.client.list_tools()
            self.last_activity_time = asyncio.get_event_loop().time()
            return True
        except Exception as e:
            logger.debug(f"Connection check failed for {self.server_name}: {e}")
            self.state = ConnectionState.ERROR
            return False
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        List tools available from the MCP server.
        
        Returns:
            List of tool dictionaries
        """
        if not await self.is_connected():
            await self.connect()
        
        try:
            tools_response = await self.client.list_tools()
            self.last_activity_time = asyncio.get_event_loop().time()
            
            # Extract tool information
            tools = []
            for tool in tools_response.tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema
                })
            
            return tools
        except Exception as e:
            logger.error(f"Failed to list tools from {self.server_name}: {e}")
            raise
    
    async def list_resources(self) -> List[Dict[str, Any]]:
        """
        List resources available from the MCP server.
        
        Returns:
            List of resource dictionaries
        """
        if not await self.is_connected():
            await self.connect()
        
        try:
            resources_response = await self.client.list_resources()
            self.last_activity_time = asyncio.get_event_loop().time()
            
            # Extract resource information
            resources = []
            for resource in resources_response.resources:
                resources.append({
                    "uri": resource.uri,
                    "name": resource.name,
                    "description": resource.description or "",
                    "mime_type": resource.mimeType
                })
            
            return resources
        except Exception as e:
            logger.error(f"Failed to list resources from {self.server_name}: {e}")
            raise
    
    async def list_prompts(self) -> List[Dict[str, Any]]:
        """
        List prompts available from the MCP server.
        
        Returns:
            List of prompt dictionaries
        """
        if not await self.is_connected():
            await self.connect()
        
        try:
            prompts_response = await self.client.list_prompts()
            self.last_activity_time = asyncio.get_event_loop().time()
            
            # Extract prompt information
            prompts = []
            for prompt in prompts_response.prompts:
                prompts.append({
                    "name": prompt.name,
                    "description": prompt.description or "",
                    "arguments": prompt.arguments or []
                })
            
            return prompts
        except Exception as e:
            logger.error(f"Failed to list prompts from {self.server_name}: {e}")
            raise
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on the MCP server.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            
        Returns:
            Tool execution result
        """
        if not await self.is_connected():
            await self.connect()
        
        try:
            result = await self.client.call_tool(tool_name, arguments)
            self.last_activity_time = asyncio.get_event_loop().time()
            return result
        except Exception as e:
            logger.error(f"Failed to call tool {tool_name} on {self.server_name}: {e}")
            raise
    
    def update_last_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity_time = asyncio.get_event_loop().time()
    
    def get_connection_state(self) -> ConnectionState:
        """Get the current connection state."""
        return self.state
    
    def set_connection_state(self, state: ConnectionState) -> None:
        """Set the connection state."""
        self.state = state
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
