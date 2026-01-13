#!/usr/bin/env python3
"""
Simple MCP Client using shared MCP utilities

This client uses the shared mcp_utils module which provides a standardized
MCP client implementation using only standard Python libraries. This approach
avoids dependency issues with the fastmcp library in some environments.
"""

import base64
import json
import os
import sys
import argparse
from datetime import datetime, timezone
from typing import Optional

# Import shared MCP utility
from mcp_utils import create_mcp_session


def _check_token_expiration(
    access_token: str
) -> None:
    """
    Check if JWT token is expired and exit with informative message if so.

    Args:
        access_token: JWT access token to check

    Exits:
        If token is expired or will expire soon
    """
    try:
        # Decode JWT payload (without verification, just to check expiry)
        parts = access_token.split('.')
        if len(parts) != 3:
            print("Warning: Invalid JWT format, cannot check expiration")
            return

        # Decode payload
        payload = parts[1]
        # Add padding if needed
        padding = len(payload) % 4
        if padding:
            payload += '=' * (4 - padding)

        decoded = base64.urlsafe_b64decode(payload)
        token_data = json.loads(decoded)

        # Check expiration
        exp = token_data.get('exp')
        if not exp:
            print("Warning: Token does not have expiration field")
            return

        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        time_until_expiry = exp_dt - now

        if time_until_expiry.total_seconds() < 0:
            # Token is expired
            print("=" * 80)
            print("TOKEN EXPIRED")
            print("=" * 80)
            print(f"Token expired at: {exp_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"Current time is: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"Token expired {abs(time_until_expiry.total_seconds()):.0f} seconds ago")
            print("")
            print("Please regenerate your token using one of these methods:")
            print("")
            print("  1. For LOB bot agents (recommended):")
            print("     ./keycloak/setup/generate-agent-token.sh lob1-bot")
            print("     ./keycloak/setup/generate-agent-token.sh lob2-bot")
            print("")
            print("  2. Use token file (for Cognito/OAuth):")
            print("     --token-file /path/to/your/.token_file")
            print("")
            print("  3. Use M2M authentication:")
            print("     Set environment variables: CLIENT_ID, CLIENT_SECRET,")
            print("     KEYCLOAK_URL, KEYCLOAK_REALM")
            print("=" * 80)
            sys.exit(1)
        elif time_until_expiry.total_seconds() < 60:
            # Token expires soon
            print(f"Warning: Token will expire in {int(time_until_expiry.total_seconds())} seconds at {exp_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        else:
            print(f"Token is valid until {exp_dt.strftime('%Y-%m-%d %H:%M:%S UTC')} ({int(time_until_expiry.total_seconds())} seconds remaining)")

    except Exception as e:
        print(f"Warning: Could not check token expiration: {e}")


def _load_token_from_file(file_path: str) -> Optional[str]:
    """Load access token from a file

    Supports two formats:
    1. Plain JWT token (single line)
    2. JSON object with 'access_token' field (from agent token generation)
    """
    try:
        with open(file_path, 'r') as f:
            content = f.read().strip()
            if not content:
                return None

            # Try to parse as JSON first (for agent token files)
            try:
                token_data = json.loads(content)
                if isinstance(token_data, dict) and 'access_token' in token_data:
                    return token_data['access_token']
            except json.JSONDecodeError:
                # Not JSON, treat as plain token string
                pass

            # Return as-is (plain JWT token)
            return content if content else None
    except FileNotFoundError:
        print(f"Warning: Token file not found: {file_path}")
    except Exception as e:
        print(f"Warning: Failed to read token file {file_path}: {e}")
    return None


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

  # Use token from file (e.g., for Cognito/OAuth servers)
  uv run mcp_client.py --url http://localhost/customer-support-assistant/mcp --token-file /path/to/.cognito_access_token list

Authentication (priority order):
  1. --token-file: Path to file containing access token
  2. OAUTH_TOKEN environment variable: Direct JWT token
  3. Environment variables: CLIENT_ID, CLIENT_SECRET, KEYCLOAK_URL, KEYCLOAK_REALM
  4. Ingress token: Automatically loaded from ~/.mcp/ingress_token if available
        """)
    parser.add_argument('--url', default='http://localhost/mcpgw/mcp',
                       help='Gateway URL (default: %(default)s)')
    parser.add_argument('--token-file',
                       help='Path to file containing access token (e.g., .cognito_access_token)')
    parser.add_argument('command', choices=['ping', 'list', 'call', 'init'],
                       help='Command to execute')
    parser.add_argument('--tool', help='Tool name for call command')
    parser.add_argument('--args', help='Tool arguments as JSON string')

    args = parser.parse_args()

    # Load authentication (priority: token-file > OAUTH_TOKEN env var > M2M > ingress token)
    access_token = None

    # Try loading from file first if specified
    if args.token_file:
        access_token = _load_token_from_file(args.token_file)

    # Fall back to OAUTH_TOKEN environment variable if no token file or file loading failed
    if not access_token:
        access_token = os.getenv('OAUTH_TOKEN')

    # Fall back to M2M credentials if no OAUTH_TOKEN
    if not access_token:
        access_token = _load_m2m_credentials()

    # Check token expiration before making any API calls
    if access_token:
        _check_token_expiration(access_token)

    # Create MCP session using shared utility (it will auto-load ingress token if needed)
    try:
        with create_mcp_session(args.url, access_token) as client:
            # Check what authentication was actually used
            if client.access_token:
                if args.token_file:
                    print(f"✓ Token file authentication successful ({args.token_file})")
                elif os.getenv('OAUTH_TOKEN'):
                    print("✓ OAuth token authentication successful (OAUTH_TOKEN env var)")
                elif access_token:
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