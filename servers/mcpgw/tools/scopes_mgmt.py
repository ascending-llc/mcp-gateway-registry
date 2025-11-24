"""
Scopes and groups management tools.

These tools provide functionality to manage access control scopes and groups:
- Add/remove servers from scopes groups
- Create/delete groups
- List groups and their configuration
"""

import logging
import base64
import httpx
from typing import Dict, Any, List
from fastmcp import Context

from config import settings

logger = logging.getLogger(__name__)


async def call_scopes_api(endpoint: str, form_data: Dict[str, Any], method: str = "POST") -> Dict[str, Any]:
    """
    Helper function for calling scopes management API endpoints.
    """
    try:
        registry_admin_user = settings.registry_username or "admin"
        registry_admin_password = settings.registry_password

        if not registry_admin_password:
            return {"success": False, "error": "REGISTRY_PASSWORD environment variable not set. Cannot authenticate to internal API."}

        credentials = f"{registry_admin_user}:{registry_admin_password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
        }
        
        if method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(
                    f"{settings.registry_base_url}/{endpoint}",
                    headers=headers,
                    timeout=30.0
                )
            else:
                response = await client.post(
                    f"{settings.registry_base_url}/{endpoint}",
                    data=form_data,
                    headers=headers,
                    timeout=30.0
                )

        if response.status_code == 200:
            result = response.json()
            return result
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}",
                "status_code": response.status_code
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def add_server_to_scopes_groups_impl(server_name: str, group_names: List[str], ctx: Context = None) -> Dict[str, Any]:
    """
    Add a server and all its known tools/methods to specific scopes groups.
    """
    logger.info(f"add_server_to_scopes_groups called with server_name={server_name}, group_names={group_names}")
    form_data = {
        "server_name": server_name,
        "group_names": ",".join(group_names)
    }
    return await call_scopes_api("api/internal/add-to-groups", form_data)


async def remove_server_from_scopes_groups_impl(server_name: str, group_names: List[str], ctx: Context = None) -> Dict[str, Any]:
    """
    Remove a server from specific scopes groups.
    """
    logger.info(f"remove_server_from_scopes_groups called with server_name={server_name}, group_names={group_names}")
    form_data = {
        "server_name": server_name,
        "group_names": ",".join(group_names)
    }
    return await call_scopes_api("api/internal/remove-from-groups", form_data)


async def create_group_impl(group_name: str, description: str = "", ctx: Context = None) -> Dict[str, Any]:
    """
    Create a new group in both Keycloak and scopes.yml.
    """
    logger.info(f"create_group called with group_name={group_name}")
    form_data = {
        "group_name": group_name,
        "description": description
    }
    return await call_scopes_api("api/internal/create-group", form_data)


async def delete_group_impl(group_name: str, ctx: Context = None) -> Dict[str, Any]:
    """
    Delete a group from both Keycloak and scopes.yml.
    """
    logger.info(f"delete_group called with group_name={group_name}")
    form_data = {"group_name": group_name}
    return await call_scopes_api("api/internal/delete-group", form_data)


async def list_groups_impl(ctx: Context = None) -> Dict[str, Any]:
    """
    List all groups from Keycloak and scopes.yml with synchronization status.
    """
    logger.info("list_groups called")
    result = await call_scopes_api("api/internal/list-groups", {}, method="GET")
    
    if result.get("success") or "keycloak_groups" in result:
        result["success"] = True
        result["summary"] = {
            "total_keycloak": len(result.get("keycloak_groups", [])),
            "total_scopes": len(result.get("scopes_groups", {})),
            "synchronized_count": len(result.get("synchronized", [])),
            "keycloak_only_count": len(result.get("keycloak_only", [])),
            "scopes_only_count": len(result.get("scopes_only", []))
        }
    
    return result

