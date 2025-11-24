"""
Service management tools.

These tools provide functionality to manage MCP services in the registry:
- Register new services
- List all services
- Toggle service status
- Remove services
- Refresh service tools
- Check health status
"""

import logging
import json
import base64
import httpx
from typing import Dict, Any, Optional, List
from fastmcp import Context
from config import settings
from core.registry import call_registry_api

logger = logging.getLogger(__name__)


async def toggle_service_impl(service_path: str, ctx: Context = None) -> Dict[str, Any]:
    """
    Toggles the enabled/disabled state of a registered MCP server in the gateway.
    """
    endpoint = "/api/internal/toggle"
    form_data = {"service_path": service_path}
    return await call_registry_api("POST", endpoint, ctx, data=form_data)


async def register_service_impl(
    server_name: str,
    path: str,
    proxy_pass_url: str,
    description: Optional[str] = "",
    tags: Optional[List[str]] = None,
    num_tools: Optional[int] = 0,
    num_stars: Optional[int] = 0,
    is_python: Optional[bool] = False,
    license: Optional[str] = "N/A",
    auth_provider: Optional[str] = None,
    auth_type: Optional[str] = None,
    supported_transports: Optional[List[str]] = None,
    headers: Optional[List[Dict[str, str]]] = None,
    tool_list: Optional[List[Dict[str, Any]]] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Registers a new MCP server with the gateway.
    """
    endpoint = "/api/internal/register"
    tags_str = ",".join(tags) if isinstance(tags, list) and tags is not None else tags

    form_data = {
        "name": server_name,
        "path": path,
        "proxy_pass_url": proxy_pass_url,
        "description": description if description is not None else "",
        "tags": tags_str if tags_str is not None else "",
        "num_tools": num_tools,
        "num_stars": num_stars,
        "is_python": is_python,
        "license_str": license
    }

    if auth_provider is not None:
        form_data["auth_provider"] = auth_provider
    if auth_type is not None:
        form_data["auth_type"] = auth_type
    if supported_transports is not None:
        form_data["supported_transports"] = json.dumps(supported_transports) if isinstance(supported_transports, list) else supported_transports
    if headers is not None:
        form_data["headers"] = json.dumps(headers) if isinstance(headers, list) else headers
    if tool_list is not None:
        form_data["tool_list_json"] = json.dumps(tool_list) if isinstance(tool_list, list) else tool_list

    form_data = {k: v for k, v in form_data.items() if v is not None}
    return await call_registry_api("POST", endpoint, ctx, data=form_data)


async def list_services_impl(ctx: Context = None) -> Dict[str, Any]:
    """
    Lists all registered MCP services in the gateway.
    """
    logger.info("MCPGW: list_services tool called")
    endpoint = "/api/internal/list"

    try:
        result = await call_registry_api("GET", endpoint, ctx)

        if isinstance(result, dict) and "services" in result:
            logger.info(f"MCPGW: Successfully retrieved {result.get('total_count', len(result['services']))} services")
            return result
        else:
            logger.warning(f"MCPGW: Unexpected response format from registry list endpoint: {result}")
            return {
                "services": [],
                "total_count": 0,
                "error": "Unexpected response format from registry"
            }

    except Exception as e:
        logger.error(f"MCPGW: Failed to list services: {e}")
        return {
            "services": [],
            "total_count": 0,
            "error": f"Failed to retrieve services: {str(e)}"
        }


async def remove_service_impl(service_path: str, ctx: Context = None) -> Dict[str, Any]:
    """
    Removes a registered MCP server from the gateway.
    """
    endpoint = "/api/internal/remove"
    form_data = {"service_path": service_path}
    return await call_registry_api("POST", endpoint, ctx, data=form_data)


async def refresh_service_impl(service_path: str, ctx: Context = None) -> Dict[str, Any]:
    """
    Triggers a refresh of the tool list for a specific registered MCP server.
    """
    endpoint = f"/api/refresh/{service_path.lstrip('/')}"
    return await call_registry_api("POST", endpoint, ctx)


async def healthcheck_impl(ctx: Context = None) -> Dict[str, Any]:
    """
    Retrieves health status information from all registered MCP servers.
    """
    try:
        registry_username = settings.registry_username or "admin"
        registry_password = settings.registry_password

        if not registry_password:
            raise Exception("REGISTRY_PASSWORD not configured in environment")

        credentials = f"{registry_username}:{registry_password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        healthcheck_url = f"{settings.registry_base_url}/api/internal/healthcheck"
        logger.info(f"Calling internal health check endpoint: {healthcheck_url}")

        async with httpx.AsyncClient() as client:
            response = await client.post(healthcheck_url, headers=headers)

            if response.status_code == 200:
                health_data = response.json()
                logger.info(f"Retrieved health status data for {len(health_data)} servers")
                return health_data
            else:
                logger.error(f"Health check API returned status {response.status_code}: {response.text}")
                raise Exception(f"Health check API call failed with status {response.status_code}")

    except Exception as e:
        logger.error(f"Error retrieving health status: {e}")
        raise Exception(f"Failed to retrieve health status: {str(e)}")

