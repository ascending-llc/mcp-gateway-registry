#!/usr/bin/env python3
"""
Ingress OAuth Authentication Script

This script handles OAuth authentication for ingress (inbound) connections to the MCP Gateway.
It specifically handles Cognito M2M (Machine-to-Machine) authentication for the MCP Gateway itself.

The script:
1. Validates required INGRESS OAuth environment variables
2. Performs Cognito M2M authentication using client_credentials grant
3. Saves tokens to ingress.json in the OAuth tokens directory
4. Does not generate MCP configuration files (handled by oauth_creds.sh)

Environment Variables Required:
- INGRESS_OAUTH_USER_POOL_ID: Cognito User Pool ID
- INGRESS_OAUTH_CLIENT_ID: Cognito App Client ID for M2M
- INGRESS_OAUTH_CLIENT_SECRET: Cognito App Client Secret for M2M
- AWS_REGION: AWS region (defaults to us-east-1)

Usage:
    python ingress_oauth.py
    python ingress_oauth.py --verbose
    python ingress_oauth.py --force  # Force new token generation
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

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
    """Validate that all required INGRESS OAuth environment variables are set."""
    required_vars = [
        "INGRESS_OAUTH_USER_POOL_ID",
        "INGRESS_OAUTH_CLIENT_ID", 
        "INGRESS_OAUTH_CLIENT_SECRET"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error("Missing required INGRESS OAuth environment variables:")
        for var in missing_vars:
            logger.error(f"  - {var}")
        logger.error("\nPlease set the following environment variables:")
        for var in missing_vars:
            logger.error(f"  export {var}=<value>")
        logger.error("\nOr add them to your .env file")
        raise SystemExit(1)
    
    logger.debug("All required INGRESS OAuth environment variables are set")


def _get_cognito_domain(user_pool_id: str, region: str) -> str:
    """Generate Cognito domain from user pool ID."""
    # Use user pool ID without underscores as domain (standard Cognito format)
    domain = user_pool_id.replace('_', '')
    return f"https://{domain}.auth.{region}.amazoncognito.com"


def _perform_m2m_authentication(
    client_id: str,
    client_secret: str, 
    user_pool_id: str,
    region: str
) -> Dict[str, Any]:
    """Perform M2M (client credentials) OAuth 2.0 authentication with Cognito."""
    try:
        # Generate token URL
        cognito_domain = _get_cognito_domain(user_pool_id, region)
        token_url = f"{cognito_domain}/oauth2/token"
        
        # Prepare the token request
        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        
        logger.info(f"Requesting M2M token from {token_url}")
        logger.debug(f"Using client_id: {client_id[:10]}..." if client_id else "No client_id")
        
        response = requests.post(
            token_url,
            data=payload,
            headers=headers,
            timeout=30
        )
        
        if not response.ok:
            logger.error(f"M2M token request failed with status {response.status_code}. Response: {response.text}")
            raise ValueError(f"Token request failed: {response.text}")
        
        token_data = response.json()
        
        if "access_token" not in token_data:
            logger.error(f"Access token not found in M2M response. Keys found: {list(token_data.keys())}")
            raise ValueError("No access token in response")
        
        # Calculate expiry time
        expires_at = None
        if "expires_in" in token_data:
            expires_at = time.time() + token_data["expires_in"]
        
        # Prepare result
        result = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),  # M2M typically doesn't have refresh tokens
            "expires_at": expires_at,
            "token_type": token_data.get("token_type", "Bearer"),
            "provider": "cognito_m2m",
            "client_id": client_id,
            "user_pool_id": user_pool_id,
            "region": region
        }
        
        logger.info("🎉 M2M token obtained successfully!")
        
        if expires_at:
            expires_in = int(expires_at - time.time())
            logger.info(f"Token expires in: {expires_in} seconds")
        
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during M2M token request: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to obtain M2M token: {e}")
        raise


def _save_ingress_tokens(token_data: Dict[str, Any]) -> str:
    """Save ingress tokens to ingress.json file."""
    try:
        # Create .oauth-tokens directory in current working directory
        token_dir = Path.cwd() / ".oauth-tokens"
        token_dir.mkdir(exist_ok=True, mode=0o700)
        
        # Save to ingress.json
        ingress_path = token_dir / "ingress.json"
        
        # Prepare token data for storage
        save_data = {
            "provider": "cognito_m2m",
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at"),
            "expires_at_human": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(token_data["expires_at"])) if token_data.get("expires_at") else None,
            "token_type": token_data.get("token_type", "Bearer"),
            "client_id": token_data["client_id"],
            "user_pool_id": token_data["user_pool_id"],
            "region": token_data["region"],
            "saved_at": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
            "usage_notes": "This token is for INGRESS authentication to the MCP Gateway (Cognito M2M)"
        }
        
        with open(ingress_path, "w") as f:
            json.dump(save_data, f, indent=2)
        
        # Secure the file
        ingress_path.chmod(0o600)
        logger.info(f"📁 Saved ingress tokens to: {ingress_path}")
        
        return str(ingress_path)
        
    except Exception as e:
        logger.error(f"Failed to save ingress tokens: {e}")
        raise


def _load_existing_tokens() -> Optional[Dict[str, Any]]:
    """Load existing ingress tokens if they exist and are valid."""
    try:
        ingress_path = Path.cwd() / ".oauth-tokens" / "ingress.json"
        
        if not ingress_path.exists():
            return None
        
        with open(ingress_path) as f:
            token_data = json.load(f)
        
        # Check if token is expired
        if token_data.get("expires_at"):
            expires_at = token_data["expires_at"]
            # Add 5 minute margin
            if time.time() + 300 >= expires_at:
                logger.info("Existing ingress token is expired or will expire soon")
                return None
        
        logger.info("Found valid existing ingress token")
        return token_data
        
    except Exception as e:
        logger.debug(f"Failed to load existing tokens: {e}")
        return None


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ingress OAuth Authentication for MCP Gateway (Cognito M2M)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ingress_oauth.py                    # Generate ingress token
  python ingress_oauth.py --verbose          # With debug logging
  python ingress_oauth.py --force            # Force new token generation

Environment Variables Required:
  INGRESS_OAUTH_USER_POOL_ID    # Cognito User Pool ID
  INGRESS_OAUTH_CLIENT_ID       # Cognito Client ID for M2M
  INGRESS_OAUTH_CLIENT_SECRET   # Cognito Client Secret for M2M
  AWS_REGION                    # AWS region (optional, defaults to us-east-1)
"""
    )
    
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Enable verbose debug logging")
    parser.add_argument("--force", "-f", action="store_true",
                       help="Force new token generation, ignore existing valid tokens")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    
    try:
        # Validate environment variables
        _validate_environment_variables()
        
        # Get configuration from environment
        client_id = os.getenv("INGRESS_OAUTH_CLIENT_ID")
        client_secret = os.getenv("INGRESS_OAUTH_CLIENT_SECRET") 
        user_pool_id = os.getenv("INGRESS_OAUTH_USER_POOL_ID")
        region = os.getenv("AWS_REGION", "us-east-1")
        
        logger.info("🔐 Starting INGRESS OAuth authentication (Cognito M2M)")
        logger.info(f"User Pool ID: {user_pool_id}")
        logger.info(f"Client ID: {client_id[:10]}...") 
        logger.info(f"Region: {region}")
        
        # Check for existing valid tokens (unless force is specified)
        if not args.force:
            existing_tokens = _load_existing_tokens()
            if existing_tokens:
                logger.info("✅ Using existing valid ingress token")
                logger.info(f"Token expires at: {existing_tokens.get('expires_at_human', 'Unknown')}")
                return 0
        
        # Perform M2M authentication
        token_data = _perform_m2m_authentication(
            client_id=client_id,
            client_secret=client_secret,
            user_pool_id=user_pool_id,
            region=region
        )
        
        # Save tokens
        saved_path = _save_ingress_tokens(token_data)
        
        logger.info("✅ INGRESS OAuth authentication completed successfully!")
        logger.info(f"Tokens saved to: {saved_path}")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ INGRESS OAuth authentication failed: {e}")
        if args.verbose:
            import traceback
            logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())