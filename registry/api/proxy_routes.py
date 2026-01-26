"""
Dynamic MCP server proxy routes.
"""

import logging
import httpx
from typing import Dict, Any, Optional, Union
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from registry.utils.log import metrics
from registry.auth.dependencies import CurrentUser
from registry.services.server_service_v1 import server_service_v1
from registry.utils.crypto_utils import decrypt_auth_fields
from registry.core.mcp_client import _build_headers_for_server
from registry.schemas.proxy_tool_schema import (
    ToolExecutionRequest,
    ToolExecutionResponse,
    ResourceReadRequest,
    ResourceReadResponse,
    PromptExecutionRequest,
    PromptExecutionResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MCP Proxy"])

# Shared httpx client for connection pooling
proxy_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, read=60.0),
    follow_redirects=True,
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
)

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
    # Build proxy headers - start with request headers
    headers = dict(request.headers)
    
    # Add context headers for tracing/logging
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
    
    # Build authentication headers for external MCP server
    if server_config:
        decrypt_config_fields = decrypt_auth_fields(server_config)
        auth_headers = _build_headers_for_server(decrypt_config_fields)
        headers.update(auth_headers)
        logger.debug("Built authentication headers for backend server")

    body = await request.body()
    
    try:
        accept_header = request.headers.get("accept", "")
        client_accepts_sse = "text/event-stream" in accept_header
        
        logger.debug(f"Accept: {accept_header}, Client SSE: {client_accepts_sse}, Transport: {transport_type}")
        
        # Optimize: Only use streaming if client accepts SSE
        if not client_accepts_sse:
            # Regular HTTP request (most common case for MCP JSON-RPC)
            response = await proxy_client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body
            )
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type")
            )
        
        # Client accepts SSE - check if backend returns SSE
        logger.debug("Client accepts SSE - checking backend response type")
        
        # Manually manage stream lifecycle (can't use async with - it closes too early)
        stream_context = proxy_client.stream(
            request.method,
            target_url,
            headers=headers,
            content=body
        )
        backend_response = await stream_context.__aenter__()
        
        backend_content_type = backend_response.headers.get("content-type", "")
        is_sse = "text/event-stream" in backend_content_type
        
        logger.debug(f"Backend: status={backend_response.status_code}, content-type={backend_content_type or 'none'}")
        
        # If backend doesn't return SSE, read full response and close stream
        if not is_sse:
            content_bytes = await backend_response.aread()
            await stream_context.__aexit__(None, None, None)
            
            return Response(
                content=content_bytes,
                status_code=backend_response.status_code,
                headers=dict(backend_response.headers),
                media_type=backend_content_type or "application/octet-stream"
            )
        
        # Backend is returning true SSE - keep stream open and forward it
        logger.info(f"Streaming SSE from backend")
        
        response_headers = {
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
        
        # Forward MCP session header if present
        if "mcp-session-id" in backend_response.headers:
            response_headers["Mcp-Session-Id"] = backend_response.headers["mcp-session-id"]
        
        # Stream content from backend to client - cleanup when done
        async def stream_sse():
            try:
                async for chunk in backend_response.aiter_bytes():
                    yield chunk
            except Exception as e:
                logger.error(f"SSE streaming error: {e}")
                raise
            finally:
                # Close stream when done streaming
                await stream_context.__aexit__(None, None, None)
        
        return StreamingResponse(
            stream_sse(),
            status_code=backend_response.status_code,
            media_type="text/event-stream",
            headers=response_headers
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

@router.post(
    "/tools/call",
    response_model=None,
    responses={
        200: {
            "description": "Tool execution result",
            "content": {
                "application/json": {
                    "model": ToolExecutionResponse,
                    "example": {
                        "success": True,
                        "server_id": "12345",
                        "server_path": "/tavilysearch",
                        "tool_name": "tavily_search_mcp_tavily_search",
                        "result": {"data": "..."}
                    }
                },
                "text/event-stream": {
                    "example": "event: message\ndata: {...}\n\n"
                }
            }
        }
    }
)
async def execute_tool(
    body: ToolExecutionRequest,
    user_context: CurrentUser
) -> Union[Response, ToolExecutionResponse]:
    """
    Execute a tool on an MCP server.
    
    Request body:
    {
        "server_id": "12345",
        "server_path": "/tavilysearch",
        "tool_name": "tavily_search_mcp_tavily_search",
        "arguments": {
            "query": "Donald Trump news"
        }
    }
    
    Returns:
        - SSE stream (text/event-stream) if backend returns SSE format
        - JSON (ToolExecutionResponse) otherwise
    """
    tool_name = body.tool_name
    arguments = body.arguments
        
    username = user_context.get("username", "unknown")
    server = await server_service_v1.get_server_by_id(body.server_id)
    logger.info(
        f"🔧 Tool execution from user '{username}': {tool_name} on {body.server_id}"
    )
               
    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"Server not found: {body.server_id}"
        )
    config = server.config or {}   
    
    # Get target URL from server config
    proxy_pass_url = config.get("url")
    if not proxy_pass_url:
        raise HTTPException(
            status_code=500,
            detail="Server URL not configured"
        )
    
    # Ensure proxy_pass_url has trailing slash
    if not proxy_pass_url.endswith('/'):
        proxy_pass_url += '/'
        
    mcp_request_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "tavily_search",
            "arguments": arguments
        }
    }    
    try:
        # Build headers for tracking purpose
        headers = {
            "Content-Type": "application/json",
            "X-User": username,
            "X-Username": username,
            "X-Tool-Name": tool_name,
        }
        
        if config:
            decrypted_config = decrypt_auth_fields(config)
            auth_headers = _build_headers_for_server(decrypted_config)
            headers.update(auth_headers)
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                proxy_pass_url,
                json=mcp_request_body,
                headers=headers
            )
            response.raise_for_status()
            
            # Check content type or response format
            content_type = response.headers.get("content-type", "")
            response_text = response.text
            
            # If response is SSE format, return it directly as SSE
            if "text/event-stream" in content_type or response_text.startswith(("event:", "data:")):
                logger.info(f"✅ Returning SSE response for tool: {tool_name}")
                return Response(
                    content=response_text,
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no"
                    }
                )
            
            # Otherwise parse as JSON and return structured response
            result = response.json()
        
        logger.info(
            f"✅ Tool execution successful: {tool_name}"
        )
        
        return ToolExecutionResponse(
            success=True,
            server_id=body.server_id,
            server_path=server.path,
            tool_name=tool_name,
            result=result,
        )
        
    except httpx.HTTPError as e:
        logger.error(f"❌ Tool execution failed: {e}")
        
        return ToolExecutionResponse(
            success=False,
            server_id=body.server_id,
            server_path=server.path,
            tool_name=tool_name,
            error=f"HTTP error: {str(e)}",
        )


@router.post(
    "/resources/read",
    response_model=None,
    responses={
        200: {
            "description": "Resource read result",
            "content": {
                "application/json": {
                    "model": ResourceReadResponse,
                    "example": {
                        "success": True,
                        "server_id": "12345",
                        "server_path": "/tavilysearch",
                        "resource_uri": "tavily://search-results/AI",
                        "contents": [{"uri": "...", "mimeType": "...", "text": "..."}]
                    }
                }
            }
        }
    }
)
async def read_resource(
    body: ResourceReadRequest,
    user_context: CurrentUser
) -> Union[Response, ResourceReadResponse]:
    """
    Read/access an MCP resource.
    
    Request body:
    {
        "server_id": "12345",
        "resource_uri": "tavily://search-results/AI"
    }
    
    Returns:
        Resource contents (text, JSON, binary, etc.)
    """
    resource_uri = body.resource_uri
    username = user_context.get("username", "unknown")
    
    server = await server_service_v1.get_server_by_id(body.server_id)
    logger.info(
        f"📄 Resource read from user '{username}': {resource_uri} on {body.server_id}"
    )
    
    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"Server not found: {body.server_id}"
        )
    
    config = server.config or {}
    proxy_pass_url = config.get("url")
    
    if not proxy_pass_url:
        raise HTTPException(status_code=500, detail="Server URL not configured")
    
    if not proxy_pass_url.endswith('/'):
        proxy_pass_url += '/'
    
    # MOCK: Return hardcoded response for POC
    logger.info(f"✅ (MOCK) Returning cached search results for: {resource_uri}")
    
    return ResourceReadResponse(
        success=True,
        server_id=body.server_id,
        server_path=server.path,
        resource_uri=resource_uri,
        contents=[
            {
                "uri": resource_uri,
                "mimeType": "application/json",
                "text": '{"results": [{"title": "AI News", "snippet": "Latest AI developments..."}]}'
            }
        ]
    )


@router.post(
    "/prompts/execute",
    response_model=None,
    responses={
        200: {
            "description": "Prompt execution result",
            "content": {
                "application/json": {
                    "model": PromptExecutionResponse,
                    "example": {
                        "success": True,
                        "server_id": "12345",
                        "server_path": "/tavilysearch",
                        "prompt_name": "research_assistant",
                        "messages": [{"role": "...", "content": {...}}]
                    }
                }
            }
        }
    }
)
async def execute_prompt(
    body: PromptExecutionRequest,
    user_context: CurrentUser
) -> Union[Response, PromptExecutionResponse]:
    """
    Execute an MCP prompt (get prompt template with arguments filled in).
    
    Request body:
    {
        "server_id": "12345",
        "prompt_name": "research_assistant",
        "arguments": {
            "topic": "Artificial Intelligence",
            "depth": "comprehensive"
        }
    }
    
    Returns:
        Prompt messages ready for LLM consumption
    """
    prompt_name = body.prompt_name
    arguments = body.arguments or {}
    username = user_context.get("username", "unknown")
    
    server = await server_service_v1.get_server_by_id(body.server_id)
    logger.info(
        f"💬 Prompt execution from user '{username}': {prompt_name} on {body.server_id}"
    )
    
    if not server:
        raise HTTPException(
            status_code=404,
            detail=f"Server not found: {body.server_id}"
        )
    
    config = server.config or {}
    proxy_pass_url = config.get("url")
    
    if not proxy_pass_url:
        raise HTTPException(status_code=500, detail="Server URL not configured")
    
    if not proxy_pass_url.endswith('/'):
        proxy_pass_url += '/'
    
    # MOCK: Return hardcoded prompt response for POC
    topic = arguments.get("topic", "general topic")
    depth = arguments.get("depth", "basic")
    
    logger.info(f"✅ (MOCK) Returning prompt messages for: {prompt_name} (topic={topic}, depth={depth})")
    
    return PromptExecutionResponse(
        success=True,
        server_id=body.server_id,
        server_path=server.path,
        prompt_name=prompt_name,
        description=f"AI research assistant for {topic}",
        messages=[
            {
                "role": "system",
                "content": {
                    "type": "text",
                    "text": f"You are a research assistant specializing in {topic}. Provide {depth} analysis."
                }
            },
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": f"Research and analyze: {topic}"
                }
            }
        ]
    )


# ========== Catch-All Dynamic Proxy Route ==========
@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_mcp_proxy(request: Request, full_path: str):
    """
    Dynamic catch-all route for MCP server proxying.
    This replaces nginx {{LOCATION_BLOCKS}}.
    
    CRITICAL: This catch-all route matches ANY path pattern, so it must be defined LAST.
    FastAPI matches routes in order, so this will capture all unmatched routes.
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
    # Get auth context from middleware (already validated by AuthMiddleware)
    auth_context = getattr(request.state, "user", None)
    if not auth_context:
        logger.warning(f"Auth failed for {path}: No authentication context")
        raise HTTPException(status_code=401, detail="Authentication required")
    
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
    
    metrics.record_server_request(server_name=server.serverName)
    
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

