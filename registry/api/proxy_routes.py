"""
Dynamic MCP server proxy routes.
Replaces nginx {{LOCATION_BLOCKS}} with FastAPI dynamic routing.
"""

import logging
import httpx
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from registry.utils.log import metrics
from registry.services.server_service_v1 import server_service_v1
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
            logger.info("Using SSE streaming mode")
            
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
            logger.info("Using regular HTTP mode")
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
                logger.info("Response body: [binary data]")
            
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


async def extract_server_path_from_request(request_path: str) -> Optional[str]:
    """
    Extract registered server path prefix from request URL.
    
    Tries progressively shorter path segments until finding a registered server.
    For example, "/github/repos/list" will check:
    1. /github/repos/list
    2. /github/repos  
    3. /github
    
    Args:
        request_path: Full incoming request path (e.g., /github/repos/list)
        
    Returns:
        Registered server path if found, None otherwise
    """
    # Split path into segments
    segments = [s for s in request_path.split('/') if s]
    
    # Try progressively shorter paths (longest first for specificity)
    for i in range(len(segments), 0, -1):
        candidate_path = '/' + '/'.join(segments[:i])
        
        # Query database for this exact path
        server = await server_service_v1.get_server_by_path(candidate_path)
        if server:
            return candidate_path
    
    return None


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_mcp_proxy(request: Request, full_path: str):
    """
    Dynamic catch-all route for MCP server proxying.
    This replaces nginx {{LOCATION_BLOCKS}}.
    
    NOTE: This must be registered LAST in main.py so other routes take precedence.
    """
    path = f"/{full_path}"
       
    # Extract registered server path from request URL
    server_path = await extract_server_path_from_request(path)
    if not server_path:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Get server by the extracted path (guaranteed unique in database)
    server = await server_service_v1.get_server_by_path(server_path)
    if not server:
        raise HTTPException(status_code=404, detail="Not found")
    
    # Check if server is enabled
    config = server.config or {}
    if not config.get("enabled", False):
        return JSONResponse(
            status_code=503,
            content={
                "error": "Service disabled",
                "service": server.path
            }
        )
    # Validate authentication
    try:
        auth_context = await validate_auth(request)
    except HTTPException as e:
        logger.warning(f"Auth failed for {path}: {e.detail}")
        raise
    
    # Get target URL from server config
    proxy_pass_url = config.get("url")
    if not proxy_pass_url:
        logger.error(f"No URL configured for {server.path}")
        raise HTTPException(status_code=500, detail="Server misconfigured")
    
    # Ensure proxy_pass_url has trailing slash
    if not proxy_pass_url.endswith('/'):
        proxy_pass_url += '/'
    
    remaining_path = path[len(server.path):].lstrip('/')
    
    # Build full target URL
    target_url = proxy_pass_url + remaining_path
    
    # Determine transport type from server config
    transport_type = config.get("type", "streamable-http")
    
    # Build server_config for authentication
    server_config = {}
    if "apiKey" in config:
        server_config["apiKey"] = config["apiKey"]
    
    # Proxy the request
    logger.info(f"Proxying {request.method} {path} → {target_url} (transport: {transport_type})")
    
    metrics.record_server_request(server_name=full_path)
    
    return await proxy_to_mcp_server(
        request=request,
        target_url=target_url,
        auth_context=auth_context,
        transport_type=transport_type,
        server_config=server_config
    )


async def shutdown_proxy_client():
    """Cleanup proxy client on shutdown."""
    await proxy_client.aclose()
    logger.info("Proxy client closed")
