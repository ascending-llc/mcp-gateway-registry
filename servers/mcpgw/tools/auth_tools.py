"""
Authentication debugging tools.

These tools help developers and administrators debug authentication context
and HTTP request information.
"""

import logging
import asyncio
from typing import Dict, Any
from fastmcp.server.dependencies import get_http_request
from core.auth import log_auth_context
from fastmcp import Context

logger = logging.getLogger(__name__)


async def debug_auth_context_impl(ctx: Context = None) -> Dict[str, Any]:
    """
    Debug tool to explore what authentication context is available.
    This tool helps understand what auth information can be accessed through the MCP Context.
    
    Returns:
        Dict[str, Any]: Detailed debug information about available auth context
    """
    if not ctx:
        return {"error": "No context available"}

    debug_info = {
        "context_type": type(ctx).__name__,
        "available_attributes": sorted([attr for attr in dir(ctx) if not attr.startswith('_')]),
        "context_properties": {}
    }

    # Try to access each property safely
    for prop in ['client_id', 'request_id', 'session', 'request_context', 'fastmcp']:
        try:
            value = getattr(ctx, prop, "NOT_AVAILABLE")
            if value == "NOT_AVAILABLE":
                debug_info["context_properties"][prop] = "NOT_AVAILABLE"
            elif value is None:
                debug_info["context_properties"][prop] = "None"
            else:
                debug_info["context_properties"][prop] = {
                    "type": type(value).__name__,
                    "available": True
                }

                # For session, explore further
                if prop == "session" and value:
                    session_attrs = [attr for attr in dir(value) if not attr.startswith('_')]
                    debug_info["context_properties"][prop]["attributes"] = session_attrs[:20]

                    # Check for transport
                    if hasattr(value, 'transport') and value.transport:
                        transport = value.transport
                        transport_attrs = [attr for attr in dir(transport) if not attr.startswith('_')]
                        debug_info["context_properties"][prop]["transport"] = {
                            "type": type(transport).__name__,
                            "attributes": transport_attrs[:20]
                        }

                # For request_context, explore further
                if prop == "request_context" and value:
                    rc_attrs = [attr for attr in dir(value) if not attr.startswith('_')]
                    debug_info["context_properties"][prop]["attributes"] = rc_attrs[:20]

                    if hasattr(value, 'meta') and value.meta:
                        meta = value.meta
                        meta_attrs = [attr for attr in dir(meta) if not attr.startswith('_')]
                        debug_info["context_properties"][prop]["meta"] = {
                            "type": type(meta).__name__,
                            "attributes": meta_attrs[:20]
                        }

        except Exception as e:
            debug_info["context_properties"][prop] = f"ERROR: {str(e)}"

    # Log the full auth context
    auth_context = await log_auth_context("debug_auth_context", ctx)
    debug_info["extracted_auth_context"] = auth_context

    return debug_info


async def get_http_headers_impl(ctx: Context) -> Dict[str, Any]:
    """
    FastMCP 2.0 tool to access HTTP headers directly.
    This tool demonstrates how to get HTTP request information including auth headers.
    
    Returns:
        Dict[str, Any]: HTTP request information including headers
    """
    if not ctx:
        return {"error": "No context available"}

    result = {
        "fastmcp_version": "2.0",
        "tool_name": "get_http_headers",
        "timestamp": str(asyncio.get_event_loop().time())
    }

    try:
        http_request = get_http_request()

        if http_request:
            all_headers = dict(http_request.headers)
            auth_headers = {}
            other_headers = {}

            for key, value in all_headers.items():
                key_lower = key.lower()
                if key_lower in ['authorization', 'x-user-pool-id', 'x-client-id',
                                 'x-region', 'cookie', 'x-api-key']:
                    if key_lower == 'authorization':
                        if value.startswith('Bearer '):
                            auth_headers[key] = f"Bearer <TOKEN_HIDDEN> (length: {len(value)})"
                        else:
                            auth_headers[key] = f"<AUTH_HIDDEN> (length: {len(value)})"
                    elif key_lower == 'cookie':
                        cookies = [c.split('=')[0] for c in value.split(';')]
                        auth_headers[key] = f"Cookies: {', '.join(cookies)}"
                    else:
                        auth_headers[key] = value
                else:
                    other_headers[key] = value

            result.update({
                "http_request_available": True,
                "method": http_request.method,
                "url": str(http_request.url),
                "path": http_request.url.path,
                "query_params": dict(http_request.query_params),
                "client_info": {
                    "host": http_request.client.host if http_request.client else "Unknown",
                    "port": http_request.client.port if http_request.client else "Unknown"
                },
                "auth_headers": auth_headers,
                "other_headers": other_headers,
                "total_headers_count": len(all_headers)
            })

            await ctx.info(f"🔐 HTTP Headers Debug - Auth Headers Found: {list(auth_headers.keys())}")
        else:
            result.update({
                "http_request_available": False,
                "error": "No HTTP request context available"
            })
            await ctx.warning("No HTTP request context available - may be running in non-HTTP transport mode")

    except RuntimeError as e:
        result.update({
            "http_request_available": False,
            "error": f"Not in HTTP context: {str(e)}",
            "transport_mode": "Likely STDIO or other non-HTTP transport"
        })
        await ctx.info(f"Not in HTTP context - this is expected for STDIO transport: {e}")

    except Exception as e:
        result.update({
            "http_request_available": False,
            "error": f"Error accessing HTTP request: {str(e)}"
        })
        await ctx.error(f"Error accessing HTTP request: {e}")
        logger.error(f"Error in get_http_headers: {e}", exc_info=True)

    return result
