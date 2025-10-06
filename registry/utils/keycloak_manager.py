"""
Keycloak group management utilities.

This module provides functions to manage groups in Keycloak via the Admin REST API.
It handles authentication, group CRUD operations, and integrates with the registry.
"""

import os
import logging
import httpx
from typing import Dict, Any, List, Optional
import base64


logger = logging.getLogger(__name__)


KEYCLOAK_ADMIN_URL: str = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_REALM: str = os.environ.get("KEYCLOAK_REALM", "mcp-gateway")
KEYCLOAK_ADMIN: str = os.environ.get("KEYCLOAK_ADMIN", "admin")
KEYCLOAK_ADMIN_PASSWORD: Optional[str] = os.environ.get("KEYCLOAK_ADMIN_PASSWORD")


async def _get_keycloak_admin_token() -> str:
    """
    Get admin access token from Keycloak for Admin API calls.

    Returns:
        Admin access token string

    Raises:
        Exception: If authentication fails
    """
    if not KEYCLOAK_ADMIN_PASSWORD:
        raise Exception("KEYCLOAK_ADMIN_PASSWORD environment variable not set")

    token_url = f"{KEYCLOAK_ADMIN_URL}/realms/master/protocol/openid-connect/token"

    data = {
        "username": KEYCLOAK_ADMIN,
        "password": KEYCLOAK_ADMIN_PASSWORD,
        "grant_type": "password",
        "client_id": "admin-cli"
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(token_url, data=data, headers=headers)
            response.raise_for_status()

            token_data = response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                raise Exception("No access token in Keycloak response")

            logger.info("Successfully obtained Keycloak admin token")
            return access_token

    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to authenticate with Keycloak: HTTP {e.response.status_code}")
        raise Exception(f"Keycloak authentication failed: HTTP {e.response.status_code}") from e
    except Exception as e:
        logger.error(f"Error getting Keycloak admin token: {e}")
        raise Exception(f"Failed to authenticate with Keycloak: {e}") from e


async def create_keycloak_group(
    group_name: str,
    description: str = ""
) -> Dict[str, Any]:
    """
    Create a group in Keycloak.

    Args:
        group_name: Name of the group to create
        description: Optional description for the group

    Returns:
        Dict containing group information including ID

    Raises:
        Exception: If group creation fails
    """
    logger.info(f"Creating Keycloak group: {group_name}")

    try:
        # Get admin token
        admin_token = await _get_keycloak_admin_token()

        # Prepare group data
        group_data = {
            "name": group_name,
            "attributes": {
                "description": [description] if description else []
            }
        }

        # Create group via Admin API
        groups_url = f"{KEYCLOAK_ADMIN_URL}/admin/realms/{KEYCLOAK_REALM}/groups"
        headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(groups_url, json=group_data, headers=headers)

            if response.status_code == 201:
                logger.info(f"Successfully created Keycloak group: {group_name}")

                # Get the created group's details
                group_info = await get_keycloak_group(group_name)
                return group_info

            elif response.status_code == 409:
                logger.warning(f"Group already exists in Keycloak: {group_name}")
                raise Exception(f"Group '{group_name}' already exists in Keycloak")

            else:
                logger.error(f"Failed to create group: HTTP {response.status_code} - {response.text}")
                raise Exception(f"Failed to create group in Keycloak: HTTP {response.status_code}")

    except Exception as e:
        logger.error(f"Error creating Keycloak group '{group_name}': {e}")
        raise


async def delete_keycloak_group(
    group_name: str
) -> bool:
    """
    Delete a group from Keycloak.

    Args:
        group_name: Name of the group to delete

    Returns:
        True if successful

    Raises:
        Exception: If group deletion fails
    """
    logger.info(f"Deleting Keycloak group: {group_name}")

    try:
        # Get admin token
        admin_token = await _get_keycloak_admin_token()

        # First, get the group ID
        group_info = await get_keycloak_group(group_name)
        group_id = group_info.get("id")

        if not group_id:
            raise Exception(f"Group '{group_name}' not found in Keycloak")

        # Delete group via Admin API
        delete_url = f"{KEYCLOAK_ADMIN_URL}/admin/realms/{KEYCLOAK_REALM}/groups/{group_id}"
        headers = {
            "Authorization": f"Bearer {admin_token}"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(delete_url, headers=headers)

            if response.status_code == 204:
                logger.info(f"Successfully deleted Keycloak group: {group_name}")
                return True

            elif response.status_code == 404:
                logger.warning(f"Group not found in Keycloak: {group_name}")
                raise Exception(f"Group '{group_name}' not found in Keycloak")

            else:
                logger.error(f"Failed to delete group: HTTP {response.status_code} - {response.text}")
                raise Exception(f"Failed to delete group from Keycloak: HTTP {response.status_code}")

    except Exception as e:
        logger.error(f"Error deleting Keycloak group '{group_name}': {e}")
        raise


async def get_keycloak_group(
    group_name: str
) -> Dict[str, Any]:
    """
    Get a group's details from Keycloak by name.

    Args:
        group_name: Name of the group to retrieve

    Returns:
        Dict containing group information (id, name, path, attributes, etc.)

    Raises:
        Exception: If group retrieval fails or group not found
    """
    logger.info(f"Getting Keycloak group: {group_name}")

    try:
        # Get admin token
        admin_token = await _get_keycloak_admin_token()

        # List all groups and find the one with matching name
        groups_url = f"{KEYCLOAK_ADMIN_URL}/admin/realms/{KEYCLOAK_REALM}/groups"
        headers = {
            "Authorization": f"Bearer {admin_token}"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(groups_url, headers=headers)
            response.raise_for_status()

            groups = response.json()

            # Find group by name
            for group in groups:
                if group.get("name") == group_name:
                    logger.info(f"Found group: {group_name} with ID: {group.get('id')}")
                    return group

            # Group not found
            raise Exception(f"Group '{group_name}' not found in Keycloak")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error getting group: {e.response.status_code}")
        raise Exception(f"Failed to get group from Keycloak: HTTP {e.response.status_code}") from e
    except Exception as e:
        logger.error(f"Error getting Keycloak group '{group_name}': {e}")
        raise


async def list_keycloak_groups() -> List[Dict[str, Any]]:
    """
    List all groups in Keycloak realm.

    Returns:
        List of dicts containing group information

    Raises:
        Exception: If listing groups fails
    """
    logger.info("Listing all Keycloak groups")

    try:
        # Get admin token
        admin_token = await _get_keycloak_admin_token()

        # List all groups
        groups_url = f"{KEYCLOAK_ADMIN_URL}/admin/realms/{KEYCLOAK_REALM}/groups"
        headers = {
            "Authorization": f"Bearer {admin_token}"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(groups_url, headers=headers)
            response.raise_for_status()

            groups = response.json()
            logger.info(f"Retrieved {len(groups)} groups from Keycloak")

            return groups

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error listing groups: {e.response.status_code}")
        raise Exception(f"Failed to list groups from Keycloak: HTTP {e.response.status_code}") from e
    except Exception as e:
        logger.error(f"Error listing Keycloak groups: {e}")
        raise


async def group_exists_in_keycloak(
    group_name: str
) -> bool:
    """
    Check if a group exists in Keycloak.

    Args:
        group_name: Name of the group to check

    Returns:
        True if group exists, False otherwise
    """
    try:
        await get_keycloak_group(group_name)
        return True
    except Exception:
        return False
