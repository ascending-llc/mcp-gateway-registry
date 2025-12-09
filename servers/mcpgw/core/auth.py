"""
Authentication and authorization functionality.

This module handles authentication context extraction, session validation,
and user access verification for tools.
"""

import logging
import json
import httpx
from typing import Dict, Any, List
from fastmcp import Context
from fastmcp.server.dependencies import get_http_request

from core.scopes import extract_user_scopes_from_headers

logger = logging.getLogger(__name__)


async def extract_auth_context(ctx: Context) -> Dict[str, Any]:
    """
    Extract authentication context from the MCP Context.
    FastMCP 2.0 version with improved HTTP header access.
    
    Args:
        ctx: FastMCP Context object
        
    Returns:
        Dict containing authentication information
    """
    try:
        # Basic context information we can reliably access
        auth_context = {
            "request_id": ctx.request_id,
            "client_id": ctx.client_id,
            "session_available": ctx.session is not None,
            "request_context_available": ctx.request_context is not None,
        }
        
        # Try to get HTTP request information using FastMCP 2.0 dependency system
        try:
            http_request = get_http_request()
            if http_request:
                auth_context["http_request_available"] = True
                
                # Access HTTP headers directly
                headers = dict(http_request.headers)
                auth_headers = {}
                
                # Extract auth-related headers
                for key, value in headers.items():
                    key_lower = key.lower()
                    if key_lower in ['authorization', 'x-user-pool-id', 'x-client-id', 'x-region', 
                                    'x-scopes', 'x-user', 'x-username', 'x-auth-method', 'cookie']:
                        if key_lower == 'authorization':
                            # Don't log full auth token, just indicate presence
                            auth_headers[key] = "Bearer Token Present" if value.startswith('Bearer ') else "Auth Header Present"
                        elif key_lower == 'cookie' and 'mcp_gateway_session=' in value:
                            # Extract session cookie safely
                            import re
                            match = re.search(r'mcp_gateway_session=([^;]+)', value)
                            if match:
                                cookie_value = match.group(1)
                                auth_headers["session_cookie"] = cookie_value[:20] + "..." if len(cookie_value) > 20 else cookie_value
                        else:
                            auth_headers[key] = str(value)[:100]  # Truncate long values
                
                if auth_headers:
                    auth_context["auth_headers"] = auth_headers
                else:
                    auth_context["auth_headers"] = "No auth headers found"
                
                # Additional HTTP request info
                auth_context["http_info"] = {
                    "method": http_request.method,
                    "url": str(http_request.url),
                    "client_host": http_request.client.host if http_request.client else "Unknown",
                    "user_agent": headers.get("user-agent", "Unknown")
                }
            else:
                auth_context["http_request_available"] = False
                auth_context["auth_headers"] = "No HTTP request context"
                
        except RuntimeError as e:
            # get_http_request() raises RuntimeError when not in HTTP context
            auth_context["http_request_available"] = False
            auth_context["auth_headers"] = f"Not in HTTP context: {str(e)}"
        except Exception as http_error:
            logger.debug(f"Could not access HTTP request: {http_error}")
            auth_context["http_request_available"] = False
            auth_context["auth_headers"] = f"HTTP access error: {str(http_error)}"
        
        # Try to inspect the session for transport-level information (fallback)
        session_info = {}
        try:
            session = ctx.session
            if session:
                session_info["session_type"] = type(session).__name__
                
                # Check if session has transport
                if hasattr(session, 'transport'):
                    transport = session.transport
                    if transport:
                        session_info["transport_type"] = type(transport).__name__
                        
                        # Try to access any available transport attributes
                        transport_attrs = [attr for attr in dir(transport) if not attr.startswith('_')]
                        session_info["transport_attributes"] = transport_attrs[:10]  # Limit to avoid spam
                        
        except Exception as session_error:
            logger.debug(f"Could not access session info: {session_error}")
            session_info["error"] = str(session_error)
        
        auth_context["session_info"] = session_info
        
        # Try to access request context metadata
        request_info = {}
        try:
            request_context = ctx.request_context
            if request_context:
                request_info["request_context_type"] = type(request_context).__name__
                
                if hasattr(request_context, 'meta') and request_context.meta:
                    meta = request_context.meta
                    meta_info = {}
                    
                    # Check for standard meta attributes
                    for attr in ['client_id', 'user_pool_id', 'region', 'progressToken']:
                        if hasattr(meta, attr):
                            value = getattr(meta, attr)
                            meta_info[attr] = str(value) if value is not None else None
                    
                    request_info["meta"] = meta_info
                    
        except Exception as request_error:
            logger.debug(f"Could not access request context info: {request_error}")
            request_info["error"] = str(request_error)
        
        auth_context["request_info"] = request_info
        
        return auth_context
        
    except Exception as e:
        logger.error(f"Failed to extract auth context: {e}")
        return {
            "error": f"Failed to extract auth context: {str(e)}",
            "request_id": getattr(ctx, 'request_id', 'unknown'),
            "client_id": getattr(ctx, 'client_id', None)
        }


async def log_auth_context(tool_name: str, ctx: Context) -> Dict[str, Any]:
    """
    Log authentication context for a tool call and return the context.
    
    Args:
        tool_name: Name of the tool being called
        ctx: FastMCP Context object
        
    Returns:
        Dict containing the auth context
    """
    auth_context = await extract_auth_context(ctx)
    
    # Log the context for debugging via MCP logging
    await ctx.info(f"🔐 Auth Context for {tool_name}:")
    await ctx.info(f"   Request ID: {auth_context.get('request_id', 'Unknown')}")
    await ctx.info(f"   Client ID: {auth_context.get('client_id', 'Not present')}")
    await ctx.info(f"   Session Available: {auth_context.get('session_available', False)}")
    
    # Log auth headers if found
    auth_headers = auth_context.get('auth_headers', {})
    if auth_headers:
        await ctx.info(f"   Auth Headers Found:")
        for key, value in auth_headers.items():
            await ctx.info(f"     {key}: {value}")
    else:
        await ctx.info(f"   No auth headers detected")
    
    # Log session info if available
    session_info = auth_context.get('session_info', {})
    if session_info.get('session_type'):
        await ctx.info(f"   Session Type: {session_info['session_type']}")
        if session_info.get('transport_type'):
            await ctx.info(f"   Transport Type: {session_info['transport_type']}")
    
    # Log request info if available
    request_info = auth_context.get('request_info', {})
    if request_info.get('meta'):
        await ctx.info(f"   Request Meta: {request_info['meta']}")
    
    # Also log to server logs for debugging
    logger.info(f"AUTH_CONTEXT for {tool_name}: {json.dumps(auth_context, indent=2, default=str)}")
    
    return auth_context


async def validate_session_cookie_with_auth_server(
    session_cookie: str, 
    auth_server_url: str = None
) -> Dict[str, Any]:
    """
    Validate a session cookie with the auth server and return user context.
    
    Args:
        session_cookie: The session cookie value
        auth_server_url: URL of the auth server (defaults to settings value)
        
    Returns:
        Dict containing user context information including username, groups, scopes, etc.
    """
    if auth_server_url is None:
        from config import settings
        auth_server_url = settings.AUTH_SERVER_URL
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Call the auth server to validate the session cookie
            response = await client.post(
                f"{auth_server_url}/validate",
                headers={
                    "Cookie": f"mcp_gateway_session={session_cookie}",
                    "Content-Type": "application/json"
                },
                json={"action": "validate_session"}  # Indicate we want session validation
            )
            
            if response.status_code == 200:
                user_context = response.json()
                logger.info(f"Session validation successful for user: {user_context.get('username', 'unknown')}")
                return user_context
            else:
                logger.warning(f"Session validation failed: HTTP {response.status_code}")
                return {"valid": False, "error": f"HTTP {response.status_code}"}
                
    except Exception as e:
        logger.error(f"Error validating session cookie: {e}")
        return {"valid": False, "error": str(e)}


async def extract_user_scopes_from_auth_context(auth_context: Dict[str, Any]) -> List[str]:
    """
    Extract user scopes from the authentication context.
    
    Args:
        auth_context: Authentication context from extract_auth_context()
        
    Returns:
        List of user scopes
    """
    # Try to get scopes from auth headers (set by nginx from auth server)
    auth_headers = auth_context.get("auth_headers", {})
    if isinstance(auth_headers, dict) and "x-scopes" in auth_headers:
        scopes_header = auth_headers["x-scopes"]
        if scopes_header and scopes_header.strip():
            # Scopes are space-separated in the header
            scopes = scopes_header.split()
            logger.info(f"Extracted scopes from auth headers: {scopes}")
            return scopes
    
    logger.warning("No scopes found in auth context")
    return []


async def validate_user_access_to_tool(
    ctx: Context, 
    tool_name: str, 
    server_name: str = "mcpgw", 
    action: str = "execute"
) -> bool:
    """
    Validate if the authenticated user has access to execute a specific tool.
    
    Args:
        ctx: FastMCP Context object
        tool_name: Name of the tool being accessed
        server_name: Name of the server (default: "mcpgw")  
        action: Action being performed ("read" or "execute")
        
    Returns:
        True if access is granted, False otherwise
        
    Raises:
        Exception: If access is denied
    """
    # Extract authentication context
    auth_context = await extract_auth_context(ctx)
    
    # Get user info
    auth_headers = auth_context.get("auth_headers", {})
    username = auth_headers.get("x-user", "unknown") or auth_headers.get("x-username", "unknown")
    
    # Extract scopes
    user_scopes = await extract_user_scopes_from_auth_context(auth_context)
    
    if not user_scopes:
        logger.error(f"FGAC: Access denied for user '{username}' to tool '{tool_name}' - no scopes available")
        raise Exception(f"Access denied: No scopes configured for user")
    
    logger.info(f"FGAC: Validating access for user '{username}' to tool '{tool_name}' on server '{server_name}' with action '{action}'")
    logger.info(f"FGAC: User scopes: {user_scopes}")
    
    # Check for server-specific scopes that allow this action
    required_scope_patterns = [
        f"mcp-servers-unrestricted/{action}",  # Unrestricted access for this action
        f"mcp-servers-restricted/{action}",    # Restricted access for this action
    ]
    
    for scope in user_scopes:
        if scope in required_scope_patterns:
            logger.info(f"FGAC: Access granted - user '{username}' has scope '{scope}' for tool '{tool_name}'")
            return True
    
    # If no matching scope found, deny access
    logger.error(f"FGAC: Access denied for user '{username}' to tool '{tool_name}' - insufficient permissions")
    logger.error(f"FGAC: Required one of: {required_scope_patterns}")
    logger.error(f"FGAC: User has: {user_scopes}")
    
    raise Exception(f"Access denied: Insufficient permissions to execute '{tool_name}'. Required scopes: {required_scope_patterns}")

