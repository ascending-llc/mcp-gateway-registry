#!/usr/bin/env python3
"""
OAuth Token Refresher Service

This service monitors OAuth tokens in the .oauth-tokens directory and automatically
refreshes them before they expire. It runs continuously in the background, checking
tokens every configurable interval (default 5 minutes).

Usage:
    uv run python credentials-provider/token_refresher.py                    # Run with defaults
    uv run python credentials-provider/token_refresher.py --interval 300     # Check every 5 minutes
    uv run python credentials-provider/token_refresher.py --buffer 3600      # Refresh 1 hour before expiry
    uv run python credentials-provider/token_refresher.py --once             # Run once and exit
    uv run python credentials-provider/token_refresher.py --once --force     # Force refresh all tokens once and exit
    nohup uv run python credentials-provider/token_refresher.py > token_refresher.log 2>&1 &  # Run in background
"""

import argparse
import json
import logging
import os
import psutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


# Configuration constants
DEFAULT_CHECK_INTERVAL = 300  # 5 minutes in seconds
DEFAULT_EXPIRY_BUFFER = 3600  # 1 hour buffer before expiry

# Process management
PIDFILE_NAME = "token_refresher.pid"

# Dynamically determine paths relative to this script's location
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
OAUTH_TOKENS_DIR = PROJECT_ROOT / ".oauth-tokens"
CREDENTIALS_PROVIDER_DIR = SCRIPT_DIR

# Files to ignore during token refresh (derived files that get regenerated)
IGNORED_FILES = {
    "mcp.json",
    "vscode_mcp.json", 
    "*readable*",  # Any file with "readable" in the name
}


def _should_ignore_file(filename: str) -> bool:
    """
    Check if a token file should be ignored.
    
    Args:
        filename: Name of the token file
        
    Returns:
        True if file should be ignored, False otherwise
    """
    # Check exact matches
    if filename in {"mcp.json", "vscode_mcp.json"}:
        return True
    
    # Check for "readable" in filename
    if "readable" in filename.lower():
        return True
    
    return False


def _parse_token_file(filepath: Path) -> Optional[Dict]:
    """
    Parse a token JSON file and extract relevant information.
    
    Args:
        filepath: Path to the token file
        
    Returns:
        Token data dict or None if file cannot be parsed
    """
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            
        # Validate required fields
        if 'expires_at' not in data:
            logger.debug(f"No expires_at field in {filepath.name}")
            return None
            
        return data
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to parse {filepath.name}: {e}")
        return None


def _get_all_tokens() -> List[Tuple[Path, Dict]]:
    """
    Get all valid token files regardless of expiration status.
    
    Returns:
        List of (filepath, token_data) tuples for all valid tokens
    """
    if not OAUTH_TOKENS_DIR.exists():
        logger.error("OAuth tokens directory not found")
        return []
    
    all_tokens = []
    
    for filepath in OAUTH_TOKENS_DIR.glob("*.json"):
        # Skip ignored files
        if _should_ignore_file(filepath.name):
            logger.debug(f"Ignoring file: {filepath.name}")
            continue
        
        # Parse token file
        token_data = _parse_token_file(filepath)
        if not token_data:
            continue
        
        logger.info(f"Found token file: {filepath.name}")
        logger.debug(f"Reading token from: {filepath.absolute()}")
        all_tokens.append((filepath, token_data))
    
    return all_tokens


def _get_expiring_tokens(buffer_seconds: int = DEFAULT_EXPIRY_BUFFER) -> List[Tuple[Path, Dict]]:
    """
    Find all tokens that are expired or will expire within the buffer period.
    
    Args:
        buffer_seconds: Number of seconds before expiry to trigger refresh
        
    Returns:
        List of (filepath, token_data) tuples for expiring tokens
    """
    if not OAUTH_TOKENS_DIR.exists():
        logger.error(f"OAuth tokens directory not found: {OAUTH_TOKENS_DIR}")
        return []
    
    current_time = time.time()
    expiring_tokens = []
    
    for filepath in OAUTH_TOKENS_DIR.glob("*.json"):
        # Skip ignored files
        if _should_ignore_file(filepath.name):
            logger.debug(f"Ignoring file: {filepath.name}")
            continue
        
        # Parse token file
        token_data = _parse_token_file(filepath)
        if not token_data:
            continue
        
        logger.debug(f"Reading token from: {filepath.absolute()}")
        
        # Check expiration
        expires_at = token_data.get('expires_at', 0)
        time_until_expiry = expires_at - current_time
        
        if time_until_expiry <= buffer_seconds:
            hours_until_expiry = time_until_expiry / 3600
            if time_until_expiry <= 0:
                logger.warning(f"Token EXPIRED: {filepath.name} (expired {-hours_until_expiry:.1f} hours ago)")
            else:
                logger.info(f"Token expiring soon: {filepath.name} (expires in {hours_until_expiry:.1f} hours)")
            logger.debug(f"Will refresh token at: {filepath.absolute()}")
            expiring_tokens.append((filepath, token_data))
    
    return expiring_tokens


def _determine_refresh_method(token_data: Dict, filename: str) -> Optional[str]:
    """
    Determine which refresh method to use based on token data.
    
    Args:
        token_data: Parsed token data
        filename: Token filename
        
    Returns:
        Refresh method ('agentcore' or 'oauth') or None if cannot determine
    """
    provider = token_data.get('provider', '').lower()
    
    # Check for AgentCore/Bedrock tokens
    if 'bedrock' in provider or 'agentcore' in provider:
        return 'agentcore'
    
    # Check for OAuth providers (Atlassian, Google, GitHub, etc.)
    oauth_providers = ['atlassian', 'google', 'github', 'microsoft', 'oauth']
    if any(p in provider for p in oauth_providers):
        return 'oauth'
    
    # Try to infer from filename
    if 'bedrock' in filename.lower() or 'agentcore' in filename.lower():
        return 'agentcore'
    
    if 'egress' in filename.lower() or 'ingress' in filename.lower():
        return 'oauth'
    
    logger.warning(f"Cannot determine refresh method for {filename} with provider '{provider}'")
    return None


def _refresh_agentcore_token(token_data: Dict, filename: str) -> bool:
    """
    Refresh a Bedrock AgentCore token using generate_access_token.py.
    
    Args:
        token_data: Current token data
        filename: Token filename
        
    Returns:
        True if refresh successful, False otherwise
    """
    script_path = CREDENTIALS_PROVIDER_DIR / "agentcore-auth" / "generate_access_token.py"
    
    if not script_path.exists():
        logger.error(f"AgentCore refresh script not found: {script_path}")
        return False
    
    try:
        # Extract server name from filename if possible
        # Format: bedrock-agentcore-{server_name}-egress.json
        server_name = None
        if filename.startswith("bedrock-agentcore-") and filename.endswith("-egress.json"):
            server_name = filename.replace("bedrock-agentcore-", "").replace("-egress.json", "")
        
        logger.info(f"Refreshing AgentCore token for: {server_name or 'default'}")
        
        # Run the refresh script using uv run
        cmd = ["uv", "run", "python", str(script_path)]
        if server_name:
            # The script might accept server-specific parameters
            # Check the script for available options
            pass
        
        logger.debug(f"Running AgentCore refresh command: {' '.join(cmd)}")
        logger.debug(f"Working directory: {PROJECT_ROOT.absolute()}")
        
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully refreshed AgentCore token: {filename}")
            return True
        else:
            logger.error(f"Failed to refresh AgentCore token: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout refreshing AgentCore token: {filename}")
        return False
    except Exception as e:
        logger.error(f"Error refreshing AgentCore token {filename}: {e}")
        return False


def _refresh_oauth_token(token_data: Dict, filename: str) -> bool:
    """
    Refresh a generic OAuth token using egress_oauth.py or ingress_oauth.py.
    
    Args:
        token_data: Current token data
        filename: Token filename
        
    Returns:
        True if refresh successful, False otherwise
    """
    # Determine which OAuth script to use
    if 'ingress' in filename.lower():
        script_name = "ingress_oauth.py"
        # Ingress uses Cognito M2M and doesn't accept --provider argument
        use_provider_arg = False
    else:
        script_name = "egress_oauth.py"  # Default to egress
        use_provider_arg = True
    
    script_path = CREDENTIALS_PROVIDER_DIR / "oauth" / script_name
    
    if not script_path.exists():
        logger.error(f"OAuth refresh script not found: {script_path}")
        return False
    
    try:
        provider = token_data.get('provider', 'atlassian')
        logger.info(f"Refreshing OAuth token for provider: {provider}")
        
        # Build command based on script type
        cmd = ["uv", "run", "python", str(script_path)]
        
        # Only add --provider for egress OAuth (not ingress)
        if use_provider_arg:
            cmd.extend(["--provider", provider])
        
        logger.debug(f"Running OAuth refresh command: {' '.join(cmd)}")
        logger.debug(f"Working directory: {PROJECT_ROOT.absolute()}")
        
        # Check if we have a refresh token
        if 'refresh_token' in token_data:
            # The script should handle refresh token flow
            pass
        
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60  # OAuth flow might take longer
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully refreshed OAuth token: {filename}")
            return True
        else:
            logger.error(f"Failed to refresh OAuth token: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout refreshing OAuth token: {filename}")
        return False
    except Exception as e:
        logger.error(f"Error refreshing OAuth token {filename}: {e}")
        return False


def _refresh_token(filepath: Path, token_data: Dict) -> bool:
    """
    Refresh a single token based on its type.
    
    Args:
        filepath: Path to the token file
        token_data: Parsed token data
        
    Returns:
        True if refresh successful, False otherwise
    """
    filename = filepath.name
    refresh_method = _determine_refresh_method(token_data, filename)
    
    if not refresh_method:
        logger.error(f"Cannot determine how to refresh {filename}")
        return False
    
    if refresh_method == 'agentcore':
        return _refresh_agentcore_token(token_data, filename)
    elif refresh_method == 'oauth':
        return _refresh_oauth_token(token_data, filename)
    else:
        logger.error(f"Unknown refresh method: {refresh_method}")
        return False


def _scan_noauth_services() -> List[Dict]:
    """
    Scan registry servers and find services with auth_type: none.
    
    Returns:
        List of no-auth service configurations
    """
    registry_dir = PROJECT_ROOT / "registry" / "servers"
    noauth_services = []
    
    if not registry_dir.exists():
        logger.warning(f"Registry servers directory not found: {registry_dir}")
        return []
    
    logger.debug(f"Scanning for no-auth services in: {registry_dir}")
    
    for json_file in registry_dir.glob("*.json"):
        # Skip server_state.json
        if json_file.name == "server_state.json":
            continue
            
        try:
            with open(json_file, 'r') as f:
                server_config = json.load(f)
                
            auth_type = server_config.get("auth_type")
            if auth_type == "none":
                # Extract relevant service information
                service = {
                    "server_name": server_config.get("server_name", "Unknown"),
                    "path": server_config.get("path", ""),
                    "proxy_pass_url": server_config.get("proxy_pass_url", ""),
                    "supported_transports": server_config.get("supported_transports", ["streamable-http"]),
                    "description": server_config.get("description", ""),
                    "file_name": json_file.name
                }
                noauth_services.append(service)
                logger.debug(f"Found no-auth service: {service['server_name']} ({service['path']})")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to parse {json_file.name}: {e}")
            continue
    
    return noauth_services


def _regenerate_mcp_configs() -> bool:
    """
    Regenerate MCP configuration files (mcp.json and vscode_mcp.json) after token refresh.
    
    Returns:
        True if regeneration successful, False otherwise
    """
    logger.info("Regenerating MCP configuration files...")
    
    try:
        # Check for required files
        ingress_file = OAUTH_TOKENS_DIR / "ingress.json"
        has_ingress = ingress_file.exists()
        
        # Find all egress token files
        egress_files = []
        for file_path in OAUTH_TOKENS_DIR.glob("*-egress.json"):
            if file_path.is_file():
                egress_files.append(file_path)
                logger.debug(f"Found egress token file: {file_path.name}")
        
        # Scan for no-auth services
        noauth_services = _scan_noauth_services()
        logger.info(f"Found {len(noauth_services)} no-auth services to include")
        
        if not has_ingress and not egress_files and not noauth_services:
            logger.warning("No token files or no-auth services found, skipping MCP configuration generation")
            return True
        
        # Generate both configurations
        vscode_success = _generate_vscode_config(has_ingress, ingress_file, egress_files, noauth_services)
        roocode_success = _generate_roocode_config(has_ingress, ingress_file, egress_files, noauth_services)
        
        if vscode_success and roocode_success:
            logger.info("MCP configuration files regenerated successfully")
            return True
        else:
            logger.error("Failed to regenerate some MCP configuration files")
            return False
            
    except Exception as e:
        logger.error(f"Error regenerating MCP configs: {e}")
        return False


def _get_ingress_headers(ingress_file: Path) -> Dict[str, str]:
    """
    Extract ingress authentication headers from token file.
    
    Args:
        ingress_file: Path to ingress token file
        
    Returns:
        Dictionary of ingress headers
    """
    headers = {}
    if ingress_file.exists():
        try:
            with open(ingress_file, 'r') as f:
                ingress_data = json.load(f)
                headers = {
                    "X-Authorization": f"Bearer {ingress_data.get('access_token', '')}",
                    "X-User-Pool-Id": ingress_data.get('user_pool_id', ''),
                    "X-Client-Id": ingress_data.get('client_id', ''),
                    "X-Region": ingress_data.get('region', 'us-east-1')
                }
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read ingress file: {e}")
    
    return headers


def _create_egress_server_config(
    egress_file: Path,
    ingress_headers: Dict[str, str],
    registry_url: str,
    config_type: str = "vscode"
) -> Tuple[str, Dict]:
    """
    Create server configuration from egress token file.
    
    Args:
        egress_file: Path to egress token file
        ingress_headers: Ingress authentication headers
        registry_url: Base registry URL
        config_type: Either "vscode" or "roocode"
        
    Returns:
        Tuple of (server_key, server_config)
    """
    try:
        with open(egress_file, 'r') as f:
            egress_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to read egress file {egress_file.name}: {e}")
        return None, None
    
    provider = egress_data.get('provider', '')
    token = egress_data.get('access_token', '')
    cloud_id = egress_data.get('cloud_id', '')
    
    # Determine server key and URL
    if provider == 'atlassian':
        server_key = 'atlassian'
        headers = {"Authorization": f"Bearer {token}"}
        if cloud_id:
            headers["X-Atlassian-Cloud-Id"] = cloud_id
        if ingress_headers:
            headers.update(ingress_headers)
        url = f"{registry_url}/atlassian/mcp"
        
    elif provider == 'bedrock-agentcore':
        # Extract server name from filename
        filename = egress_file.name
        if filename.startswith("bedrock-agentcore-") and filename.endswith("-egress.json"):
            server_key = filename.replace("bedrock-agentcore-", "").replace("-egress.json", "")
        else:
            server_key = "sre-gateway"
        
        headers = {"Authorization": f"Bearer {token}"}
        if ingress_headers:
            headers.update(ingress_headers)
        url = f"{registry_url}/{server_key}/mcp"
        
    else:
        # Generic provider
        server_key = provider
        headers = {"Authorization": f"Bearer {token}"}
        if ingress_headers:
            headers.update(ingress_headers)
        url = f"{registry_url}/{provider}/mcp"
    
    # Create config based on type
    if config_type == "vscode":
        server_config = {
            "url": url,
            "headers": headers
        }
    else:  # roocode
        server_config = {
            "type": "streamable-http",
            "url": url,
            "headers": headers,
            "disabled": False,
            "alwaysAllow": []
        }
    
    return server_key, server_config


def _create_noauth_server_config(
    service: Dict,
    ingress_headers: Dict[str, str],
    registry_url: str,
    config_type: str = "vscode"
) -> Tuple[str, Dict]:
    """
    Create server configuration for no-auth service.
    
    Args:
        service: No-auth service information
        ingress_headers: Ingress authentication headers
        registry_url: Base registry URL
        config_type: Either "vscode" or "roocode"
        
    Returns:
        Tuple of (server_key, server_config)
    """
    # Use path as server key (remove leading and trailing slashes)
    server_key = service["path"].strip("/")
    if not server_key:
        return None, None
    
    # Construct service URL
    path = service["path"].rstrip("/")
    service_url = f"{registry_url}{path}/mcp"
    
    # Create config based on type
    if config_type == "vscode":
        server_config = {
            "url": service_url
        }
        if ingress_headers:
            server_config["headers"] = ingress_headers
    else:  # roocode
        # Determine transport type
        supported_transports = service.get("supported_transports", ["streamable-http"])
        transport_type = supported_transports[0] if supported_transports else "streamable-http"
        
        server_config = {
            "type": transport_type,
            "url": service_url,
            "disabled": False,
            "alwaysAllow": []
        }
        if ingress_headers:
            server_config["headers"] = ingress_headers
    
    return server_key, server_config


def _generate_vscode_config(
    has_ingress: bool,
    ingress_file: Path,
    egress_files: List[Path],
    noauth_services: List[Dict] = None
) -> bool:
    """
    Generate VS Code MCP configuration file.
    
    Args:
        has_ingress: Whether ingress token is available
        ingress_file: Path to ingress token file
        egress_files: List of egress token file paths
        noauth_services: List of no-auth service configurations
        
    Returns:
        True if generation successful, False otherwise
    """
    config_file = OAUTH_TOKENS_DIR / "vscode_mcp.json"
    
    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
            temp_path = temp_file.name
            
            # Default registry URL
            registry_url = os.getenv('REGISTRY_URL', 'https://mcpgateway.ddns.net')
            
            # Initialize configuration
            config = {"mcp": {"servers": {}}}
            
            # Get ingress headers
            ingress_headers = _get_ingress_headers(ingress_file) if has_ingress else {}
            
            # Process egress files
            for egress_file in egress_files:
                server_key, server_config = _create_egress_server_config(
                    egress_file, ingress_headers, registry_url, "vscode"
                )
                if server_key and server_config:
                    config["mcp"]["servers"][server_key] = server_config
                    logger.debug(f"Added egress service {server_key} to VS Code config")
            
            # Process no-auth services
            if noauth_services:
                for service in noauth_services:
                    server_key, server_config = _create_noauth_server_config(
                        service, ingress_headers, registry_url, "vscode"
                    )
                    
                    # Skip if already added or invalid
                    if not server_key or server_key in config["mcp"]["servers"]:
                        continue
                    
                    config["mcp"]["servers"][server_key] = server_config
                    logger.debug(f"Added no-auth service {server_key} to VS Code config")
            
            # Write JSON to temp file
            json.dump(config, temp_file, indent=2)
        
        # Move temp file to final location and set permissions
        os.rename(temp_path, config_file)
        os.chmod(config_file, 0o600)
        
        logger.info(f"Generated VS Code MCP config: {config_file}")
        logger.debug(f"VS Code config written to: {config_file.absolute()}")
        return True
        
    except Exception as e:
        logger.error(f"Error generating VS Code MCP config: {e}")
        if 'temp_path' in locals():
            try:
                os.unlink(temp_path)
            except:
                pass
        return False


def _generate_roocode_config(
    has_ingress: bool,
    ingress_file: Path,
    egress_files: List[Path],
    noauth_services: List[Dict] = None
) -> bool:
    """
    Generate Roocode MCP configuration file.
    
    Args:
        has_ingress: Whether ingress token is available
        ingress_file: Path to ingress token file
        egress_files: List of egress token file paths
        noauth_services: List of no-auth service configurations
        
    Returns:
        True if generation successful, False otherwise
    """
    config_file = OAUTH_TOKENS_DIR / "mcp.json"
    
    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
            temp_path = temp_file.name
            
            # Default registry URL
            registry_url = os.getenv('REGISTRY_URL', 'https://mcpgateway.ddns.net')
            
            # Initialize configuration
            config = {"mcpServers": {}}
            
            # Get ingress headers
            ingress_headers = _get_ingress_headers(ingress_file) if has_ingress else {}
            
            # Process egress files
            for egress_file in egress_files:
                server_key, server_config = _create_egress_server_config(
                    egress_file, ingress_headers, registry_url, "roocode"
                )
                if server_key and server_config:
                    config["mcpServers"][server_key] = server_config
                    logger.debug(f"Added egress service {server_key} to Roocode config")
            
            # Process no-auth services
            if noauth_services:
                for service in noauth_services:
                    server_key, server_config = _create_noauth_server_config(
                        service, ingress_headers, registry_url, "roocode"
                    )
                    
                    # Skip if already added or invalid
                    if not server_key or server_key in config["mcpServers"]:
                        continue
                    
                    config["mcpServers"][server_key] = server_config
                    logger.debug(f"Added no-auth service {server_key} to Roocode config")
            
            # Write JSON to temp file
            json.dump(config, temp_file, indent=2)
        
        # Move temp file to final location and set permissions
        os.rename(temp_path, config_file)
        os.chmod(config_file, 0o600)
        
        logger.info(f"Generated Roocode MCP config: {config_file}")
        logger.debug(f"Roocode config written to: {config_file.absolute()}")
        return True
        
    except Exception as e:
        logger.error(f"Error generating Roocode MCP config: {e}")
        if 'temp_path' in locals():
            try:
                os.unlink(temp_path)
            except:
                pass
        return False


def _run_refresh_cycle(
    buffer_seconds: int = DEFAULT_EXPIRY_BUFFER,
    force_refresh: bool = False
) -> None:
    """
    Run a single refresh cycle, checking and refreshing expiring tokens.
    
    Args:
        buffer_seconds: Number of seconds before expiry to trigger refresh
        force_refresh: If True, refresh all tokens regardless of expiration
    """
    logger.info("Starting token refresh cycle...")
    logger.debug(f"Token directory: {OAUTH_TOKENS_DIR.absolute()}")
    
    # Find expiring tokens
    if force_refresh:
        expiring_tokens = _get_all_tokens()
        logger.info("Force refresh enabled - will refresh all tokens")
    else:
        expiring_tokens = _get_expiring_tokens(buffer_seconds)
    
    if not expiring_tokens:
        logger.info("No tokens need refreshing")
        return
    
    logger.info(f"Found {len(expiring_tokens)} token(s) needing refresh")
    
    # Refresh each expiring token
    success_count = 0
    for filepath, token_data in expiring_tokens:
        logger.info(f"Attempting to refresh: {filepath.name}")
        logger.debug(f"Processing token file: {filepath.absolute()}")
        
        if _refresh_token(filepath, token_data):
            success_count += 1
            logger.info(f"Token successfully updated at: {filepath.absolute()}")
        else:
            logger.error(f"Failed to refresh: {filepath.name}")
            logger.error(f"Failed token location: {filepath.absolute()}")
    
    logger.info(f"Refresh cycle complete: {success_count}/{len(expiring_tokens)} tokens refreshed successfully")
    
    # Regenerate MCP configuration files if any tokens were refreshed
    if success_count > 0:
        logger.info("Regenerating MCP configuration files after token refresh...")
        if _regenerate_mcp_configs():
            logger.info("MCP configuration files updated successfully")
        else:
            logger.error("Failed to update MCP configuration files")


def _get_pidfile_path() -> Path:
    """
    Get the path to the PID file for the token refresher service.
    
    Returns:
        Path to the PID file
    """
    return PROJECT_ROOT / "token_refresher.pid"


def _write_pidfile() -> None:
    """
    Write the current process PID to the PID file.
    """
    pidfile = _get_pidfile_path()
    with open(pidfile, 'w') as f:
        f.write(str(os.getpid()))
    logger.debug(f"PID file written: {pidfile}")


def _remove_pidfile() -> None:
    """
    Remove the PID file if it exists.
    """
    pidfile = _get_pidfile_path()
    try:
        if pidfile.exists():
            pidfile.unlink()
            logger.debug(f"PID file removed: {pidfile}")
    except Exception as e:
        logger.warning(f"Failed to remove PID file: {e}")


def _kill_existing_instance() -> bool:
    """
    Kill any existing token refresher instance if running.
    
    Returns:
        True if an existing instance was killed, False if none was found
    """
    pidfile = _get_pidfile_path()
    
    if not pidfile.exists():
        logger.debug("No PID file found, no existing instance to kill")
        return False
    
    try:
        with open(pidfile, 'r') as f:
            old_pid = int(f.read().strip())
        
        # Check if process exists and is a token refresher
        if psutil.pid_exists(old_pid):
            try:
                process = psutil.Process(old_pid)
                cmdline = ' '.join(process.cmdline())
                
                # Check if it's actually our token refresher process
                if 'token_refresher.py' in cmdline:
                    logger.info(f"Found existing token refresher instance (PID: {old_pid})")
                    logger.info(f"Killing existing instance: {cmdline}")
                    
                    # Try graceful shutdown first
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                        logger.info(f"Gracefully terminated existing instance (PID: {old_pid})")
                    except psutil.TimeoutExpired:
                        # Force kill if graceful shutdown fails
                        logger.warning(f"Graceful shutdown failed, force killing PID: {old_pid}")
                        process.kill()
                        process.wait()
                        logger.info(f"Force killed existing instance (PID: {old_pid})")
                    
                    return True
                else:
                    logger.debug(f"PID {old_pid} exists but is not a token refresher process")
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.debug(f"Could not access process {old_pid}: {e}")
        else:
            logger.debug(f"PID {old_pid} no longer exists")
        
        # Clean up stale PID file
        _remove_pidfile()
        return False
        
    except (ValueError, FileNotFoundError) as e:
        logger.debug(f"Invalid or missing PID file: {e}")
        _remove_pidfile()
        return False
    except Exception as e:
        logger.error(f"Error checking for existing instance: {e}")
        return False


def _setup_signal_handlers() -> None:
    """
    Set up signal handlers for graceful shutdown.
    """
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        _remove_pidfile()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def main():
    """Main entry point for the token refresher service."""
    parser = argparse.ArgumentParser(
        description="OAuth Token Refresher Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with default settings (check every 5 minutes, refresh 1 hour before expiry)
    uv run python credentials-provider/token_refresher.py
    
    # Check every 10 minutes
    uv run python credentials-provider/token_refresher.py --interval 600
    
    # Refresh tokens 2 hours before expiry
    uv run python credentials-provider/token_refresher.py --buffer 7200
    
    # Run once and exit (for testing)
    uv run python credentials-provider/token_refresher.py --once
    
    # Force refresh all tokens once and exit
    uv run python credentials-provider/token_refresher.py --once --force
    
    # Run in background with logging
    nohup uv run python credentials-provider/token_refresher.py > token_refresher.log 2>&1 &
"""
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_CHECK_INTERVAL,
        help=f"Check interval in seconds (default: {DEFAULT_CHECK_INTERVAL})"
    )
    
    parser.add_argument(
        "--buffer",
        type=int,
        default=DEFAULT_EXPIRY_BUFFER,
        help=f"Refresh tokens this many seconds before expiry (default: {DEFAULT_EXPIRY_BUFFER})"
    )
    
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (for testing)"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force refresh all tokens regardless of expiration status"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    parser.add_argument(
        "--no-kill",
        action="store_true",
        help="Do not kill existing instance (will exit if one is running)"
    )
    
    args = parser.parse_args()
    
    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Handle existing instances
    if not args.once:  # Only check for existing instances in continuous mode
        if args.no_kill:
            pidfile = _get_pidfile_path()
            if pidfile.exists():
                try:
                    with open(pidfile, 'r') as f:
                        existing_pid = int(f.read().strip())
                    if psutil.pid_exists(existing_pid):
                        logger.error(f"Another token refresher instance is already running (PID: {existing_pid})")
                        logger.error("Use --no-kill flag to prevent automatic killing, or stop the existing instance first")
                        sys.exit(1)
                except:
                    pass  # Invalid PID file, continue
        else:
            # Kill existing instance if found
            killed = _kill_existing_instance()
            if killed:
                logger.info("Existing instance terminated, starting new instance")
                time.sleep(1)  # Brief pause to ensure cleanup
    
    logger.info("=" * 60)
    logger.info("OAuth Token Refresher Service Starting")
    logger.info(f"Check interval: {args.interval} seconds")
    logger.info(f"Expiry buffer: {args.buffer} seconds ({args.buffer / 3600:.1f} hours)")
    logger.info("OAuth tokens directory is configured")
    logger.info("=" * 60)
    
    # Set up signal handlers and PID file for continuous mode
    if not args.once:
        _setup_signal_handlers()
        _write_pidfile()
    
    try:
        # Run once or continuously
        if args.once:
            logger.info("Running single refresh cycle...")
            _run_refresh_cycle(args.buffer, args.force)
        else:
            logger.info("Starting continuous monitoring...")
            while True:
                try:
                    _run_refresh_cycle(args.buffer, args.force)
                    logger.info(f"Sleeping for {args.interval} seconds...")
                    time.sleep(args.interval)
                except KeyboardInterrupt:
                    logger.info("Received interrupt signal, shutting down...")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in refresh cycle: {e}")
                    logger.info(f"Continuing after error, sleeping for {args.interval} seconds...")
                    time.sleep(args.interval)
    finally:
        # Clean up PID file
        if not args.once:
            _remove_pidfile()
    
    logger.info("Token Refresher Service stopped")


if __name__ == "__main__":
    main()