#!/usr/bin/env python3
"""
Simple MCP Client using requests library
Sends JSON-RPC payloads to MCP Gateway without using MCP-specific libraries
"""

import os
import sys
import json
import requests
import argparse
from typing import Dict, Any, Optional


class MCPClient:
    def __init__(self, gateway_url: str, access_token: Optional[str] = None):
        self.gateway_url = gateway_url
        self.access_token = access_token
        self.session_id = None

    def _make_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make a request to the MCP Gateway"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream'
        }

        if self.access_token:
            headers['X-Authorization'] = f'Bearer {self.access_token}'

        if self.session_id:
            headers['mcp-session-id'] = self.session_id

        try:
            response = requests.post(self.gateway_url, json=payload, headers=headers)
            response.raise_for_status()

            # Handle different content types
            content_type = response.headers.get('content-type', '')
            if 'text/event-stream' in content_type:
                # Handle Server-Sent Events (SSE) response
                lines = response.text.strip().split('\n')
                for line in lines:
                    if line.startswith('data: '):
                        data_json = line[6:]  # Remove 'data: ' prefix
                        try:
                            return json.loads(data_json)
                        except json.JSONDecodeError:
                            continue
                return {"error": "No valid JSON found in SSE response"}
            else:
                # Handle regular JSON response
                return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": f"Request failed: {e}"}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response: {e}"}

    def initialize(self) -> Dict[str, Any]:
        """Initialize MCP session"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "python-mcp-client",
                    "version": "1.0.0"
                }
            }
        }

        # Make request and extract session ID from headers
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream'
        }

        if self.access_token:
            headers['X-Authorization'] = f'Bearer {self.access_token}'

        try:
            response = requests.post(self.gateway_url, json=payload, headers=headers)
            response.raise_for_status()

            # Extract session ID from response headers
            self.session_id = response.headers.get('mcp-session-id')
            if self.session_id:
                print(f"Session established: {self.session_id}")

                # Send initialized notification
                self._send_initialized()
                return response.json()
            else:
                return {"error": "No session ID received"}

        except requests.exceptions.RequestException as e:
            return {"error": f"Initialize failed: {e}"}

    def _send_initialized(self) -> None:
        """Send initialized notification to complete handshake"""
        payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        self._make_request(payload)

    def ping(self) -> Dict[str, Any]:
        """Test connectivity with ping"""
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "ping"
        }
        return self._make_request(payload)

    def list_tools(self) -> Dict[str, Any]:
        """List available tools"""
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/list"
        }
        return self._make_request(payload)

    def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Call a specific tool"""
        if arguments is None:
            arguments = {}

        payload = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        return self._make_request(payload)


def load_m2m_credentials() -> Optional[str]:
    """Load M2M credentials and get access token from Keycloak"""
    client_id = os.getenv('CLIENT_ID')
    client_secret = os.getenv('CLIENT_SECRET')
    keycloak_url = os.getenv('KEYCLOAK_URL')
    keycloak_realm = os.getenv('KEYCLOAK_REALM')

    if not all([client_id, client_secret, keycloak_url, keycloak_realm]):
        return None

    # Get access token from Keycloak
    token_url = f"{keycloak_url}/realms/{keycloak_realm}/protocol/openid-connect/token"

    data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': 'openid'
    }

    try:
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        token_data = response.json()
        return token_data.get('access_token')
    except requests.exceptions.RequestException as e:
        print(f"Failed to get M2M token: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Simple MCP Client - Communicate with MCP Gateway using JSON-RPC',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test connectivity
  uv run mcp_client.py ping

  # List available tools
  uv run mcp_client.py list

  # Find tools using natural language
  uv run mcp_client.py call --tool intelligent_tool_finder --args '{"natural_language_query":"get current time in New York"}'

  # Call any tool with arguments
  uv run mcp_client.py call --tool current_time_by_timezone --args '{"tz_name":"America/New_York"}'

  # Use different gateway URL
  uv run mcp_client.py --url http://localhost/currenttime/mcp ping

Authentication:
  Set environment variables CLIENT_ID, CLIENT_SECRET, KEYCLOAK_URL, KEYCLOAK_REALM
  Or source a credentials file: source .oauth-tokens/agent-test-agent-m2m.env
        """)
    parser.add_argument('--url', default='http://localhost/mcpgw/mcp',
                       help='Gateway URL (default: %(default)s)')
    parser.add_argument('command', choices=['ping', 'list', 'call', 'init'],
                       help='Command to execute')
    parser.add_argument('--tool', help='Tool name for call command')
    parser.add_argument('--args', help='Tool arguments as JSON string')

    args = parser.parse_args()

    # Load authentication
    access_token = load_m2m_credentials()
    if access_token:
        print("✓ M2M authentication successful")
    else:
        print("⚠ No M2M authentication available")

    # Create client
    client = MCPClient(args.url, access_token)

    # Execute command
    if args.command == 'init':
        result = client.initialize()
    elif args.command == 'ping':
        client.initialize()  # Initialize first
        result = client.ping()
    elif args.command == 'list':
        client.initialize()  # Initialize first
        result = client.list_tools()
    elif args.command == 'call':
        if not args.tool:
            print("Error: --tool is required for call command")
            sys.exit(1)

        # Parse arguments if provided
        tool_args = {}
        if args.args:
            try:
                tool_args = json.loads(args.args)
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON in --args: {e}")
                sys.exit(1)

        client.initialize()  # Initialize first
        result = client.call_tool(args.tool, tool_args)

    # Print result
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()