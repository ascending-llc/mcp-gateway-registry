#!/usr/bin/env python3
"""
Shared MCP Client Utility

This module provides a reusable MCP (Model Context Protocol) client implementation
using only standard Python libraries. We created this because some environments
block certain Python package installs, causing the fastmcp library install to fail.
This handy dandy MCP client implementation avoids external dependencies beyond
the standard library plus commonly available packages like requests.

The client supports:
- JSON-RPC 2.0 protocol over HTTP
- Authentication via Bearer tokens
- Session management with automatic initialization
- Both synchronous and asynchronous operations
- Server-Sent Events (SSE) response handling
- Automatic token loading from OAuth files
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional, Union
import urllib.request
import urllib.parse
import urllib.error


logger = logging.getLogger(__name__)


def _load_oauth_token_from_file(token_file_path: Union[str, Path]) -> Optional[str]:
    """
    Load OAuth access token from JSON file.

    Args:
        token_file_path: Path to OAuth token file

    Returns:
        Access token if found and valid, None otherwise
    """
    try:
        token_path = Path(token_file_path)
        if not token_path.exists():
            return None

        with open(token_path, 'r') as f:
            token_data = json.load(f)

        access_token = token_data.get('access_token')
        expires_at = token_data.get('expires_at', 0)

        # Check if token is expired
        if expires_at and time.time() >= expires_at:
            logger.warning(f"Token in {token_file_path} has expired")
            return None

        return access_token

    except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
        logger.debug(f"Could not load token from {token_file_path}: {e}")
        return None


def _get_auth_token(
    explicit_token: Optional[str] = None,
    env_var_name: str = "MCP_AUTH_TOKEN"
) -> Optional[str]:
    """
    Get authentication token from multiple sources in priority order.

    Priority order:
    1. Explicit token parameter
    2. Environment variable
    3. Ingress token file (.oauth-tokens/ingress.json)

    Args:
        explicit_token: Token provided directly
        env_var_name: Name of environment variable to check

    Returns:
        Access token if found, None otherwise
    """
    # 1. Explicit token has highest priority
    if explicit_token:
        return explicit_token

    # 2. Check environment variable
    env_token = os.getenv(env_var_name)
    if env_token:
        return env_token

    # 3. Try to load from ingress token file
    ingress_token_path = Path.cwd() / ".oauth-tokens" / "ingress.json"
    return _load_oauth_token_from_file(ingress_token_path)


class MCPClient:
    """
    MCP (Model Context Protocol) client implementation using standard Python libraries.

    This client handles JSON-RPC 2.0 communication over HTTP with MCP servers,
    including authentication, session management, and response parsing.
    """

    def __init__(
        self,
        gateway_url: str,
        access_token: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize MCP client.

        Args:
            gateway_url: URL of the MCP gateway endpoint
            access_token: Optional Bearer token for authentication
            timeout: Request timeout in seconds
        """
        self.gateway_url = gateway_url.rstrip('/')
        self.access_token = _get_auth_token(access_token)
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self._request_id = 0

    def _get_next_request_id(self) -> int:
        """Get next request ID for JSON-RPC calls."""
        self._request_id += 1
        return self._request_id

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers for requests."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
            'User-Agent': 'mcp-utils-client/1.0.0'
        }

        if self.access_token:
            headers['X-Authorization'] = f'Bearer {self.access_token}'

        if self.session_id:
            headers['mcp-session-id'] = self.session_id

        return headers

    def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make HTTP request to MCP gateway.

        Args:
            payload: JSON-RPC payload

        Returns:
            Parsed response data

        Raises:
            Exception: If request fails or response is invalid
        """
        headers = self._build_headers()
        data = json.dumps(payload).encode('utf-8')

        try:
            request = urllib.request.Request(
                self.gateway_url,
                data=data,
                headers=headers,
                method='POST'
            )

            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_data = response.read().decode('utf-8')
                content_type = response.headers.get('content-type', '')

                # Extract session ID from response headers if available
                session_id = response.headers.get('mcp-session-id')
                if session_id and not self.session_id:
                    self.session_id = session_id
                    logger.debug(f"Session ID established: {session_id}")

                # Handle Server-Sent Events (SSE) response
                if 'text/event-stream' in content_type:
                    return self._parse_sse_response(response_data)
                else:
                    # Handle regular JSON response
                    return json.loads(response_data)

        except urllib.error.HTTPError as e:
            error_msg = f"HTTP {e.code}: {e.reason}"
            try:
                error_response = e.read().decode('utf-8')
                error_data = json.loads(error_response)
                if 'error' in error_data:
                    error_msg = f"HTTP {e.code}: {error_data['error']}"
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
            raise Exception(error_msg)

        except urllib.error.URLError as e:
            raise Exception(f"Network error: {e.reason}")

        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}")

    def _parse_sse_response(self, sse_data: str) -> Dict[str, Any]:
        """
        Parse Server-Sent Events response format.

        Args:
            sse_data: Raw SSE response data

        Returns:
            Parsed JSON data from SSE stream
        """
        lines = sse_data.strip().split('\n')
        for line in lines:
            if line.startswith('data: '):
                data_json = line[6:]  # Remove 'data: ' prefix
                try:
                    return json.loads(data_json)
                except json.JSONDecodeError:
                    continue
        raise Exception("No valid JSON found in SSE response")

    def initialize(self) -> Dict[str, Any]:
        """
        Initialize MCP session with the gateway.

        Returns:
            Initialization response
        """
        payload = {
            "jsonrpc": "2.0",
            "id": self._get_next_request_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "mcp-utils-client",
                    "version": "1.0.0"
                }
            }
        }

        result = self._make_request(payload)

        # Send initialized notification to complete handshake
        self._send_initialized()

        return result

    def _send_initialized(self) -> None:
        """Send initialized notification to complete MCP handshake."""
        payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        try:
            self._make_request(payload)
        except Exception as e:
            # This is expected for some MCP servers that don't require the notification
            logger.debug(f"Initialized notification not sent (this is normal): {e}")

    def ping(self) -> Dict[str, Any]:
        """
        Test connectivity with ping.

        Returns:
            Ping response
        """
        payload = {
            "jsonrpc": "2.0",
            "id": self._get_next_request_id(),
            "method": "ping"
        }
        return self._make_request(payload)

    def list_tools(self) -> Dict[str, Any]:
        """
        List available tools.

        Returns:
            Tools list response
        """
        payload = {
            "jsonrpc": "2.0",
            "id": self._get_next_request_id(),
            "method": "tools/list"
        }
        return self._make_request(payload)

    def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call a specific tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments (optional)

        Returns:
            Tool execution result
        """
        if arguments is None:
            arguments = {}

        payload = {
            "jsonrpc": "2.0",
            "id": self._get_next_request_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        response = self._make_request(payload)

        # Handle MCP response format
        if "error" in response:
            raise Exception(f"MCP tool error: {response['error']}")

        if "result" in response:
            return response["result"]

        return response

    def call_mcpgw_tool(
        self,
        tool_name: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call a tool using mcpgw-specific parameter format.

        This method wraps parameters in the format expected by mcpgw tools.

        Args:
            tool_name: Name of the tool to call
            params: Parameters for the tool

        Returns:
            Tool execution result
        """
        arguments = {"params": params}
        return self.call_tool(tool_name, arguments)


class MCPSession:
    """
    Context manager for MCP client sessions.

    Automatically initializes the session on entry and ensures proper cleanup.
    Provides a convenient way to work with MCP clients in a session context.
    """

    def __init__(self, client: MCPClient):
        """
        Initialize session context.

        Args:
            client: MCP client instance
        """
        self.client = client
        self._initialized = False

    def __enter__(self) -> MCPClient:
        """Enter session context and initialize."""
        try:
            self.client.initialize()
            self._initialized = True
            logger.debug("MCP session initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MCP session: {e}")
            raise
        return self.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit session context."""
        if self._initialized:
            logger.debug("MCP session closed")


def create_mcp_client(
    gateway_url: str,
    access_token: Optional[str] = None,
    timeout: int = 30
) -> MCPClient:
    """
    Create and return a configured MCP client.

    Args:
        gateway_url: URL of the MCP gateway endpoint
        access_token: Optional Bearer token for authentication
        timeout: Request timeout in seconds

    Returns:
        Configured MCP client instance
    """
    return MCPClient(gateway_url, access_token, timeout)


def create_mcp_session(
    gateway_url: str,
    access_token: Optional[str] = None,
    timeout: int = 30
) -> MCPSession:
    """
    Create and return an MCP session context manager.

    Args:
        gateway_url: URL of the MCP gateway endpoint
        access_token: Optional Bearer token for authentication
        timeout: Request timeout in seconds

    Returns:
        MCP session context manager
    """
    client = create_mcp_client(gateway_url, access_token, timeout)
    return MCPSession(client)