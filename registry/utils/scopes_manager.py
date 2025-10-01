"""
Utility functions for managing scopes.yml file updates when servers are registered or removed.
"""

import os
import yaml
import logging
from typing import List, Dict, Any
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)


def _get_scopes_file_path() -> Path:
    """Get the path to the scopes.yml file."""
    # This is the mounted volume location in the container
    return Path("/app/auth_server/scopes.yml")


def _read_scopes_file() -> Dict[str, Any]:
    """Read the current scopes.yml file."""
    scopes_file = _get_scopes_file_path()

    if not scopes_file.exists():
        logger.error(f"Scopes file not found at {scopes_file}")
        raise FileNotFoundError(f"Scopes file not found at {scopes_file}")

    with open(scopes_file, 'r') as f:
        return yaml.safe_load(f)


def _write_scopes_file(scopes_data: Dict[str, Any]) -> None:
    """Write the updated scopes data to the file."""
    scopes_file = _get_scopes_file_path()

    # Direct write to the file (can't use atomic replacement with mounted volumes)
    # Create a backup first for safety
    backup_file = scopes_file.with_suffix('.backup')

    try:
        # Make a backup copy
        import shutil
        shutil.copy2(scopes_file, backup_file)

        # Write directly to the file
        with open(scopes_file, 'w') as f:
            # Create a custom YAML dumper that doesn't generate anchors/aliases
            class NoAnchorDumper(yaml.SafeDumper):
                def ignore_aliases(self, data):
                    return True

            yaml.dump(scopes_data, f, default_flow_style=False, sort_keys=False, Dumper=NoAnchorDumper)

        logger.info(f"Successfully updated scopes file at {scopes_file}")

        # Remove backup after successful write
        if backup_file.exists():
            backup_file.unlink()

    except Exception as e:
        logger.error(f"Failed to write scopes file: {e}")
        # Try to restore from backup if write failed
        if backup_file.exists():
            shutil.copy2(backup_file, scopes_file)
            logger.info("Restored scopes file from backup")
        raise


def _create_server_entry(server_path: str, tools: List[str]) -> Dict[str, Any]:
    """Create a server entry for scopes.yml."""
    # Remove leading slash from server path
    server_name = server_path.lstrip('/')

    return {
        "server": server_name,
        "methods": [
            "initialize",
            "notifications/initialized",
            "ping",
            "tools/list",
            "tools/call",
            "resources/list",
            "resources/templates/list"
        ],
        "tools": tools
    }


async def add_server_to_scopes(server_path: str, server_name: str, tools: List[str]) -> bool:
    """
    Add a server to all appropriate scope sections in scopes.yml.

    Args:
        server_path: The server's path (e.g., '/example-server')
        server_name: The server's display name
        tools: List of tool names the server provides

    Returns:
        True if successful, False otherwise
    """
    try:
        # Read current scopes
        scopes_data = _read_scopes_file()

        # Create the server entry
        server_entry = _create_server_entry(server_path, tools)

        # Add to unrestricted scope sections only
        sections = [
            "mcp-servers-unrestricted/read",
            "mcp-servers-unrestricted/execute"
        ]

        modified = False
        for section in sections:
            if section in scopes_data:
                # Check if server already exists in this section
                existing = [s for s in scopes_data[section]
                           if s.get('server') == server_entry['server']]

                if existing:
                    # Update existing entry
                    idx = scopes_data[section].index(existing[0])
                    scopes_data[section][idx] = server_entry.copy()
                    logger.info(f"Updated existing server {server_path} in section {section}")
                else:
                    # Add new entry
                    scopes_data[section].append(server_entry.copy())
                    logger.info(f"Added server {server_path} to section {section}")

                modified = True
            else:
                logger.warning(f"Scope section {section} not found in scopes.yml")

        if modified:
            # Write back the updated scopes
            _write_scopes_file(scopes_data)
            logger.info(f"Successfully added server {server_path} to scopes.yml")
            return True
        else:
            logger.warning(f"No sections were modified for server {server_path}")
            return False

    except Exception as e:
        logger.error(f"Failed to add server {server_path} to scopes: {e}")
        return False


async def remove_server_from_scopes(server_path: str) -> bool:
    """
    Remove a server from all scope sections in scopes.yml.

    Args:
        server_path: The server's path (e.g., '/example-server')

    Returns:
        True if successful, False otherwise
    """
    try:
        # Read current scopes
        scopes_data = _read_scopes_file()

        # Remove leading slash from server path
        server_name = server_path.lstrip('/')

        # Remove from all standard scope sections
        sections = [
            "mcp-servers-unrestricted/read",
            "mcp-servers-unrestricted/execute",
            "mcp-servers-restricted/read",
            "mcp-servers-restricted/execute"
        ]

        modified = False
        for section in sections:
            if section in scopes_data:
                original_length = len(scopes_data[section])
                scopes_data[section] = [s for s in scopes_data[section]
                                        if s.get('server') != server_name]

                if len(scopes_data[section]) < original_length:
                    logger.info(f"Removed server {server_path} from section {section}")
                    modified = True

        if modified:
            # Write back the updated scopes
            _write_scopes_file(scopes_data)
            logger.info(f"Successfully removed server {server_path} from scopes.yml")
            return True
        else:
            logger.warning(f"Server {server_path} not found in any scope sections")
            return False

    except Exception as e:
        logger.error(f"Failed to remove server {server_path} from scopes: {e}")
        return False


async def trigger_auth_server_reload() -> bool:
    """
    Trigger the auth server to reload its scopes configuration.

    Returns:
        True if successful, False otherwise
    """
    try:
        admin_user = os.environ.get("ADMIN_USER", "admin")
        admin_password = os.environ.get("ADMIN_PASSWORD")

        if not admin_password:
            logger.error("ADMIN_PASSWORD not set, cannot reload auth server")
            return False

        # Create Basic Auth header
        import base64
        credentials = f"{admin_user}:{admin_password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://auth-server:8888/internal/reload-scopes",
                headers={"Authorization": f"Basic {encoded_credentials}"},
                timeout=10.0
            )

            if response.status_code == 200:
                logger.info("Successfully triggered auth server scope reload")
                return True
            else:
                logger.error(f"Failed to reload auth server scopes: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"Failed to trigger auth server reload: {e}")
        # Non-fatal - scopes will be picked up on next restart
        return False


async def update_server_scopes(server_path: str, server_name: str, tools: List[str]) -> bool:
    """
    Update scopes for a server (add or update) and reload auth server.

    This is a convenience function that combines adding/updating scopes
    and triggering the auth server reload.

    Args:
        server_path: The server's path (e.g., '/example-server')
        server_name: The server's display name
        tools: List of tool names the server provides

    Returns:
        True if successful, False otherwise
    """
    # Add/update server in scopes.yml
    if not await add_server_to_scopes(server_path, server_name, tools):
        return False

    # Trigger auth server reload
    await trigger_auth_server_reload()

    return True


async def remove_server_scopes(server_path: str) -> bool:
    """
    Remove scopes for a server and reload auth server.

    This is a convenience function that combines removing scopes
    and triggering the auth server reload.

    Args:
        server_path: The server's path (e.g., '/example-server')

    Returns:
        True if successful, False otherwise
    """
    # Remove server from scopes.yml
    if not await remove_server_from_scopes(server_path):
        return False

    # Trigger auth server reload
    await trigger_auth_server_reload()

    return True


async def add_server_to_groups(server_path: str, group_names: List[str]) -> bool:
    """
    Add a server and all its known tools/methods to specific groups in scopes.yml.

    Gets the server's tools from the last health check and adds them to the
    specified groups using the same format as other servers.

    Args:
        server_path: The server's path (e.g., '/example-server')
        group_names: List of group names to add the server to (e.g., ['mcp-servers-restricted/read'])

    Returns:
        True if successful, False otherwise
    """
    try:
        # First, get the server info to find its tools
        from ..services.server_service import server_service

        server_info = server_service.get_server_info(server_path)
        if not server_info:
            logger.error(f"Server {server_path} not found in registry")
            return False

        # Get the tools from the last health check
        tool_list = server_info.get("tool_list", [])
        tool_names = [tool["name"] for tool in tool_list if isinstance(tool, dict) and "name" in tool]

        logger.info(f"Found {len(tool_names)} tools for server {server_path}: {tool_names}")

        # Read current scopes
        scopes_data = _read_scopes_file()

        # Create the server entry with discovered tools
        server_entry = _create_server_entry(server_path, tool_names)

        modified = False
        for group_name in group_names:
            if group_name in scopes_data:
                # Check if server already exists in this group
                existing = [s for s in scopes_data[group_name]
                           if s.get('server') == server_entry['server']]

                if existing:
                    # Update existing entry
                    idx = scopes_data[group_name].index(existing[0])
                    scopes_data[group_name][idx] = server_entry.copy()
                    logger.info(f"Updated existing server {server_path} in group {group_name}")
                else:
                    # Add new entry
                    scopes_data[group_name].append(server_entry.copy())
                    logger.info(f"Added server {server_path} to group {group_name}")

                modified = True
            else:
                logger.warning(f"Group {group_name} not found in scopes.yml")

        if modified:
            # Write back the updated scopes
            _write_scopes_file(scopes_data)
            logger.info(f"Successfully added server {server_path} to groups: {group_names}")

            # Trigger auth server reload
            await trigger_auth_server_reload()

            return True
        else:
            logger.warning(f"No groups were modified for server {server_path}")
            return False

    except Exception as e:
        logger.error(f"Failed to add server {server_path} to groups {group_names}: {e}")
        return False


async def remove_server_from_groups(server_path: str, group_names: List[str]) -> bool:
    """
    Remove a server from specific groups in scopes.yml.

    Args:
        server_path: The server's path (e.g., '/example-server')
        group_names: List of group names to remove the server from

    Returns:
        True if successful, False otherwise
    """
    try:
        # Read current scopes
        scopes_data = _read_scopes_file()

        # Remove leading slash from server path
        server_name = server_path.lstrip('/')

        modified = False
        for group_name in group_names:
            if group_name in scopes_data:
                original_length = len(scopes_data[group_name])
                scopes_data[group_name] = [s for s in scopes_data[group_name]
                                          if s.get('server') != server_name]

                if len(scopes_data[group_name]) < original_length:
                    logger.info(f"Removed server {server_path} from group {group_name}")
                    modified = True
            else:
                logger.warning(f"Group {group_name} not found in scopes.yml")

        if modified:
            # Write back the updated scopes
            _write_scopes_file(scopes_data)
            logger.info(f"Successfully removed server {server_path} from groups: {group_names}")

            # Trigger auth server reload
            await trigger_auth_server_reload()

            return True
        else:
            logger.warning(f"Server {server_path} not found in any of the specified groups")
            return False

    except Exception as e:
        logger.error(f"Failed to remove server {server_path} from groups {group_names}: {e}")
        return False