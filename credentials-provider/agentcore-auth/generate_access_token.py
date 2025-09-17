#!/usr/bin/env python3
"""
AgentCore Gateway Access Token Generator

This standalone utility generates OAuth2 access tokens for existing AgentCore Gateways
using Cognito or other OAuth providers. It can be used independently from the main
gateway creation scripts.

Usage:
    # Using Cognito (default)
    python generate_access_token.py

    # Using custom gateway ARN
    python generate_access_token.py --gateway-arn arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/my-gateway

    # Using environment variables
    export COGNITO_DOMAIN=https://your-cognito-domain.auth.us-west-2.amazoncognito.com
    export COGNITO_CLIENT_ID=your_client_id
    export COGNITO_CLIENT_SECRET=your_client_secret
    python generate_access_token.py
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


def _load_gateway_configs() -> List[Dict[str, Any]]:
    """
    Load gateway configurations from environment variables.
    Supports multiple configurations with _1, _2, _3 suffixes.

    Returns:
        List of gateway configuration dictionaries
    """
    configs = []

    # Check for numbered configurations (up to 100)
    for i in range(1, 101):
        client_id = os.environ.get(f"AGENTCORE_CLIENT_ID_{i}")
        client_secret = os.environ.get(f"AGENTCORE_CLIENT_SECRET_{i}")
        gateway_arn = os.environ.get(f"AGENTCORE_GATEWAY_ARN_{i}")
        server_name = os.environ.get(f"AGENTCORE_SERVER_NAME_{i}")

        # If we find a configuration set, add it
        if client_id and client_secret:
            config = {
                "client_id": client_id,
                "client_secret": client_secret,
                "gateway_arn": gateway_arn,
                "server_name": server_name,
                "index": i
            }
            configs.append(config)
            logger.debug(f"Found gateway configuration #{i}: {server_name or 'unnamed'}")
        elif any([client_id, client_secret, gateway_arn, server_name]):
            # Partial configuration found - warn user
            logger.warning(f"Incomplete configuration set #{i} - skipping")

    return configs


def _extract_cognito_region_from_pool_id(user_pool_id: str) -> str:
    """
    Extract Cognito region from User Pool ID.

    Args:
        user_pool_id: Cognito User Pool ID (format: region_poolId)

    Returns:
        AWS region extracted from pool ID
    """
    try:
        return user_pool_id.split("_")[0]
    except (IndexError, AttributeError):
        logger.error(f"Invalid User Pool ID format: {user_pool_id}")
        raise ValueError(f"Invalid User Pool ID format: {user_pool_id}")


def _get_cognito_token(
    cognito_domain_url: str,
    client_id: str,
    client_secret: str,
    audience: str = "MCPGateway",
) -> Dict[str, Any]:
    """
    Get OAuth2 token from Amazon Cognito or Auth0 using client credentials grant type.

    Args:
        cognito_domain_url: The full Cognito/Auth0 domain URL
        client_id: The App Client ID
        client_secret: The App Client Secret
        audience: The audience for the token (default: MCPGateway)

    Returns:
        Token response containing access_token, expires_in, token_type
    """
    # Construct the token endpoint URL
    if "auth0.com" in cognito_domain_url:
        url = f"{cognito_domain_url.rstrip('/')}/oauth/token"
        # Use JSON format for Auth0
        headers = {"Content-Type": "application/json"}
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": audience,
            "grant_type": "client_credentials",
            "scope": "invoke:gateway",
        }
        # Send as JSON for Auth0
        response_method = lambda: requests.post(url, headers=headers, json=data)
    else:
        # Cognito format
        url = f"{cognito_domain_url.rstrip('/')}/oauth2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        # Send as form data for Cognito
        response_method = lambda: requests.post(url, headers=headers, data=data)

    try:
        # Make the request
        response = response_method()
        response.raise_for_status()  # Raise exception for bad status codes

        provider_type = "Auth0" if "auth0.com" in cognito_domain_url else "Cognito"
        logger.info(f"Successfully obtained {provider_type} access token")
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting token: {e}")
        if hasattr(response, "text") and response.text:
            logger.error(f"Response: {response.text}")
        raise


def _save_egress_token(
    token_response: Dict[str, Any],
    provider: str = "bedrock-agentcore",
    server_name: Optional[str] = None,
    oauth_tokens_dir: str = ".oauth-tokens"
) -> str:
    """
    Save the access token as an egress token file following the same structure as Atlassian tokens.

    Args:
        token_response: Token response from OAuth provider
        provider: Auth provider name (default: bedrock-agentcore)
        server_name: Server name from config (for filename)
        oauth_tokens_dir: Path to .oauth-tokens directory
        
    Returns:
        Path to the saved token file
    """
    # Create oauth-tokens directory if it doesn't exist
    tokens_dir = Path(oauth_tokens_dir)
    tokens_dir.mkdir(exist_ok=True, mode=0o700)
    
    # Calculate expiration timestamp and human-readable format
    expires_in = token_response.get('expires_in', 10800)  # Default 3 hours
    current_time = time.time()
    expires_at = current_time + expires_in
    expires_at_human = datetime.fromtimestamp(expires_at, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    saved_at = datetime.fromtimestamp(current_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    
    # Build egress token data structure
    egress_data = {
        "provider": provider,
        "access_token": token_response["access_token"],
        "expires_at": expires_at,
        "expires_at_human": expires_at_human,
        "token_type": token_response.get("token_type", "Bearer"),
        "scope": token_response.get("scope", "invoke:gateway"),
        "saved_at": saved_at,
        "usage_notes": f"This token is for EGRESS authentication to {provider} external services"
    }
    
    # Add refresh token if present (though Cognito client credentials doesn't have refresh tokens)
    if "refresh_token" in token_response:
        egress_data["refresh_token"] = token_response["refresh_token"]
    
    # Determine filename: {provider}-{server_name}-egress.json or {provider}-egress.json
    if server_name:
        filename = f"{provider}-{server_name.lower()}-egress.json"
    else:
        filename = f"{provider}-egress.json"
    
    # Save to file
    egress_path = tokens_dir / filename
    with open(egress_path, 'w') as f:
        json.dump(egress_data, f, indent=2)
    
    # Set secure file permissions
    egress_path.chmod(0o600)
    
    logger.info(f"Egress token saved to {egress_path}")
    logger.info(f"Token expires at: {expires_at_human}")
    logger.info(f"Token expires in {expires_in} seconds")
    
    return str(egress_path)


def _get_cognito_domain_from_env() -> Tuple[str, Optional[str]]:
    """
    Get Cognito domain and user pool ID from environment variables.

    Returns:
        Tuple of (cognito_domain, user_pool_id)
    """
    cognito_domain = os.environ.get("COGNITO_DOMAIN") or os.environ.get("OAUTH_DOMAIN")
    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID")

    # If no domain provided, try to construct from user_pool_id
    if not cognito_domain and user_pool_id:
        cognito_region = _extract_cognito_region_from_pool_id(user_pool_id)
        cognito_domain = f"https://cognito-idp.{cognito_region}.amazonaws.com/{user_pool_id}"
        logger.info(f"Constructed Cognito domain from pool ID: {cognito_domain}")

    return cognito_domain, user_pool_id


def generate_access_token(
    gateway_index: Optional[int] = None,
    gateway_name: Optional[str] = None,
    oauth_tokens_dir: str = ".oauth-tokens",
    audience: str = "MCPGateway",
    generate_all: bool = False
) -> None:
    """
    Generate access token for AgentCore Gateway using environment variables.

    Args:
        gateway_index: Index of gateway configuration to use (1-100)
        gateway_name: Name of gateway to generate token for
        oauth_tokens_dir: Path to .oauth-tokens directory
        audience: Token audience for OAuth providers
        generate_all: Generate tokens for all configured gateways
    """
    # Load environment variables
    load_dotenv()

    # Get singleton Cognito configuration
    cognito_domain, user_pool_id = _get_cognito_domain_from_env()

    if not cognito_domain:
        raise ValueError("COGNITO_DOMAIN or COGNITO_USER_POOL_ID must be set in .env file")

    # Load gateway configurations
    gateway_configs = _load_gateway_configs()

    if not gateway_configs:
        raise ValueError("No gateway configurations found. Please set AGENTCORE_CLIENT_ID_1, AGENTCORE_CLIENT_SECRET_1, etc. in .env file")

    # Determine which configurations to process
    configs_to_process = []

    if generate_all:
        configs_to_process = gateway_configs
        logger.info(f"Generating tokens for all {len(gateway_configs)} configured gateways")
    elif gateway_index:
        config = next((c for c in gateway_configs if c['index'] == gateway_index), None)
        if not config:
            raise ValueError(f"No configuration found for index {gateway_index}")
        configs_to_process = [config]
    elif gateway_name:
        config = next((c for c in gateway_configs if c.get('server_name') == gateway_name), None)
        if not config:
            available_names = [c.get('server_name', f"config_{c['index']}") for c in gateway_configs]
            raise ValueError(f"No configuration found for gateway '{gateway_name}'. Available: {', '.join(available_names)}")
        configs_to_process = [config]
    else:
        # Default to first configuration
        configs_to_process = [gateway_configs[0]]
        logger.info(f"Using first gateway configuration: {gateway_configs[0].get('server_name', 'config_1')}")

    # Resolve oauth_tokens_dir path relative to current working directory
    if not Path(oauth_tokens_dir).is_absolute():
        oauth_tokens_path = Path.cwd() / oauth_tokens_dir
    else:
        oauth_tokens_path = Path(oauth_tokens_dir)

    # Process each configuration
    for config in configs_to_process:
        client_id = config['client_id']
        client_secret = config['client_secret']
        gateway_arn = config.get('gateway_arn')
        server_name = config.get('server_name')

        logger.info(f"\nProcessing gateway configuration #{config['index']}: {server_name or 'unnamed'}")

        if gateway_arn:
            logger.info(f"Gateway ARN: {gateway_arn}")

        logger.info("Generating OAuth2 access token...")

        try:
            # Generate token
            token_response = _get_cognito_token(
                cognito_domain_url=cognito_domain,
                client_id=client_id,
                client_secret=client_secret,
                audience=audience,
            )

            # Save token as egress token file
            saved_path = _save_egress_token(
                token_response=token_response,
                provider="bedrock-agentcore",
                server_name=server_name,
                oauth_tokens_dir=str(oauth_tokens_path)
            )

            logger.info(f"Token generation completed successfully! Egress token saved to {saved_path}")

        except Exception as e:
            logger.error(f"Failed to generate token for {server_name or f'config_{config['index']}'}: {e}")
            if not generate_all:
                raise


def _parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed command line arguments
    """
    parser = argparse.ArgumentParser(
        description="Generate OAuth2 access tokens for AgentCore Gateways",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate token for first configured gateway
    python generate_access_token.py

    # Generate token for specific gateway by index
    python generate_access_token.py --gateway-index 2

    # Generate token for specific gateway by name
    python generate_access_token.py --gateway-name sre-gateway

    # Generate tokens for ALL configured gateways
    python generate_access_token.py --all

    # Custom oauth-tokens directory
    python generate_access_token.py --oauth-tokens-dir /path/to/.oauth-tokens

    # Custom audience for Auth0
    python generate_access_token.py --audience "https://api.mycompany.com"

Environment Variables:
    # Singleton configuration (shared across all gateways):
    COGNITO_DOMAIN          - Cognito/OAuth domain URL
    COGNITO_USER_POOL_ID    - Cognito User Pool ID

    # Per-gateway configuration (use _1, _2, etc. suffixes):
    AGENTCORE_CLIENT_ID_1     - OAuth client ID for gateway 1
    AGENTCORE_CLIENT_SECRET_1 - OAuth client secret for gateway 1
    AGENTCORE_GATEWAY_ARN_1   - Gateway ARN for gateway 1
    AGENTCORE_SERVER_NAME_1   - Server name for gateway 1
        """,
    )

    parser.add_argument(
        "--gateway-index",
        type=int,
        help="Index of gateway configuration to use (1-100)",
    )

    parser.add_argument(
        "--gateway-name",
        help="Name of gateway to generate token for",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate tokens for all configured gateways",
    )

    parser.add_argument(
        "--oauth-tokens-dir",
        default=".oauth-tokens",
        help="Path to .oauth-tokens directory (default: .oauth-tokens)",
    )

    parser.add_argument(
        "--audience",
        default="MCPGateway",
        help="Token audience (default: MCPGateway)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = _parse_arguments()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        generate_access_token(
            gateway_index=args.gateway_index,
            gateway_name=args.gateway_name,
            oauth_tokens_dir=args.oauth_tokens_dir,
            audience=args.audience,
            generate_all=args.all,
        )
    except Exception as e:
        logger.error(f"Token generation failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()