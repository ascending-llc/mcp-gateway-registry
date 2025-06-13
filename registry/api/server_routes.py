import json
import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Request, Form, Depends, HTTPException, status, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ..core.config import settings
from ..auth.dependencies import web_auth, api_auth, enhanced_auth
from ..services.server_service import server_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Templates
templates = Jinja2Templates(directory=settings.templates_dir)


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
        user_context = enhanced_auth(session)
    except HTTPException as e:
        logger.info(f"Authentication failed at root route: {e.detail}, redirecting to login")
        return RedirectResponse(url="/login", status_code=302)
        
    from ..auth.dependencies import user_has_ui_permission_for_service
    
    # Helper function for templates
    def can_perform_action(permission: str, service_name: str) -> bool:
        """Check if user has UI permission for a specific service"""
        return user_has_ui_permission_for_service(permission, service_name, user_context.get('ui_permissions', {}))
    
    service_data = []
    search_query = query.lower() if query else ""
    
    # Get servers based on user permissions
    if user_context['is_admin']:
        # Admin users see all servers
        all_servers = server_service.get_all_servers()
        logger.info(f"Admin user {user_context['username']} accessing all {len(all_servers)} servers")
    else:
        # Filtered users see only accessible servers
        all_servers = server_service.get_all_servers_with_permissions(user_context['accessible_servers'])
        logger.info(f"User {user_context['username']} accessing {len(all_servers)} of {len(server_service.get_all_servers())} total servers")
    
    sorted_server_paths = sorted(
        all_servers.keys(), 
        key=lambda p: all_servers[p]["server_name"]
    )
    
    # Filter services based on UI permissions
    accessible_services = user_context.get('accessible_services', [])
    
    for path in sorted_server_paths:
        server_info = all_servers[path]
        server_name = server_info["server_name"]
        
        # Check if user can list this service
        if 'all' not in accessible_services and server_name not in accessible_services:
            logger.debug(f"Filtering out service '{server_name}' - user doesn't have list_service permission")
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
            "can_perform_action": can_perform_action  # Helper function for permission checks
        },
    )


@router.post("/toggle/{service_path:path}")
async def toggle_service_route(
    request: Request,
    service_path: str,
    enabled: Annotated[str | None, Form()] = None,
    user_context: Annotated[dict, Depends(enhanced_auth)] = None,
):
    """Toggle a service on/off (requires toggle_service UI permission)."""
    from ..search.service import faiss_service
    from ..health.service import health_service
    from ..core.nginx_service import nginx_service
    from ..auth.dependencies import user_has_ui_permission_for_service
    
    if not service_path.startswith("/"):
        service_path = "/" + service_path
        
    server_info = server_service.get_server_info(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not registered")
    
    service_name = server_info["server_name"]
    
    # Check if user has toggle_service permission for this specific service
    if not user_has_ui_permission_for_service('toggle_service', service_name, user_context.get('ui_permissions', {})):
        logger.warning(f"User {user_context['username']} attempted to toggle service {service_name} without toggle_service permission")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"You do not have permission to toggle {service_name}"
        )

    # For non-admin users, check if they have access to this specific server
    if not user_context['is_admin']:
        if not server_service.user_can_access_server_path(service_path, user_context['accessible_servers']):
            logger.warning(f"User {user_context['username']} attempted to toggle service {service_path} without access")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="You do not have access to this server"
            )

    new_state = enabled == "on"
    success = server_service.toggle_service(service_path, new_state)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to toggle service")
    
    server_name = server_info["server_name"]
    logger.info(f"Toggled '{server_name}' ({service_path}) to {new_state} by user '{user_context['username']}'")

    # If enabling, perform immediate health check
    status = "disabled"
    last_checked_iso = None
    if new_state:
        logger.info(f"Performing immediate health check for {service_path} upon toggle ON...")
        try:
            status, last_checked_dt = await health_service.perform_immediate_health_check(service_path)
            last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
            logger.info(f"Immediate health check for {service_path} completed. Status: {status}")
        except Exception as e:
            logger.error(f"ERROR during immediate health check for {service_path}: {e}")
            status = f"error: immediate check failed ({type(e).__name__})"
    else:
        # When disabling, set status to disabled
        status = "disabled"
        logger.info(f"Service {service_path} toggled OFF. Status set to disabled.")

    # Update FAISS metadata with new enabled state
    await faiss_service.add_or_update_service(service_path, server_info, new_state)
    
    # Regenerate Nginx configuration
    enabled_servers = {
        path: server_service.get_server_info(path) 
        for path in server_service.get_enabled_services()
    }
    await nginx_service.generate_config_async(enabled_servers)
    
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
            "num_tools": server_info.get("num_tools", 0)
        }
    )


@router.post("/register")
async def register_service(
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    path: Annotated[str, Form()],
    proxy_pass_url: Annotated[str, Form()],
    tags: Annotated[str, Form()] = "",
    num_tools: Annotated[int, Form()] = 0,
    num_stars: Annotated[int, Form()] = 0,
    is_python: Annotated[bool, Form()] = False,
    license_str: Annotated[str, Form(alias="license")] = "N/A",
    user_context: Annotated[dict, Depends(enhanced_auth)] = None,
):
    """Register a new service (requires register_service UI permission)."""
    from ..search.service import faiss_service
    from ..health.service import health_service
    from ..core.nginx_service import nginx_service
    from ..auth.dependencies import user_has_ui_permission_for_service
    
    # Check if user has register_service permission for any service
    ui_permissions = user_context.get('ui_permissions', {})
    register_permissions = ui_permissions.get('register_service', [])
    
    if not register_permissions:
        logger.warning(f"User {user_context['username']} attempted to register service without register_service permission")
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
        "tool_list": []
    }

    # Register the server
    success = server_service.register_server(server_entry)
    
    if not success:
        return JSONResponse(
            status_code=400,
            content={"error": f"Service with path '{path}' already exists or failed to save"},
        )

    # Add to FAISS index (disabled by default)
    await faiss_service.add_or_update_service(path, server_entry, False)
    
    # Regenerate Nginx configuration
    enabled_servers = {
        server_path: server_service.get_server_info(server_path) 
        for server_path in server_service.get_enabled_services()
    }
    await nginx_service.generate_config_async(enabled_servers)
    
    # Broadcast health status update to WebSocket clients
    await health_service.broadcast_health_update(path)
    
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
    request: Request, 
    service_path: str, 
    user_context: Annotated[dict, Depends(enhanced_auth)]
):
    """Show edit form for a service (requires modify_service UI permission)."""
    from ..auth.dependencies import user_has_ui_permission_for_service
    
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    server_info = server_service.get_server_info(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not found")
    
    service_name = server_info["server_name"]
    
    # Check if user has modify_service permission for this specific service
    if not user_has_ui_permission_for_service('modify_service', service_name, user_context.get('ui_permissions', {})):
        logger.warning(f"User {user_context['username']} attempted to access edit form for {service_name} without modify_service permission")
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
    service_path: str, 
    name: Annotated[str, Form()], 
    proxy_pass_url: Annotated[str, Form()], 
    user_context: Annotated[dict, Depends(enhanced_auth)], 
    description: Annotated[str, Form()] = "", 
    tags: Annotated[str, Form()] = "", 
    num_tools: Annotated[int, Form()] = 0, 
    num_stars: Annotated[int, Form()] = 0, 
    is_python: Annotated[bool | None, Form()] = False,  
    license_str: Annotated[str, Form(alias="license")] = "N/A", 
):
    """Handle server edit form submission (requires modify_service UI permission)."""
    from ..search.service import faiss_service
    from ..core.nginx_service import nginx_service
    from ..auth.dependencies import user_has_ui_permission_for_service
    
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    # Check if the server exists and get service name
    server_info = server_service.get_server_info(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not found")
    
    service_name = server_info["server_name"]
    
    # Check if user has modify_service permission for this specific service
    if not user_has_ui_permission_for_service('modify_service', service_name, user_context.get('ui_permissions', {})):
        logger.warning(f"User {user_context['username']} attempted to edit service {service_name} without modify_service permission")
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
    
    # Regenerate Nginx configuration
    enabled_servers = {
        path: server_service.get_server_info(path) 
        for path in server_service.get_enabled_services()
    }
    await nginx_service.generate_config_async(enabled_servers)
    
    logger.info(f"Server '{name}' ({service_path}) updated by user '{user_context['username']}'")

    # Redirect back to the main page
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/api/server_details/{service_path:path}")
async def get_server_details(
    service_path: str,
    user_context: Annotated[dict, Depends(enhanced_auth)]
):
    """Get server details by path, or all servers if path is 'all' (filtered by permissions)."""
    # Normalize the path to ensure it starts with '/'
    if not service_path.startswith('/'):
        service_path = '/' + service_path
    
    # Special case: if path is 'all' or '/all', return details for all accessible servers
    if service_path == '/all':
        if user_context['is_admin']:
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
            logger.warning(f"User {user_context['username']} attempted to access server details for {service_path} without access")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="You do not have access to this server"
            )
    
    return server_info


@router.get("/api/tools/{service_path:path}")
async def get_service_tools(
    service_path: str,
    user_context: Annotated[dict, Depends(enhanced_auth)]
):
    """Get tool list for a service (filtered by permissions)."""
    from ..core.mcp_client import mcp_client_service
    from ..search.service import faiss_service
    
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
            logger.warning(f"User {user_context['username']} attempted to access tools for {service_path} without access")
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
        # Call MCP client to fetch fresh tools
        tool_list = await mcp_client_service.get_tools_from_server(proxy_pass_url)
        
        if tool_list is None:
            raise HTTPException(status_code=503, detail="Failed to fetch tools from MCP server. Service may be unhealthy.")
        
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
        
        return {"service_path": service_path, "tools": tool_list}
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error fetching tools for {service_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching tools: {str(e)}")


@router.post("/api/refresh/{service_path:path}")
async def refresh_service(
    service_path: str, 
    user_context: Annotated[dict, Depends(enhanced_auth)]
):
    """Refresh service health and tool information (requires health_check_service permission)."""
    from ..search.service import faiss_service
    from ..health.service import health_service
    from ..core.mcp_client import mcp_client_service
    from ..core.nginx_service import nginx_service
    from ..auth.dependencies import user_has_ui_permission_for_service
    
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    server_info = server_service.get_server_info(service_path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not registered")
    
    service_name = server_info["server_name"]
    
    # Check if user has health_check_service permission for this specific service
    if not user_has_ui_permission_for_service('health_check_service', service_name, user_context.get('ui_permissions', {})):
        logger.warning(f"User {user_context['username']} attempted to refresh service {service_name} without health_check_service permission")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"You do not have permission to refresh {service_name}"
        )

    # For non-admin users, check if they have access to this specific server
    if not user_context['is_admin']:
        if not server_service.user_can_access_server_path(service_path, user_context['accessible_servers']):
            logger.warning(f"User {user_context['username']} attempted to refresh service {service_path} without access")
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
        
        # Regenerate Nginx config after manual refresh
        logger.info(f"Regenerating Nginx config after manual refresh for {service_path}...")
        enabled_servers = {
            path: server_service.get_server_info(path) 
            for path in server_service.get_enabled_services()
        }
        await nginx_service.generate_config_async(enabled_servers)
        
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