import json
import asyncio
import logging
import os
from typing import Annotated

from fastapi import APIRouter, Request, Form, Depends, HTTPException, status, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import httpx

from ..core.config import settings
from ..auth.dependencies import web_auth, api_auth, enhanced_auth, nginx_proxied_auth
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
    logger.info(f"DEBUG: User {user_context['username']} accessible_services: {accessible_services}")
    logger.info(f"DEBUG: User {user_context['username']} ui_permissions: {user_context.get('ui_permissions', {})}")
    logger.info(f"DEBUG: User {user_context['username']} scopes: {user_context.get('scopes', [])}")
    
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
            "can_perform_action": can_perform_action  # Helper function for permission checks
        },
    )


@router.get("/servers")
async def get_servers_json(
    query: str | None = None,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
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

    # Add to FAISS index with current enabled state
    is_enabled = server_service.is_service_enabled(path)
    await faiss_service.add_or_update_service(path, server_entry, is_enabled)
    
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


@router.post("/internal/register")
async def internal_register_service(
    request: Request,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    path: Annotated[str, Form()],
    proxy_pass_url: Annotated[str, Form()],
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
    """Internal service registration endpoint for mcpgw-server (requires HTTP Basic Authentication with admin credentials)."""
    logger.warning("INTERNAL REGISTER: Function called - starting execution")  # TODO: replace with debug

    import base64
    import os
    from ..search.service import faiss_service
    from ..health.service import health_service
    from ..core.nginx_service import nginx_service

    logger.warning(f"INTERNAL REGISTER: Request parameters - name={name}, path={path}, proxy_pass_url={proxy_pass_url}")  # TODO: replace with debug

    # Check for HTTP Basic Authentication
    auth_header = request.headers.get("Authorization")
    logger.warning(f"INTERNAL REGISTER: Auth header present: {auth_header is not None}")  # TODO: replace with debug

    if not auth_header or not auth_header.startswith("Basic "):
        logger.warning("INTERNAL REGISTER: Authentication failed - no valid Basic auth header")  # TODO: replace with debug
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Decode Basic Auth credentials
    try:
        encoded_credentials = auth_header.split(" ")[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
        username, password = decoded_credentials.split(":", 1)
        logger.warning(f"INTERNAL REGISTER: Decoded credentials - username={username}")  # TODO: replace with debug
    except (IndexError, ValueError, Exception) as e:
        logger.warning(f"INTERNAL REGISTER: Auth decoding failed: {e}")  # TODO: replace with debug
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication format",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Verify admin credentials from environment
    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    logger.warning(f"INTERNAL REGISTER: Checking credentials - expected_user={admin_user}, has_password={admin_password is not None}")  # TODO: replace with debug

    if not admin_password:
        logger.warning("INTERNAL REGISTER: ADMIN_PASSWORD environment variable not set")  # TODO: replace with debug
        logger.error("ADMIN_PASSWORD environment variable not set for internal registration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server configuration error"
        )

    if username != admin_user or password != admin_password:
        logger.warning(f"INTERNAL REGISTER: Auth failed - expected {admin_user}, got {username}")  # TODO: replace with debug
        logger.warning(f"Failed admin authentication attempt for internal registration from {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.warning(f"INTERNAL REGISTER: Authentication successful for user {username}")  # TODO: replace with debug
    logger.info(f"Internal service registration request from admin user '{username}'")

    # Validate path format
    if not path.startswith('/'):
        path = '/' + path
    logger.warning(f"INTERNAL REGISTER: Validated path: {path}")  # TODO: replace with debug

    # Process tags
    tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()] if tags else []
    logger.warning(f"INTERNAL REGISTER: Processed tags: {tag_list}")  # TODO: replace with debug

    # Process supported_transports
    if supported_transports:
        try:
            transports_list = json.loads(supported_transports) if supported_transports.startswith('[') else [t.strip() for t in supported_transports.split(',')]
        except Exception as e:
            logger.warning(f"INTERNAL REGISTER: Failed to parse supported_transports, using default: {e}")
            transports_list = ["streamable-http"]
    else:
        transports_list = ["streamable-http"]

    # Process headers
    headers_list = []
    if headers:
        try:
            headers_list = json.loads(headers) if isinstance(headers, str) else headers
        except Exception as e:
            logger.warning(f"INTERNAL REGISTER: Failed to parse headers: {e}")

    # Process tool_list
    tool_list = []
    if tool_list_json:
        try:
            tool_list = json.loads(tool_list_json) if isinstance(tool_list_json, str) else tool_list_json
        except Exception as e:
            logger.warning(f"INTERNAL REGISTER: Failed to parse tool_list_json: {e}")

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
        "tool_list": tool_list
    }

    # Add optional fields if provided
    if auth_provider:
        server_entry["auth_provider"] = auth_provider
    if headers_list:
        server_entry["headers"] = headers_list

    logger.warning(f"INTERNAL REGISTER: Created server entry: {server_entry}")  # TODO: replace with debug
    logger.warning(f"INTERNAL REGISTER: Overwrite parameter: {overwrite}")  # TODO: replace with debug

    # Check if server exists and handle overwrite logic
    existing_server = server_service.get_server_info(path)
    if existing_server and not overwrite:
        logger.warning(f"INTERNAL REGISTER: Server exists and overwrite=False for path {path}")  # TODO: replace with debug
        return JSONResponse(
            status_code=409,  # Conflict status code for existing resource
            content={
                "error": "Service registration failed",
                "reason": f"A service with path '{path}' already exists",
                "suggestion": "Set overwrite=true or use the remove command first"
            },
        )

    # Register the server (this will overwrite if server exists and overwrite=True)
    logger.warning("INTERNAL REGISTER: Calling server_service.register_server")  # TODO: replace with debug
    if existing_server and overwrite:
        logger.warning(f"INTERNAL REGISTER: Overwriting existing server at path {path}")  # TODO: replace with debug
        success = server_service.update_server(path, server_entry)
    else:
        success = server_service.register_server(server_entry)

    if not success:
        logger.warning(f"INTERNAL REGISTER: Registration failed for path {path}")  # TODO: replace with debug
        return JSONResponse(
            status_code=409,  # Conflict status code for existing resource
            content={
                "error": "Service registration failed",
                "reason": f"Failed to register service at path '{path}'",
                "suggestion": "Check server logs for detailed error information"
            },
        )

    logger.warning("INTERNAL REGISTER: Auto-enabling newly registered server")  # TODO: replace with debug

    # Automatically enable the newly registered server BEFORE FAISS indexing
    try:
        toggle_success = server_service.toggle_service(path, True)
        if toggle_success:
            logger.info(f"Successfully auto-enabled server {path} after registration")
        else:
            logger.warning(f"Failed to auto-enable server {path} after registration")
    except Exception as e:
        logger.error(f"Error auto-enabling server {path}: {e}")
        # Non-fatal error - server is registered but not enabled

    logger.warning(f"INTERNAL REGISTER: Server registered successfully, adding to FAISS index")  # TODO: replace with debug

    # Add to FAISS index with current enabled state (should be True after auto-enable)
    is_enabled = server_service.is_service_enabled(path)
    await faiss_service.add_or_update_service(path, server_entry, is_enabled)

    logger.warning("INTERNAL REGISTER: Regenerating Nginx configuration")  # TODO: replace with debug

    # Regenerate Nginx configuration
    enabled_servers = {
        server_path: server_service.get_server_info(server_path)
        for server_path in server_service.get_enabled_services()
    }
    await nginx_service.generate_config_async(enabled_servers)

    logger.warning("INTERNAL REGISTER: Broadcasting health status update")  # TODO: replace with debug

    # Broadcast health status update to WebSocket clients
    await health_service.broadcast_health_update(path)

    logger.warning("INTERNAL REGISTER: Updating scopes.yml for new server")  # TODO: replace with debug

    # Update scopes.yml with the new server's tools
    from ..utils.scopes_manager import update_server_scopes

    # Get the tool list from the server entry
    tool_names = []
    if "tool_list" in server_entry and server_entry["tool_list"]:
        tool_names = [tool["name"] for tool in server_entry["tool_list"] if "name" in tool]

    # Update scopes and reload auth server
    try:
        await update_server_scopes(path, name, tool_names)
        logger.info(f"Successfully updated scopes for server {path} with {len(tool_names)} tools")
    except Exception as e:
        logger.error(f"Failed to update scopes for server {path}: {e}")
        # Non-fatal error - server is registered but scopes not updated

    logger.warning(f"INTERNAL REGISTER: Registration complete, returning success response")  # TODO: replace with debug
    logger.info(f"New service registered via internal endpoint: '{name}' at path '{path}' by admin '{username}'")

    return JSONResponse(
        status_code=201,
        content={
            "message": "Service registered successfully",
            "service": server_entry,
        },
    )


@router.post("/internal/remove")
async def internal_remove_service(
    request: Request,
    service_path: Annotated[str, Form()],
):
    """Internal service removal endpoint for mcpgw-server (requires HTTP Basic Authentication with admin credentials)."""
    import base64
    import os
    from ..search.service import faiss_service
    from ..health.service import health_service
    from ..core.nginx_service import nginx_service

    logger.warning("INTERNAL REMOVE: Function called - starting execution")  # TODO: replace with debug

    # Check for HTTP Basic Authentication
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        logger.warning("INTERNAL REMOVE: No Basic Auth header found")  # TODO: replace with debug
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.warning("INTERNAL REMOVE: Basic Auth header found, decoding credentials")  # TODO: replace with debug

    # Decode Basic Auth credentials
    try:
        encoded_credentials = auth_header.split(" ")[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
        username, password = decoded_credentials.split(":", 1)
        logger.warning(f"INTERNAL REMOVE: Decoded username: {username}")  # TODO: replace with debug
    except (IndexError, ValueError, Exception):
        logger.warning("INTERNAL REMOVE: Failed to decode Basic Auth credentials")  # TODO: replace with debug
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication format",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Verify admin credentials from environment
    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    logger.warning(f"INTERNAL REMOVE: Checking credentials against admin_user: {admin_user}")  # TODO: replace with debug

    if not admin_password:
        logger.error("ADMIN_PASSWORD environment variable not set for internal removal")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server configuration error"
        )

    if username != admin_user or password != admin_password:
        logger.warning(f"Failed admin authentication attempt for internal removal from {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.warning(f"INTERNAL REMOVE: Authentication successful for admin user '{username}'")  # TODO: replace with debug
    logger.info(f"Internal service removal request from admin user '{username}' for service '{service_path}'")

    # Validate path format
    if not service_path.startswith('/'):
        service_path = '/' + service_path

    logger.warning(f"INTERNAL REMOVE: Normalized service path: {service_path}")  # TODO: replace with debug

    # Check if server exists
    server_info = server_service.get_server_info(service_path)
    if not server_info:
        logger.warning(f"INTERNAL REMOVE: Service not found at path '{service_path}'")  # TODO: replace with debug
        return JSONResponse(
            status_code=404,
            content={
                "error": "Service not found",
                "reason": f"No service registered at path '{service_path}'",
                "suggestion": "Check the service path and ensure it is registered"
            },
        )

    logger.warning(f"INTERNAL REMOVE: Service found, proceeding with removal")  # TODO: replace with debug

    # Remove the server
    success = server_service.remove_server(service_path)

    if not success:
        logger.warning(f"INTERNAL REMOVE: Failed to remove service at path '{service_path}'")  # TODO: replace with debug
        return JSONResponse(
            status_code=500,
            content={
                "error": "Service removal failed",
                "reason": f"Failed to remove service at path '{service_path}'",
                "suggestion": "Check server logs for detailed error information"
            },
        )

    logger.warning(f"INTERNAL REMOVE: Service removed successfully, updating FAISS index")  # TODO: replace with debug

    # Remove from FAISS index
    await faiss_service.remove_service(service_path)

    logger.warning("INTERNAL REMOVE: Regenerating Nginx configuration")  # TODO: replace with debug

    # Regenerate Nginx configuration
    enabled_servers = {
        server_path: server_service.get_server_info(server_path)
        for server_path in server_service.get_enabled_services()
    }
    await nginx_service.generate_config_async(enabled_servers)

    logger.warning("INTERNAL REMOVE: Broadcasting health status update")  # TODO: replace with debug

    # Broadcast health status update to WebSocket clients
    await health_service.broadcast_health_update(service_path)

    logger.warning("INTERNAL REMOVE: Removing server from scopes.yml")  # TODO: replace with debug

    # Remove server from scopes.yml and reload auth server
    from ..utils.scopes_manager import remove_server_scopes

    try:
        await remove_server_scopes(service_path)
        logger.info(f"Successfully removed server {service_path} from scopes")
    except Exception as e:
        logger.error(f"Failed to remove server {service_path} from scopes: {e}")
        # Non-fatal error - server is removed but scopes not updated

    logger.warning(f"INTERNAL REMOVE: Removal complete, returning success response")  # TODO: replace with debug
    logger.info(f"Service removed via internal endpoint: '{service_path}' by admin '{username}'")

    return JSONResponse(
        status_code=200,
        content={
            "message": "Service removed successfully",
            "service_path": service_path,
        },
    )


@router.post("/internal/toggle")
async def internal_toggle_service(
    request: Request,
    service_path: Annotated[str, Form()],
):
    """Internal service toggle endpoint for mcpgw-server (requires HTTP Basic Authentication with admin credentials)."""
    import base64
    import os
    from ..search.service import faiss_service
    from ..health.service import health_service
    from ..core.nginx_service import nginx_service

    logger.warning("INTERNAL TOGGLE: Function called - starting execution")  # TODO: replace with debug

    # Check for HTTP Basic Authentication
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        logger.warning("INTERNAL TOGGLE: No Basic Auth header found")  # TODO: replace with debug
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.warning("INTERNAL TOGGLE: Basic Auth header found, decoding credentials")  # TODO: replace with debug

    # Decode Basic Auth credentials
    try:
        encoded_credentials = auth_header.split(" ")[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
        username, password = decoded_credentials.split(":", 1)
        logger.warning(f"INTERNAL TOGGLE: Decoded username: {username}")  # TODO: replace with debug
    except (IndexError, ValueError, Exception):
        logger.warning("INTERNAL TOGGLE: Failed to decode Basic Auth credentials")  # TODO: replace with debug
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication format",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Verify admin credentials from environment
    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    logger.warning(f"INTERNAL TOGGLE: Checking credentials against admin_user: {admin_user}")  # TODO: replace with debug

    if not admin_password:
        logger.error("ADMIN_PASSWORD environment variable not set for internal toggle")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server configuration error"
        )

    if username != admin_user or password != admin_password:
        logger.warning(f"Failed admin authentication attempt for internal toggle from {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.warning(f"INTERNAL TOGGLE: Admin authentication successful for user '{username}'")  # TODO: replace with debug

    # Ensure service_path starts with /
    if not service_path.startswith("/"):
        service_path = "/" + service_path

    # Check if server exists
    server_info = server_service.get_server_info(service_path)
    if not server_info:
        logger.warning(f"INTERNAL TOGGLE: Service not found at path '{service_path}'")  # TODO: replace with debug
        return JSONResponse(
            status_code=404,
            content={
                "error": "Service not found",
                "reason": f"No service registered at path '{service_path}'",
                "suggestion": "Check the service path and ensure it is registered"
            },
        )

    logger.warning(f"INTERNAL TOGGLE: Service found, proceeding with toggle")  # TODO: replace with debug

    # Get current state and toggle it
    current_state = server_service.is_service_enabled(service_path)
    new_state = not current_state
    success = server_service.toggle_service(service_path, new_state)

    if not success:
        logger.warning(f"INTERNAL TOGGLE: Failed to toggle service at path '{service_path}'")  # TODO: replace with debug
        return JSONResponse(
            status_code=500,
            content={
                "error": "Service toggle failed",
                "reason": f"Failed to toggle service at path '{service_path}'",
                "suggestion": "Check server logs for detailed error information"
            },
        )

    server_name = server_info["server_name"]
    logger.info(f"Toggled '{server_name}' ({service_path}) to {new_state} by admin '{username}'")

    # If enabling, perform immediate health check
    status_result = "disabled"
    last_checked_iso = None
    if new_state:
        logger.info(f"Performing immediate health check for {service_path} upon toggle ON...")
        try:
            status_result, last_checked_dt = await health_service.perform_immediate_health_check(service_path)
            last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
            logger.info(f"Immediate health check for {service_path} completed. Status: {status_result}")
        except Exception as e:
            logger.error(f"ERROR during immediate health check for {service_path}: {e}")
            status_result = f"error: immediate check failed ({type(e).__name__})"
    else:
        # When disabling, set status to disabled
        status_result = "disabled"
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

    logger.warning(f"INTERNAL TOGGLE: Toggle complete, returning success response")  # TODO: replace with debug
    return JSONResponse(
        status_code=200,
        content={
            "message": f"Service toggled successfully",
            "service_path": service_path,
            "new_enabled_state": new_state,
            "status": status_result,
            "last_checked_iso": last_checked_iso,
            "num_tools": server_info.get("num_tools", 0)
        },
    )


@router.post("/internal/healthcheck")
async def internal_healthcheck(request: Request):
    """Internal health check endpoint for mcpgw-server (requires HTTP Basic Authentication with admin credentials)."""
    import base64
    import os
    from ..health.service import health_service

    logger.warning("INTERNAL HEALTHCHECK: Function called - starting execution")  # TODO: replace with debug

    # Check for HTTP Basic Authentication
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        logger.warning("INTERNAL HEALTHCHECK: No Basic Auth header found")  # TODO: replace with debug
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.warning("INTERNAL HEALTHCHECK: Basic Auth header found, decoding credentials")  # TODO: replace with debug

    # Decode Basic Auth credentials
    try:
        encoded_credentials = auth_header.split(" ")[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
        username, password = decoded_credentials.split(":", 1)
        logger.warning(f"INTERNAL HEALTHCHECK: Decoded username: {username}")  # TODO: replace with debug
    except (IndexError, ValueError, Exception):
        logger.warning("INTERNAL HEALTHCHECK: Failed to decode Basic Auth credentials")  # TODO: replace with debug
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication format",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Verify admin credentials from environment
    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if not admin_password:
        logger.error("INTERNAL HEALTHCHECK: ADMIN_PASSWORD not set in environment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error"
        )

    if username != admin_user or password != admin_password:
        logger.warning(f"INTERNAL HEALTHCHECK: Invalid credentials for user: {username}")  # TODO: replace with debug
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.warning(f"INTERNAL HEALTHCHECK: Admin authenticated successfully: {username}")  # TODO: replace with debug

    # Get health status for all servers
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


@router.get("/tokens", response_class=HTMLResponse)
async def token_generation_page(
    request: Request,
    user_context: Annotated[dict, Depends(enhanced_auth)]
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


@router.get("/tools/{service_path:path}")
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
        # Call MCP client to fetch fresh tools using server configuration
        tool_list = await mcp_client_service.get_tools_from_server_with_server_info(proxy_pass_url, server_info)

        if tool_list is None:
            # If live fetch fails but we have cached tools, use those
            cached_tools = server_info.get("tool_list")
            if cached_tools is not None and isinstance(cached_tools, list):
                logger.warning(f"Failed to fetch live tools for {service_path}, using cached tools")
                return {"service_path": service_path, "tools": cached_tools, "cached": True}
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

@router.post("/internal/add-to-groups")
async def internal_add_server_to_groups(
    request: Request,
    server_name: Annotated[str, Form()],
    group_names: Annotated[str, Form()],  # Comma-separated list
):
    """Internal endpoint to add a server to specific scopes groups (requires HTTP Basic Authentication with admin credentials)."""
    import base64
    import os
    from ..utils.scopes_manager import add_server_to_groups

    # Extract and validate Basic Auth
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        credentials = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = credentials.split(":", 1)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Basic"},
        )

    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not admin_password:
        logger.error("ADMIN_PASSWORD environment variable not set for internal add-to-groups")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server configuration error"
        )

    if username != admin_user or password != admin_password:
        logger.warning(f"Failed admin authentication attempt for internal add-to-groups from {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Parse group names from comma-separated string
    groups = [group.strip() for group in group_names.split(",") if group.strip()]
    if not groups:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid group names provided"
        )

    # Convert server name to path format
    server_path = f"/{server_name}" if not server_name.startswith("/") else server_name

    logger.info(f"Adding server {server_path} to groups {groups} via internal endpoint by admin '{username}'")

    try:
        success = await add_server_to_groups(server_path, groups)

        if success:
            return JSONResponse(
                status_code=200,
                content={
                    "message": "Server successfully added to groups",
                    "server_path": server_path,
                    "groups": groups
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to add server to groups"
            )

    except Exception as e:
        logger.error(f"Error adding server {server_path} to groups {groups}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.post("/internal/remove-from-groups")
async def internal_remove_server_from_groups(
    request: Request,
    server_name: Annotated[str, Form()],
    group_names: Annotated[str, Form()],  # Comma-separated list
):
    """Internal endpoint to remove a server from specific scopes groups (requires HTTP Basic Authentication with admin credentials)."""
    import base64
    import os
    from ..utils.scopes_manager import remove_server_from_groups

    # Extract and validate Basic Auth
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        credentials = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = credentials.split(":", 1)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Basic"},
        )

    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not admin_password:
        logger.error("ADMIN_PASSWORD environment variable not set for internal remove-from-groups")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server configuration error"
        )

    if username != admin_user or password != admin_password:
        logger.warning(f"Failed admin authentication attempt for internal remove-from-groups from {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Parse group names from comma-separated string
    groups = [group.strip() for group in group_names.split(",") if group.strip()]
    if not groups:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid group names provided"
        )

    # Convert server name to path format
    server_path = f"/{server_name}" if not server_name.startswith("/") else server_name

    logger.info(f"Removing server {server_path} from groups {groups} via internal endpoint by admin '{username}'")

    try:
        success = await remove_server_from_groups(server_path, groups)

        if success:
            return JSONResponse(
                status_code=200,
                content={
                    "message": "Server successfully removed from groups",
                    "server_path": server_path,
                    "groups": groups
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to remove server from groups"
            )

    except Exception as e:
        logger.error(f"Error removing server {server_path} from groups {groups}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.get("/internal/list")
async def internal_list_services(
    request: Request,
):
    """Internal service listing endpoint for mcpgw-server (requires HTTP Basic Authentication with admin credentials)."""
    import base64
    import os

    logger.warning("INTERNAL LIST: Function called - starting execution")  # TODO: replace with debug

    # Check for HTTP Basic Authentication
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        logger.warning("INTERNAL LIST: No Basic Auth header found")  # TODO: replace with debug
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.warning("INTERNAL LIST: Basic Auth header found, decoding credentials")  # TODO: replace with debug

    # Decode Basic Auth credentials
    try:
        encoded_credentials = auth_header.split(" ")[1]
        decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
        username, password = decoded_credentials.split(":", 1)
        logger.warning(f"INTERNAL LIST: Decoded username: {username}")  # TODO: replace with debug
    except (IndexError, ValueError, Exception):
        logger.warning("INTERNAL LIST: Failed to decode Basic Auth credentials")  # TODO: replace with debug
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication format",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Verify admin credentials from environment
    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    logger.warning(f"INTERNAL LIST: Checking credentials against admin_user: {admin_user}")  # TODO: replace with debug

    if not admin_password:
        logger.error("ADMIN_PASSWORD environment variable not set for internal list")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server configuration error"
        )

    if username != admin_user or password != admin_password:
        logger.warning(f"Failed admin authentication attempt for internal list from {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.warning(f"INTERNAL LIST: Authentication successful for admin user '{username}'")  # TODO: replace with debug
    logger.info(f"Internal service list request from admin user '{username}'")

    # Get all servers (admin access - no permission filtering)
    all_servers = server_service.get_all_servers()

    logger.warning(f"INTERNAL LIST: Found {len(all_servers)} servers")  # TODO: replace with debug

    # Transform the data to include enabled status and health information
    services = []
    for service_path, server_info in all_servers.items():
        from ..health.service import health_service

        # Get real health status from health service
        health_data = health_service._get_service_health_data(service_path)

        service_data = {
            "server_name": server_info.get("server_name", "Unknown"),
            "path": service_path,
            "description": server_info.get("description", ""),
            "proxy_pass_url": server_info.get("proxy_pass_url", ""),
            "is_enabled": server_service.is_service_enabled(service_path),
            "tags": server_info.get("tags", []),
            "num_tools": server_info.get("num_tools", 0),
            "num_stars": server_info.get("num_stars", 0),
            "is_python": server_info.get("is_python", False),
            "license": server_info.get("license", "N/A"),
            "health_status": health_data["status"],
            "last_checked_iso": health_data["last_checked_iso"],
            "tool_list": server_info.get("tool_list", [])
        }
        services.append(service_data)

    logger.warning(f"INTERNAL LIST: Returning {len(services)} services")  # TODO: replace with debug
    logger.info(f"Internal service list completed for admin user '{username}' - returned {len(services)} services")

    return JSONResponse(
        status_code=200,
        content={
            "services": services,
            "total_count": len(services)
        },
    )


@router.post("/internal/create-group")
async def internal_create_group(
    request: Request,
    group_name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    create_in_keycloak: Annotated[bool, Form()] = True,
):
    """Internal endpoint to create a new group in both Keycloak and scopes.yml (requires HTTP Basic Authentication with admin credentials)."""
    import base64
    import os
    from ..utils.scopes_manager import create_group_in_scopes
    from ..utils.keycloak_manager import create_keycloak_group, group_exists_in_keycloak

    # Extract and validate Basic Auth
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        credentials = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = credentials.split(":", 1)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Basic"},
        )

    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not admin_password:
        logger.error("ADMIN_PASSWORD environment variable not set for internal create-group")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server configuration error"
        )

    if username != admin_user or password != admin_password:
        logger.warning(f"Failed admin authentication attempt for internal create-group from {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Validate group name
    if not group_name or not group_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group name is required"
        )

    logger.info(f"Creating group '{group_name}' via internal endpoint by admin '{username}'")

    try:
        # Create in Keycloak first if requested
        keycloak_created = False
        if create_in_keycloak:
            try:
                # Check if group already exists in Keycloak
                if await group_exists_in_keycloak(group_name):
                    logger.warning(f"Group '{group_name}' already exists in Keycloak")
                else:
                    await create_keycloak_group(group_name, description)
                    keycloak_created = True
                    logger.info(f"Group '{group_name}' created in Keycloak")
            except Exception as e:
                logger.error(f"Failed to create group in Keycloak: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create group in Keycloak: {str(e)}"
                )

        # Create in scopes.yml
        scopes_success = await create_group_in_scopes(group_name, description)

        if scopes_success:
            return JSONResponse(
                status_code=200,
                content={
                    "message": "Group successfully created",
                    "group_name": group_name,
                    "created_in_keycloak": keycloak_created,
                    "created_in_scopes": True
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create group in scopes.yml (may already exist)"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating group '{group_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.post("/internal/delete-group")
async def internal_delete_group(
    request: Request,
    group_name: Annotated[str, Form()],
    delete_from_keycloak: Annotated[bool, Form()] = True,
    force: Annotated[bool, Form()] = False,
):
    """Internal endpoint to delete a group from both Keycloak and scopes.yml (requires HTTP Basic Authentication with admin credentials)."""
    import base64
    import os
    from ..utils.scopes_manager import delete_group_from_scopes
    from ..utils.keycloak_manager import delete_keycloak_group, group_exists_in_keycloak

    # Extract and validate Basic Auth
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        credentials = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = credentials.split(":", 1)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Basic"},
        )

    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not admin_password:
        logger.error("ADMIN_PASSWORD environment variable not set for internal delete-group")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server configuration error"
        )

    if username != admin_user or password != admin_password:
        logger.warning(f"Failed admin authentication attempt for internal delete-group from {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Validate group name
    if not group_name or not group_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group name is required"
        )

    # Prevent deletion of system groups
    system_groups = [
        "UI-Scopes",
        "group_mappings",
        "mcp-registry-admin",
        "mcp-registry-user",
        "mcp-registry-developer",
        "mcp-registry-operator"
    ]

    if group_name in system_groups:
        logger.warning(f"Attempt to delete system group '{group_name}' by admin '{username}'")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot delete system group '{group_name}'"
        )

    logger.info(f"Deleting group '{group_name}' via internal endpoint by admin '{username}'")

    try:
        # Delete from scopes.yml first
        scopes_success = await delete_group_from_scopes(group_name, remove_from_mappings=True)

        if not scopes_success:
            logger.warning(f"Group '{group_name}' not found in scopes.yml or deletion failed")

        # Delete from Keycloak if requested
        keycloak_deleted = False
        if delete_from_keycloak:
            try:
                if await group_exists_in_keycloak(group_name):
                    await delete_keycloak_group(group_name)
                    keycloak_deleted = True
                    logger.info(f"Group '{group_name}' deleted from Keycloak")
                else:
                    logger.warning(f"Group '{group_name}' not found in Keycloak")
            except Exception as e:
                logger.error(f"Failed to delete group from Keycloak: {e}")
                # Continue anyway - scopes deletion might have succeeded

        if scopes_success or keycloak_deleted:
            return JSONResponse(
                status_code=200,
                content={
                    "message": "Group deletion completed",
                    "group_name": group_name,
                    "deleted_from_keycloak": keycloak_deleted,
                    "deleted_from_scopes": scopes_success
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group '{group_name}' not found in either Keycloak or scopes.yml"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting group '{group_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.get("/internal/list-groups")
async def internal_list_groups(
    request: Request,
    include_keycloak: bool = True,
    include_scopes: bool = True,
):
    """Internal endpoint to list groups from Keycloak and/or scopes.yml (requires HTTP Basic Authentication with admin credentials)."""
    import base64
    import os
    from ..utils.scopes_manager import list_groups_from_scopes
    from ..utils.keycloak_manager import list_keycloak_groups

    # Extract and validate Basic Auth
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        credentials = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = credentials.split(":", 1)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Basic"},
        )

    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not admin_password:
        logger.error("ADMIN_PASSWORD environment variable not set for internal list-groups")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server configuration error"
        )

    if username != admin_user or password != admin_password:
        logger.warning(f"Failed admin authentication attempt for internal list-groups from {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    logger.info(f"Listing groups via internal endpoint by admin '{username}'")

    try:
        result = {
            "keycloak_groups": [],
            "scopes_groups": {},
            "synchronized": [],
            "keycloak_only": [],
            "scopes_only": []
        }

        # Get groups from Keycloak
        keycloak_group_names = set()
        if include_keycloak:
            try:
                keycloak_groups = await list_keycloak_groups()
                result["keycloak_groups"] = [
                    {
                        "name": group.get("name"),
                        "id": group.get("id"),
                        "path": group.get("path", "")
                    }
                    for group in keycloak_groups
                ]
                keycloak_group_names = {group.get("name") for group in keycloak_groups}
                logger.info(f"Found {len(keycloak_groups)} groups in Keycloak")
            except Exception as e:
                logger.error(f"Failed to list Keycloak groups: {e}")
                result["keycloak_error"] = str(e)

        # Get groups from scopes.yml
        scopes_group_names = set()
        if include_scopes:
            try:
                scopes_data = await list_groups_from_scopes()
                result["scopes_groups"] = scopes_data.get("groups", {})
                scopes_group_names = set(scopes_data.get("groups", {}).keys())
                logger.info(f"Found {len(scopes_group_names)} groups in scopes.yml")
            except Exception as e:
                logger.error(f"Failed to list scopes groups: {e}")
                result["scopes_error"] = str(e)

        # Find synchronized and out-of-sync groups
        if include_keycloak and include_scopes:
            result["synchronized"] = list(keycloak_group_names & scopes_group_names)
            result["keycloak_only"] = list(keycloak_group_names - scopes_group_names)
            result["scopes_only"] = list(scopes_group_names - keycloak_group_names)

        return JSONResponse(
            status_code=200,
            content=result
        )

    except Exception as e:
        logger.error(f"Error listing groups: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.post("/tokens/generate")
async def generate_user_token(
    request: Request,
    user_context: Annotated[dict, Depends(enhanced_auth)]
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
        if not isinstance(expires_in_hours, int) or expires_in_hours <= 0 or expires_in_hours > 24:
            raise HTTPException(
                status_code=400,
                detail="expires_in_hours must be an integer between 1 and 24"
            )
        
        # Validate requested_scopes
        if requested_scopes and not isinstance(requested_scopes, list):
            raise HTTPException(
                status_code=400,
                detail="requested_scopes must be a list of strings"
            )
        
        # Prepare request to auth server
        auth_request = {
            "user_context": {
                "username": user_context["username"],
                "scopes": user_context["scopes"],
                "groups": user_context["groups"]
            },
            "requested_scopes": requested_scopes,
            "expires_in_hours": expires_in_hours,
            "description": description
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
                timeout=10.0
            )
            
            if response.status_code == 200:
                token_data = response.json()
                logger.info(f"Successfully generated token for user '{user_context['username']}'")

                # Format response to match expected structure (including refresh token)
                formatted_response = {
                    "success": True,
                    "tokens": {
                        "access_token": token_data.get("access_token"),
                        "refresh_token": token_data.get("refresh_token"),
                        "expires_in": token_data.get("expires_in"),
                        "refresh_expires_in": token_data.get("refresh_expires_in"),
                        "token_type": token_data.get("token_type", "Bearer"),
                        "scope": token_data.get("scope", "")
                    },
                    "keycloak_url": getattr(settings, 'keycloak_url', None) or "http://keycloak:8080",
                    "realm": getattr(settings, 'keycloak_realm', None) or "mcp-gateway",
                    "client_id": "user-generated",
                    # Legacy fields for backward compatibility
                    "token_data": token_data,
                    "user_scopes": user_context["scopes"],
                    "requested_scopes": requested_scopes or user_context["scopes"]
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
                    detail=f"Token generation failed: {error_detail}"
                )
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error generating token for user '{user_context['username']}': {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error generating token"
        )


@router.get("/admin/tokens")
async def get_admin_tokens(
    user_context: Annotated[dict, Depends(enhanced_auth)]
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
            detail="This endpoint is only available to admin users"
        )

    try:
        from ..utils.keycloak_manager import (
            KEYCLOAK_ADMIN_URL,
            KEYCLOAK_REALM
        )

        # Get M2M client credentials from environment
        m2m_client_id = os.getenv("KEYCLOAK_M2M_CLIENT_ID", "mcp-gateway-m2m")
        m2m_client_secret = os.getenv("KEYCLOAK_M2M_CLIENT_SECRET")

        if not m2m_client_secret:
            raise HTTPException(
                status_code=500,
                detail="Keycloak M2M client secret not configured"
            )

        # Get tokens from Keycloak mcp-gateway realm using M2M client_credentials
        token_url = f"{KEYCLOAK_ADMIN_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"

        data = {
            "grant_type": "client_credentials",
            "client_id": m2m_client_id,
            "client_secret": m2m_client_secret
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

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
                "client_id": m2m_client_id
            }

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Failed to retrieve Keycloak tokens: HTTP {e.response.status_code}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to authenticate with Keycloak: HTTP {e.response.status_code}"
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving Keycloak tokens: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error retrieving Keycloak tokens"
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
    user_context: Annotated[dict, Depends(nginx_proxied_auth)],
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
    logger.info(f"API register service request from user '{user_context.get('username')}' for service '{name}'")

    # Implementation extracted from internal_register_service to avoid duplicating auth logic
    # Auth is already validated by nginx_proxied_auth dependency
    from ..search.service import faiss_service
    from ..health.service import health_service
    from ..core.nginx_service import nginx_service

    # Validate path format
    if not path.startswith('/'):
        path = '/' + path
    logger.warning(f"SERVERS REGISTER: Validated path: {path}")

    # Process tags
    tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()] if tags else []

    # Process supported_transports
    if supported_transports:
        try:
            transports_list = json.loads(supported_transports) if supported_transports.startswith('[') else [t.strip() for t in supported_transports.split(',')]
        except Exception as e:
            logger.warning(f"SERVERS REGISTER: Failed to parse supported_transports, using default: {e}")
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
            tool_list = json.loads(tool_list_json) if isinstance(tool_list_json, str) else tool_list_json
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
        "tool_list": tool_list
    }

    # Add optional fields if provided
    if auth_provider:
        server_entry["auth_provider"] = auth_provider
    if headers_list:
        server_entry["headers"] = headers_list

    # Check if server exists and handle overwrite logic
    existing_server = server_service.get_server_info(path)
    if existing_server and not overwrite:
        logger.warning(f"SERVERS REGISTER: Server exists and overwrite=False for path {path}")
        return JSONResponse(
            status_code=409,
            content={
                "error": "Service registration failed",
                "reason": f"A service with path '{path}' already exists",
                "detail": "Use overwrite=true to replace existing service"
            }
        )

    try:
        # Register service (use update_server if overwriting, otherwise register_server)
        if existing_server and overwrite:
            logger.info(f"Overwriting existing server at path {path} by user {user_context.get('username')}")
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
                    "detail": "Check server logs for more information"
                }
            )

        logger.info(f"Service registered successfully via API: {path} by user {user_context.get('username')}")

        # Trigger async tasks for health check and FAISS sync
        asyncio.create_task(health_service.perform_immediate_health_check(path))
        asyncio.create_task(faiss_service.save_data())

        return JSONResponse(
            status_code=201,
            content={
                "path": path,
                "name": name,
                "message": f"Service '{name}' registered successfully at path '{path}'"
            }
        )

    except Exception as e:
        logger.error(f"Service registration failed for {path}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Service registration failed: {str(e)}"
        )


@router.post("/servers/toggle")
async def toggle_service_api(
    path: Annotated[str, Form()],
    new_state: Annotated[bool, Form()],
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
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
    from ..search.service import faiss_service
    from ..health.service import health_service
    from ..core.nginx_service import nginx_service

    logger.info(f"API toggle service request from user '{user_context.get('username')}' for path '{path}' to {new_state}")

    # Normalize path
    if not path.startswith('/'):
        path = '/' + path

    # Check if server exists
    server_info = server_service.get_server_info(path)
    if not server_info:
        raise HTTPException(status_code=404, detail="Service path not registered")

    # Toggle the service
    success = server_service.toggle_service(path, new_state)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to toggle service")

    logger.info(f"Toggled '{server_info['server_name']}' ({path}) to {new_state} by user '{user_context.get('username')}'")

    # If enabling, perform immediate health check
    status = "disabled"
    last_checked_iso = None
    if new_state:
        logger.info(f"Performing immediate health check for {path} upon toggle ON...")
        try:
            status, last_checked_dt = await health_service.perform_immediate_health_check(path)
            last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
            logger.info(f"Immediate health check for {path} completed. Status: {status}")
        except Exception as e:
            logger.error(f"ERROR during immediate health check for {path}: {e}")
            status = f"error: immediate check failed ({type(e).__name__})"
    else:
        # When disabling, set status to disabled
        status = "disabled"
        logger.info(f"Service {path} toggled OFF. Status set to disabled.")

    # Update FAISS metadata with new enabled state
    await faiss_service.add_or_update_service(path, server_info, new_state)

    # Regenerate Nginx configuration
    enabled_servers = {
        server_path: server_service.get_server_info(server_path)
        for server_path in server_service.get_enabled_services()
    }
    await nginx_service.generate_config_async(enabled_servers)

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
            "num_tools": server_info.get("num_tools", 0)
        }
    )


@router.post("/servers/remove")
async def remove_service_api(
    path: Annotated[str, Form()],
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
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
    from ..search.service import faiss_service
    from ..health.service import health_service
    from ..core.nginx_service import nginx_service
    from ..utils.scopes_manager import remove_server_scopes

    logger.info(f"API remove service request from user '{user_context.get('username')}' for path '{path}'")

    # Normalize path
    if not path.startswith('/'):
        path = '/' + path

    # Check if server exists
    server_info = server_service.get_server_info(path)
    if not server_info:
        logger.warning(f"Service not found at path '{path}'")
        return JSONResponse(
            status_code=404,
            content={
                "error": "Service not found",
                "reason": f"No service registered at path '{path}'",
                "suggestion": "Check the service path and ensure it is registered"
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
                "suggestion": "Check server logs for detailed error information"
            },
        )

    logger.info(f"Service removed successfully: {path} by user {user_context.get('username')}")

    # Remove from FAISS index
    await faiss_service.remove_service(path)

    # Regenerate Nginx configuration
    enabled_servers = {
        server_path: server_service.get_server_info(server_path)
        for server_path in server_service.get_enabled_services()
    }
    await nginx_service.generate_config_async(enabled_servers)

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
        content={
            "message": "Service removed successfully",
            "path": path
        }
    )


@router.get("/servers/health")
async def healthcheck_api(
    request: Request,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
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
    logger.info(f"API healthcheck request from user '{user_context.get('username') if user_context else 'unknown'}'")

    # Call the existing internal_healthcheck function
    return await internal_healthcheck(request)


@router.post("/servers/groups/add")
async def add_server_to_groups_api(
    request: Request,
    server_name: Annotated[str, Form()],
    group_names: Annotated[str, Form()],
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
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
    logger.info(f"API add to groups request from user '{user_context.get('username')}' for server '{server_name}'")

    # Call the existing internal_add_server_to_groups function
    return await internal_add_server_to_groups(request, server_name, group_names)


@router.post("/servers/groups/remove")
async def remove_server_from_groups_api(
    request: Request,
    server_name: Annotated[str, Form()],
    group_names: Annotated[str, Form()],
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
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
    logger.info(f"API remove from groups request from user '{user_context.get('username')}' for server '{server_name}'")

    # Call the existing internal_remove_server_from_groups function
    return await internal_remove_server_from_groups(request, server_name, group_names)


@router.post("/servers/groups/create")
async def create_group_api(
    request: Request,
    group_name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    create_in_keycloak: Annotated[bool, Form()] = True,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
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
    logger.info(f"API create group request from user '{user_context.get('username')}' for group '{group_name}'")

    # Call the existing internal_create_group function
    return await internal_create_group(request, group_name, description, create_in_keycloak)


@router.post("/servers/groups/delete")
async def delete_group_api(
    request: Request,
    group_name: Annotated[str, Form()],
    delete_from_keycloak: Annotated[bool, Form()] = True,
    force: Annotated[bool, Form()] = False,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
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
    logger.info(f"API delete group request from user '{user_context.get('username')}' for group '{group_name}'")

    # Call the existing internal_delete_group function
    return await internal_delete_group(request, group_name, delete_from_keycloak, force)


@router.get("/servers/groups")
async def list_groups_api(
    request: Request,
    include_keycloak: bool = True,
    include_scopes: bool = True,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
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
    logger.info(f"API list groups request from user '{user_context.get('username') if user_context else 'unknown'}'")

    # Call the existing internal_list_groups function
    return await internal_list_groups(request, include_keycloak, include_scopes)


@router.get("/servers/tools/{service_path:path}")
async def get_service_tools_api(
    service_path: str,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
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
    logger.info(f"API get tools request from user '{user_context.get('username') if user_context else 'unknown'}' for path '{service_path}'")

    # Call the existing get_service_tools function
    return await get_service_tools(service_path=service_path, user_context=user_context)
