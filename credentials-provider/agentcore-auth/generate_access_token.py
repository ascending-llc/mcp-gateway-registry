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
from typing import Any, Dict, Optional

import requests
import yaml
from dotenv import load_dotenv

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


def _load_config(config_file: str = "config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_file: Path to the configuration file

    Returns:
        Configuration dictionary
    """
    try:
        config_path = Path(config_file)
        if not config_path.exists():
            logger.warning(f"Config file {config_file} not found, using environment variables only")
            return {}

        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}
            logger.info(f"Loaded configuration from {config_file}")
            return config
    except Exception as e:
        logger.error(f"Failed to load config file {config_file}: {e}")
        return {}


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


def _get_cognito_domain_from_config(
    user_pool_id: Optional[str] = None,
    custom_domain: Optional[str] = None
) -> str:
    """
    Construct Cognito domain URL from User Pool ID or use custom domain.

    Args:
        user_pool_id: Cognito User Pool ID
        custom_domain: Custom Cognito domain URL

    Returns:
        Complete Cognito domain URL
    """
    if custom_domain:
        return custom_domain

    if user_pool_id:
        cognito_region = _extract_cognito_region_from_pool_id(user_pool_id)
        return f"https://cognito-idp.{cognito_region}.amazonaws.com/{user_pool_id}"

    raise ValueError("Either user_pool_id or custom_domain must be provided")


def generate_access_token(
    gateway_arn: Optional[str] = None,
    config_file: str = "config.yaml",
    oauth_tokens_dir: str = ".oauth-tokens",
    audience: str = "MCPGateway"
) -> None:
    """
    Generate access token for AgentCore Gateway using configuration and environment variables.

    Args:
        gateway_arn: Optional gateway ARN (for reference/validation)
        config_file: Path to configuration file
        oauth_tokens_dir: Path to .oauth-tokens directory
        audience: Token audience for OAuth providers
    """
    # Load environment variables
    load_dotenv()

    # Load configuration - handle relative paths from script directory
    script_dir = Path(__file__).parent
    if not Path(config_file).is_absolute():
        config_file_path = script_dir / config_file
    else:
        config_file_path = Path(config_file)
    
    config = _load_config(str(config_file_path))

    # Get configuration values with environment variable fallbacks
    cognito_domain = (
        os.environ.get("COGNITO_DOMAIN") or 
        config.get("oauth_domain")
    )
    
    client_id = (
        os.environ.get("COGNITO_CLIENT_ID") or 
        os.environ.get("OAUTH_CLIENT_ID") or
        config.get("client_id") or
        config.get("oauth_client_id")
    )
    
    client_secret = (
        os.environ.get("COGNITO_CLIENT_SECRET") or 
        os.environ.get("OAUTH_CLIENT_SECRET")
    )
    
    user_pool_id = config.get("user_pool_id")
    server_name = config.get("server_name")

    # If no domain provided, try to construct from user_pool_id
    if not cognito_domain and user_pool_id:
        cognito_domain = _get_cognito_domain_from_config(user_pool_id=user_pool_id)
        logger.info(f"Constructed Cognito domain from pool ID: {cognito_domain}")

    # Validate required parameters
    missing_params = []
    if not cognito_domain:
        missing_params.append("COGNITO_DOMAIN (or user_pool_id in config)")
    if not client_id:
        missing_params.append("COGNITO_CLIENT_ID")
    if not client_secret:
        missing_params.append("COGNITO_CLIENT_SECRET")

    if missing_params:
        logger.error(f"Missing required parameters: {', '.join(missing_params)}")
        logger.error("Please set these in your .env file or config.yaml")
        raise ValueError(f"Missing required parameters: {', '.join(missing_params)}")

    # Log gateway ARN if provided
    if gateway_arn:
        logger.info(f"Generating token for gateway: {gateway_arn}")
    elif config.get("gateway_arn"):
        logger.info(f"Gateway ARN from config: {config['gateway_arn']}")

    logger.info("Generating OAuth2 access token...")

    # Generate token
    token_response = _get_cognito_token(
        cognito_domain_url=cognito_domain,
        client_id=client_id,
        client_secret=client_secret,
        audience=audience,
    )

    # Resolve oauth_tokens_dir path relative to current working directory
    if not Path(oauth_tokens_dir).is_absolute():
        oauth_tokens_path = Path.cwd() / oauth_tokens_dir
    else:
        oauth_tokens_path = Path(oauth_tokens_dir)
    
    # Save token as egress token file
    saved_path = _save_egress_token(
        token_response=token_response,
        provider="bedrock-agentcore",
        server_name=server_name,
        oauth_tokens_dir=str(oauth_tokens_path)
    )

    logger.info(f"Token generation completed successfully! Egress token saved to {saved_path}")


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
    # Generate egress token using config.yaml and .env
    python generate_access_token.py

    # Specify gateway ARN
    python generate_access_token.py --gateway-arn arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/my-gateway

    # Custom oauth-tokens directory
    python generate_access_token.py --oauth-tokens-dir /path/to/.oauth-tokens

    # Custom audience for Auth0
    python generate_access_token.py --audience "https://api.mycompany.com"

Environment Variables:
    COGNITO_DOMAIN        - Cognito/OAuth domain URL
    COGNITO_CLIENT_ID     - OAuth client ID  
    COGNITO_CLIENT_SECRET - OAuth client secret
        """,
    )

    parser.add_argument(
        "--gateway-arn",
        help="Gateway ARN (optional, for reference)",
    )

    parser.add_argument(
        "--config-file",
        default="config.yaml",
        help="Configuration file path (default: config.yaml)",
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
            gateway_arn=args.gateway_arn,
            config_file=args.config_file,
            oauth_tokens_dir=args.oauth_tokens_dir,
            audience=args.audience,
        )
    except Exception as e:
        logger.error(f"Token generation failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()