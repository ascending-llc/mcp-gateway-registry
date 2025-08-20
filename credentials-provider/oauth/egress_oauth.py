#!/usr/bin/env python3
"""
Egress OAuth Authentication Script

This script handles OAuth authentication for egress (outbound) connections to external services.
It supports multiple OAuth providers with Atlassian as the default.

The script:
1. Validates required EGRESS OAuth environment variables
2. Performs OAuth authentication flow for external providers (Atlassian, Google, GitHub, etc.)
3. Saves tokens to {provider}-egress.json in the OAuth tokens directory
4. Does not generate MCP configuration files (handled by oauth_creds.sh)

Environment Variables Required (with numbered configuration sets):
- EGRESS_OAUTH_CLIENT_ID_N: OAuth Client ID for external provider
- EGRESS_OAUTH_CLIENT_SECRET_N: OAuth Client Secret for external provider  
- EGRESS_OAUTH_REDIRECT_URI_N: OAuth Redirect URI (defaults to localhost:8080/callback)
- EGRESS_OAUTH_SCOPE_N: OAuth scopes (optional, uses provider defaults)
- EGRESS_PROVIDER_NAME_N: Provider name (atlassian, google, github, etc.)
- EGRESS_MCP_SERVER_NAME_N: MCP server name for token file naming

Where N is a configuration number from 1 to 100.

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


def _find_available_configurations() -> List[int]:
    """Find all available configuration sets (1-100) based on environment variables."""
    available_configs = []
    
    for i in range(1, 101):  # Check configurations 1-100
        required_vars = [
            f"EGRESS_OAUTH_CLIENT_ID_{i}",
            f"EGRESS_OAUTH_CLIENT_SECRET_{i}",
            f"EGRESS_OAUTH_REDIRECT_URI_{i}"
        ]
        
        # Check if all required variables for this config set exist
        if all(os.getenv(var) for var in required_vars):
            available_configs.append(i)
    
    return available_configs


def _validate_environment_variables() -> None:
    """Validate that at least one complete EGRESS OAuth configuration set is available."""
    available_configs = _find_available_configurations()
    
    if not available_configs:
        logger.error("No complete EGRESS OAuth configuration sets found!")
        logger.error("Please set at least one complete configuration set with variables like:")
        logger.error("  EGRESS_OAUTH_CLIENT_ID_1=<value>")
        logger.error("  EGRESS_OAUTH_CLIENT_SECRET_1=<value>") 
        logger.error("  EGRESS_OAUTH_REDIRECT_URI_1=<value>")
        logger.error("  EGRESS_PROVIDER_NAME_1=<provider>")
        logger.error("  EGRESS_MCP_SERVER_NAME_1=<server>")
        logger.error("\nConfiguration sets can be numbered from _1 to _100")
        raise SystemExit(1)
    
    logger.debug(f"Found {len(available_configs)} complete configuration sets: {available_configs}")


def _run_generic_oauth_flow_for_config(config_num: int, provider: str, force_new: bool = False, verbose: bool = False) -> Dict[str, Any]:
    """Run the generic OAuth flow using a specific configuration set."""
    import subprocess
    
    # Get configuration-specific environment variables
    client_id = os.getenv(f"EGRESS_OAUTH_CLIENT_ID_{config_num}")
    client_secret = os.getenv(f"EGRESS_OAUTH_CLIENT_SECRET_{config_num}")
    redirect_uri = os.getenv(f"EGRESS_OAUTH_REDIRECT_URI_{config_num}")
    scope = os.getenv(f"EGRESS_OAUTH_SCOPE_{config_num}")
    
    if not all([client_id, client_secret, redirect_uri]):
        raise ValueError(f"Missing required OAuth configuration for set {config_num}")
    
    # Build command with configuration-specific parameters
    cmd = [
        "python", 
        str(Path(__file__).parent / "generic_oauth_flow.py"),
        "--provider", provider,
        "--client-id", client_id,
        "--client-secret", client_secret,
        "--redirect-uri", redirect_uri
    ]
    
    if scope:
        cmd.extend(["--scope", scope])
    
    if force_new:
        cmd.append("--force")
    
    if verbose:
        cmd.append("--verbose")
    
    logger.info(f"Running OAuth flow for provider: {provider} (config set {config_num})")
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
            logger.error(f"OAuth flow failed with exit code {result.returncode}")
            logger.error(f"stdout: {result.stdout}")
            logger.error(f"stderr: {result.stderr}")
            raise RuntimeError(f"Generic OAuth flow failed for {provider}")
        
        logger.debug(f"OAuth flow completed successfully")
        logger.debug(f"stdout: {result.stdout}")
        
        # Parse the JSON output from the OAuth flow
        import json
        
        # Extract JSON from stdout (last line should be the JSON output)
        output_lines = result.stdout.strip().split('\n')
        json_output = None
        
        for line in reversed(output_lines):
            try:
                json_output = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        
        if not json_output:
            raise RuntimeError("Could not parse JSON output from OAuth flow")
        
        return json_output
        
    except subprocess.TimeoutExpired:
        logger.error(f"OAuth flow timed out after 5 minutes")
        raise RuntimeError(f"OAuth flow timed out for {provider}")
    except Exception as e:
        logger.error(f"Error running OAuth flow: {e}")
        raise


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


def _save_egress_tokens(token_data: Dict[str, Any], provider: str, mcp_server_name: Optional[str] = None) -> str:
    """Save egress tokens to provider-specific egress file."""
    try:
        # Create .oauth-tokens directory in current working directory
        token_dir = Path.cwd() / ".oauth-tokens"
        token_dir.mkdir(exist_ok=True, mode=0o700)
        
        # Save to {provider}-{server_name}-egress.json if server name provided
        if mcp_server_name:
            egress_path = token_dir / f"{provider}-{mcp_server_name}-egress.json"
        else:
            # Save to {provider}-egress.json
            egress_path = token_dir / f"{provider}-egress.json"
        
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


def _load_existing_tokens(provider: str = None, mcp_server_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load existing egress tokens if they exist and are valid."""
    try:
        # If provider specified, look for provider-specific file
        if provider:
            # Try provider-server specific file first if server name provided
            if mcp_server_name:
                egress_path = Path.cwd() / ".oauth-tokens" / f"{provider}-{mcp_server_name}-egress.json"
                if not egress_path.exists():
                    # Fallback to provider-only file
                    egress_path = Path.cwd() / ".oauth-tokens" / f"{provider}-egress.json"
            else:
                egress_path = Path.cwd() / ".oauth-tokens" / f"{provider}-egress.json"
        else:
            # Fallback to generic egress.json for backward compatibility
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

Environment Variables Required (numbered configuration sets 1-100):
  EGRESS_OAUTH_CLIENT_ID_N         # OAuth Client ID for external provider
  EGRESS_OAUTH_CLIENT_SECRET_N     # OAuth Client Secret for external provider
  EGRESS_OAUTH_REDIRECT_URI_N      # OAuth Redirect URI (defaults to localhost:8080/callback)
  EGRESS_OAUTH_SCOPE_N             # OAuth scopes (optional, uses provider defaults)
  EGRESS_PROVIDER_NAME_N           # Provider name (atlassian, google, github, etc.)
  EGRESS_MCP_SERVER_NAME_N         # MCP server name for token file naming
  
  Where N is a number from 1 to 100 (e.g., EGRESS_OAUTH_CLIENT_ID_1)
"""
    )
    
    parser.add_argument("--provider", choices=supported_providers, default=None,
                       help="External OAuth provider (if not specified, processes all available configurations)")
    parser.add_argument("--mcp-server-name", type=str, default=None,
                       help="MCP server name (e.g., jira, confluence) for provider-specific configs")
    parser.add_argument("--config-set", type=int, default=None,
                       help="Specific configuration set number (1-100) to process")
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
        
        # Get available configurations
        available_configs = _find_available_configurations()
        
        # Determine which configurations to process
        if args.config_set:
            # Process specific configuration set
            if args.config_set not in available_configs:
                logger.error(f"Configuration set {args.config_set} not found or incomplete")
                return 1
            configs_to_process = [args.config_set]
        elif args.provider:
            # Find configurations for specific provider
            configs_to_process = []
            for config_num in available_configs:
                provider_name = os.getenv(f"EGRESS_PROVIDER_NAME_{config_num}")
                if provider_name == args.provider:
                    configs_to_process.append(config_num)
            
            if not configs_to_process:
                logger.error(f"No configurations found for provider: {args.provider}")
                return 1
        else:
            # Process all available configurations
            configs_to_process = available_configs
        
        logger.info(f"🔐 Processing {len(configs_to_process)} configuration(s): {configs_to_process}")
        
        success_count = 0
        failure_count = 0
        
        for config_num in configs_to_process:
            try:
                # Get configuration details
                provider = os.getenv(f"EGRESS_PROVIDER_NAME_{config_num}")
                server_name = os.getenv(f"EGRESS_MCP_SERVER_NAME_{config_num}")
                
                if not provider:
                    logger.warning(f"Skipping config {config_num}: EGRESS_PROVIDER_NAME_{config_num} not set")
                    continue
                
                logger.info(f"\n📋 Processing configuration {config_num}: {provider}" + 
                           (f" ({server_name})" if server_name else ""))
                
                # Check for existing valid tokens (unless force is specified)
                if not args.force:
                    existing_tokens = _load_existing_tokens(provider, server_name)
                    if existing_tokens and existing_tokens.get("provider") == provider:
                        server_info = f" ({server_name})" if server_name else ""
                        logger.info(f"✅ Using existing valid egress token for {provider}{server_info}")
                        logger.info(f"Token expires at: {existing_tokens.get('expires_at_human', 'Unknown')}")
                        success_count += 1
                        continue
                
                # Run OAuth flow for this configuration
                token_data = _run_generic_oauth_flow_for_config(
                    config_num=config_num,
                    provider=provider,
                    force_new=args.force,
                    verbose=args.verbose
                )
                
                # Save tokens to {provider}-egress.json or {provider}-{server_name}-egress.json
                saved_path = _save_egress_tokens(token_data, provider, server_name)
                
                logger.info(f"✅ EGRESS OAuth authentication completed for {provider}!")
                logger.info(f"Tokens saved to: {saved_path}")
                success_count += 1
                
            except Exception as e:
                logger.error(f"❌ Failed to process configuration {config_num}: {e}")
                if args.verbose:
                    import traceback
                    logger.error(traceback.format_exc())
                failure_count += 1
        
        # Summary
        logger.info(f"\n📊 Summary: {success_count} successful, {failure_count} failed")
        
        return 0 if failure_count == 0 else 1
        
    except Exception as e:
        logger.error(f"❌ EGRESS OAuth authentication failed: {e}")
        if args.verbose:
            import traceback
            logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())