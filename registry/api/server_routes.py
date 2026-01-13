import logging
import httpx
import os
import json
import asyncio
from typing import Annotated
from fastapi import (APIRouter, Request, Form, HTTPException, Cookie, status, Depends)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .internal_routes import (internal_list_groups, internal_healthcheck, internal_add_server_to_groups,
                              internal_remove_server_from_groups, internal_create_group, internal_delete_group)
from ..core.mcp_client import mcp_client_service
from ..core.config import settings
from ..services.server_service import server_service
from ..auth.dependencies import user_has_ui_permission_for_service
from ..auth.dependencies import CurrentUser
from ..health.service import health_service
from ..utils.scopes_manager import remove_server_scopes
from ..services.security_scanner import security_scanner_service

logger = logging.getLogger(__name__)

router = APIRouter()


class RatingRequest(BaseModel):
    rating: int

# Templates
templates = Jinja2Templates(directory=settings.templates_dir)


async def _perform_security_scan_on_registration(
    path: str,
    proxy_pass_url: str,
    server_entry: dict,
    headers_list: list | None = None,
) -> None:
    """Perform security scan on newly registered server.

    Handles the complete security scan workflow including:
    - Running the security scan with configured analyzers
    - Adding security-pending tag if scan fails
    - Disabling server if configured and scan fails
    - Updating FAISS and regenerating Nginx config if server disabled

    All scan failures are non-fatal and will be logged but not raised.

    Args:
        path: Server path (e.g., /mcpgw)
        proxy_pass_url: URL to scan
        server_entry: Server metadata dictionary
        headers_list: Optional headers for authenticated endpoints
    """
    scan_config = security_scanner_service.get_scan_config()
    if not (scan_config.enabled and scan_config.scan_on_registration):
        return

    logger.info(f"Running security scan for newly registered server: {path}")

    try:
        # Prepare headers if needed (for authenticated endpoints)
        headers_json = None
        if headers_list:
            headers_json = json.dumps(headers_list)

        # Run the security scan
        scan_result = await security_scanner_service.scan_server(
            server_url=proxy_pass_url,
            analyzers=scan_config.analyzers,
            api_key=scan_config.llm_api_key,
            headers=headers_json,
            timeout=scan_config.scan_timeout_seconds,
        )

        # Handle unsafe servers
        if not scan_result.is_safe:
            logger.warning(
                f"Server {path} failed security scan. "
                f"Critical: {scan_result.critical_issues}, High: {scan_result.high_severity}"
            )

            # Add security-pending tag if configured
            if scan_config.add_security_pending_tag:
                current_tags = server_entry.get("tags", [])
                if "security-pending" not in current_tags:
                    current_tags.append("security-pending")
                    server_entry["tags"] = current_tags
                    server_service.update_server(path, server_entry)
                    logger.info(f"Added 'security-pending' tag to {path}")

            # Disable server if configured
            if scan_config.block_unsafe_servers:
                from ..search.service import faiss_service
                from ..core.nginx_service import nginx_service

                server_service.toggle_service(path, False)
                logger.warning(f"Disabled server {path} due to failed security scan")

                # Update FAISS with disabled state
                await faiss_service.add_or_update_service(path, server_entry, False)

                # Regenerate Nginx config to remove disabled server
                enabled_servers = {
                    server_path: server_service.get_server_info(server_path)
                    for server_path in server_service.get_enabled_services()
                }
                await nginx_service.generate_config_async(enabled_servers)
        else:
            logger.info(f"Server {path} passed security scan")

    except Exception as e:
        logger.error(f"Security scan failed for {path}: {e}")
        # Non-fatal error - server is registered but scan failed


@router.get("/", response_class=HTMLResponse)
async def read_root(
        request: Request,
        query: str | None = None,
        session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
):
    """Main dashboard page showing services based on user permissions."""
    # Check authentication first and redirect if not authenticated
    if not session:
        logger.info("No session cookie at root route, redirecting to login")
        return RedirectResponse(url="/login", status_code=302)
    try:
        # Get user context
        user_context = CurrentUser
    except HTTPException as e:
        logger.info(
            f"Authentication failed at root route: {e.detail}, redirecting to login"
        )
        return RedirectResponse(url="/login", status_code=302)

    # Helper function for templates
    def can_perform_action(permission: str, service_name: str) -> bool:
        """Check if user has UI permission for a specific service"""
        return user_has_ui_permission_for_service(permission, service_name, user_context.get('ui_permissions', {}))

    service_data = []
    search_query = query.lower() if query else ""

    # Get servers based on user permissions
    if user_context["is_admin"]:
        # Admin users see all servers
        all_servers = server_service.get_all_servers()
        logger.info(
            f"Admin user {user_context['username']} accessing all {len(all_servers)} servers"
        )
    else:
        # Filtered users see only accessible servers
        all_servers = server_service.get_all_servers_with_permissions(user_context['accessible_servers'])
        logger.info(
            f"User {user_context['username']} accessing {len(all_servers)} of {len(server_service.get_all_servers())} total servers")

    sorted_server_paths = sorted(
        all_servers.keys(),
        key=lambda p: all_servers[p]["server_name"]
    )

    # Filter services based on UI permissions
    accessible_services = user_context.get('accessible_services', [])
    logger.info(f"DEBUG: User {user_context['username']} accessible_services: {accessible_services}")
    logger.info(f"DEBUG: User {user_context['username']} ui_permissions: {user_context.get('ui_permissions', {})}")
    logger.info(f"DEBUG: User {user_context['username']} scopes: {user_context.get('scopes', [])}")

    for path in sorted_server_paths:
        server_info = all_servers[path]
        server_name = server_info["server_name"]

        # Check if user can list this service
        if "all" not in accessible_services and server_name not in accessible_services:
            logger.debug(
                f"Filtering out service '{server_name}' - user doesn't have list_service permission"
            )
            continue

        # Include description and tags in search
        searchable_text = f"{server_name.lower()} {server_info.get('description', '').lower()} {' '.join(server_info.get('tags', []))}"
        if not search_query or search_query in searchable_text:
            # Get real health status from health service
            from ..health.service import health_service

            health_data = health_service._get_service_health_data(path)

            service_data.append(
                {
                    "display_name": server_name,
                    "path": path,
                    "description": server_info.get("description", ""),
                    "proxy_pass_url": server_info.get("proxy_pass_url", ""),
                    "is_enabled": server_service.is_service_enabled(path),
                    "tags": server_info.get("tags", []),
                    "num_tools": server_info.get("num_tools", 0),
                    "num_stars": server_info.get("num_stars", 0),
                    "is_python": server_info.get("is_python", False),
                    "license": server_info.get("license", "N/A"),
                    "health_status": health_data["status"],
                    "last_checked_iso": health_data["last_checked_iso"]
                }
            )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "services": service_data,
            "username": user_context['username'],
            "user_context": user_context,  # Pass full user context to template
            "can_perform_action": can_perform_action,  # Helper function for permission checks
        },
    )


@router.get("/servers")
async def get_servers_json(
        user_context: CurrentUser,
        query: str | None = None,
):
    """Get servers data as JSON for React frontend and external API (supports both session cookies and Bearer tokens)."""
    # CRITICAL DIAGNOSTIC: Log user_context received by endpoint
    logger.debug(f"[GET_SERVERS_DEBUG] Received user_context: {user_context}")
    logger.debug(f"[GET_SERVERS_DEBUG] user_context type: {type(user_context)}")
    if user_context:
        logger.debug(
            f"[GET_SERVERS_DEBUG] Username: {user_context.get('username', 'NOT PRESENT')}"
        )
        logger.debug(
            f"[GET_SERVERS_DEBUG] Scopes: {user_context.get('scopes', 'NOT PRESENT')}"
        )
        logger.debug(
            f"[GET_SERVERS_DEBUG] Auth method: {user_context.get('auth_method', 'NOT PRESENT')}"
        )

    service_data = []
    search_query = query.lower() if query else ""

    # Get servers based on user permissions (same logic as root route)
    if user_context["is_admin"]:
        all_servers = server_service.get_all_servers()
    else:
        all_servers = server_service.get_all_servers_with_permissions(user_context['accessible_servers'])

    sorted_server_paths = sorted(
        all_servers.keys(),
        key=lambda p: all_servers[p]["server_name"]
    )

    # Filter services based on UI permissions (same logic as root route)
    accessible_services = user_context.get("accessible_services", [])

    for path in sorted_server_paths:
        server_info = all_servers[path]
        server_name = server_info["server_name"]
        # Extract technical name from path (remove leading and trailing slashes)
        technical_name = path.strip("/")

        # Check if user can list this service using technical name
        if (
            "all" not in accessible_services
            and technical_name not in accessible_services
        ):
            continue

        # Include description and tags in search
        searchable_text = f"{server_name.lower()} {server_info.get('description', '').lower()} {' '.join(server_info.get('tags', []))}"
        if not search_query or search_query in searchable_text:
            # Get real health status from health service
            from ..health.service import health_service

            health_data = health_service._get_service_health_data(path)

            service_data.append(
                {
                    "display_name": server_name,
                    "path": path,
                    "description": server_info.get("description", ""),
                    "proxy_pass_url": server_info.get("proxy_pass_url", ""),
                    "is_enabled": server_service.is_service_enabled(path),
                    "tags": server_info.get("tags", []),
                    "num_tools": server_info.get("num_tools", 0),
                    "num_stars": server_info.get("num_stars", 0),
                    "is_python": server_info.get("is_python", False),
                    "license": server_info.get("license", "N/A"),
                    "health_status": health_data["status"],
                    "last_checked_iso": health_data["last_checked_iso"]
                }
            )

    return {"servers": service_data}


@router.post("/toggle/{service_path:path}")
async def toggle_service_route(
        user_context: CurrentUser,
        service_path: str,
        enabled: Annotated[str | None, Form()] = None,
):
    """Toggle a service on/off (requires toggle_service UI permission)."""
    if not service_path.startswith("/"):
        service_path = "/" + service_path
    server_info = server_service.get_server_info(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not registered")

    service_name = server_info["server_name"]

    # Check if user has toggle_service permission for this specific service
    if not user_has_ui_permission_for_service('toggle_service', service_name, user_context.get('ui_permissions', {})):
        logger.warning(f"User {user_context['username']} attempted to toggle service"
                       f" {service_name} without toggle_service permission")
        raise HTTPException(
            status_code=403,
            detail=f"You do not have permission to toggle {service_name}"
        )

    # For non-admin users, check if they have access to this specific server
    if not user_context["is_admin"]:
        if not server_service.user_can_access_server_path(
            service_path, user_context["accessible_servers"]
        ):
            logger.warning(
                f"User {user_context['username']} attempted to toggle service {service_path} without access"
            )
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this server"
            )

    new_state = enabled == "on"
    success = server_service.toggle_service(service_path, new_state)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to toggle service")

    server_name = server_info["server_name"]
    logger.info(
        f"Toggled '{server_name}' ({service_path}) to {new_state} by user '{user_context['username']}'"
    )

    # If enabling, perform immediate health check
    status = "disabled"
    last_checked_iso = None
    if new_state:
        logger.info(
            f"Performing immediate health check for {service_path} upon toggle ON..."
        )
        try:
            (
                status,
                last_checked_dt,
            ) = await health_service.perform_immediate_health_check(service_path)
            last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
            logger.info(
                f"Immediate health check for {service_path} completed. Status: {status}"
            )
        except Exception as e:
            logger.error(f"ERROR during immediate health check for {service_path}: {e}")
            status = f"error: immediate check failed ({type(e).__name__})"
    else:
        # When disabling, set status to disabled
        status = "disabled"
        logger.info(f"Service {service_path} toggled OFF. Status set to disabled.")

    # Update FAISS metadata with new enabled state
    await faiss_service.add_or_update_service(service_path, server_info, new_state)

    # Broadcast health status update to WebSocket clients
    await health_service.broadcast_health_update(service_path)

    return JSONResponse(
        status_code=200,
        content={
            "message": f"Toggle request for {service_path} processed.",
            "service_path": service_path,
            "new_enabled_state": new_state,
            "status": status,
            "last_checked_iso": last_checked_iso,
            "num_tools": server_info.get("num_tools", 0),
        },
    )


@router.post("/register")
async def register_service(
        user_context: CurrentUser,
        name: Annotated[str, Form()],
        description: Annotated[str, Form()],
        path: Annotated[str, Form()],
        proxy_pass_url: Annotated[str, Form()],
        tags: Annotated[str, Form()] = "",
        num_tools: Annotated[int, Form()] = 0,
        num_stars: Annotated[int, Form()] = 0,
        is_python: Annotated[bool, Form()] = False,
        license_str: Annotated[str, Form(alias="license")] = "N/A",
):
    """Register a new service (requires register_service UI permission)."""
    # Check if user has register_service permission for any service
    ui_permissions = user_context.get('ui_permissions', {})
    register_permissions = ui_permissions.get('register_service', [])

    if not register_permissions:
        logger.warning(
            f"User {user_context['username']} attempted to register service without register_service permission")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to register new services"
        )

    logger.info(f"Service registration request from user '{user_context['username']}'")
    logger.info(f"Name: {name}, Path: {path}, URL: {proxy_pass_url}")

    # Ensure path starts with a slash
    if not path.startswith("/"):
        path = "/" + path

    # Process tags
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

    # Create server entry
    server_entry = {
        "server_name": name,
        "description": description,
        "path": path,
        "proxy_pass_url": proxy_pass_url,
        "tags": tag_list,
        "num_tools": num_tools,
        "num_stars": num_stars,
        "is_python": is_python,
        "license": license_str,
        "tool_list": [],
    }

    # Register the server
    success = server_service.register_server(server_entry)

    if not success:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Service with path '{path}' already exists or failed to save"
            },
        )

    # Add to FAISS index with current enabled state
    is_enabled = server_service.is_service_enabled(path)
    await faiss_service.add_or_update_service(path, server_entry, is_enabled)

    # Broadcast health status update to WebSocket clients
    await health_service.broadcast_health_update(path)

    await _perform_security_scan_on_registration(path, proxy_pass_url, server_entry)

    logger.info(f"New service registered: '{name}' at path '{path}' by user '{user_context['username']}'")

    return JSONResponse(
        status_code=201,
        content={
            "message": "Service registered successfully",
            "service": server_entry,
        },
    )


@router.get("/edit/{service_path:path}", response_class=HTMLResponse)
async def edit_server_form(
        user_context: CurrentUser,
        request: Request,
        service_path: str,
):
    """Show edit form for a service (requires modify_service UI permission)."""
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    server_info = server_service.get_server_info(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not found")

    service_name = server_info["server_name"]

    # Check if user has modify_service permission for this specific service
    if not user_has_ui_permission_for_service('modify_service', service_name, user_context.get('ui_permissions', {})):
        logger.warning(f"User {user_context['username']} attempted to "
                       f"access edit form for {service_name} without modify_service permission")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to modify {service_name}"
        )

    # For non-admin users, check if they have access to this specific server
    if not user_context['is_admin']:
        if not server_service.user_can_access_server_path(service_path, user_context['accessible_servers']):
            logger.warning(f"User {user_context['username']} attempted to edit service {service_path} without access")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to edit this server"
            )

    return templates.TemplateResponse(
        "edit_server.html",
        {
            "request": request,
            "server": server_info,
            "username": user_context['username'],
            "user_context": user_context
        }
    )


@router.post("/edit/{service_path:path}")
async def edit_server_submit(
        user_context: CurrentUser,
        service_path: str,
        name: Annotated[str, Form()],
        proxy_pass_url: Annotated[str, Form()],
        description: Annotated[str, Form()] = "",
        tags: Annotated[str, Form()] = "",
        num_tools: Annotated[int, Form()] = 0,
        num_stars: Annotated[int, Form()] = 0,
        is_python: Annotated[bool | None, Form()] = False,
        license_str: Annotated[str, Form(alias="license")] = "N/A",
):
    """Handle server edit form submission (requires modify_service UI permission)."""
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    # Check if the server exists and get service name
    server_info = server_service.get_server_info(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not found")

    service_name = server_info["server_name"]

    # Check if user has modify_service permission for this specific service
    if not user_has_ui_permission_for_service('modify_service', service_name, user_context.get('ui_permissions', {})):
        logger.warning(
            f"User {user_context['username']} attempted to edit service {service_name} without modify_service permission")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to modify {service_name}"
        )

    # For non-admin users, check if they have access to this specific server
    if not user_context['is_admin']:
        if not server_service.user_can_access_server_path(service_path, user_context['accessible_servers']):
            logger.warning(f"User {user_context['username']} attempted to edit service {service_path} without access")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to edit this server"
            )

    # Process tags
    tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]

    # Prepare updated server data
    updated_server_entry = {
        "server_name": name,
        "description": description,
        "path": service_path,
        "proxy_pass_url": proxy_pass_url,
        "tags": tag_list,
        "num_tools": num_tools,
        "num_stars": num_stars,
        "is_python": bool(is_python),
        "license": license_str,
        "tool_list": []  # Keep existing or initialize
    }

    # Update server
    success = server_service.update_server(service_path, updated_server_entry)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save updated server data")

    # Update FAISS metadata (keep current enabled state)
    is_enabled = server_service.is_service_enabled(service_path)
    await faiss_service.add_or_update_service(service_path, updated_server_entry, is_enabled)

    # Changes take effect immediately without config reload

    logger.info(f"Server '{name}' ({service_path}) updated by user '{user_context['username']}'")

    # Redirect back to the main page
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/tokens", response_class=HTMLResponse)
async def token_generation_page(
        request: Request,
        user_context: CurrentUser,
):
    """Show token generation page for authenticated users."""
    return templates.TemplateResponse(
        "token_generation.html",
        {
            "request": request,
            "username": user_context['username'],
            "user_context": user_context,
            "user_scopes": user_context['scopes'],
            "available_scopes": user_context['scopes']  # For the UI to show what's available
        }
    )


@router.get("/server_details/{service_path:path}")
async def get_server_details(
        service_path: str,
        user_context: CurrentUser,
):
    """Get server details by path, or all servers if path is 'all' (filtered by permissions)."""
    # Normalize the path to ensure it starts with '/'
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    # Special case: if path is 'all' or '/all', return details for all accessible servers
    if service_path == "/all":
        if user_context["is_admin"]:
            return server_service.get_all_servers()
        else:
            return server_service.get_all_servers_with_permissions(user_context['accessible_servers'])

    # Regular case: return details for a specific server
    server_info = server_service.get_server_info(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not registered")

    # For non-admin users, check if they have access to this specific server
    if not user_context['is_admin']:
        if not server_service.user_can_access_server_path(service_path, user_context['accessible_servers']):
            logger.warning(
                f"User {user_context['username']} attempted to access server details for {service_path} without access")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this server"
            )

    return server_info


@router.get("/tools/{service_path:path}")
async def get_service_tools(
        service_path: str,
        user_context: CurrentUser,
):
    """Get tool list for a service (filtered by permissions)."""
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    # Handle special case for '/all' to return tools from all accessible servers  
    if service_path == '/all':
        all_tools = []
        all_servers_tools = {}

        # Get servers based on user permissions
        if user_context['is_admin']:
            all_servers = server_service.get_all_servers()
        else:
            all_servers = server_service.get_all_servers_with_permissions(user_context['accessible_servers'])

        for path, server_info in all_servers.items():
            # For '/all', we can use cached data to avoid too many MCP calls
            tool_list = server_info.get("tool_list")

            if tool_list is not None and isinstance(tool_list, list):
                # Add server information to each tool
                server_tools = []
                for tool in tool_list:
                    # Create a copy of the tool with server info added
                    tool_with_server = dict(tool)
                    tool_with_server["server_path"] = path
                    tool_with_server["server_name"] = server_info.get("server_name", "Unknown")
                    server_tools.append(tool_with_server)

                all_tools.extend(server_tools)
                all_servers_tools[path] = server_tools

        return {
            "service_path": "all",
            "tools": all_tools,
            "servers": all_servers_tools
        }

    # Handle specific server case - fetch live tools from MCP server
    server_info = server_service.get_server_info(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not registered")

    # For non-admin users, check if they have access to this specific server
    if not user_context['is_admin']:
        if not server_service.user_can_access_server_path(service_path, user_context['accessible_servers']):
            logger.warning(
                f"User {user_context['username']} attempted to access tools for {service_path} without access")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this server"
            )

    # Check if service is enabled and healthy
    is_enabled = server_service.is_service_enabled(service_path)
    if not is_enabled:
        raise HTTPException(status_code=400, detail="Cannot fetch tools from disabled service")

    proxy_pass_url = server_info.get("proxy_pass_url")
    if not proxy_pass_url:
        raise HTTPException(status_code=500, detail="Service has no proxy URL configured")

    logger.info(f"Fetching live tools for {service_path} from {proxy_pass_url}")

    try:
        # Call MCP client to fetch fresh tools using server configuration
        tool_list = await mcp_client_service.get_tools_from_server_with_server_info(proxy_pass_url, server_info)

        if tool_list is None:
            # If live fetch fails but we have cached tools, use those
            cached_tools = server_info.get("tool_list")
            if cached_tools is not None and isinstance(cached_tools, list):
                logger.warning(f"Failed to fetch live tools for {service_path}, using cached tools")
                return {"service_path": service_path, "tools": cached_tools, "cached": True}
            raise HTTPException(status_code=503,
                                detail="Failed to fetch tools from MCP server. Service may be unhealthy.")

        # Update the server registry with the fresh tools
        new_tool_count = len(tool_list)
        current_tool_count = server_info.get("num_tools", 0)

        if current_tool_count != new_tool_count or server_info.get("tool_list") != tool_list:
            logger.info(f"Updating tool list for {service_path}. New count: {new_tool_count}")

            # Update server info with fresh tools
            updated_server_info = server_info.copy()
            updated_server_info["tool_list"] = tool_list
            updated_server_info["num_tools"] = new_tool_count

            # Save updated server info
            success = server_service.update_server(service_path, updated_server_info)
            if success:
                logger.info(f"Successfully updated tool list for {service_path}")

                # Update FAISS index with new tool data
                await faiss_service.add_or_update_service(service_path, updated_server_info, is_enabled)
                logger.info(f"Updated FAISS index for {service_path}")
            else:
                logger.error(f"Failed to save updated tool list for {service_path}")

        return {"service_path": service_path, "tools": tool_list, "cached": False}

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error fetching tools for {service_path}: {e}")
        # Try to return cached tools if available
        cached_tools = server_info.get("tool_list")
        if cached_tools is not None and isinstance(cached_tools, list):
            logger.warning(f"Error fetching live tools for {service_path}, falling back to cached tools: {e}")
            return {"service_path": service_path, "tools": cached_tools, "cached": True}
        raise HTTPException(status_code=500, detail=f"Error fetching tools: {str(e)}")


@router.post("/refresh/{service_path:path}")
async def refresh_service(
        service_path: str,
        user_context: CurrentUser,
):
    """Refresh service health and tool information (requires health_check_service permission)."""
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    server_info = server_service.get_server_info(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not registered")

    service_name = server_info["server_name"]

    # Check if user has health_check_service permission for this specific service
    if not user_has_ui_permission_for_service('health_check_service', service_name,
                                              user_context.get('ui_permissions', {})):
        logger.warning(f"User {user_context['username']} attempted to "
                       f"refresh service {service_name} without health_check_service permission")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to refresh {service_name}"
        )

    # For non-admin users, check if they have access to this specific server
    if not user_context['is_admin']:
        if not server_service.user_can_access_server_path(service_path, user_context['accessible_servers']):
            logger.warning(f"User {user_context['username']} attempted "
                           f"to refresh service {service_path} without access")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this server"
            )

    # Check if service is enabled
    is_enabled = server_service.is_service_enabled(service_path)
    if not is_enabled:
        raise HTTPException(status_code=400, detail="Cannot refresh disabled service")

    proxy_pass_url = server_info.get("proxy_pass_url")
    if not proxy_pass_url:
        raise HTTPException(status_code=500, detail="Service has no proxy URL configured")

    logger.info(f"Refreshing service {service_path} at {proxy_pass_url} by user '{user_context['username']}'")

    try:
        # Perform immediate health check
        status, last_checked_dt = await health_service.perform_immediate_health_check(service_path)
        last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
        logger.info(f"Manual refresh health check for {service_path} completed. Status: {status}")

    except Exception as e:
        logger.error(f"ERROR during manual refresh check for {service_path}: {e}")
        # Still broadcast the error state
        await health_service.broadcast_health_update(service_path)
        raise HTTPException(status_code=500, detail=f"Refresh check failed: {e}")

    # Update FAISS index
    await faiss_service.add_or_update_service(service_path, server_info, is_enabled)

    # Broadcast the updated status
    await health_service.broadcast_health_update(service_path)

    logger.info(f"Service '{service_path}' refreshed by user '{user_context['username']}'")
    return {
        "message": f"Service {service_path} refreshed successfully",
        "service_path": service_path,
        "status": status,
        "last_checked_iso": last_checked_iso,
        "num_tools": server_info.get("num_tools", 0)
    }


@router.post("/tokens/generate")
async def generate_user_token(
        request: Request,
        user_context: CurrentUser,
):
    """
    Generate a JWT token for the authenticated user.

    Request body should contain:
    {
        "requested_scopes": ["scope1", "scope2"],  // Optional, defaults to user's current scopes
        "expires_in_hours": 8,                     // Optional, defaults to 8 hours
        "description": "Token for automation"      // Optional description
    }

    Returns:
        Generated JWT token with expiration info

    Raises:
        HTTPException: If request fails or user lacks permissions
    """

    try:
        # Parse request body
        try:
            body = await request.json()
        except Exception as e:
            logger.warning(f"Invalid JSON in token generation request: {e}")
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON in request body"
            )

        requested_scopes = body.get("requested_scopes", [])
        expires_in_hours = body.get("expires_in_hours", 8)
        description = body.get("description", "")

        # Validate expires_in_hours
        if (
            not isinstance(expires_in_hours, int)
            or expires_in_hours <= 0
            or expires_in_hours > 24
        ):
            raise HTTPException(
                status_code=400,
                detail="expires_in_hours must be an integer between 1 and 24",
            )

        # Validate requested_scopes
        if requested_scopes and not isinstance(requested_scopes, list):
            raise HTTPException(
                status_code=400, detail="requested_scopes must be a list of strings"
            )

        # Prepare request to auth server
        auth_request = {
            "user_context": {
                "username": user_context["username"],
                "scopes": user_context["scopes"],
                "groups": user_context["groups"],
            },
            "requested_scopes": requested_scopes,
            "expires_in_hours": expires_in_hours,
            "description": description,
        }

        # Call auth server internal API (no authentication needed since both are trusted internal services)
        async with httpx.AsyncClient() as client:
            headers = {
                "Content-Type": "application/json"
            }

            auth_server_url = settings.auth_server_url
            response = await client.post(
                f"{auth_server_url}/internal/tokens",
                json=auth_request,
                headers=headers,
                timeout=10.0,
            )

            if response.status_code == 200:
                token_data = response.json()
                logger.info(
                    f"Successfully generated token for user '{user_context['username']}'"
                )

                # Format response to match expected structure (including refresh token)
                formatted_response = {
                    "success": True,
                    "tokens": {
                        "access_token": token_data.get("access_token"),
                        "refresh_token": token_data.get("refresh_token"),
                        "expires_in": token_data.get("expires_in"),
                        "refresh_expires_in": token_data.get("refresh_expires_in"),
                        "token_type": token_data.get("token_type", "Bearer"),
                        "scope": token_data.get("scope", ""),
                    },
                    "keycloak_url": getattr(settings, "keycloak_url", None)
                    or "http://keycloak:8080",
                    "realm": getattr(settings, "keycloak_realm", None) or "mcp-gateway",
                    "client_id": "user-generated",
                    # Legacy fields for backward compatibility
                    "token_data": token_data,
                    "user_scopes": user_context["scopes"],
                    "requested_scopes": requested_scopes or user_context["scopes"],
                }

                return formatted_response
            else:
                error_detail = "Unknown error"
                try:
                    error_response = response.json()
                    error_detail = error_response.get("detail", "Unknown error")
                except:
                    error_detail = response.text

                logger.warning(f"Auth server returned error {response.status_code}: {error_detail}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Token generation failed: {error_detail}",
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error generating token for user '{user_context['username']}': {e}"
        )
        raise HTTPException(status_code=500, detail="Internal error generating token")


@router.get("/admin/tokens")
async def get_admin_tokens(
        user_context: CurrentUser,
):
    """
    Admin-only endpoint to retrieve JWT tokens from Keycloak.

    Returns both access token and refresh token for admin users.

    Returns:
        JSON object containing access_token, refresh_token, expires_in, etc.

    Raises:
        HTTPException: If user is not admin or token retrieval fails
    """
    # Check if user is admin
    if not user_context.get("is_admin", False):
        logger.warning(
            f"Non-admin user {user_context['username']} attempted to access admin tokens"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available to admin users",
        )

    try:
        from ..utils.keycloak_manager import KEYCLOAK_ADMIN_URL, KEYCLOAK_REALM

        # Get M2M client credentials from environment
        m2m_client_id = os.getenv("KEYCLOAK_M2M_CLIENT_ID", "mcp-gateway-m2m")
        m2m_client_secret = os.getenv("KEYCLOAK_M2M_CLIENT_SECRET")

        if not m2m_client_secret:
            raise HTTPException(
                status_code=500, detail="Keycloak M2M client secret not configured"
            )

        # Get tokens from Keycloak mcp-gateway realm using M2M client_credentials
        token_url = f"{KEYCLOAK_ADMIN_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"

        data = {
            "grant_type": "client_credentials",
            "client_id": m2m_client_id,
            "client_secret": m2m_client_secret,
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(token_url, data=data, headers=headers)
            response.raise_for_status()

            token_data = response.json()

            # No refresh tokens - users should configure longer token lifetimes in Keycloak if needed
            refresh_token = None
            refresh_expires_in_seconds = 0

            logger.info(
                f"Admin user {user_context['username']} retrieved Keycloak M2M tokens (no refresh token - configure token lifetime in Keycloak if needed)"
            )

            return {
                "success": True,
                "tokens": {
                    "access_token": token_data.get("access_token"),
                    "refresh_token": refresh_token,  # Custom-generated refresh token
                    "expires_in": token_data.get("expires_in"),
                    "refresh_expires_in": refresh_expires_in_seconds,
                    "token_type": token_data.get("token_type", "Bearer"),
                    "scope": token_data.get("scope", ""),
                },
                "keycloak_url": KEYCLOAK_ADMIN_URL,
                "realm": KEYCLOAK_REALM,
                "client_id": m2m_client_id,
            }

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Failed to retrieve Keycloak tokens: HTTP {e.response.status_code}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to authenticate with Keycloak: HTTP {e.response.status_code}",
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving Keycloak tokens: {e}")
        raise HTTPException(
            status_code=500, detail="Internal error retrieving Keycloak tokens"
        )


# ============================================================================
# NEW API: /api/servers/* endpoints with JWT Bearer Token Authentication
# ============================================================================
# These are the modern, JWT-authenticated equivalents of the /api/internal/*
# endpoints. They use Depends(nginx_proxied_auth) for authentication and
# support fine-grained permission checks via user context.
#
# Architecture:
# - Both /api/internal/* and /api/servers/* call the same internal functions
# - No code duplication; external API simply wraps existing endpoints
# - User context from JWT is passed through for audit logging
#
# Migration Path:
# Phase 1 (Now): Both endpoints work identically with same business logic
# Phase 2 (Future): Clients migrate to /api/servers/*
# Phase 3 (Future): /api/internal/* deprecated with sunset headers
# Phase 4 (Future): /api/internal/* removed in major version


@router.post("/servers/register")
async def register_service_api(
    request: Request,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    path: Annotated[str, Form()],
    proxy_pass_url: Annotated[str, Form()],
    user_context: CurrentUser,
    tags: Annotated[str, Form()] = "",
    num_tools: Annotated[int, Form()] = 0,
    num_stars: Annotated[int, Form()] = 0,
    is_python: Annotated[bool, Form()] = False,
    license_str: Annotated[str, Form(alias="license")] = "N/A",
    overwrite: Annotated[bool, Form()] = True,
    auth_provider: Annotated[str | None, Form()] = None,
    auth_type: Annotated[str | None, Form()] = None,
    supported_transports: Annotated[str | None, Form()] = None,
    headers: Annotated[str | None, Form()] = None,
    tool_list_json: Annotated[str | None, Form()] = None,
):
    """
    Register a service via JWT Bearer Token authentication (External API).

    This endpoint provides the same functionality as POST /api/internal/register
    but uses modern JWT Bearer token authentication via nginx headers, making it
    suitable for external service-to-service communication.

    **Authentication:** JWT Bearer token (via nginx X-User header)
    **Authorization:** Requires valid JWT token from auth system

    **Request body (form data):**
    - `name` (required): Service name
    - `description` (required): Service description
    - `path` (required): Service path (e.g., /myservice)
    - `proxy_pass_url` (required): Proxy URL (e.g., http://localhost:8000)
    - `tags` (optional): Comma-separated tags
    - `num_tools` (optional): Number of tools
    - `num_stars` (optional): Star rating
    - `is_python` (optional): Is Python server (boolean)
    - `license` (optional): License name
    - `overwrite` (optional): Overwrite if exists (boolean, default true)
    - `auth_provider` (optional): Auth provider name
    - `auth_type` (optional): Auth type (e.g., oauth, basic)
    - `supported_transports` (optional): JSON array of transports
    - `headers` (optional): JSON object of headers
    - `tool_list_json` (optional): JSON array of tool definitions

    **Response:**
    - `201 Created`: Service registered successfully
    - `400 Bad Request`: Invalid input data
    - `401 Unauthorized`: Missing or invalid JWT token
    - `409 Conflict`: Service already exists (unless overwrite=true)
    - `500 Internal Server Error`: Server error

    **Example:**
    ```bash
    curl -X POST https://registry.example.com/api/servers/register \\
      -H "Authorization: Bearer $JWT_TOKEN" \\
      -F "name=My Service" \\
      -F "description=My MCP Service" \\
      -F "path=/myservice" \\
      -F "proxy_pass_url=http://localhost:8000"
    ```
    """
    logger.info(
        f"API register service request from user '{user_context.get('username')}' for service '{name}'"
    )

    # Validate path format
    if not path.startswith("/"):
        path = "/" + path
    logger.warning(f"SERVERS REGISTER: Validated path: {path}")

    # Process tags
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else []

    # Process supported_transports
    if supported_transports:
        try:
            transports_list = json.loads(supported_transports) if supported_transports.startswith('[') else [t.strip()
                                                                                                             for t in
                                                                                                             supported_transports.split(
                                                                                                                 ',')]
        except Exception as e:
            logger.warning(
                f"SERVERS REGISTER: Failed to parse supported_transports, using default: {e}"
            )
            transports_list = ["streamable-http"]
    else:
        transports_list = ["streamable-http"]

    # Process headers
    headers_list = []
    if headers:
        try:
            headers_list = json.loads(headers) if isinstance(headers, str) else headers
        except Exception as e:
            logger.warning(f"SERVERS REGISTER: Failed to parse headers: {e}")

    # Process tool_list
    tool_list = []
    if tool_list_json:
        try:
            tool_list = (
                json.loads(tool_list_json)
                if isinstance(tool_list_json, str)
                else tool_list_json
            )
        except Exception as e:
            logger.warning(f"SERVERS REGISTER: Failed to parse tool_list_json: {e}")

    # Create server entry
    server_entry = {
        "server_name": name,
        "description": description,
        "path": path,
        "proxy_pass_url": proxy_pass_url,
        "supported_transports": transports_list,
        "auth_type": auth_type if auth_type else "none",
        "tags": tag_list,
        "num_tools": num_tools,
        "num_stars": num_stars,
        "is_python": is_python,
        "license": license_str,
        "tool_list": tool_list,
    }

    # Add optional fields if provided
    if auth_provider:
        server_entry["auth_provider"] = auth_provider
    if headers_list:
        server_entry["headers"] = headers_list

    # Check if server exists and handle overwrite logic
    existing_server = server_service.get_server_info(path)
    if existing_server and not overwrite:
        logger.warning(
            f"SERVERS REGISTER: Server exists and overwrite=False for path {path}"
        )
        return JSONResponse(
            status_code=409,
            content={
                "error": "Service registration failed",
                "reason": f"A service with path '{path}' already exists",
                "detail": "Use overwrite=true to replace existing service",
            },
        )

    try:
        # Register service (use update_server if overwriting, otherwise register_server)
        if existing_server and overwrite:
            logger.info(
                f"Overwriting existing server at path {path} by user {user_context.get('username')}"
            )
            success = server_service.update_server(path, server_entry)
        else:
            success = server_service.register_server(server_entry)

        if not success:
            logger.error(f"Service registration failed for {path}")
            return JSONResponse(
                status_code=409,
                content={
                    "error": "Service registration failed",
                    "reason": f"Failed to register service at path '{path}'",
                    "detail": "Check server logs for more information",
                },
            )

        logger.info(
            f"Service registered successfully via API: {path} by user {user_context.get('username')}"
        )

        # Security scanning if enabled
        await _perform_security_scan_on_registration(
            path, proxy_pass_url, server_entry, headers_list
        )

        # Trigger async tasks for health check and FAISS sync
        asyncio.create_task(health_service.perform_immediate_health_check(path))
        asyncio.create_task(faiss_service.add_or_update_service(path, server_entry, server_service.is_service_enabled(path)))
        return JSONResponse(
            status_code=201,
            content={
                "path": path,
                "name": name,
                "message": f"Service '{name}' registered successfully at path '{path}'",
            },
        )

    except Exception as e:
        logger.error(f"Service registration failed for {path}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Service registration failed: {str(e)}"
        )


@router.post("/servers/toggle")
async def toggle_service_api(
        path: Annotated[str, Form()],
        new_state: Annotated[bool, Form()],
        user_context: CurrentUser = None,
):
    """
    Toggle a service's enabled/disabled state via JWT authentication (External API).

    This endpoint provides the same functionality as POST /api/internal/toggle
    but uses modern JWT Bearer token authentication.

    **Authentication:** JWT Bearer token (via nginx X-User header)
    **Authorization:** Requires valid JWT token from auth system

    **Request body (form data):**
    - `path` (required): Service path
    - `new_state` (required): New state (true=enabled, false=disabled)

    **Response:**
    Returns the updated service status.

    **Example:**
    ```bash
    curl -X POST https://registry.example.com/api/servers/toggle \\
      -H "Authorization: Bearer $JWT_TOKEN" \\
      -F "path=/myservice" \\
      -F "new_state=true"
    ```
    """
    logger.info(
        f"API toggle service request from user '{user_context.get('username')}' for path '{path}' to {new_state}")

    # Normalize path
    if not path.startswith("/"):
        path = "/" + path

    # Check if server exists
    server_info = server_service.get_server_info(path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not registered")

    # Toggle the service
    success = server_service.toggle_service(path, new_state)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to toggle service")

    logger.info(f"Toggled '{server_info['server_name']}' "
                f"({path}) to {new_state} by user '{user_context.get('username')}'")

    # If enabling, perform immediate health check
    status = "disabled"
    last_checked_iso = None
    if new_state:
        logger.info(f"Performing immediate health check for {path} upon toggle ON...")
        try:
            (
                status,
                last_checked_dt,
            ) = await health_service.perform_immediate_health_check(path)
            last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
            logger.info(
                f"Immediate health check for {path} completed. Status: {status}"
            )
        except Exception as e:
            logger.error(f"ERROR during immediate health check for {path}: {e}")
            status = f"error: immediate check failed ({type(e).__name__})"
    else:
        # When disabling, set status to disabled
        status = "disabled"
        logger.info(f"Service {path} toggled OFF. Status set to disabled.")

    # Update FAISS metadata with new enabled state
    await faiss_service.add_or_update_service(path, server_info, new_state)

    # Broadcast health status update to WebSocket clients
    await health_service.broadcast_health_update(path)

    return JSONResponse(
        status_code=200,
        content={
            "message": f"Toggle request for {path} processed.",
            "service_path": path,
            "new_enabled_state": new_state,
            "status": status,
            "last_checked_iso": last_checked_iso,
            "num_tools": server_info.get("num_tools", 0),
        },
    )


@router.post("/servers/remove")
async def remove_service_api(
        path: Annotated[str, Form()],
        user_context: CurrentUser = None,
):
    """
    Remove a service via JWT Bearer Token authentication (External API).

    This endpoint provides the same functionality as POST /api/internal/remove
    but uses modern JWT Bearer token authentication.

    **Authentication:** JWT Bearer token (via nginx X-User header)
    **Authorization:** Requires valid JWT token from auth system

    **Request body (form data):**
    - `path` (required): Service path to remove

    **Response:**
    Returns confirmation of removal.

    **Example:**
    ```bash
    curl -X POST https://registry.example.com/api/servers/remove \\
      -H "Authorization: Bearer $JWT_TOKEN" \\
      -F "path=/myservice"
    ```
    """
    logger.info(f"API remove service request from user '{user_context.get('username')}' for path '{path}'")

    # Normalize path
    if not path.startswith("/"):
        path = "/" + path

    # Check if server exists
    server_info = server_service.get_server_info(path)
    if not server_info:
        logger.warning(f"Service not found at path '{path}'")
        return JSONResponse(
            status_code=404,
            content={
                "error": "Service not found",
                "reason": f"No service registered at path '{path}'",
                "suggestion": "Check the service path and ensure it is registered",
            },
        )

    # Remove the server
    success = server_service.remove_server(path)

    if not success:
        logger.warning(f"Failed to remove service at path '{path}'")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Service removal failed",
                "reason": f"Failed to remove service at path '{path}'",
                "suggestion": "Check server logs for detailed error information",
            },
        )

    logger.info(
        f"Service removed successfully: {path} by user {user_context.get('username')}"
    )

    # Remove from FAISS index
    await faiss_service.remove_service(path)

    # Broadcast health status update to WebSocket clients
    await health_service.broadcast_health_update(path)

    # Remove server from scopes.yml and reload auth server
    try:
        await remove_server_scopes(path)
        logger.info(f"Successfully removed server {path} from scopes")
    except Exception as e:
        logger.warning(f"Failed to remove server {path} from scopes: {e}")

    return JSONResponse(
        status_code=200,
        content={"message": "Service removed successfully", "path": path},
    )


# IMPORTANT: Specific routes with path suffixes (/health, /rate, /rating, /toggle)
# must come BEFORE catch-all /servers/ routes to prevent FastAPI from matching them incorrectly

@router.get("/servers/health")
async def healthcheck_api(
        request: Request,
        user_context: CurrentUser = None,
):
    """
    Get health status for all registered services via JWT authentication (External API).

    This endpoint provides the same functionality as GET /api/internal/healthcheck
    but uses modern JWT Bearer token authentication.

    **Authentication:** JWT Bearer token (via nginx X-User header)
    **Authorization:** Requires valid JWT token from auth system

    **Response:**
    Returns health status for all services.

    **Example:**
    ```bash
    curl -X GET https://registry.example.com/api/servers/health \\
      -H "Authorization: Bearer $JWT_TOKEN"
    ```
    """
    from ..health.service import health_service

    logger.info(
        f"API healthcheck request from user '{user_context.get('username') if user_context else 'unknown'}'"
    )

    # Get health status for all servers using JWT authentication
    try:
        health_data = health_service.get_all_health_status()
        logger.info(f"Retrieved health status for {len(health_data)} servers")

        return JSONResponse(
            status_code=200,
            content=health_data
        )

    except Exception as e:
        logger.error(f"Failed to retrieve health status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve health status: {str(e)}"
        )


@router.post("/servers/groups/add")
async def add_server_to_groups_api(
        request: Request,
        server_name: Annotated[str, Form()],
        group_names: Annotated[str, Form()],
        user_context: CurrentUser = None,
):
    """
    Add a service to scope groups via JWT authentication (External API).

    This endpoint provides the same functionality as POST /api/internal/add-to-groups
    but uses modern JWT Bearer token authentication.

    **Authentication:** JWT Bearer token (via nginx X-User header)
    **Authorization:** Requires valid JWT token from auth system

    **Request body (form data):**
    - `server_name` (required): Service name
    - `group_names` (required): Comma-separated list of group names

    **Response:**
    Returns confirmation of group assignment.

    **Example:**
    ```bash
    curl -X POST https://registry.example.com/api/servers/groups/add \\
      -H "Authorization: Bearer $JWT_TOKEN" \\
      -F "server_name=myservice" \\
      -F "group_names=admin,developers"
    ```
    """
    logger.info(
        f"API add to groups request from user '{user_context.get('username')}' for server '{server_name}'"
    )

    # Call the existing internal_add_server_to_groups function
    return await internal_add_server_to_groups(server_name, group_names)


@router.post("/servers/groups/remove")
async def remove_server_from_groups_api(
        request: Request,
        server_name: Annotated[str, Form()],
        group_names: Annotated[str, Form()],
        user_context: CurrentUser = None,
):
    """
    Remove a service from scope groups via JWT authentication (External API).

    This endpoint provides the same functionality as POST /api/internal/remove-from-groups
    but uses modern JWT Bearer token authentication.

    **Authentication:** JWT Bearer token (via nginx X-User header)
    **Authorization:** Requires valid JWT token from auth system

    **Request body (form data):**
    - `server_name` (required): Service name
    - `group_names` (required): Comma-separated list of group names to remove

    **Response:**
    Returns confirmation of removal from groups.

    **Example:**
    ```bash
    curl -X POST https://registry.example.com/api/servers/groups/remove \\
      -H "Authorization: Bearer $JWT_TOKEN" \\
      -F "server_name=myservice" \\
      -F "group_names=developers"
    ```
    """
    logger.info(
        f"API remove from groups request from user '{user_context.get('username')}' for server '{server_name}'"
    )

    # Call the existing internal_remove_server_from_groups function
    return await internal_remove_server_from_groups(server_name, group_names)


@router.post("/servers/groups/create")
async def create_group_api(
        request: Request,
        group_name: Annotated[str, Form()],
        description: Annotated[str, Form()] = "",
        create_in_keycloak: Annotated[bool, Form()] = True,
        user_context: CurrentUser = None,
):
    """
    Create a new scope group via JWT authentication (External API).

    This endpoint provides the same functionality as POST /api/internal/create-group
    but uses modern JWT Bearer token authentication.

    **Authentication:** JWT Bearer token (via nginx X-User header)
    **Authorization:** Requires valid JWT token from auth system

    **Request body (form data):**
    - `group_name` (required): Name of the new group
    - `description` (optional): Group description
    - `create_in_keycloak` (optional): Whether to create in Keycloak (default: true)

    **Response:**
    Returns confirmation of group creation.

    **Example:**
    ```bash
    curl -X POST https://registry.example.com/api/servers/groups/create \\
      -H "Authorization: Bearer $JWT_TOKEN" \\
      -F "group_name=new-team" \\
      -F "description=Team for new project" \\
      -F "create_in_keycloak=true"
    ```
    """
    logger.info(
        f"API create group request from user '{user_context.get('username')}' for group '{group_name}'"
    )

    # Call the existing internal_create_group function
    return await internal_create_group(group_name=group_name, description=description, create_in_keycloak=create_in_keycloak)


@router.post("/servers/groups/delete")
async def delete_group_api(
        request: Request,
        group_name: Annotated[str, Form()],
        delete_from_keycloak: Annotated[bool, Form()] = True,
        force: Annotated[bool, Form()] = False,
        user_context: CurrentUser = None,
):
    """
    Delete a scope group via JWT authentication (External API).

    This endpoint provides the same functionality as POST /api/internal/delete-group
    but uses modern JWT Bearer token authentication.

    **Authentication:** JWT Bearer token (via nginx X-User header)
    **Authorization:** Requires valid JWT token from auth system

    **Request body (form data):**
    - `group_name` (required): Name of the group to delete
    - `delete_from_keycloak` (optional): Whether to delete from Keycloak (default: true)
    - `force` (optional): Force deletion of system groups (default: false)

    **Response:**
    Returns confirmation of group deletion.

    **Example:**
    ```bash
    curl -X POST https://registry.example.com/api/servers/groups/delete \\
      -H "Authorization: Bearer $JWT_TOKEN" \\
      -F "group_name=old-team" \\
      -F "delete_from_keycloak=true" \\
      -F "force=false"
    ```
    """
    logger.info(
        f"API delete group request from user '{user_context.get('username')}' for group '{group_name}'"
    )

    # Call the existing internal_delete_group function
    return await internal_delete_group(group_name=group_name, delete_from_keycloak=delete_from_keycloak, force=force)


@router.get("/servers/groups")
async def list_groups_api(
        request: Request,
        include_keycloak: bool = True,
        include_scopes: bool = True,
        user_context: CurrentUser = None,
):
    """
    List all scope groups via JWT Bearer Token authentication (External API).

    This endpoint provides the same functionality as GET /api/internal/list-groups
    but uses modern JWT Bearer token authentication.

    **Authentication:** JWT Bearer token (via nginx X-User header)
    **Authorization:** Requires valid JWT token from auth system

    **Response:**
    Returns a list of all groups and their synchronization status.

    **Example:**
    ```bash
    curl -X GET https://registry.example.com/api/servers/groups \\
      -H "Authorization: Bearer $JWT_TOKEN"
    ```
    """
    logger.info(
        f"API list groups request from user '{user_context.get('username') if user_context else 'unknown'}'"
    )

    # Call the existing internal_list_groups function
    return await internal_list_groups(include_keycloak=include_keycloak, include_scopes=include_scopes)


@router.post("/servers/{path:path}/rate")
async def rate_server(
    path: str,
    request: RatingRequest,
    user_context: CurrentUser,
):
    """Save integer ratings to server."""
    if not path.startswith("/"):
        path = "/" + path

    server_info = server_service.get_server_info(path)
    if not server_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server not found at path '{path}'",
        )

    # For non-admin users, check if they have access to this specific server
    if not user_context['is_admin']:
        if not server_service.user_can_access_server_path(path, user_context['accessible_servers']):
            logger.warning(
                f"User {user_context['username']} attempted to rate server {path} without permission"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this server",
            )

    try:
        avg_rating = server_service.update_rating(path, user_context["username"], request.rating)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error updating rating: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save rating",
        )

    return {
        "message": "Rating added successfully",
        "average_rating": avg_rating,
    }


@router.get("/servers/{path:path}/rating")
async def get_server_rating(
    path: str,
    user_context: CurrentUser,
):
    """Get server rating information."""
    if not path.startswith("/"):
        path = "/" + path

    server_info = server_service.get_server_info(path)
    if not server_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server not found at path '{path}'",
        )

    # For non-admin users, check if they have access to this specific server
    if not user_context['is_admin']:
        if not server_service.user_can_access_server_path(path, user_context['accessible_servers']):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this server",
            )

    return {
        "num_stars": server_info.get("num_stars", 0.0),
        "rating_details": server_info.get("rating_details", []),
    }


@router.get("/servers/{path:path}/security-scan")
async def get_server_security_scan(
    path: str,
    user_context: CurrentUser,
):
    """
    Get security scan results for a server.

    Returns the latest security scan results for the specified server,
    including threat analysis, severity levels, and detailed findings.

    **Authentication:** JWT Bearer token or session cookie
    **Authorization:** Requires admin privileges or access to the server

    **Path Parameters:**
    - `path` (required): Server path (e.g., /cloudflare-docs)

    **Response:**
    Returns security scan results with analysis_results and tool_results.

    **Example:**
    ```bash
    curl -X GET http://localhost/api/servers/cloudflare-docs/security-scan \\
      --cookie-jar .cookies --cookie .cookies
    ```
    """
    if not path.startswith("/"):
        path = "/" + path

    # Check if server exists
    server_info = server_service.get_server_info(path)
    if not server_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server not found at path '{path}'",
        )

    # Check user permissions
    if not user_context["is_admin"]:
        if not server_service.user_can_access_server_path(
            path, user_context["accessible_servers"]
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this server",
            )

    # Get scan results
    scan_result = security_scanner_service.get_scan_result(path)
    if not scan_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No security scan results found for server '{path}'. "
            "The server may not have been scanned yet.",
        )

    return scan_result


@router.post("/servers/{path:path}/rescan")
async def rescan_server(
    path: str,
    user_context: CurrentUser,
):
    """
    Trigger a manual security scan for a server.

    Initiates a new security scan for the specified server and returns
    the results. This endpoint is useful for re-scanning servers after
    updates or for on-demand security assessments.

    **Authentication:** JWT Bearer token or session cookie
    **Authorization:** Requires admin privileges

    **Path Parameters:**
    - `path` (required): Server path (e.g., /cloudflare-docs)

    **Response:**
    Returns the newly generated security scan results.

    **Example:**
    ```bash
    curl -X POST http://localhost/api/servers/cloudflare-docs/rescan \\
      --cookie-jar .cookies --cookie .cookies
    ```
    """
    # Only admins can trigger manual scans
    if not user_context["is_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can trigger security scans",
        )

    if not path.startswith("/"):
        path = "/" + path

    # Check if server exists
    server_info = server_service.get_server_info(path)
    if not server_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server not found at path '{path}'",
        )

    # Get server URL from server info
    server_url = server_info.get("proxy_pass_url")
    if not server_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Server '{path}' does not have a proxy_pass_url configured",
        )

    logger.info(
        f"Manual security scan requested by user '{user_context.get('username')}' "
        f"for server '{path}' at URL '{server_url}'"
    )

    try:
        # Trigger security scan
        scan_result = await security_scanner_service.scan_server(
            server_url=server_url, analyzers=None, api_key=None, headers=None, timeout=None
        )

        # Return the scan result data
        return {
            "server_url": scan_result.server_url,
            "server_path": path,
            "scan_timestamp": scan_result.scan_timestamp,
            "is_safe": scan_result.is_safe,
            "critical_issues": scan_result.critical_issues,
            "high_severity": scan_result.high_severity,
            "medium_severity": scan_result.medium_severity,
            "low_severity": scan_result.low_severity,
            "analyzers_used": scan_result.analyzers_used,
            "scan_failed": scan_result.scan_failed,
            "error_message": scan_result.error_message,
            "raw_output": scan_result.raw_output,
        }
    except Exception as e:
        logger.exception(f"Failed to scan server '{path}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scan server: {str(e)}",
        )


@router.get("/servers/tools/{service_path:path}")
async def get_service_tools_api(
        service_path: str,
        user_context: CurrentUser = None,
):
    """
    Get tool list for a service via JWT Bearer Token authentication (External API).

    This endpoint provides the same functionality as GET /tools/{service_path}
    but uses modern JWT Bearer token authentication.

    **Authentication:** JWT Bearer token (via nginx X-User header)
    **Authorization:** Requires valid JWT token from auth system

    **Path Parameters:**
    - `service_path` (required): Service path (e.g., /myservice or /all for all services)

    **Response:**
    Returns the list of tools available on the service, filtered by user permissions.

    **Example:**
    ```bash
    curl -X GET https://registry.example.com/api/servers/tools/myservice \\
      -H "Authorization: Bearer $JWT_TOKEN"

    # Get tools from all accessible services
    curl -X GET https://registry.example.com/api/servers/tools/all \\
      -H "Authorization: Bearer $JWT_TOKEN"
    ```
    """
    logger.info(
        f"API get tools request from user '{user_context.get('username') if user_context else 'unknown'}' for path '{service_path}'")

    # Call the existing get_service_tools function
    return await get_service_tools(service_path=service_path, user_context=user_context)

@router.get("/servers")
async def get_servers_json(
    query: str | None = None,
    user_context: CurrentUser = None,
):
    """Get servers data as JSON for React frontend and external API (supports both session cookies and Bearer tokens)."""
    # CRITICAL DIAGNOSTIC: Log user_context received by endpoint
    logger.debug(f"[GET_SERVERS_DEBUG] Received user_context: {user_context}")
    logger.debug(f"[GET_SERVERS_DEBUG] user_context type: {type(user_context)}")
    if user_context:
        logger.debug(f"[GET_SERVERS_DEBUG] Username: {user_context.get('username', 'NOT PRESENT')}")
        logger.debug(f"[GET_SERVERS_DEBUG] Scopes: {user_context.get('scopes', 'NOT PRESENT')}")
        logger.debug(f"[GET_SERVERS_DEBUG] Auth method: {user_context.get('auth_method', 'NOT PRESENT')}")

    service_data = []
    search_query = query.lower() if query else ""

    # Get servers based on user permissions (same logic as root route)
    if user_context['is_admin']:
        all_servers = server_service.get_all_servers()
    else:
        all_servers = server_service.get_all_servers_with_permissions(user_context['accessible_servers'])
    
    sorted_server_paths = sorted(
        all_servers.keys(), 
        key=lambda p: all_servers[p]["server_name"]
    )
    
    # Filter services based on UI permissions (same logic as root route)
    accessible_services = user_context.get('accessible_services', [])

    for path in sorted_server_paths:
        server_info = all_servers[path]
        server_name = server_info["server_name"]
        # Extract technical name from path (remove leading and trailing slashes)
        technical_name = path.strip('/')

        # Check if user can list this service using technical name
        if 'all' not in accessible_services and technical_name not in accessible_services:
            continue
        
        # Include description and tags in search
        searchable_text = f"{server_name.lower()} {server_info.get('description', '').lower()} {' '.join(server_info.get('tags', []))}"
        if not search_query or search_query in searchable_text:
            # Get real health status from health service
            from ..health.service import health_service
            health_data = health_service._get_service_health_data(path)
            
            service_data.append(
                {
                    "display_name": server_name,
                    "path": path,
                    "description": server_info.get("description", ""),
                    "proxy_pass_url": server_info.get("proxy_pass_url", ""),
                    "is_enabled": server_service.is_service_enabled(path),
                    "tags": server_info.get("tags", []),
                    "num_tools": server_info.get("num_tools", 0),
                    "num_stars": server_info.get("num_stars", 0),
                    "is_python": server_info.get("is_python", False),
                    "license": server_info.get("license", "N/A"),
                    "health_status": health_data["status"],  
                    "last_checked_iso": health_data["last_checked_iso"]
                }
            )
    
    return {"servers": service_data}
