"""
Dynamic MCP server proxy routes.
Replaces nginx {{LOCATION_BLOCKS}} with FastAPI dynamic routing.
"""

import logging
import httpx
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.background import BackgroundTask

from registry.services.server_service import server_service
from registry.health.service import health_service
from registry.constants import HealthStatus
from registry.core.config import settings

logger = logging.getLogger(__name__)

# Create router WITHOUT prefix (we'll handle dynamic paths)
router = APIRouter(tags=["MCP Proxy"])

# Shared httpx client for connection pooling
proxy_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, read=60.0),
    follow_redirects=True,
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
)


async def validate_auth(request: Request) -> Dict[str, Any]:
    """
    Validate authentication by calling auth-server /validate endpoint.
    Replaces nginx auth_request pattern.
    """
    # Build validation headers
    validation_headers = {
        "X-Original-URI": request.url.path,
        "X-Original-Method": request.method,
        "X-Original-URL": str(request.url),
        "X-User-Pool-Id": request.headers.get("X-User-Pool-Id", ""),
        "X-Client-Id": request.headers.get("X-Client-Id", ""),
        "X-Region": request.headers.get("X-Region", ""),
        "X-Authorization": request.headers.get("X-Authorization", ""),
        "Authorization": request.headers.get("Authorization", ""),
    }
    
    # Get request body for validation (replaces Lua body capture)
    body = await request.body()
    if body:
        validation_headers["X-Body"] = body.decode("utf-8", errors="ignore")
    
    try:
        response = await proxy_client.get(
            f"{settings.auth_server_url}/validate",
            headers=validation_headers,
            cookies=request.cookies,
            timeout=10.0
        )
        
        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Authentication required")
        elif response.status_code == 403:
            raise HTTPException(status_code=403, detail="Access forbidden")
        elif response.status_code != 200:
            logger.warning(f"Auth validation returned {response.status_code}")
            raise HTTPException(status_code=502, detail="Auth validation failed")
        
        # Return auth context from response headers
        return {
            "username": response.headers.get("X-Username", ""),
            "user": response.headers.get("X-User", ""),
            "client_id": response.headers.get("X-Client-Id", ""),
            "scopes": response.headers.get("X-Scopes", "").split(),
            "auth_method": response.headers.get("X-Auth-Method", ""),
            "server_name": response.headers.get("X-Server-Name", ""),
            "tool_name": response.headers.get("X-Tool-Name", ""),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth validation error: {e}")
        raise HTTPException(status_code=500, detail="Auth validation error")


async def proxy_to_mcp_server(
    request: Request,
    target_url: str,
    auth_context: Dict[str, Any],
    transport_type: str = "streamable-http",
    server_config: Optional[Dict[str, Any]] = None
) -> Response:
    """
    Proxy request to MCP server with auth headers.
    Handles both regular HTTP and SSE streaming.
    
    Args:
        request: Incoming FastAPI request
        target_url: Backend MCP server URL
        auth_context: Gateway authentication context
        transport_type: Transport protocol type
        server_config: Server configuration including apiKey authentication
    """
    # Build proxy headers
    headers = dict(request.headers)
    headers.update({
        "X-User": auth_context.get("username", ""),
        "X-Username": auth_context.get("username", ""),
        "X-Client-Id": auth_context.get("client_id", ""),
        "X-Scopes": " ".join(auth_context.get("scopes", [])),
        "X-Auth-Method": auth_context.get("auth_method", ""),
        "X-Server-Name": auth_context.get("server_name", ""),
        "X-Tool-Name": auth_context.get("tool_name", ""),
        "X-Original-URL": str(request.url),
    })
    
    # Remove host header to avoid conflicts
    headers.pop("host", None)
    
    # Process backend server apiKey authentication if configured
    if server_config:
        api_key_config = server_config.get("apiKey")
        if api_key_config and isinstance(api_key_config, dict):
            key_value = api_key_config.get("key")
            authorization_type = api_key_config.get("authorization_type", "bearer").lower()
            
            if key_value:
                if authorization_type == "bearer":
                    # Bearer token: Authorization: Bearer <key>
                    headers['Authorization'] = f'Bearer {key_value}'
                    logger.debug("Added Bearer authentication header for backend server")
                elif authorization_type == "basic":
                    # Basic auth: Authorization: Basic <key>
                    headers['Authorization'] = f'Basic {key_value}'
                    logger.debug("Added Basic authentication header for backend server")
                elif authorization_type == "custom":
                    # Custom header: use custom_header field as header name
                    custom_header = api_key_config.get("custom_header")
                    if custom_header:
                        headers[custom_header] = key_value
                        logger.debug(f"Added custom authentication header for backend server: {custom_header}")
                    else:
                        logger.warning("apiKey with authorization_type='custom' but no custom_header specified")
                else:
                    logger.warning(f"Unknown authorization_type: {authorization_type}, defaulting to Bearer")
                    headers['Authorization'] = f'Bearer {key_value}'

    body = await request.body()
    
    try:
        accept_header = request.headers.get("accept", "")
        client_accepts_sse = "text/event-stream" in accept_header
        
        logger.info(f"Accept header: {accept_header}")
        logger.info(f"Client accepts SSE: {client_accepts_sse}")
        logger.info(f"Transport type: {transport_type}")
        
        # Always use streaming mode if client accepts SSE
        if client_accepts_sse:
            logger.info(f"Using SSE streaming mode")
            
            # We need to peek at response to get headers before starting the stream
            # Open the stream context but keep it alive
            stream_manager = {"response": None, "context": None}
            
            async def setup_stream():
                """Initialize stream and capture headers"""
                stream_manager["context"] = proxy_client.stream(
                    request.method,
                    target_url,
                    headers=headers,
                    content=body
                )
                stream_manager["response"] = await stream_manager["context"].__aenter__()
                return stream_manager["response"]
            
            async def cleanup_stream():
                """Clean up stream when done"""
                if stream_manager["context"] and stream_manager["response"]:
                    await stream_manager["context"].__aexit__(None, None, None)
            
            backend_response = await setup_stream()
            
            # Build response headers from backend
            response_headers = {
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            }
            
            # Forward important MCP headers, this is the standard MCP session header
            if "mcp-session-id" in backend_response.headers:
                session_id = backend_response.headers["mcp-session-id"]
                response_headers["Mcp-Session-Id"] = session_id
                logger.info(f"Forwarding Mcp-Session-Id: {session_id}")
            
            # Generator that streams from already-opened response
            async def stream_content():
                try:
                    async for chunk in backend_response.aiter_bytes():
                        yield chunk
                finally:
                    await cleanup_stream()
            
            return StreamingResponse(
                stream_content(),
                status_code=backend_response.status_code,
                media_type="text/event-stream",
                headers=response_headers
            )
        else:
            # Regular HTTP request
            logger.info(f"Using regular HTTP mode")
            response = await proxy_client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body
            )
            
            try:
                content_str = response.content.decode('utf-8')
                logger.info(f"Response body: {content_str[:1000]}")
            except:
                logger.info(f"Response body: [binary data]")
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type")
            )
            
    except httpx.TimeoutException:
        logger.error(f"Timeout proxying to {target_url}")
        return JSONResponse(
            status_code=504,
            content={"error": "Gateway timeout"}
        )
    except Exception as e:
        logger.error(f"Error proxying to {target_url}: {e}")
        return JSONResponse(
            status_code=502,
            content={"error": "Bad gateway", "detail": str(e)}
        )


def find_matching_mcp_server(path: str) -> Optional[tuple[str, Dict[str, Any]]]:
    """Find MCP server configuration matching the request path."""
    all_servers = server_service.get_all_servers()
    
    # Sort by path length (longest first) to match most specific route
    sorted_servers = sorted(
        all_servers.items(),
        key=lambda x: len(x[0]),
        reverse=True
    )
    
    for service_path, server_info in sorted_servers:
        if not server_service.is_service_enabled(service_path):
            continue
        
        if path.startswith(service_path):
            return (service_path, server_info)
    
    return None


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_mcp_proxy(request: Request, full_path: str):
    """
    Dynamic catch-all route for MCP server proxying.
    This replaces nginx {{LOCATION_BLOCKS}}.
    
    NOTE: This must be registered LAST in main.py so other routes take precedence.
    """
    path = f"/{full_path}"
       
    # Find matching MCP server
    match = find_matching_mcp_server(path)
    if match is None:
        # Not an MCP route
        raise HTTPException(status_code=404, detail="Not found")
    
    service_path, server_info = match
    
    # Check if server is healthy
    health_status = health_service.server_health_status.get(service_path, HealthStatus.UNKNOWN)
    if not HealthStatus.is_healthy(health_status):
        return JSONResponse(
            status_code=503,
            content={
                "error": "Service unavailable",
                "status": str(health_status),
                "service": service_path
            }
        )
    
    # Validate authentication
    try:
        auth_context = await validate_auth(request)
    except HTTPException as e:
        logger.warning(f"Auth failed for {path}: {e.detail}")
        raise
    
    # Get target URL and transport type
    proxy_pass_url = server_info.get("proxy_pass_url")
    if not proxy_pass_url:
        logger.error(f"No proxy_pass_url configured for {service_path}")
        raise HTTPException(status_code=500, detail="Server misconfigured")
    
    # Ensure proxy_pass_url has trailing slash
    if not proxy_pass_url.endswith('/'):
        proxy_pass_url += '/'
    
    remaining_path = path[len(service_path):].lstrip('/')
    
    # Build full target URL
    target_url = proxy_pass_url + remaining_path
    
    # Determine transport type
    supported_transports = server_info.get("supported_transports", ["streamable-http"])
    transport_type = "sse" if "sse" in supported_transports else "streamable-http"
    
    # Proxy the request
    logger.info(f"Proxying {request.method} {path} → {target_url} (transport: {transport_type})")
    return await proxy_to_mcp_server(
        request=request,
        target_url=target_url,
        auth_context=auth_context,
        transport_type=transport_type,
        server_config=server_info
    )


async def shutdown_proxy_client():
    """Cleanup proxy client on shutdown."""
    await proxy_client.aclose()
    logger.info("Proxy client closed")
