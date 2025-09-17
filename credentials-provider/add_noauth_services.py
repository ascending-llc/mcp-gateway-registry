#!/usr/bin/env python3
"""
Add No-Auth Services to MCP Configuration

This script scans the registry/servers JSON files and adds services with
auth_type: "none" to the MCP configuration files (vscode_mcp.json and mcp.json).
These services only require ingress authentication headers for access.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


def _load_env_file() -> None:
    """Load environment variables from .env file in project root."""
    # Get the project root directory (parent of credentials-provider)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    env_file = project_root / ".env"

    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Remove quotes if present
                        value = value.strip('"').strip("'")
                        os.environ[key] = value
            logger.debug(f"Loaded environment variables from {env_file}")
        except Exception as e:
            logger.warning(f"Failed to load .env file: {e}")
    else:
        logger.debug(f"No .env file found at {env_file}")


def _load_json_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Load and parse a JSON file safely."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load {file_path}: {e}")
        return None


def _save_json_file(
    file_path: Path, 
    data: Dict[str, Any], 
    description: str
) -> None:
    """Save data to JSON file safely."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.chmod(file_path, 0o600)
        logger.info(f"✅ Updated {description}: {file_path}")
    except Exception as e:
        logger.error(f"Failed to save {description} to {file_path}: {e}")


def _get_registry_servers_dir() -> Path:
    """Get the path to the registry servers directory."""
    script_dir = Path(__file__).parent
    registry_dir = script_dir.parent / "registry" / "servers"
    
    if not registry_dir.exists():
        raise FileNotFoundError(f"Registry servers directory not found: {registry_dir}")
    
    return registry_dir


def _get_oauth_tokens_dir() -> Path:
    """Get the path to the oauth tokens directory."""
    script_dir = Path(__file__).parent
    tokens_dir = script_dir.parent / ".oauth-tokens"
    
    if not tokens_dir.exists():
        tokens_dir.mkdir(mode=0o700, parents=True)
        logger.info(f"Created oauth tokens directory: {tokens_dir}")
    
    return tokens_dir


def _scan_noauth_services() -> List[Dict[str, Any]]:
    """Scan registry servers and find services with auth_type: none."""
    registry_dir = _get_registry_servers_dir()
    noauth_services = []
    
    logger.info(f"Scanning registry servers directory: {registry_dir}")
    
    for json_file in registry_dir.glob("*.json"):
        # Skip server_state.json as requested
        if json_file.name == "server_state.json":
            continue
            
        server_config = _load_json_file(json_file)
        if not server_config:
            continue
            
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
            logger.info(f"Found no-auth service: {service['server_name']} ({service['path']})")
    
    return noauth_services


def _get_ingress_headers() -> Optional[Dict[str, str]]:
    """Get ingress authentication headers from tokens file."""
    tokens_dir = _get_oauth_tokens_dir()
    ingress_file = tokens_dir / "ingress.json"

    # Check AUTH_PROVIDER from environment
    auth_provider = os.environ.get('AUTH_PROVIDER', '')

    if auth_provider == 'keycloak':
        # When using Keycloak, get token from agent token file
        agent_token_file = tokens_dir / "agent-ai-coding-assistant-m2m-token.json"
        if agent_token_file.exists():
            agent_data = _load_json_file(agent_token_file)
            if agent_data and agent_data.get('access_token'):
                logger.debug("Using Keycloak agent token for ingress authentication")
                headers = {
                    "X-Authorization": f"Bearer {agent_data.get('access_token', '')}"
                }
                return headers

        # If no Keycloak token found, fall through to check ingress.json
        logger.warning("No Keycloak agent token found, trying ingress.json")

    if not ingress_file.exists():
        if auth_provider == 'keycloak':
            logger.warning("No ingress.json or Keycloak agent token found - no-auth services will have no headers")
        else:
            logger.warning("No ingress.json file found - no-auth services will have no headers")
        return None

    ingress_data = _load_json_file(ingress_file)
    if not ingress_data:
        return None

    headers = {
        "X-Authorization": f"Bearer {ingress_data.get('access_token', '')}",
        "X-User-Pool-Id": ingress_data.get('user_pool_id', ''),
        "X-Client-Id": ingress_data.get('client_id', ''),
        "X-Region": ingress_data.get('region', 'us-east-1')
    }

    return headers


def _update_vscode_config(
    noauth_services: List[Dict[str, Any]], 
    ingress_headers: Optional[Dict[str, str]]
) -> None:
    """Update VS Code MCP configuration with no-auth services."""
    tokens_dir = _get_oauth_tokens_dir()
    vscode_file = tokens_dir / "vscode_mcp.json"
    
    # Load existing config or create new one
    config = _load_json_file(vscode_file) or {"mcp": {"servers": {}}}
    
    # Ensure structure exists
    if "mcp" not in config:
        config["mcp"] = {}
    if "servers" not in config["mcp"]:
        config["mcp"]["servers"] = {}
    
    registry_url = os.environ.get("REGISTRY_URL", "https://mcpgateway.ddns.net")
    
    # Add no-auth services
    for service in noauth_services:
        # Use path as server key (remove leading and trailing slashes)
        server_key = service["path"].strip("/")
        if not server_key:
            continue
            
        # Construct service URL (handle trailing slashes properly)
        path = service["path"].rstrip("/")
        # Check if this server should skip the /mcp suffix (e.g., atlassian)
        servers_no_mcp_suffix = ["/atlassian"]
        if path in servers_no_mcp_suffix:
            service_url = f"{registry_url}{path}"
        else:
            service_url = f"{registry_url}{path}/mcp"
        
        # Create server configuration
        server_config = {
            "url": service_url
        }
        
        # Add headers if ingress auth is available
        if ingress_headers:
            server_config["headers"] = ingress_headers.copy()
        
        config["mcp"]["servers"][server_key] = server_config
        logger.info(f"Added {server_key} to VS Code config: {service_url}")
    
    _save_json_file(vscode_file, config, "VS Code MCP configuration")


def _update_roocode_config(
    noauth_services: List[Dict[str, Any]], 
    ingress_headers: Optional[Dict[str, str]]
) -> None:
    """Update Roocode MCP configuration with no-auth services."""
    tokens_dir = _get_oauth_tokens_dir()
    roocode_file = tokens_dir / "mcp.json"
    
    # Load existing config or create new one
    config = _load_json_file(roocode_file) or {"mcpServers": {}}
    
    # Ensure structure exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}
    
    registry_url = os.environ.get("REGISTRY_URL", "https://mcpgateway.ddns.net")
    
    # Add no-auth services
    for service in noauth_services:
        # Use path as server key (remove leading and trailing slashes)
        server_key = service["path"].strip("/")
        if not server_key:
            continue
            
        # Construct service URL (handle trailing slashes properly)
        path = service["path"].rstrip("/")
        # Check if this server should skip the /mcp suffix (e.g., atlassian)
        servers_no_mcp_suffix = ["/atlassian"]
        if path in servers_no_mcp_suffix:
            service_url = f"{registry_url}{path}"
        else:
            service_url = f"{registry_url}{path}/mcp"
        
        # Determine transport type
        supported_transports = service.get("supported_transports", ["streamable-http"])
        transport_type = supported_transports[0] if supported_transports else "streamable-http"
        
        # Create server configuration
        server_config = {
            "type": transport_type,
            "url": service_url,
            "disabled": False,
            "alwaysAllow": []
        }
        
        # Add headers if ingress auth is available
        if ingress_headers:
            server_config["headers"] = ingress_headers.copy()
        
        config["mcpServers"][server_key] = server_config
        logger.info(f"Added {server_key} to Roocode config: {service_url} ({transport_type})")
    
    _save_json_file(roocode_file, config, "Roocode MCP configuration")


def _parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Add no-auth services to MCP configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose debug logging"
    )
    
    return parser.parse_args()


def main() -> None:
    """Main function to add no-auth services to MCP configurations."""
    try:
        # Load environment variables from .env file
        _load_env_file()

        # Parse command line arguments
        args = _parse_arguments()

        # Set logging level based on verbose flag
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.debug("Verbose logging enabled")
        
        logger.info("🔍 Starting no-auth services discovery and configuration update")
        
        # Scan for no-auth services
        noauth_services = _scan_noauth_services()
        
        if not noauth_services:
            logger.info("No services with auth_type: 'none' found")
            return
        
        logger.info(f"Found {len(noauth_services)} no-auth services")
        
        # Get ingress authentication headers
        ingress_headers = _get_ingress_headers()
        
        if ingress_headers:
            logger.info("Using ingress authentication headers for no-auth services")
        else:
            logger.warning("No ingress authentication available - services will have no headers")
        
        # Update both MCP configuration files
        _update_vscode_config(noauth_services, ingress_headers)
        _update_roocode_config(noauth_services, ingress_headers)
        
        logger.info("✅ Successfully updated MCP configurations with no-auth services")
        
    except Exception as e:
        logger.error(f"Failed to update MCP configurations: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()