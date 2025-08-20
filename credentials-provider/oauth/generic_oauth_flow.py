#!/usr/bin/env python3
"""
Generic OAuth 2.0 Authorization Flow Script

A standalone, generic OAuth 2.0 authorization script that can work with multiple providers
including Atlassian, Google, GitHub, and others. Now powered by FastAPI for reliable callback handling.

This script provides:
1. Multi-provider OAuth 2.0 support with configurable providers
2. FastAPI-based local callback server for reliable authorization code handling
3. Secure file-based token storage
4. Automatic token refresh functionality
5. PKCE support for enhanced security
6. Beautiful browser callback pages with auto-close functionality
7. Immediate token exchange during callback for better user experience
8. Comprehensive logging and error handling

Usage:
    # Interactive mode (recommended for first-time users)
    python generic_oauth_flow.py
    
    # Command line mode
    python generic_oauth_flow.py --provider atlassian --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
    python generic_oauth_flow.py --provider google --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
    python generic_oauth_flow.py --config-file oauth_config.json
    
    # Force interactive mode even with partial args
    python generic_oauth_flow.py --interactive

Environment variables are also supported:
- EGRESS_OAUTH_CLIENT_ID
- EGRESS_OAUTH_CLIENT_SECRET
- EGRESS_OAUTH_REDIRECT_URI
- EGRESS_OAUTH_SCOPE

Dependencies:
    pip install requests pyyaml
"""

import argparse
import base64
import hashlib
import http.server
import json
import logging
import os
import secrets
import socketserver
import sys
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Removed keyring dependency - using file-based storage only
import requests
import yaml

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("generic-oauth")

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Load .env from the same directory as this script
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        logger.debug(f"Loaded environment variables from {env_file}")
    else:
        # Fallback: try parent directory (project root)
        env_file_parent = Path(__file__).parent.parent / '.env'
        if env_file_parent.exists():
            load_dotenv(env_file_parent)
            logger.debug(f"Loaded environment variables from {env_file_parent}")
        else:
            # Final fallback: try current working directory
            load_dotenv()
            logger.debug("Tried to load .env from current working directory")
except ImportError:
    logger.debug("python-dotenv not available, skipping .env loading")


def _validate_environment_variables() -> None:
    """Validate that all required INGRESS and EGRESS OAuth environment variables are set."""
    required_ingress_vars = [
        "INGRESS_OAUTH_USER_POOL_ID",
        "INGRESS_OAUTH_CLIENT_ID",
        "INGRESS_OAUTH_CLIENT_SECRET"
    ]
    
    required_egress_vars = [
        "EGRESS_OAUTH_CLIENT_ID",
        "EGRESS_OAUTH_CLIENT_SECRET",
        "EGRESS_OAUTH_REDIRECT_URI"
    ]
    
    missing_vars = []
    
    # Check INGRESS variables
    for var in required_ingress_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    # Check EGRESS variables
    for var in required_egress_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error("Missing required environment variables:")
        for var in missing_vars:
            logger.error(f"  - {var}")
        logger.error("\nPlease set the following environment variables:")
        logger.error("INGRESS OAuth variables (for MCP Gateway authentication):")
        for var in required_ingress_vars:
            if var in missing_vars:
                logger.error(f"  export {var}=<value>")
        logger.error("\nEGRESS OAuth variables (for external OAuth providers):")
        for var in required_egress_vars:
            if var in missing_vars:
                logger.error(f"  export {var}=<value>")
        logger.error("\nOr add them to your .env file")
        raise SystemExit(1)
    
    logger.debug("All required INGRESS and EGRESS OAuth environment variables are set")


# Environment variable validation will be done conditionally in main()

# Constants
TOKEN_EXPIRY_MARGIN = 300  # 5 minutes in seconds
# Removed keyring service name - using file-based storage only
DEFAULT_REDIRECT_PORT = 8080

# Load OAuth provider configurations from YAML file
def _load_oauth_providers() -> Dict[str, Any]:
    """Load OAuth provider configurations from YAML file."""
    yaml_path = Path(__file__).parent / "oauth_providers.yaml"
    
    # Fallback to embedded minimal config if YAML file doesn't exist
    if not yaml_path.exists():
        logger.warning(f"OAuth providers YAML file not found at {yaml_path}")
        logger.warning("Using minimal embedded configuration")
        return {
            "atlassian": {
                "display_name": "Atlassian Cloud",
                "auth_url": "https://auth.atlassian.com/authorize",
                "token_url": "https://auth.atlassian.com/oauth/token",
                "user_info_url": "https://api.atlassian.com/oauth/token/accessible-resources",
                "scopes": ["read:jira-work", "write:jira-work", "offline_access"],
                "response_type": "code",
                "grant_type": "authorization_code",
                "audience": "api.atlassian.com",
                "requires_pkce": False,
                "additional_params": {"prompt": "consent"}
            }
        }
    
    try:
        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f)
            providers = config.get('providers', {})
            logger.debug(f"Loaded {len(providers)} OAuth providers from {yaml_path}")
            return providers
    except Exception as e:
        logger.error(f"Failed to load OAuth providers from YAML: {e}")
        return {}

# Load OAuth provider configurations
OAUTH_PROVIDERS = _load_oauth_providers()

# Global variables for callback handling
authorization_code = None
received_state = None
callback_received = False
callback_error = None
pkce_verifier = None
oauth_config_global = None


@dataclass
class OAuthConfig:
    """OAuth 2.0 configuration for any provider."""
    provider: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: List[str]
    provider_config: Dict[str, Any]
    cloud_id: Optional[str] = None
    refresh_token: Optional[str] = None
    access_token: Optional[str] = None
    expires_at: Optional[float] = None
    additional_params: Optional[Dict[str, str]] = None

    @property
    def is_token_expired(self) -> bool:
        """Check if the access token is expired or will expire soon."""
        if not self.access_token or not self.expires_at:
            return True
        return time.time() + TOKEN_EXPIRY_MARGIN >= self.expires_at

    def get_authorization_url(self, state: str, pkce_challenge: Optional[str] = None) -> str:
        """Get the authorization URL for the OAuth 2.0 flow."""
        params = {
            "client_id": self.client_id,
            "scope": " ".join(self.scopes),
            "redirect_uri": self.redirect_uri,
            "response_type": self.provider_config["response_type"],
            "state": state,
        }

        # Add provider-specific parameters
        if "audience" in self.provider_config:
            params["audience"] = self.provider_config["audience"]

        # Add PKCE challenge if required
        if pkce_challenge and self.provider_config.get("requires_pkce", False):
            params["code_challenge"] = pkce_challenge
            params["code_challenge_method"] = "S256"

        # Add any additional parameters
        if self.additional_params:
            params.update(self.additional_params)
        if "additional_params" in self.provider_config:
            params.update(self.provider_config["additional_params"])

        return f"{self.provider_config['auth_url']}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_tokens(self, code: str, pkce_verifier: Optional[str] = None) -> bool:
        """Exchange the authorization code for access and refresh tokens."""
        try:
            payload = {
                "grant_type": self.provider_config["grant_type"],
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
            }

            # Add PKCE verifier if required
            if pkce_verifier and self.provider_config.get("requires_pkce", False):
                payload["code_verifier"] = pkce_verifier

            headers = {"Accept": "application/json"}
            
            # Apply provider-specific headers if configured
            if "token_headers" in self.provider_config:
                headers.update(self.provider_config["token_headers"])

            logger.info(f"Exchanging authorization code for tokens at {self.provider_config['token_url']}")
            
            response = requests.post(
                self.provider_config["token_url"],
                data=payload,
                headers=headers,
                timeout=30
            )

            logger.debug(f"Token exchange response status: {response.status_code}")
            
            if not response.ok:
                logger.error(f"Token exchange failed with status {response.status_code}. Response: {response.text}")
                return False

            token_data = response.json()

            if "access_token" not in token_data:
                logger.error(f"Access token not found in response. Keys found: {list(token_data.keys())}")
                return False

            self.access_token = token_data["access_token"]
            
            # Handle refresh token (not all providers support it)
            if "refresh_token" in token_data:
                self.refresh_token = token_data["refresh_token"]
            elif "offline_access" in self.scopes:
                logger.warning("Refresh token not found despite 'offline_access' scope being included.")

            # Set token expiry
            if "expires_in" in token_data:
                self.expires_at = time.time() + token_data["expires_in"]

            # Get provider-specific info (like cloud ID for Atlassian)
            self._get_provider_info()

            # Save the tokens
            self._save_tokens()

            logger.info("🎉 OAuth authorization flow completed successfully!")
            if self.expires_at:
                expires_in = int(self.expires_at - time.time())
                logger.info(f"Access token expires in {expires_in} seconds")
            
            if self.cloud_id:
                logger.info(f"Retrieved Cloud ID: {self.cloud_id}")

            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during token exchange: {e}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {e}")
            return False

    def refresh_access_token(self) -> bool:
        """Refresh the access token using the refresh token."""
        if not self.refresh_token:
            logger.error("No refresh token available")
            return False

        try:
            payload = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            }

            logger.debug("Refreshing access token...")
            response = requests.post(self.provider_config["token_url"], data=payload, timeout=30)
            response.raise_for_status()

            token_data = response.json()
            self.access_token = token_data["access_token"]
            
            # Refresh token might be rotated
            if "refresh_token" in token_data:
                self.refresh_token = token_data["refresh_token"]
                
            if "expires_in" in token_data:
                self.expires_at = time.time() + token_data["expires_in"]

            self._save_tokens()
            logger.info("Successfully refreshed access token")
            return True

        except Exception as e:
            logger.error(f"Failed to refresh access token: {e}")
            return False

    def ensure_valid_token(self) -> bool:
        """Ensure the access token is valid, refreshing if necessary."""
        if not self.is_token_expired:
            return True
        return self.refresh_access_token()

    def _get_provider_info(self) -> None:
        """Get provider-specific information (e.g., cloud ID for Atlassian)."""
        # Check if provider requires cloud ID from user info
        if self.provider_config.get("requires_cloud_id") and self.provider_config.get("cloud_id_from_user_info") and self.access_token:
            try:
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(self.provider_config["user_info_url"], headers=headers, timeout=30)
                response.raise_for_status()

                resources = response.json()
                if resources and len(resources) > 0:
                    # Generic handling - assumes first resource has an 'id' field
                    self.cloud_id = resources[0].get("id")
                    if self.cloud_id:
                        logger.debug(f"Found cloud ID for {self.provider}: {self.cloud_id}")
                else:
                    logger.warning(f"No resources found for {self.provider}")
            except Exception as e:
                logger.error(f"Failed to get cloud ID for {self.provider}: {e}")

    # Removed keyring username method - using file-based storage only

    def _save_tokens(self) -> None:
        """Save the tokens securely using file-based storage."""
        try:
            token_data = {
                "provider": self.provider,
                "refresh_token": self.refresh_token,
                "access_token": self.access_token,
                "expires_at": self.expires_at,
                "cloud_id": self.cloud_id,
                "scopes": self.scopes,
            }

            # Save to file
            self._save_tokens_to_file(token_data)

        except Exception as e:
            logger.error(f"Failed to save tokens: {e}")

    def _save_tokens_to_file(self, token_data: Dict) -> None:
        """Save tokens to a file as fallback storage."""
        try:
            # Create provider-specific directory structure (with backwards compatibility)
            primary_token_dir = Path.cwd() / ".oauth-tokens"
            primary_token_dir.mkdir(exist_ok=True, mode=0o700)
            
            # Primary token file with provider in name
            token_path = primary_token_dir / f"oauth-{self.provider}-{self.client_id}.json"
            
            # Save essential token data
            essential_token_data = {
                "provider": self.provider,
                "refresh_token": self.refresh_token,
                "access_token": self.access_token,
                "expires_at": self.expires_at,
                "cloud_id": self.cloud_id,
            }
            
            with open(token_path, "w") as f:
                json.dump(essential_token_data, f, indent=2)
            
            # Secure the file
            token_path.chmod(0o600)
            logger.info(f"📁 Saved OAuth tokens to: {token_path}")

            # Save a readable version with usage examples
            readable_token_path = primary_token_dir / f"oauth-{self.provider}-{self.client_id}-readable.json"
            readable_data = {
                "provider": self.provider,
                "provider_display_name": self.provider_config.get("display_name", self.provider),
                "client_id": self.client_id,
                "cloud_id": self.cloud_id,
                "scopes": self.scopes,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at,
                "expires_at_human": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(self.expires_at)) if self.expires_at else None,
                "saved_at": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
                "usage_examples": {
                    "curl_with_bearer": f"curl -H 'Authorization: Bearer {self.access_token}' {self.provider_config.get('user_info_url', '<API_ENDPOINT>')}",
                    "python_requests": f"headers = {{'Authorization': 'Bearer {self.access_token}'}}; requests.get('<API_ENDPOINT>', headers=headers)",
                    "token_file_location": f"The token is saved at: {token_path}",
                    "vscode_mcp_config": f"VS Code MCP config saved at: {primary_token_dir}/vscode_mcp.json",
                    "roocode_mcp_config": f"Roocode MCP config saved at: {primary_token_dir}/mcp.json"
                }
            }
            
            with open(readable_token_path, "w") as f:
                json.dump(readable_data, f, indent=2)
            
            readable_token_path.chmod(0o600)
            logger.info(f"📄 Saved readable token info to: {readable_token_path}")

            # Create VS Code MCP configuration file for supported providers
            self._create_vscode_mcp_config(primary_token_dir)
            
            # Create Roocode MCP configuration file for supported providers
            self._create_roocode_mcp_config(primary_token_dir)

        except Exception as e:
            logger.error(f"Failed to save tokens to file: {e}")

    def _create_vscode_mcp_config(self, token_dir: Path) -> None:
        """Create VS Code MCP configuration file for supported providers."""
        try:
            # Only create MCP config for providers that have MCP gateway support
            if self.provider not in ["atlassian"]:
                logger.debug(f"Skipping VS Code MCP config - {self.provider} not supported")
                return
            
            vscode_config_path = token_dir / "vscode_mcp.json"
            
            # Load environment variables for MCP Gateway configuration
            registry_url = os.getenv("REGISTRY_URL", "https://mcpgateway.ddns.net")
            aws_region = os.getenv("AWS_REGION", "us-east-1")
            user_pool_id = os.getenv("INGRESS_OAUTH_USER_POOL_ID")
            
            # Get the appropriate client ID - use the MCP Gateway client ID from env
            mcp_client_id = os.getenv("INGRESS_OAUTH_CLIENT_ID")
            
            # Get MCP Gateway auth token
            mcp_auth_token = os.getenv("MCP_SERVER1_AUTH_TOKEN", "")
            if mcp_auth_token.startswith('"') and mcp_auth_token.endswith('"'):
                mcp_auth_token = mcp_auth_token[1:-1]  # Remove quotes
            
            # Create the VS Code MCP configuration
            mcp_config = {
                "mcp": {
                    "servers": {}
                }
            }
            
            if self.provider == "atlassian":
                mcp_config["mcp"]["servers"]["atlassian"] = {
                    "url": f"{registry_url}/atlassian/mcp",
                    "headers": {
                        # MCP Gateway authentication headers
                        "X-Authorization": f"Bearer {mcp_auth_token}",
                        "X-User-Pool-Id": user_pool_id,
                        "X-Client-Id": mcp_client_id,
                        "X-Region": aws_region,
                        # Atlassian-specific headers
                        "Authorization": f"Bearer {self.access_token}",
                        "X-Atlassian-Cloud-Id": self.cloud_id or ""
                    }
                }
            
            # Save the VS Code MCP configuration
            with open(vscode_config_path, "w") as f:
                json.dump(mcp_config, f, indent=4)
            
            vscode_config_path.chmod(0o600)
            logger.info(f"🔧 Created VS Code MCP configuration: {vscode_config_path}")
            
        except Exception as e:
            logger.error(f"Failed to create VS Code MCP configuration: {e}")

    def _create_roocode_mcp_config(self, token_dir: Path) -> None:
        """Create Roocode MCP configuration file for supported providers."""
        try:
            # Only create MCP config for providers that have MCP gateway support
            if self.provider not in ["atlassian"]:
                logger.debug(f"Skipping Roocode MCP config - {self.provider} not supported")
                return
            
            roocode_config_path = token_dir / "mcp.json"
            
            # Load environment variables for MCP Gateway configuration
            registry_url = os.getenv("REGISTRY_URL", "https://mcpgateway.ddns.net")
            aws_region = os.getenv("AWS_REGION", "us-east-1")
            user_pool_id = os.getenv("INGRESS_OAUTH_USER_POOL_ID")
            
            # Get the appropriate client ID - use the MCP Gateway client ID from env
            mcp_client_id = os.getenv("INGRESS_OAUTH_CLIENT_ID")
            
            # Get MCP Gateway auth token
            mcp_auth_token = os.getenv("MCP_SERVER1_AUTH_TOKEN", "")
            if mcp_auth_token.startswith('"') and mcp_auth_token.endswith('"'):
                mcp_auth_token = mcp_auth_token[1:-1]  # Remove quotes
            
            # Create the Roocode MCP configuration
            mcp_config = {
                "mcpServers": {}
            }
            
            if self.provider == "atlassian":
                mcp_config["mcpServers"]["atlassian"] = {
                    "type": "streamable-http",
                    "url": f"{registry_url}/atlassian/mcp",
                    "headers": {
                        # MCP Gateway authentication headers
                        "X-Authorization": f"Bearer {mcp_auth_token}",
                        "X-User-Pool-Id": user_pool_id,
                        "X-Client-Id": mcp_client_id,
                        "X-Region": aws_region,
                        # Atlassian-specific headers
                        "Authorization": f"Bearer {self.access_token}",
                        "X-Atlassian-Cloud-Id": self.cloud_id or ""
                    },
                    "disabled": False,
                    "alwaysAllow": []
                }
            
            # Save the Roocode MCP configuration
            with open(roocode_config_path, "w") as f:
                json.dump(mcp_config, f, indent=2)
            
            roocode_config_path.chmod(0o600)
            logger.info(f"🔧 Created Roocode MCP configuration: {roocode_config_path}")
            
        except Exception as e:
            logger.error(f"Failed to create Roocode MCP configuration: {e}")

    @staticmethod
    def load_tokens(provider: str, client_id: str) -> Dict[str, Any]:
        """Load tokens from file storage."""
        # Try primary token file format first
        primary_tokens = OAuthConfig._load_tokens_from_file(provider, client_id)
        if primary_tokens:
            return primary_tokens
        
        return {}


    @staticmethod
    def _load_tokens_from_file(provider: str, client_id: str) -> Dict[str, Any]:
        """Load tokens from primary file format."""
        token_path = Path.cwd() / ".oauth-tokens" / f"oauth-{provider}-{client_id}.json"

        if not token_path.exists():
            return {}

        try:
            with open(token_path) as f:
                token_data = json.load(f)
                logger.debug(f"Loaded OAuth tokens from file {token_path}")
                return token_data
        except Exception as e:
            logger.error(f"Failed to load tokens from file: {e}")
            return {}


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    # Generate code verifier (43-128 characters)
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    
    # Generate code challenge
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    
    return code_verifier, code_challenge


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback."""

    def do_GET(self) -> None:
        """Handle GET requests (OAuth callback)."""
        global authorization_code, callback_received, callback_error, received_state, oauth_config_global

        parsed_path = urllib.parse.urlparse(self.path)
        logger.debug(f"CallbackHandler received GET request for: {self.path}")

        # Ignore favicon requests politely
        if parsed_path.path == "/favicon.ico":
            self.send_error(404, "File not found")
            logger.debug("CallbackHandler: Ignored /favicon.ico request.")
            return

        # Process only /callback path
        if parsed_path.path != "/callback":
            self.send_error(404, "Not Found: Only /callback is supported.")
            logger.warning(
                f"CallbackHandler: Received request for unexpected path: {parsed_path.path}"
            )
            return

        # Parse the query parameters from the URL
        query = parsed_path.query
        params = urllib.parse.parse_qs(query)

        if "error" in params:
            callback_error = params["error"][0]
            callback_received = True
            logger.error(f"Authorization error from callback: {callback_error}")
            self._send_response(f"Authorization failed: {callback_error}", status=400)
            return

        if "code" in params:
            authorization_code = params["code"][0]
            if "state" in params:
                received_state = params["state"][0]
            callback_received = True
            logger.info(
                "Authorization code and state received successfully via callback."
            )
            
            # Try immediate token exchange if config is available
            message = "Authorization successful! You can close this window now."
            if oauth_config_global:
                try:
                    logger.info("Attempting immediate token exchange...")
                    success = oauth_config_global.exchange_code_for_tokens(authorization_code, pkce_verifier)
                    
                    if success:
                        message = "Authorization successful! Tokens have been saved securely. You can close this window now."
                        logger.info("🎉 Token exchange completed successfully during callback!")
                    else:
                        message = "Authorization received but token exchange failed. Check the logs for details."
                        logger.error("Token exchange failed during callback")
                except Exception as e:
                    logger.error(f"Error during immediate token exchange: {e}")
                    message = "Authorization received but token exchange encountered an error. Check the logs for details."
            
            self._send_response(message)
        else:
            logger.error("Invalid callback: 'code' or 'error' parameter missing.")
            self._send_response(
                "Invalid callback: Authorization code missing", status=400
            )

    def _send_response(self, message: str, status: int = 200) -> None:
        """Send response to the browser."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>OAuth Authorization</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            text-align: center;
            padding: 40px;
            max-width: 600px;
            margin: 0 auto;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            color: white;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            color: #333;
        }}
        .success-icon {{
            font-size: 64px;
            color: #10B981;
            margin-bottom: 20px;
        }}
        .error-icon {{
            font-size: 64px;
            color: #EF4444;
            margin-bottom: 20px;
        }}
        h1 {{
            margin: 0 0 20px 0;
            font-size: 28px;
            font-weight: 600;
        }}
        .message {{
            font-size: 18px;
            margin-bottom: 20px;
            line-height: 1.5;
        }}
        .countdown {{
            font-size: 14px;
            color: #6B7280;
            margin-top: 20px;
        }}
        .success-bg {{ background: linear-gradient(135deg, #10B981 0%, #059669 100%); }}
        .error-bg {{ background: linear-gradient(135deg, #EF4444 0%, #DC2626 100%); }}
    </style>
</head>
<body class="{"success-bg" if status == 200 else "error-bg"}">
    <div class="container">
        <div class="{"success-icon" if status == 200 else "error-icon"}">
            {"✅" if status == 200 else "❌"}
        </div>
        <h1>{"OAuth Authorization Complete!" if status == 200 else "OAuth Authorization Failed"}</h1>
        <div class="message">{message}</div>
        <div class="countdown" id="countdown">This window will close in <span id="timer">5</span> seconds...</div>
    </div>
    <script>
        let timer = 5;
        const timerElement = document.getElementById('timer');
        const countdownElement = document.getElementById('countdown');
        
        const interval = setInterval(() => {{
            timer--;
            timerElement.textContent = timer;
            if (timer <= 0) {{
                clearInterval(interval);
                countdownElement.textContent = 'Closing window...';
                window.close();
            }}
        }}, 1000);
        
        // Also try to close on click
        document.addEventListener('click', () => window.close());
    </script>
</body>
</html>"""
        
        # Encode the HTML content
        content = html.encode('utf-8')
        content_length = len(content)
        
        # Send HTTP response with proper headers
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        
        # Write content and ensure it's flushed
        self.wfile.write(content)
        self.wfile.flush()

    def log_message(self, format: str, *args) -> None:
        """Override to suppress default HTTP server logging."""
        return


def start_callback_server(port: int) -> socketserver.TCPServer:
    """Start a local server to receive the OAuth callback."""
    handler = CallbackHandler
    httpd = socketserver.TCPServer(("localhost", port), handler)
    server_thread = threading.Thread(target=httpd.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    logger.info(f"Started callback server on port {port}")
    return httpd


def wait_for_callback(timeout: int = 300) -> bool:
    """Wait for the callback to be received."""
    global callback_received, callback_error, authorization_code
    
    start_time = time.time()
    while not callback_received and (time.time() - start_time) < timeout:
        time.sleep(1)

    if not callback_received:
        logger.error(f"Timed out waiting for authorization callback after {timeout} seconds")
        logger.info("You can still visit the authorization URL and complete the flow manually")
        return False

    if callback_error:
        logger.error(f"Authorization error: {callback_error}")
        return False

    if not authorization_code:
        logger.error("No authorization code received")
        return False

    logger.info(f"Received authorization code: {authorization_code[:20]}...")
    return True


def parse_redirect_uri(redirect_uri: str) -> tuple[str, int]:
    """Parse the redirect URI to extract host and port."""
    parsed = urllib.parse.urlparse(redirect_uri)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.hostname, port


def load_config_file(config_path: str) -> Dict[str, Any]:
    """Load OAuth configuration from a JSON file."""
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config file {config_path}: {e}")
        return {}


def interactive_provider_selection() -> str:
    """Interactive provider selection menu."""
    print("\n🔐 OAuth 2.0 Provider Selection")
    print("=" * 40)
    
    providers = list(OAUTH_PROVIDERS.keys())
    for i, provider in enumerate(providers, 1):
        display_name = OAUTH_PROVIDERS[provider]["display_name"]
        is_m2m = OAUTH_PROVIDERS[provider].get("is_m2m", False)
        m2m_label = " [M2M/No Browser]" if is_m2m else ""
        print(f"{i}. {display_name} ({provider}){m2m_label}")
    
    while True:
        try:
            choice = input(f"\nSelect a provider (1-{len(providers)}): ").strip()
            if not choice:
                continue
            
            index = int(choice) - 1
            if 0 <= index < len(providers):
                selected_provider = providers[index]
                print(f"✅ Selected: {OAUTH_PROVIDERS[selected_provider]['display_name']}")
                return selected_provider
            else:
                print(f"❌ Please enter a number between 1 and {len(providers)}")
        except ValueError:
            print("❌ Please enter a valid number")
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            sys.exit(0)


def interactive_input(prompt: str, required: bool = True, is_secret: bool = False) -> str:
    """Get interactive input with validation."""
    import getpass
    
    while True:
        try:
            if is_secret:
                value = getpass.getpass(f"{prompt}: ").strip()
            else:
                value = input(f"{prompt}: ").strip()
            
            if value or not required:
                return value
            
            if required:
                print("❌ This field is required. Please enter a value.")
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            sys.exit(0)


def interactive_scopes_input(provider_config: Dict[str, Any]) -> List[str]:
    """Interactive scopes selection."""
    default_scopes = provider_config.get("scopes", [])
    
    print(f"\n📋 OAuth Scopes")
    print(f"Default scopes: {', '.join(default_scopes)}")
    
    custom_input = input("Enter custom scopes (comma or space-separated) or press Enter for defaults: ").strip()
    
    if custom_input:
        # Handle both comma-separated and space-separated scopes
        if "," in custom_input:
            custom_scopes = [scope.strip() for scope in custom_input.split(",")]
        else:
            custom_scopes = [scope.strip() for scope in custom_input.split()]
        return custom_scopes
    
    return default_scopes


def interactive_configuration() -> Dict[str, Any]:
    """Interactive configuration setup."""
    print("\n🚀 Generic OAuth 2.0 Flow - Interactive Setup")
    print("=" * 50)
    print("This will help you set up OAuth 2.0 authentication with various providers.")
    print("You can press Ctrl+C at any time to exit.\n")
    
    # Provider selection
    provider = interactive_provider_selection()
    provider_config = OAUTH_PROVIDERS[provider]
    
    print(f"\n📝 Setting up {provider_config['display_name']} OAuth")
    print("=" * 40)
    
    # Client credentials
    print("\n🔑 Client Credentials")
    print("These can be obtained from your OAuth provider's developer console.")
    
    # Map of known provider console URLs
    provider_consoles = {
        "atlassian": "https://developer.atlassian.com/console/myapps/",
        "google": "https://console.developers.google.com/",
        "github": "https://github.com/settings/developers",
        "cognito": "https://console.aws.amazon.com/cognito/",
        "microsoft": "https://portal.azure.com/",
        "slack": "https://api.slack.com/apps",
        "discord": "https://discord.com/developers/applications",
        "linkedin": "https://www.linkedin.com/developers/apps",
        "spotify": "https://developer.spotify.com/dashboard/",
        "twitter": "https://developer.twitter.com/en/portal/dashboard"
    }
    
    if provider in provider_consoles:
        print(f"  • {provider_config['display_name']}: {provider_consoles[provider]}")
    
    client_id = interactive_input("\nClient ID", required=True)
    client_secret = interactive_input("Client Secret", required=True, is_secret=True)
    
    # Redirect URI (skip for M2M providers)
    if not provider_config.get("is_m2m", False):
        print(f"\n🔄 Redirect URI")
        
        # Try to get public IP for better remote access
        try:
            import subprocess
            public_ip = subprocess.check_output(['curl', '-s', 'http://checkip.amazonaws.com/']).decode().strip()
            suggested_redirect = f"http://{public_ip}:{DEFAULT_REDIRECT_PORT}/callback"
            print(f"Suggested (for remote access): {suggested_redirect}")
        except:
            suggested_redirect = f"http://localhost:{DEFAULT_REDIRECT_PORT}/callback"
            print(f"Default (localhost): {suggested_redirect}")
        
        custom_redirect = input("Enter custom redirect URI or press Enter for suggested: ").strip()
        redirect_uri = custom_redirect if custom_redirect else suggested_redirect
    else:
        # M2M flow doesn't need redirect URI
        redirect_uri = "urn:ietf:wg:oauth:2.0:oob"  # Standard placeholder for M2M
    
    # Scopes
    scopes = interactive_scopes_input(provider_config)
    
    # Provider-specific configuration for templates
    additional_config = {}
    
    # Check if provider requires template variables
    if "requires_template_vars" in provider_config:
        print(f"\n⚙️  Additional Configuration for {provider_config['display_name']}")
        
        for var_name in provider_config["requires_template_vars"]:
            # Get default value if available
            default_value = provider_config.get("template_var_defaults", {}).get(var_name)
            
            # Format the prompt
            prompt = var_name.replace('_', ' ').title()
            if default_value:
                prompt = f"{prompt} (default: {default_value})"
            
            # Get input or use default
            value = interactive_input(prompt, required=False)
            if not value and default_value:
                value = default_value
            elif not value:
                value = interactive_input(f"{prompt} (required)", required=True)
            
            additional_config[var_name] = value
    
    # Summary
    print(f"\n📋 Configuration Summary")
    print("=" * 30)
    print(f"Provider: {provider_config['display_name']}")
    print(f"Client ID: {client_id}")
    print(f"Client Secret: {'*' * len(client_secret)}")
    print(f"Redirect URI: {redirect_uri}")
    print(f"Scopes: {', '.join(scopes)}")
    
    if additional_config:
        for key, value in additional_config.items():
            print(f"{key.replace('_', ' ').title()}: {value}")
    
    # Confirmation
    confirm = input(f"\n✅ Proceed with OAuth flow? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Cancelled by user")
        sys.exit(0)
    
    return {
        "provider": provider,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "scopes": scopes,
        **additional_config
    }


def run_m2m_flow(config: OAuthConfig) -> bool:
    """Run the M2M (client credentials) OAuth 2.0 flow.
    
    Args:
        config: OAuth configuration
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Prepare the token request
        payload = {
            "grant_type": "client_credentials",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
        }
        
        # Add scopes if specified (only if non-empty)
        if config.scopes and len(config.scopes) > 0:
            payload["scope"] = " ".join(config.scopes)
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        
        logger.info(f"Requesting M2M token from {config.provider_config['token_url']}")
        logger.debug(f"Using client_id: {config.client_id[:10]}..." if config.client_id else "No client_id")
        logger.debug(f"Scopes: {config.scopes}")
        
        response = requests.post(
            config.provider_config["token_url"],
            data=payload,
            headers=headers,
            timeout=30
        )
        
        if not response.ok:
            logger.error(f"M2M token request failed with status {response.status_code}. Response: {response.text}")
            return False
        
        token_data = response.json()
        
        if "access_token" not in token_data:
            logger.error(f"Access token not found in M2M response. Keys found: {list(token_data.keys())}")
            return False
        
        config.access_token = token_data["access_token"]
        
        # M2M tokens typically don't have refresh tokens
        if "refresh_token" in token_data:
            config.refresh_token = token_data["refresh_token"]
        
        # Set token expiry
        if "expires_in" in token_data:
            config.expires_at = time.time() + token_data["expires_in"]
        
        # Save the tokens
        config._save_tokens()
        
        logger.info(f"🎉 M2M token obtained successfully for {config.provider_config['display_name']}!")
        
        if config.expires_at:
            expires_in = int(config.expires_at - time.time())
            logger.info(f"Token expires in: {expires_in} seconds")
        
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during M2M token request: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to obtain M2M token: {e}")
        return False


def run_oauth_flow(config: OAuthConfig, force_new: bool = False) -> bool:
    """Run the OAuth 2.0 authorization flow.
    
    Args:
        config: OAuth configuration
        force_new: If True, delete existing tokens and force new authorization
    """
    # Check if this is an M2M provider
    if config.provider_config.get("is_m2m", False):
        logger.info("Provider configured for M2M/Client Credentials flow")
        return run_m2m_flow(config)
    
    global pkce_verifier, authorization_code, received_state, callback_received, callback_error, oauth_config_global

    # Reset global variables
    authorization_code = None
    received_state = None
    callback_received = False
    callback_error = None
    oauth_config_global = config  # Make config available to callback handler

    # Handle force delete of existing tokens
    if force_new:
        logger.info("🗑️  Force delete requested - removing existing tokens")
        _delete_existing_tokens(config.provider, config.client_id)

    # Check for existing valid tokens (skip if force_new)
    if not force_new:
        token_data = OAuthConfig.load_tokens(config.provider, config.client_id)
        if token_data:
            config.refresh_token = token_data.get("refresh_token")
            config.access_token = token_data.get("access_token")
            config.expires_at = token_data.get("expires_at")
            config.cloud_id = token_data.get("cloud_id")

            if config.access_token and not config.is_token_expired:
                logger.info("Found valid existing access token")
                return True
            elif config.refresh_token:
                logger.info("Found refresh token, attempting to refresh access token")
                if config.refresh_access_token():
                    return True

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(16)

    # Generate PKCE pair if required
    pkce_challenge = None
    if config.provider_config.get("requires_pkce", False):
        pkce_verifier, pkce_challenge = generate_pkce_pair()
        logger.debug("Generated PKCE challenge for enhanced security")

    # Start local callback server if using localhost
    hostname, port = parse_redirect_uri(config.redirect_uri)
    httpd = None

    if hostname and hostname.lower() in ["localhost", "127.0.0.1"]:
        try:
            httpd = start_callback_server(port)
        except OSError as e:
            logger.error(f"Failed to start callback server: {e}")
            logger.error(f"Make sure port {port} is available")
            return False

    # Get the authorization URL
    auth_url = config.get_authorization_url(state, pkce_challenge)

    # Open the browser for authorization
    logger.info(f"Opening browser for {config.provider_config['display_name']} authorization")
    logger.info("If the browser doesn't open automatically, visit this URL:")
    logger.info(auth_url)
    
    webbrowser.open(auth_url)

    # Wait for the callback
    logger.info("Waiting for authorization callback...")
    callback_success = wait_for_callback()
    
    # Clean up global config reference
    oauth_config_global = None
    
    if not callback_success:
        if httpd:
            httpd.shutdown()
        return False

    # Verify state to prevent CSRF attacks
    if received_state != state:
        logger.warning(f"State mismatch! Expected: {state}, Received: {received_state}")
        logger.warning("This might be from a previous authorization attempt. Continuing anyway...")
        # Don't fail on state mismatch in case of VS Code port forwarding or browser refresh
    else:
        logger.info("CSRF state verified successfully")

    # Check if token exchange already happened in the callback
    if config.access_token:
        logger.info("Token exchange was already completed during callback")
        success = True
    else:
        # Exchange the code for tokens if not done already
        logger.info("Exchanging authorization code for tokens...")
        success = config.exchange_code_for_tokens(authorization_code, pkce_verifier)

    if httpd:
        httpd.shutdown()

    if success:
        logger.info(f"🎉 {config.provider_config['display_name']} OAuth authorization completed successfully!")
        
        # Display useful information
        logger.info("\n📋 Configuration Summary:")
        logger.info(f"Provider: {config.provider_config['display_name']}")
        logger.info(f"Client ID: {config.client_id}")
        logger.info(f"Scopes: {', '.join(config.scopes)}")
        
        if config.cloud_id:
            logger.info(f"Cloud ID: {config.cloud_id}")
        
        if config.expires_at:
            expires_in = int(config.expires_at - time.time())
            logger.info(f"Token expires in: {expires_in} seconds")

        logger.info("\n💡 Tokens have been saved securely and can be used by other applications")
        
    return success


def _delete_existing_tokens(provider: str, client_id: str) -> None:
    """Delete existing tokens from all storage locations."""
    deleted_files = []
    
    # Keyring deletion removed - using file-based storage only
    
    # Delete primary token file
    primary_token_path = Path.cwd() / ".oauth-tokens" / f"oauth-{provider}-{client_id}.json"
    if primary_token_path.exists():
        primary_token_path.unlink()
        deleted_files.append(str(primary_token_path))
        logger.debug(f"Deleted primary token file: {primary_token_path}")
    
    # Delete readable token file
    readable_token_path = Path.cwd() / ".oauth-tokens" / f"oauth-{provider}-{client_id}-readable.json"
    if readable_token_path.exists():
        readable_token_path.unlink()
        deleted_files.append(str(readable_token_path))
        logger.debug(f"Deleted readable token file: {readable_token_path}")
    
    
    if deleted_files:
        logger.info(f"🗑️  Deleted {len(deleted_files)} existing token file(s)")
        for file_path in deleted_files:
            logger.debug(f"   - {file_path}")
    else:
        logger.info("🗑️  No existing token files found to delete")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generic OAuth 2.0 Authorization Flow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generic_oauth_flow.py --provider atlassian --client-id YOUR_ID --client-secret YOUR_SECRET
  python generic_oauth_flow.py --provider google --client-id YOUR_ID --client-secret YOUR_SECRET
  python generic_oauth_flow.py --provider cognito_m2m --client-id YOUR_ID --client-secret YOUR_SECRET  # M2M flow
  python generic_oauth_flow.py --config-file oauth_config.json
  python generic_oauth_flow.py --provider atlassian --force  # Force new auth, delete existing tokens
  python generic_oauth_flow.py   # Interactive mode

Supported providers: """ + ", ".join(OAUTH_PROVIDERS.keys())
    )
    
    parser.add_argument("--provider", choices=list(OAUTH_PROVIDERS.keys()), 
                       help="OAuth provider")
    parser.add_argument("--client-id", help="OAuth Client ID")
    parser.add_argument("--client-secret", help="OAuth Client Secret")
    parser.add_argument("--redirect-uri", 
                       help="OAuth Redirect URI (default: http://localhost:8080/callback)")
    parser.add_argument("--scope", nargs="*", help="OAuth Scopes (space-separated)")
    parser.add_argument("--config-file", help="JSON configuration file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--interactive", "-i", action="store_true", 
                       help="Force interactive mode even if some args are provided")
    parser.add_argument("--force", "-f", action="store_true", 
                       help="Force new OAuth flow by deleting existing tokens")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    # Load configuration from file if provided
    config_data = {}
    if args.config_file:
        config_data = load_config_file(args.config_file)

    # Check if we should use interactive mode
    use_interactive = (
        args.interactive or 
        (not args.provider and not args.client_id and not args.client_secret and not args.config_file)
    )

    if use_interactive:
        # Show welcome message for truly interactive mode (no args at all)
        if not any([args.provider, args.client_id, args.client_secret, args.config_file]):
            print("🚀 Welcome to the Generic OAuth 2.0 Flow!")
            print("No arguments provided, starting interactive setup...\n")
        
        # Interactive configuration
        try:
            interactive_config = interactive_configuration()
            config_data.update(interactive_config)
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            return 0

    # Get configuration from args, config file, environment, or interactive input
    provider = args.provider or config_data.get("provider") or os.getenv("EGRESS_OAUTH_PROVIDER")
    
    # For Cognito providers, use INGRESS credentials (for MCP Gateway auth)
    # For other providers, use EGRESS credentials (for external OAuth providers)
    if provider and provider.startswith("cognito"):
        client_id = args.client_id or config_data.get("client_id") or os.getenv("INGRESS_OAUTH_CLIENT_ID")
        client_secret = args.client_secret or config_data.get("client_secret") or os.getenv("INGRESS_OAUTH_CLIENT_SECRET")
        logger.info("Using INGRESS OAuth credentials for Cognito provider")
    else:
        client_id = args.client_id or config_data.get("client_id") or os.getenv("EGRESS_OAUTH_CLIENT_ID")
        client_secret = args.client_secret or config_data.get("client_secret") or os.getenv("EGRESS_OAUTH_CLIENT_SECRET")
        logger.info("Using EGRESS OAuth credentials for external provider")
    
    redirect_uri = (args.redirect_uri or 
                   config_data.get("redirect_uri") or 
                   os.getenv("EGRESS_OAUTH_REDIRECT_URI") or 
                   f"http://localhost:{DEFAULT_REDIRECT_PORT}/callback")
    
    # Handle scopes
    scopes = None
    if args.scope:
        scopes = args.scope
    elif config_data.get("scopes"):
        scopes = config_data["scopes"]
    elif os.getenv("EGRESS_OAUTH_SCOPE"):
        scopes = os.getenv("EGRESS_OAUTH_SCOPE").split()

    # Validate required arguments (only if not using interactive mode)
    if not use_interactive:
        missing = []
        if not provider:
            missing.append("provider")
        if not client_id:
            missing.append("client-id")
        if not client_secret:
            missing.append("client-secret")

        if missing:
            logger.error(f"Missing required arguments: {', '.join(missing)}")
            logger.info("💡 Tip: Run without arguments for interactive mode!")
            parser.print_help()
            return 1
    
    # Only validate environment variables if we're relying on them 
    # (i.e., when not using command-line args or config file)
    if not args.provider and not args.client_id and not args.client_secret and not args.config_file and not use_interactive:
        _validate_environment_variables()

    if provider not in OAUTH_PROVIDERS:
        logger.error(f"Unsupported provider: {provider}")
        logger.error(f"Supported providers: {', '.join(OAUTH_PROVIDERS.keys())}")
        return 1

    # Get provider configuration
    provider_config = OAUTH_PROVIDERS[provider].copy()
    
    # Use provider default scopes if none specified
    if not scopes:
        scopes = provider_config["scopes"]

    # Handle provider-specific URL templating
    if "requires_template_vars" in provider_config:
        template_vars = {}
        
        for var_name in provider_config["requires_template_vars"]:
            # Try to get value from config_data or environment
            value = config_data.get(var_name) or os.getenv(var_name.upper())
            
            # Special handling for Cognito domain - derive from user pool ID if not provided
            if not value and var_name == "domain" and provider in ["cognito", "cognito_m2m"]:
                # Try to derive domain from INGRESS_OAUTH_USER_POOL_ID
                user_pool_id = os.getenv("INGRESS_OAUTH_USER_POOL_ID")
                if user_pool_id:
                    # Use user pool ID without underscores as domain (standard Cognito format)
                    value = user_pool_id.replace('_', '')
                    logger.info(f"Derived Cognito domain from user pool ID: {value}")
            
            # Use default if available and no value found
            if not value and "template_var_defaults" in provider_config:
                value = provider_config["template_var_defaults"].get(var_name)
            
            if not value:
                if use_interactive:
                    logger.error(f"{var_name} configuration was not completed properly for {provider}")
                else:
                    logger.error(f"{var_name} is required for {provider_config['display_name']}")
                    logger.error(f"Set {var_name.upper()} environment variable or add '{var_name}' to config file")
                    # Provide helpful hint for Cognito domain
                    if var_name == "domain" and provider in ["cognito", "cognito_m2m"]:
                        logger.error("Hint: You can also set INGRESS_OAUTH_USER_POOL_ID and the domain will be derived automatically")
                return 1
            
            template_vars[var_name] = value
        
        # Update URLs with template variables
        for key in ["auth_url", "token_url", "user_info_url"]:
            if "{" in provider_config.get(key, ""):
                provider_config[key] = provider_config[key].format(**template_vars)

    # Create OAuth configuration
    oauth_config = OAuthConfig(
        provider=provider,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=scopes,
        provider_config=provider_config,
        additional_params=config_data.get("additional_params")
    )

    # Ensure scopes is a list for proper processing
    if isinstance(scopes, str):
        scopes = scopes.split()
    
    # Update OAuth configuration with corrected scopes
    oauth_config.scopes = scopes
    
    # Check for critical scopes (generic check for offline_access)
    if "offline_access" in provider_config.get("scopes", []) and "offline_access" not in scopes:
        logger.warning(f"⚠️  WARNING: 'offline_access' scope is recommended for {provider_config['display_name']}!")
        logger.warning("Without this scope, refresh tokens may not be issued.")
        
        if use_interactive:
            proceed = input("\nDo you want to proceed anyway? (y/N): ")
        else:
            proceed = input("Do you want to proceed anyway? (y/n): ")
        
        if proceed.lower() != "y":
            return 1

    # Run the OAuth flow
    success = run_oauth_flow(oauth_config, force_new=args.force)
    
    # Output token data as JSON if successful (for integration with other scripts)
    if success and oauth_config.access_token:
        token_output = {
            "provider": oauth_config.provider,
            "access_token": oauth_config.access_token,
            "refresh_token": oauth_config.refresh_token,
            "expires_at": oauth_config.expires_at,
            "cloud_id": oauth_config.cloud_id,
            "scopes": oauth_config.scopes
        }
        print(json.dumps(token_output))
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())