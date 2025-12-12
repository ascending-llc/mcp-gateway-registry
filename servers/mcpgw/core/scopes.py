"""
Scopes management functionality.

This module handles loading and checking user scopes for fine-grained access control (FGAC).
Scopes determine which tools and servers users can access.
"""

import logging
import yaml
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Global variable to cache loaded scopes
_scopes_config: Optional[Dict[str, Any]] = None


async def load_scopes_config() -> Dict[str, Any]:
    """
    Load and parse the scopes.yml configuration file.
    
    Returns:
        Dict containing the parsed scopes configuration
    """
    global _scopes_config

    if _scopes_config is not None:
        return _scopes_config

    try:
        from config import settings
        scopes_path = settings.scopes_config_path

        if not scopes_path.exists():
            logger.warning(f"Scopes file not found at {scopes_path}")
            return {}

        with open(scopes_path, 'r') as f:
            _scopes_config = yaml.safe_load(f)

        logger.info(f"Successfully loaded scopes configuration from {scopes_path}")
        return _scopes_config

    except Exception as e:
        logger.error(f"Failed to load scopes configuration: {e}")
        return {}


def check_tool_access(
        server_name: str,
        tool_name: str,
        user_scopes: List[str],
        scopes_config: Dict[str, Any]
) -> bool:
    """
    Check if a user has access to a specific tool based on their scopes.
    
    Args:
        server_name: Name of the server (e.g., 'mcpgw', 'fininfo')
        tool_name: Name of the tool 
        user_scopes: List of scopes the user has
        scopes_config: Parsed scopes configuration
        
    Returns:
        True if user has access, False otherwise
    """
    if not scopes_config or not user_scopes:
        logger.warning(f"Access denied: {server_name}.{tool_name} - no scopes config or user scopes")
        return False
    
    logger.info(f"Checking access for {server_name}.{tool_name} with user scopes: {user_scopes}")
    logger.info(f"Available scope keys in config: {list(scopes_config.keys())}")
    
    # Check direct scope access
    for user_scope in user_scopes:
        logger.info(f"Checking user scope: {user_scope}")
        if user_scope in scopes_config:
            scope_data = scopes_config[user_scope]
            logger.info(f"Found scope data for {user_scope}: {type(scope_data)}")
            if isinstance(scope_data, list):
                # This is a server scope (like mcp-servers-unrestricted/read)
                for server_config in scope_data:
                    logger.info(f"Checking server config: {server_config.get('server')} vs {server_name}")
                    # Normalize server names by stripping trailing slashes for comparison
                    config_server_name = server_config.get('server', '').rstrip('/')
                    normalized_server_name = server_name.rstrip('/')
                    if config_server_name == normalized_server_name:
                        tools = server_config.get('tools', [])
                        logger.info(f"Available tools for {server_name}: {tools}")
                        if tool_name in tools:
                            logger.info(f"Access granted: {server_name}.{tool_name} via scope {user_scope}")
                            return True

    # Check group mappings for additional access
    group_mappings = scopes_config.get('group_mappings', {})
    logger.debug(f"Checking group mappings: {group_mappings}")
    for group, mapped_scopes in group_mappings.items():
        if group in user_scopes:
            logger.debug(f"User is in group {group}, checking mapped scopes: {mapped_scopes}")
            # User is in this group, check the mapped scopes
            for mapped_scope in mapped_scopes:
                if mapped_scope in scopes_config:
                    scope_data = scopes_config[mapped_scope]
                    if isinstance(scope_data, list):
                        for server_config in scope_data:
                            # Normalize server names by stripping trailing slashes for comparison
                            config_server_name = server_config.get('server', '').rstrip('/')
                            normalized_server_name = server_name.rstrip('/')
                            if config_server_name == normalized_server_name:
                                tools = server_config.get('tools', [])
                                if tool_name in tools:
                                    logger.info(f"Access granted: {server_name}.{tool_name} via group {group} -> {mapped_scope}")
                                    return True
    
    logger.warning(f"Access denied: {server_name}.{tool_name} for scopes {user_scopes}")
    return False

