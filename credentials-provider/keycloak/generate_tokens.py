#!/usr/bin/env python3
"""
Generate OAuth2 access tokens for MCP agents using Keycloak
Python version of generate-agent-token.sh with batch processing capabilities
"""

import os
import sys
import json
import requests
import argparse
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import glob
from pathlib import Path


class Colors:
    """ANSI color codes for console output"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


class TokenGenerator:
    """Generate tokens for MCP agents using Keycloak OAuth2"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.setup_logging()

    def setup_logging(self):
        """Setup logging configuration"""
        level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def log(self, message: str):
        """Log info message if verbose mode is enabled"""
        if self.verbose:
            print(f"{Colors.BLUE}[INFO]{Colors.NC} {message}")

    def error(self, message: str):
        """Print error message"""
        print(f"{Colors.RED}[ERROR]{Colors.NC} {message}", file=sys.stderr)

    def success(self, message: str):
        """Print success message"""
        print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {message}")

    def warning(self, message: str):
        """Print warning message"""
        print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {message}")

    def load_agent_config(self, agent_name: str, oauth_tokens_dir: str) -> Optional[Dict[str, Any]]:
        """Load agent configuration from JSON file"""
        config_file = os.path.join(oauth_tokens_dir, f"{agent_name}.json")

        if not os.path.exists(config_file):
            self.error(f"Config file not found: {config_file}")
            return None

        self.log(f"Loading config from: {config_file}")

        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            return config
        except json.JSONDecodeError as e:
            self.error(f"Failed to parse JSON config file: {e}")
            return None
        except Exception as e:
            self.error(f"Failed to load config file: {e}")
            return None

    def get_token_from_keycloak(self, client_id: str, client_secret: str,
                               keycloak_url: str, realm: str) -> Optional[Dict[str, Any]]:
        """Request access token from Keycloak"""
        token_url = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/token"

        self.log(f"Token URL: {token_url}")
        self.log(f"Client ID: {client_id}")
        self.log(f"Realm: {realm}")

        data = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
            'scope': 'openid email profile'
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        try:
            response = requests.post(token_url, data=data, headers=headers)
            response.raise_for_status()

            token_data = response.json()

            # Check for error in response
            if 'error_description' in token_data:
                self.error(f"Token request failed: {token_data['error_description']}")
                return None

            # Validate access token exists
            if 'access_token' not in token_data:
                self.error("No access token in response")
                self.log(f"Response: {token_data}")
                return None

            return token_data

        except requests.exceptions.RequestException as e:
            self.error(f"Failed to make token request to Keycloak: {e}")
            return None
        except json.JSONDecodeError as e:
            self.error(f"Invalid JSON response: {e}")
            return None

    def save_token_files(self, agent_name: str, token_data: Dict[str, Any],
                        client_id: str, client_secret: str, keycloak_url: str,
                        realm: str, oauth_tokens_dir: str) -> bool:
        """Save token to both .env and .json files"""
        access_token = token_data['access_token']
        expires_in = token_data.get('expires_in')

        # Create output directory
        os.makedirs(oauth_tokens_dir, exist_ok=True)

        # Generate timestamps
        generated_at = datetime.now(timezone.utc).isoformat()
        expires_at = None
        if expires_in:
            expiry_timestamp = datetime.now(timezone.utc).timestamp() + expires_in
            expires_at = datetime.fromtimestamp(expiry_timestamp, timezone.utc).isoformat()

        # Save .env file
        env_file = os.path.join(oauth_tokens_dir, f"{agent_name}.env")
        try:
            with open(env_file, 'w') as f:
                f.write(f"# Generated access token for {agent_name}\n")
                f.write(f"# Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f'export ACCESS_TOKEN="{access_token}"\n')
                f.write(f'export CLIENT_ID="{client_id}"\n')
                f.write(f'export CLIENT_SECRET="{client_secret}"\n')
                f.write(f'export KEYCLOAK_URL="{keycloak_url}"\n')
                f.write(f'export KEYCLOAK_REALM="{realm}"\n')
                f.write('export AUTH_PROVIDER="keycloak"\n')
        except Exception as e:
            self.error(f"Failed to save .env file: {e}")
            return False

        # Save .json file with metadata
        json_file = os.path.join(oauth_tokens_dir, f"{agent_name}-token.json")
        token_json = {
            "agent_name": agent_name,
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "generated_at": generated_at,
            "expires_at": expires_at,
            "provider": "keycloak",
            "keycloak_url": keycloak_url,
            "keycloak_realm": realm,
            "client_id": client_id,
            "scope": "openid email profile",
            "metadata": {
                "generated_by": "generate_tokens.py",
                "script_version": "1.0",
                "token_format": "JWT",
                "auth_method": "client_credentials"
            }
        }

        try:
            with open(json_file, 'w') as f:
                json.dump(token_json, f, indent=2)
        except Exception as e:
            self.error(f"Failed to save JSON file: {e}")
            return False

        self.success(f"Token saved to: {env_file}")
        self.success(f"Token metadata saved to: {json_file}")

        # Display token info
        print(f"\nAccess Token: {access_token}")
        if expires_in:
            print(f"Expires in: {expires_in} seconds")
            if expires_at:
                expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                print(f"Expires at: {expiry_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print()

        return True

    def generate_token_for_agent(self, agent_name: str, client_id: str = None,
                                client_secret: str = None, keycloak_url: str = None,
                                realm: str = "mcp-gateway", oauth_tokens_dir: str = None) -> bool:
        """Generate token for a single agent"""
        if oauth_tokens_dir is None:
            oauth_tokens_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.oauth-tokens')

        # Load config from JSON if parameters not provided
        config = None
        if not all([client_id, client_secret, keycloak_url]):
            config = self.load_agent_config(agent_name, oauth_tokens_dir)
            if not config:
                return False

        # Use provided parameters or fall back to config
        if not client_id:
            client_id = config.get('client_id')
        if not client_secret:
            client_secret = config.get('client_secret')
        if not keycloak_url:
            keycloak_url = config.get('keycloak_url') or config.get('gateway_url', '').split('/realms/')[0]

        # Also try to get realm from config
        if config and realm == "mcp-gateway":
            config_realm = config.get('keycloak_realm') or config.get('realm')
            if config_realm:
                realm = config_realm

        # Validate required parameters
        if not client_id:
            self.error("CLIENT_ID is required. Provide via --client-id or in config file.")
            return False
        if not client_secret:
            self.error("CLIENT_SECRET is required. Provide via --client-secret or in config file.")
            return False
        if not keycloak_url:
            self.error("KEYCLOAK_URL is required. Provide via --keycloak-url or in config file.")
            return False

        print(f"Requesting access token for agent: {agent_name}")

        # Get token from Keycloak
        token_data = self.get_token_from_keycloak(client_id, client_secret, keycloak_url, realm)
        if not token_data:
            return False

        self.success("Access token generated successfully!")

        # Save token files
        return self.save_token_files(agent_name, token_data, client_id, client_secret,
                                   keycloak_url, realm, oauth_tokens_dir)

    def find_agent_configs(self, oauth_tokens_dir: str) -> List[str]:
        """Find all agent-{}.json files, excluding agent-{}-token.json files"""
        if not os.path.exists(oauth_tokens_dir):
            self.warning(f"OAuth tokens directory not found: {oauth_tokens_dir}")
            return []

        # Find all agent-*.json files
        pattern = os.path.join(oauth_tokens_dir, "agent-*.json")
        all_files = glob.glob(pattern)

        # Filter out token files (agent-*-token.json)
        agent_configs = []
        for file_path in all_files:
            filename = os.path.basename(file_path)
            if not filename.endswith('-token.json'):
                # Use the full filename without extension as agent name
                agent_name = filename[:-5]  # Remove '.json' (5 chars)
                agent_configs.append(agent_name)

        return sorted(agent_configs)

    def generate_tokens_for_all_agents(self, oauth_tokens_dir: str = None,
                                     keycloak_url: str = None, realm: str = "mcp-gateway") -> bool:
        """Generate tokens for all agents found in .oauth-tokens directory"""
        if oauth_tokens_dir is None:
            oauth_tokens_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.oauth-tokens')

        self.log(f"Searching for agent configs in: {oauth_tokens_dir}")

        agent_configs = self.find_agent_configs(oauth_tokens_dir)

        if not agent_configs:
            self.warning("No agent configuration files found")
            return True

        self.success(f"Found {len(agent_configs)} agent configuration(s): {', '.join(agent_configs)}")

        success_count = 0
        total_count = len(agent_configs)

        for agent_name in agent_configs:
            print(f"\n{'='*60}")
            print(f"Processing agent: {agent_name}")
            print('='*60)

            try:
                if self.generate_token_for_agent(agent_name, keycloak_url=keycloak_url,
                                               realm=realm, oauth_tokens_dir=oauth_tokens_dir):
                    success_count += 1
                else:
                    self.error(f"Failed to generate token for agent: {agent_name}")
            except Exception as e:
                self.error(f"Exception while processing agent {agent_name}: {e}")

        print(f"\n{'='*60}")
        print(f"Token generation complete: {success_count}/{total_count} successful")
        print('='*60)

        return success_count == total_count


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Generate OAuth2 access tokens for MCP agents using Keycloak',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate tokens for all agents in .oauth-tokens directory
  python generate_tokens.py --all-agents

  # Generate token for specific agent
  python generate_tokens.py --agent-name my-agent

  # Generate token with custom parameters
  python generate_tokens.py --agent-name my-agent --client-id custom-client --keycloak-url http://localhost:8080

  # Generate tokens for all agents with custom Keycloak URL
  python generate_tokens.py --all-agents --keycloak-url http://localhost:8080
        """
    )

    parser.add_argument('--agent-name', type=str,
                       help='Specific agent name to generate token for')
    parser.add_argument('--all-agents', action='store_true',
                       help='Generate tokens for all agents found in .oauth-tokens directory')
    parser.add_argument('--client-id', type=str,
                       help='OAuth2 client ID (overrides config file)')
    parser.add_argument('--client-secret', type=str,
                       help='OAuth2 client secret (overrides config file)')
    parser.add_argument('--keycloak-url', type=str,
                       help='Keycloak server URL (overrides config file)')
    parser.add_argument('--realm', type=str, default='mcp-gateway',
                       help='Keycloak realm (default: mcp-gateway)')
    parser.add_argument('--oauth-dir', type=str,
                       help='OAuth tokens directory (default: ../../.oauth-tokens)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')

    args = parser.parse_args()

    # Validate arguments
    if not args.all_agents and not args.agent_name:
        parser.error("Must specify either --all-agents or --agent-name")

    if args.all_agents and args.agent_name:
        parser.error("Cannot specify both --all-agents and --agent-name")

    # Initialize token generator
    generator = TokenGenerator(verbose=args.verbose)

    # Determine oauth tokens directory
    oauth_tokens_dir = args.oauth_dir
    if oauth_tokens_dir is None:
        oauth_tokens_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.oauth-tokens')

    try:
        if args.all_agents:
            # Generate tokens for all agents
            success = generator.generate_tokens_for_all_agents(
                oauth_tokens_dir=oauth_tokens_dir,
                keycloak_url=args.keycloak_url,
                realm=args.realm
            )
        else:
            # Generate token for specific agent
            success = generator.generate_token_for_agent(
                agent_name=args.agent_name,
                client_id=args.client_id,
                client_secret=args.client_secret,
                keycloak_url=args.keycloak_url,
                realm=args.realm,
                oauth_tokens_dir=oauth_tokens_dir
            )

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        generator.warning("Operation interrupted by user")
        sys.exit(1)
    except Exception as e:
        generator.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()