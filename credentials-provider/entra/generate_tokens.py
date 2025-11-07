#!/usr/bin/env python3
"""
Generate Microsoft Entra ID (Azure AD) tokens for MCP agents.

This script supports multiple authentication flows:
1. Client Credentials Flow (for M2M/service accounts)
2. Device Code Flow (requires browser interaction)

Usage:
    # Generate tokens for all agents
    python generate_tokens.py --all-agents
    
    # Generate token for specific agent
    python generate_tokens.py --agent-name agent-my-agent
    
    # Client credentials flow (M2M)
    python generate_tokens.py --tenant-id <tenant_id> --client-id <client_id> \
                              --client-secret <secret> --flow client_credentials
    
    # Save tokens to file
    python generate_tokens.py --tenant-id <tenant_id> --client-id <client_id> \
                              --output tokens.json

Environment Variables:
    ENTRA_TENANT_ID: Azure AD tenant ID
    ENTRA_CLIENT_ID: Application (client) ID
    ENTRA_CLIENT_SECRET: Client secret (for client credentials flow)
"""

import argparse
import glob
import json
import logging
import os
import sys
import time
import requests
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List


class Colors:
    """ANSI color codes for console output"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


class EntraTokenGenerator:
    """Generate tokens from Microsoft Entra ID."""

    def __init__(
            self,
            tenant_id: Optional[str] = None,
            client_id: Optional[str] = None,
            client_secret: Optional[str] = None,
            authority: Optional[str] = None,
            verbose: bool = False
    ):
        """Initialize token generator.
        
        Args:
            tenant_id: Azure AD tenant ID
            client_id: Application (client) ID
            client_secret: Client secret (required for client credentials flow)
            authority: Custom authority URL (defaults to global Azure AD)
            verbose: Enable verbose logging
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.verbose = verbose
        self.setup_logging()

        if tenant_id:
            self.authority = authority or f"https://login.microsoftonline.com/{tenant_id}"
            self.token_url = f"{self.authority}/oauth2/v2.0/token"
            self.device_code_url = f"{self.authority}/oauth2/v2.0/devicecode"
            self.auth_url = f"{self.authority}/oauth2/v2.0/authorize"

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

    def get_device_code_token(
            self,
            scope: str = "openid profile email User.Read offline_access"
    ) -> Dict[str, Any]:
        """Get tokens using device code flow (interactive).
        
        This is the recommended flow for CLI tools and testing.
        User will need to visit a URL and enter a code.
        
        Args:
            scope: OAuth2 scopes to request
            
        Returns:
            Dictionary containing access_token, refresh_token, etc.
        """
        print("Starting device code flow...")

        # Request device code
        data = {
            'client_id': self.client_id,
            'scope': scope
        }

        response = requests.post(self.device_code_url, data=data)
        response.raise_for_status()
        device_code_data = response.json()

        # Display instructions to user
        print("\n" + "=" * 70)
        print("DEVICE CODE AUTHENTICATION")
        print("=" * 70)
        print(f"\n1. Visit: {device_code_data['verification_uri']}")
        print(f"2. Enter code: {device_code_data['user_code']}")
        print(f"\nWaiting for authentication (expires in {device_code_data['expires_in']} seconds)...")
        print("=" * 70 + "\n")

        # Poll for token
        device_code = device_code_data['device_code']
        interval = device_code_data.get('interval', 5)
        expires_in = device_code_data['expires_in']
        start_time = time.time()

        while True:
            if time.time() - start_time > expires_in:
                raise TimeoutError("Device code expired before user completed authentication")

            time.sleep(interval)

            token_data = {
                'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
                'device_code': device_code,
                'client_id': self.client_id
            }

            # Add client_secret if available (required for confidential clients)
            if self.client_secret:
                token_data['client_secret'] = self.client_secret

            response = requests.post(self.token_url, data=token_data)
            result = response.json()

            if response.status_code == 200:
                print("✓ Authentication successful!")
                return result

            error = result.get('error')
            if error == 'authorization_pending':
                print(".", end="", flush=True)
                continue
            elif error == 'slow_down':
                interval += 5
                continue
            elif error in ['authorization_declined', 'bad_verification_code', 'expired_token']:
                raise ValueError(f"Authentication failed: {error}")
            else:
                raise ValueError(f"Unexpected error: {error} - {result.get('error_description')}")

    def get_client_credentials_token(
            self,
            scope: str = "https://graph.microsoft.com/.default"
    ) -> Dict[str, Any]:
        """Get token using client credentials flow (M2M).
        
        This flow is for service-to-service authentication.
        Requires client_secret to be set.
        
        Args:
            scope: OAuth2 scope (use .default for all configured permissions)
            
        Returns:
            Dictionary containing access_token
        """
        if not self.client_secret:
            raise ValueError("Client secret is required for client credentials flow")

        print("Requesting token using client credentials flow...")

        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': scope
        }

        try:
            response = requests.post(self.token_url, data=data)
            response.raise_for_status()

            token_data = response.json()
            print("✓ Token generated successfully!")

            return token_data
        except requests.exceptions.HTTPError as e:
            # Try to get detailed error message from response
            error_detail = "No additional details"
            try:
                error_data = response.json()
                error_detail = error_data.get('error_description', error_data.get('error', str(error_data)))
            except Exception as e:
                error_detail = response.text if response.text else str(e)

            self.error(f"HTTP Error: {e}")
            self.error(f"Details: {error_detail}")
            raise

    def refresh_token(
            self,
            refresh_token: str,
            scope: str = "openid profile email User.Read offline_access"
    ) -> Dict[str, Any]:
        """Refresh an access token.
        
        Args:
            refresh_token: The refresh token
            scope: OAuth2 scopes to request
            
        Returns:
            Dictionary containing new access_token and refresh_token
        """
        print("Refreshing access token...")

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.client_id,
            'scope': scope
        }

        if self.client_secret:
            data['client_secret'] = self.client_secret

        response = requests.post(self.token_url, data=data)
        response.raise_for_status()

        token_data = response.json()
        print("✓ Token refreshed successfully!")

        return token_data

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode JWT token (without validation) to inspect claims.
        
        Args:
            token: JWT token string
            
        Returns:
            Dictionary containing token claims
        """
        import base64

        # Split token into parts
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT token format")

        # Decode payload (add padding if needed)
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding

        decoded_bytes = base64.urlsafe_b64decode(payload)
        return json.loads(decoded_bytes)

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

    def find_agent_configs(self, oauth_tokens_dir: str) -> List[str]:
        """Find all agent-{}.json files for Entra ID, excluding agent-{}-token.json files"""
        if not os.path.exists(oauth_tokens_dir):
            self.warning(f"OAuth tokens directory not found: {oauth_tokens_dir}")
            return []

        # Find all agent-*.json files
        pattern = os.path.join(oauth_tokens_dir, "agent-*.json")
        all_files = glob.glob(pattern)

        # Filter out token files (agent-*-token.json) and non-Entra configs
        agent_configs = []
        skipped_configs = []

        for file_path in all_files:
            filename = os.path.basename(file_path)
            if filename.endswith('-token.json'):
                continue

            # Use the full filename without extension as agent name
            agent_name = filename[:-5]  # Remove '.json' (5 chars)

            # Check if this config is for Entra ID
            try:
                with open(file_path, 'r') as f:
                    config = json.load(f)
                    auth_provider = config.get('auth_provider', '').lower()

                    # Check if config has Entra-specific fields or provider is set to entra
                    has_entra_fields = any([
                        'tenant_id' in config,
                        'entra_tenant_id' in config,
                        auth_provider == 'entra',
                        auth_provider == 'azure',
                        auth_provider == 'azuread'
                    ])

                    # Skip if explicitly set to another provider
                    if auth_provider and auth_provider not in ['entra', 'azure', 'azuread', '']:
                        skipped_configs.append((agent_name, auth_provider))
                        continue

                    # Only include if it has Entra fields or no provider specified
                    if has_entra_fields or not auth_provider:
                        agent_configs.append(agent_name)
                    else:
                        skipped_configs.append((agent_name, 'unknown'))

            except (json.JSONDecodeError, Exception) as e:
                self.warning(f"Failed to parse {filename}: {e}")
                continue

        if skipped_configs and self.verbose:
            self.log(f"Skipped {len(skipped_configs)} non-Entra configs:")
            for name, provider in skipped_configs:
                self.log(f"  - {name} (provider: {provider})")

        return sorted(agent_configs)

    def save_token_files(self, agent_name: str, token_data: Dict[str, Any],
                         tenant_id: str, client_id: str, client_secret: str,
                         scope: str, oauth_tokens_dir: str) -> bool:
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
                f.write(f'export TENANT_ID="{tenant_id}"\n')
                f.write(f'export CLIENT_ID="{client_id}"\n')
                f.write(f'export CLIENT_SECRET="{client_secret}"\n')
                f.write('export AUTH_PROVIDER="entra"\n')
        except Exception as e:
            self.error(f"Failed to save .env file: {e}")
            return False

        # Save .json file with metadata
        json_file = os.path.join(oauth_tokens_dir, f"{agent_name}-token.json")
        token_json = {
            "agent_name": agent_name,
            "access_token": access_token,
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_in": expires_in,
            "generated_at": generated_at,
            "expires_at": expires_at,
            "provider": "entra",
            "tenant_id": tenant_id,
            "client_id": client_id,
            "scope": scope,
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

        # Display token info (redacted for security)
        def redact_sensitive_value(value: str, show_chars: int = 8) -> str:
            if not value or len(value) <= show_chars:
                return "*" * len(value) if value else ""
            return value[:show_chars] + "*" * (len(value) - show_chars)

        redacted_token = redact_sensitive_value(access_token, 8)
        print(f"\nAccess Token: {redacted_token}")
        if expires_in:
            print(f"Expires in: {expires_in} seconds")
            if expires_at:
                expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                print(f"Expires at: {expiry_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print()

        return True

    def generate_token_for_agent(self, agent_name: str, tenant_id: str = None,
                                 client_id: str = None, client_secret: str = None,
                                 scope: str = None, oauth_tokens_dir: str = None,
                                 flow: str = "client_credentials") -> bool:
        """Generate token for a single agent"""
        if oauth_tokens_dir is None:
            oauth_tokens_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                            '.oauth-tokens')

        # Load config from JSON if parameters not provided
        config = None
        if not all([tenant_id, client_id, client_secret]):
            config = self.load_agent_config(agent_name, oauth_tokens_dir)
            if not config:
                return False

        # Use provided parameters or fall back to config
        if not tenant_id:
            tenant_id = config.get('tenant_id') or config.get('entra_tenant_id')
        if not client_id:
            client_id = config.get('client_id') or config.get('entra_client_id')
        if not client_secret:
            client_secret = config.get('client_secret') or config.get('entra_client_secret')
        if not scope:
            scope = config.get('scope', 'https://graph.microsoft.com/.default')

        # Validate required parameters
        if not tenant_id:
            self.error("TENANT_ID is required. Provide via --tenant-id or in config file.")
            return False
        if not client_id:
            self.error("CLIENT_ID is required. Provide via --client-id or in config file.")
            return False
        if not client_secret:
            self.error("CLIENT_SECRET is required. Provide via --client-secret or in config file.")
            return False

        # Update instance variables
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.authority = f"https://login.microsoftonline.com/{tenant_id}"
        self.token_url = f"{self.authority}/oauth2/v2.0/token"

        print(f"Requesting access token for agent: {agent_name}")

        # Get token from Entra ID
        try:
            if flow == "client_credentials":
                token_data = self.get_client_credentials_token(scope=scope)
            elif flow == "device_code":
                token_data = self.get_device_code_token(scope=scope)
            else:
                self.error(f"Unsupported flow: {flow}")
                return False

            if not token_data:
                return False

            self.success("Access token generated successfully!")

            # Save token files
            return self.save_token_files(agent_name, token_data, tenant_id, client_id,
                                         client_secret, scope, oauth_tokens_dir)

        except Exception as e:
            self.error(f"Failed to generate token: {e}")
            return False

    def generate_tokens_for_all_agents(self, oauth_tokens_dir: str = None,
                                       tenant_id: str = None, scope: str = None,
                                       flow: str = "client_credentials") -> bool:
        """Generate tokens for all agents found in .oauth-tokens directory"""
        if oauth_tokens_dir is None:
            oauth_tokens_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                            '.oauth-tokens')

        self.log(f"Searching for Entra ID agent configs in: {oauth_tokens_dir}")

        # Get all agent files first to show total
        all_pattern = os.path.join(oauth_tokens_dir, "agent-*.json")
        all_files = [f for f in glob.glob(all_pattern) if not f.endswith('-token.json')]
        total_files = len(all_files)

        agent_configs = self.find_agent_configs(oauth_tokens_dir)

        if not agent_configs:
            if total_files > 0:
                self.warning(
                    f"No Entra ID agent configurations found (found {total_files} agent config(s) for other providers)")
                self.warning("To generate tokens for Entra ID agents, ensure config files have:")
                self.warning("  - 'tenant_id' field, OR")
                self.warning("  - 'auth_provider': 'entra'")
            else:
                self.warning("No agent configuration files found in directory")
            return True

        skipped_count = total_files - len(agent_configs)
        if skipped_count > 0:
            print(f"Skipped {skipped_count} non-Entra config(s) (use --verbose to see details)")

        self.success(f"Found {len(agent_configs)} Entra ID agent configuration(s): {', '.join(agent_configs)}")

        success_count = 0
        total_count = len(agent_configs)

        for agent_name in agent_configs:
            print(f"\n{'=' * 60}")
            print(f"Processing agent: {agent_name}")
            print('=' * 60)

            try:
                if self.generate_token_for_agent(agent_name, tenant_id=tenant_id,
                                                 scope=scope, oauth_tokens_dir=oauth_tokens_dir,
                                                 flow=flow):
                    success_count += 1
                else:
                    self.error(f"Failed to generate token for agent: {agent_name}")
            except Exception as e:
                self.error(f"Exception while processing agent {agent_name}: {e}")
                if self.verbose:
                    import traceback
                    traceback.print_exc()

        print(f"\n{'=' * 60}")
        print(f"Token generation complete: {success_count}/{total_count} successful")
        print('=' * 60)

        return success_count == total_count


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate Microsoft Entra ID tokens for MCP agents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate tokens for all agents in .oauth-tokens directory
  python generate_tokens.py --all-agents

  # Generate token for specific agent
  python generate_tokens.py --agent-name agent-my-agent

  # Generate token with custom parameters
  python generate_tokens.py --agent-name agent-my-agent --tenant-id <tenant_id> --client-id <client_id>

  # Generate tokens for all agents with custom Tenant ID
  python generate_tokens.py --all-agents --tenant-id <tenant_id>

  # Traditional usage (non-agent mode)
  python generate_tokens.py --tenant-id <tenant_id> --client-id <client_id> --flow client_credentials
        """
    )

    # Agent-related arguments
    parser.add_argument(
        '--agent-name',
        type=str,
        help='Specific agent name to generate token for'
    )

    parser.add_argument(
        '--all-agents',
        action='store_true',
        help='Generate tokens for all agents found in .oauth-tokens directory'
    )

    parser.add_argument(
        '--oauth-dir',
        type=str,
        help='OAuth tokens directory (default: ../../.oauth-tokens)'
    )

    # Entra ID configuration
    parser.add_argument(
        '--tenant-id',
        default=os.environ.get('ENTRA_TENANT_ID'),
        help='Azure AD tenant ID (or env: ENTRA_TENANT_ID)'
    )

    parser.add_argument(
        '--client-id',
        default=os.environ.get('ENTRA_CLIENT_ID'),
        help='Application (client) ID (or env: ENTRA_CLIENT_ID)'
    )

    parser.add_argument(
        '--client-secret',
        default=os.environ.get('ENTRA_CLIENT_SECRET'),
        help='Client secret (or env: ENTRA_CLIENT_SECRET)'
    )

    parser.add_argument(
        '--flow',
        choices=['device_code', 'client_credentials', 'refresh'],
        default='client_credentials',
        help='Authentication flow to use (default: client_credentials for agents, device_code for legacy)'
    )

    parser.add_argument(
        '--scope',
        help='OAuth2 scopes (space-separated or comma-separated)'
    )

    parser.add_argument(
        '--refresh-token',
        help='Refresh token (for refresh flow)'
    )

    parser.add_argument(
        '--output',
        help='Output file path to save tokens (legacy mode only)'
    )

    parser.add_argument(
        '--decode',
        action='store_true',
        help='Decode and display token claims'
    )

    parser.add_argument(
        '--authority',
        help='Custom authority URL (for sovereign clouds)'
    )

    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    # Validate argument combinations
    agent_mode = args.all_agents or args.agent_name
    legacy_mode = not agent_mode

    if args.all_agents and args.agent_name:
        parser.error("Cannot specify both --all-agents and --agent-name")

    # Create token generator
    generator = EntraTokenGenerator(
        tenant_id=args.tenant_id,
        client_id=args.client_id,
        client_secret=args.client_secret,
        authority=args.authority,
        verbose=args.verbose
    )

    # Determine oauth tokens directory
    oauth_tokens_dir = args.oauth_dir
    if oauth_tokens_dir is None:
        oauth_tokens_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.oauth-tokens')

    try:
        # Agent mode - batch processing
        if agent_mode:
            if args.all_agents:
                # Generate tokens for all agents
                success = generator.generate_tokens_for_all_agents(
                    oauth_tokens_dir=oauth_tokens_dir,
                    tenant_id=args.tenant_id,
                    scope=args.scope,
                    flow=args.flow
                )
            else:
                # Generate token for specific agent
                success = generator.generate_token_for_agent(
                    agent_name=args.agent_name,
                    tenant_id=args.tenant_id,
                    client_id=args.client_id,
                    client_secret=args.client_secret,
                    scope=args.scope,
                    oauth_tokens_dir=oauth_tokens_dir,
                    flow=args.flow
                )

            sys.exit(0 if success else 1)

        # Legacy mode - single token generation
        else:
            # Validate required arguments for legacy mode
            if not args.tenant_id:
                parser.error("--tenant-id is required (or set ENTRA_TENANT_ID)")

            if not args.client_id:
                parser.error("--client-id is required (or set ENTRA_CLIENT_ID)")

            # Generate tokens based on flow
            token_data = None
            if args.flow == 'device_code':
                scope = args.scope or "openid profile email User.Read offline_access"
                token_data = generator.get_device_code_token(scope=scope)

            elif args.flow == 'client_credentials':
                scope = args.scope or "https://graph.microsoft.com/.default"
                token_data = generator.get_client_credentials_token(scope=scope)

            elif args.flow == 'refresh':
                if not args.refresh_token:
                    parser.error("--refresh-token is required for refresh flow")
                scope = args.scope or "openid profile email User.Read offline_access"
                token_data = generator.refresh_token(
                    refresh_token=args.refresh_token,
                    scope=scope
                )

            # Add metadata
            token_data['generated_at'] = time.time()
            token_data['expires_at'] = time.time() + token_data.get('expires_in', 3600)

            # Decode token if requested
            if args.decode and 'access_token' in token_data:
                print("\n" + "=" * 70)
                print("TOKEN CLAIMS")
                print("=" * 70)
                claims = generator.decode_token(token_data['access_token'])
                print(json.dumps(claims, indent=2))
                print("=" * 70 + "\n")

            # Output tokens
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(token_data, f, indent=2)
                print(f"\n✓ Tokens saved to: {args.output}")
            else:
                print("\n" + "=" * 70)
                print("TOKENS")
                print("=" * 70)
                print(json.dumps(token_data, indent=2))
                print("=" * 70)

            # Display useful information
            print("\nToken Information:")
            print(f"  Token Type: {token_data.get('token_type', 'Bearer')}")
            print(f"  Expires In: {token_data.get('expires_in', 'N/A')} seconds")
            if 'scope' in token_data:
                print(f"  Scopes: {token_data['scope']}")

            return 0

    except KeyboardInterrupt:
        generator.warning("Operation interrupted by user")
        sys.exit(1)
    except Exception as e:
        generator.error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    sys.exit(main())
