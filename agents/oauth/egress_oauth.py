#!/usr/bin/env python3
"""
Egress OAuth Authentication Script

This script handles OAuth authentication for egress (outbound) connections to external services.
It supports multiple OAuth providers with Atlassian as the default.

The script:
1. Validates required EGRESS OAuth environment variables
2. Performs OAuth authentication flow for external providers (Atlassian, Google, GitHub, etc.)
3. Saves tokens to egress.json in the OAuth tokens directory
4. Does not generate MCP configuration files (handled by oauth_creds.sh)

Environment Variables Required:
- EGRESS_OAUTH_CLIENT_ID: OAuth Client ID for external provider
- EGRESS_OAUTH_CLIENT_SECRET: OAuth Client Secret for external provider  
- EGRESS_OAUTH_REDIRECT_URI: OAuth Redirect URI (defaults to localhost:8080/callback)
- EGRESS_OAUTH_SCOPE: OAuth scopes (optional, uses provider defaults)

Usage:
    python egress_oauth.py                                    # Use Atlassian (default)
    python egress_oauth.py --provider google                  # Use Google
    python egress_oauth.py --provider atlassian --verbose     # Atlassian with debug
    python egress_oauth.py --force                            # Force new token generation
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

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
    """Validate that all required EGRESS OAuth environment variables are set."""
    required_vars = [
        "EGRESS_OAUTH_CLIENT_ID",
        "EGRESS_OAUTH_CLIENT_SECRET",
        "EGRESS_OAUTH_REDIRECT_URI"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error("Missing required EGRESS OAuth environment variables:")
        for var in missing_vars:
            logger.error(f"  - {var}")
        logger.error("\nPlease set the following environment variables:")
        for var in missing_vars:
            logger.error(f"  export {var}=<value>")
        logger.error("\nOr add them to your .env file")
        raise SystemExit(1)
    
    logger.debug("All required EGRESS OAuth environment variables are set")


def _run_generic_oauth_flow(provider: str, force_new: bool = False, verbose: bool = False) -> Dict[str, Any]:
    """Run the generic OAuth flow using the existing script."""
    import subprocess
    
    # Build command
    cmd = [
        "python", 
        str(Path(__file__).parent / "generic_oauth_flow.py"),
        "--provider", provider
    ]
    
    if force_new:
        cmd.append("--force")
    
    if verbose:
        cmd.append("--verbose")
    
    logger.info(f"Running OAuth flow for provider: {provider}")
    logger.debug(f"Command: {' '.join(cmd)}")
    
    try:
        # Run the generic OAuth flow
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            logger.error(f"OAuth flow failed for {provider}")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"STDERR: {result.stderr}")
            raise RuntimeError(f"OAuth flow failed with return code {result.returncode}")
        
        logger.info(f"✅ OAuth flow completed successfully for {provider}")
        if verbose:
            logger.debug(f"OAuth flow output: {result.stdout}")
        
        # Parse the output to extract token information
        # The generic_oauth_flow.py saves tokens to ~/.oauth-tokens/
        return _load_provider_tokens(provider)
        
    except subprocess.TimeoutExpired:
        logger.error(f"OAuth flow timed out for {provider}")
        raise
    except Exception as e:
        logger.error(f"Failed to run OAuth flow for {provider}: {e}")
        raise


def _load_provider_tokens(provider: str) -> Dict[str, Any]:
    """Load tokens for the specified provider from the OAuth tokens directory."""
    try:
        token_dir = Path.cwd() / ".oauth-tokens"
        
        # Look for provider-specific token files
        pattern = f"oauth-{provider}-*.json"
        token_files = list(token_dir.glob(pattern))
        
        if not token_files:
            raise FileNotFoundError(f"No token files found for provider {provider}")
        
        # Use the most recent token file
        latest_file = max(token_files, key=lambda f: f.stat().st_mtime)
        
        with open(latest_file) as f:
            token_data = json.load(f)
        
        logger.debug(f"Loaded tokens from: {latest_file}")
        return token_data
        
    except Exception as e:
        logger.error(f"Failed to load provider tokens for {provider}: {e}")
        raise


def _save_egress_tokens(token_data: Dict[str, Any], provider: str) -> str:
    """Save egress tokens to egress.json file."""
    try:
        # Create .oauth-tokens directory in current working directory
        token_dir = Path.cwd() / ".oauth-tokens"
        token_dir.mkdir(exist_ok=True, mode=0o700)
        
        # Save to egress.json
        egress_path = token_dir / "egress.json"
        
        # Prepare token data for storage
        save_data = {
            "provider": provider,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": token_data.get("expires_at"),
            "expires_at_human": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(token_data["expires_at"])) if token_data.get("expires_at") else None,
            "cloud_id": token_data.get("cloud_id"),  # For Atlassian
            "scopes": token_data.get("scopes", []),
            "saved_at": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
            "usage_notes": f"This token is for EGRESS authentication to {provider} external services"
        }
        
        with open(egress_path, "w") as f:
            json.dump(save_data, f, indent=2)
        
        # Secure the file
        egress_path.chmod(0o600)
        logger.info(f"📁 Saved egress tokens to: {egress_path}")
        
        return str(egress_path)
        
    except Exception as e:
        logger.error(f"Failed to save egress tokens: {e}")
        raise


def _load_existing_tokens() -> Optional[Dict[str, Any]]:
    """Load existing egress tokens if they exist and are valid."""
    try:
        egress_path = Path.cwd() / ".oauth-tokens" / "egress.json"
        
        if not egress_path.exists():
            return None
        
        with open(egress_path) as f:
            token_data = json.load(f)
        
        # Check if token is expired
        if token_data.get("expires_at"):
            expires_at = token_data["expires_at"]
            # Add 5 minute margin
            if time.time() + 300 >= expires_at:
                logger.info("Existing egress token is expired or will expire soon")
                return None
        
        logger.info("Found valid existing egress token")
        return token_data
        
    except Exception as e:
        logger.debug(f"Failed to load existing tokens: {e}")
        return None


def _get_supported_providers() -> List[str]:
    """Get list of supported external providers (exclude cognito providers)."""
    try:
        import yaml
        yaml_path = Path(__file__).parent / "oauth_providers.yaml"
        
        if not yaml_path.exists():
            # Fallback to known external providers
            return ["atlassian", "google", "github", "microsoft", "slack", "discord", "linkedin", "spotify", "twitter"]
        
        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f)
            providers = config.get('providers', {})
            
        # Filter out cognito providers (those are for ingress)
        external_providers = [
            name for name, config in providers.items() 
            if not name.startswith("cognito")
        ]
        
        return external_providers
        
    except Exception as e:
        logger.debug(f"Failed to load providers list: {e}")
        # Fallback to known external providers
        return ["atlassian", "google", "github", "microsoft", "slack", "discord", "linkedin", "spotify", "twitter"]


def main() -> int:
    """Main entry point."""
    supported_providers = _get_supported_providers()
    
    parser = argparse.ArgumentParser(
        description="Egress OAuth Authentication for External Services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python egress_oauth.py                                    # Use Atlassian (default)
  python egress_oauth.py --provider google                  # Use Google
  python egress_oauth.py --provider github --verbose        # GitHub with debug
  python egress_oauth.py --force                            # Force new token generation

Supported Providers:
  {', '.join(supported_providers)}

Environment Variables Required:
  EGRESS_OAUTH_CLIENT_ID       # OAuth Client ID for external provider
  EGRESS_OAUTH_CLIENT_SECRET   # OAuth Client Secret for external provider
  EGRESS_OAUTH_REDIRECT_URI    # OAuth Redirect URI (defaults to localhost:8080/callback)
  EGRESS_OAUTH_SCOPE           # OAuth scopes (optional, uses provider defaults)
"""
    )
    
    parser.add_argument("--provider", choices=supported_providers, default="atlassian",
                       help="External OAuth provider (default: atlassian)")
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
        
        logger.info(f"🔐 Starting EGRESS OAuth authentication for: {args.provider}")
        
        # Check for existing valid tokens (unless force is specified)
        if not args.force:
            existing_tokens = _load_existing_tokens()
            if existing_tokens and existing_tokens.get("provider") == args.provider:
                logger.info(f"✅ Using existing valid egress token for {args.provider}")
                logger.info(f"Token expires at: {existing_tokens.get('expires_at_human', 'Unknown')}")
                return 0
        
        # Run OAuth flow for the specified provider
        token_data = _run_generic_oauth_flow(
            provider=args.provider,
            force_new=args.force,
            verbose=args.verbose
        )
        
        # Save tokens to egress.json
        saved_path = _save_egress_tokens(token_data, args.provider)
        
        logger.info(f"✅ EGRESS OAuth authentication completed successfully for {args.provider}!")
        logger.info(f"Tokens saved to: {saved_path}")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ EGRESS OAuth authentication failed: {e}")
        if args.verbose:
            import traceback
            logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())