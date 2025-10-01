#!/usr/bin/env python3
"""
Simple MCP Client using shared MCP utilities

This client uses the shared mcp_utils module which provides a standardized
MCP client implementation using only standard Python libraries. This approach
avoids dependency issues with the fastmcp library in some environments.
"""

import os
import sys
import json
import argparse
from typing import Optional

# Import shared MCP utility
from mcp_utils import create_mcp_session


def _load_m2m_credentials() -> Optional[str]:
    """Load M2M credentials and get access token from Keycloak"""
    client_id = os.getenv('CLIENT_ID')
    client_secret = os.getenv('CLIENT_SECRET')
    keycloak_url = os.getenv('KEYCLOAK_URL')
    keycloak_realm = os.getenv('KEYCLOAK_REALM')

    if not all([client_id, client_secret, keycloak_url, keycloak_realm]):
        return None

    # Import requests only when needed for M2M authentication
    try:
        import requests
    except ImportError:
        print("Warning: requests library not available for M2M authentication")
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
    except Exception as e:
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

  # Call any tool with arguments (specify correct server URL)
  uv run mcp_client.py --url http://localhost/currenttime/mcp call --tool current_time_by_timezone --args '{"tz_name":"America/New_York"}'

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

    # Load authentication (try M2M first, then let mcp_utils handle ingress token)
    access_token = _load_m2m_credentials()

    # Create MCP session using shared utility (it will auto-load ingress token if needed)
    try:
        with create_mcp_session(args.url, access_token) as client:
            # Check what authentication was actually used
            if client.access_token:
                if access_token:
                    print("✓ M2M authentication successful")
                else:
                    print("✓ Ingress token authentication successful")
            else:
                print("⚠ No authentication available")
            # Execute command
            if args.command == 'init':
                result = {"status": "initialized", "session_id": client.session_id}
            elif args.command == 'ping':
                result = client.ping()
            elif args.command == 'list':
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

                result = client.call_tool(args.tool, tool_args)

            # Print result
            print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()