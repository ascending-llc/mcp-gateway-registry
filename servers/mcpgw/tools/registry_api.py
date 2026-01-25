"""
Two-Phase Tool Discovery & Execution for Claude
Phase 1: discover_tools - Find available tools
Phase 2: execute_tool - Execute a specific discovered tool
"""

import logging
from typing import Any, Dict, List, Optional, Callable, Tuple
from fastmcp import Context
from pydantic import Field
from core.registry import call_registry_api

logger = logging.getLogger(__name__)


async def execute_tool_impl(
    server_path: str,
    tool_name: str,
    arguments: Dict[str, Any],
    server_id: Optional[str] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Phase 2: Execute a specific tool that was discovered.
    
    Args:
        server_path: Server path from discovery (e.g., '/github')
        tool_name: Exact tool name from discovery
        arguments: Tool-specific arguments as key-value pairs
        server_id: Optional server ID from discovery (e.g., '6972e222755441652c23090f')
        ctx: FastMCP context with user auth
    
    Returns:
        Tool execution result
    
    Example:
        result = await execute_tool_impl(
            server_path="/github",
            tool_name="search_pull_requests",
            arguments={
                "owner": "agentic-community",
                "repo": "mcp-gateway-registry",
                "state": "open"
            },
            server_id="6972e222755441652c23090f"
        )
    """
    logger.info(f"🔧 Executing tool: {tool_name} on {server_path}" + (f" (server_id: {server_id})" if server_id else ""))
    
    try:
        # Build request payload
        payload = {
            "server_path": server_path,
            "tool_name": tool_name,
            "arguments": arguments
        }
        if server_id:
            payload["server_id"] = server_id
        
        # Use centralized registry API call with automatic auth header extraction
        result = await call_registry_api(
            method="POST",
            endpoint="/proxy/tools/call",
            ctx=ctx,
            json=payload
        )
        
        logger.info(f"✅ Tool execution successful: {tool_name}")
        return result
            
    except Exception as e:
        logger.error(f"❌ Tool execution failed: {e}")
        raise Exception(f"Tool execution failed: {str(e)}")


# ============================================================================
# Tool Factory Functions for Registration
# ============================================================================

def get_tools() -> List[Tuple[str, Callable]]:
    """
    Export tools for registration in server.py.
    
    Returns:
        List of (tool_name, tool_function) tuples ready for registration
    """
    
    # Define tool wrapper function with proper signature and decorators
    async def execute_tool(
        server_path: str = Field(..., description="Server path from discovery (e.g., '/github')"),
        tool_name: str = Field(..., description="Exact tool name from discovery (e.g., 'search_pull_requests')"),
        arguments: Dict[str, Any] = Field(..., description="Tool-specific arguments as key-value pairs"),
        server_id: Optional[str] = Field(None, description="Optional server ID from discovery (e.g., '123412346972e222755441652c23090f')"),
        ctx: Optional[Context] = None
    ) -> Dict[str, Any]:
        """
        🔧 Execute a specific tool that you discovered.
        You must provide the exact server_path and tool_name from discovery results.
        Optionally provide server_id for more specific routing.

        Required fields:
        - server_path: The server path (e.g., '/github')
        - tool_name: The exact tool name (e.g., 'search_pull_requests')
        - arguments: Tool-specific arguments as a JSON object

        Optional fields:
        - server_id: The server ID (e.g., '6972e222755441652c23090f')

        Example:
            result = execute_tool(
                server_path="/github",
                tool_name="search_pull_requests",
                arguments={
                    "owner": "agentic-community",
                    "repo": "mcp-gateway-registry",
                    "state": "open"
                },
                server_id="6972e222755441652c23090f"  # Optional
            )

        Returns:
            Tool execution result (format depends on the tool)
        """
        return await execute_tool_impl(server_path, tool_name, arguments, server_id, ctx)
    
    # Return list of (name, function) tuples
    return [
        ("execute_tool", execute_tool),
    ]

