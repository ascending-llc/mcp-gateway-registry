"""
MCP Gateway Registry API Tools
- execute_tool: Execute tools from any MCP server
- read_resource: Read/access resources from any MCP server
- execute_prompt: Execute prompts from any MCP server
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
    Execute a specific tool that was discovered.
    
    Args:
        server_id: server ID from discovery (e.g., '6972e222755441652c23090f')
        server_path: Server path from discovery (e.g., '/github')
        tool_name: Exact tool name from discovery
        arguments: Tool-specific arguments as key-value pairs
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

async def read_resource_impl(
    server_id: str,
    resource_uri: str,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Read/access a resource from an MCP server.
    
    Args:
        server_id: Server ID from discovery
        resource_uri: Resource URI to read (e.g., 'tavily://search-results/AI')
        ctx: FastMCP context with user auth
    
    Returns:
        Resource contents (text, JSON, binary, etc.)
    
    Example:
        result = await read_resource_impl(
            server_id="6972e222755441652c23090f",
            resource_uri="tavily://search-results/AI"
        )
    """
    logger.info(f"📄 Reading resource: {resource_uri} from server {server_id}")
    
    try:
        # Build request payload
        payload = {
            "server_id": server_id,
            "resource_uri": resource_uri
        }
        
        # Use centralized registry API call with automatic auth header extraction
        result = await call_registry_api(
            method="POST",
            endpoint="/proxy/resources/read",
            ctx=ctx,
            json=payload
        )
        
        logger.info(f"✅ Resource read successful: {resource_uri}")
        return result
            
    except Exception as e:
        logger.error(f"❌ Resource read failed: {e}")
        raise Exception(f"Resource read failed: {str(e)}")


async def execute_prompt_impl(
    server_id: str,
    prompt_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Execute a prompt from an MCP server.
    
    Args:
        server_id: Server ID from discovery
        prompt_name: Name of the prompt to execute
        arguments: Optional prompt arguments
        ctx: FastMCP context with user auth
    
    Returns:
        Prompt messages ready for LLM consumption
    
    Example:
        result = await execute_prompt_impl(
            server_id="6972e222755441652c23090f",
            prompt_name="research_assistant",
            arguments={
                "topic": "Artificial Intelligence",
                "depth": "comprehensive"
            }
        )
    """
    logger.info(f"💬 Executing prompt: {prompt_name} on server {server_id}")
    
    try:
        # Build request payload
        payload = {
            "server_id": server_id,
            "prompt_name": prompt_name,
            "arguments": arguments or {}
        }
        
        # Use centralized registry API call with automatic auth header extraction
        result = await call_registry_api(
            method="POST",
            endpoint="/proxy/prompts/execute",
            ctx=ctx,
            json=payload
        )
        
        logger.info(f"✅ Prompt execution successful: {prompt_name}")
        return result
            
    except Exception as e:
        logger.error(f"❌ Prompt execution failed: {e}")
        raise Exception(f"Prompt execution failed: {str(e)}")


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
        server_path: str = Field(..., description="Server path from discovery (e.g., '/tavilysearch' for web search)"),
        tool_name: str = Field(..., description="Exact tool name from discovery (e.g., 'tavily_search')"),
        arguments: Dict[str, Any] = Field(..., description="Tool parameters from input_schema"),
        server_id: str = Field(..., description="Server ID from discovery"),
        ctx: Optional[Context] = None
    ) -> Dict[str, Any]:
        """
        🚀 AUTO-USE: Execute any discovered tool to get real-time data.

        **Common use cases:**
        - Web search: execute_tool(server_path="/tavilysearch", tool_name="tavily_search", arguments={"query": "..."})
        - Extract URLs: execute_tool(server_path="/tavilysearch", tool_name="tavily_extract", arguments={"urls": [...]})
        - GitHub operations: execute_tool(server_path="/github", tool_name="search_pull_requests", arguments={...})

        **Workflow:**
        1. Use discover_tools to find the right tool
        2. Use execute_tool with the discovered server_path and tool_name
        3. Pass arguments according to the tool's input_schema

        **Example for web search:**
        ```
        # User asks: "What's the latest news about AI?"
        result = execute_tool(
            server_path="/tavilysearch",
            tool_name="tavily_search",
            arguments={"query": "latest AI news", "max_results": 5},
            server_id="6972e222755441652c23090f"
        )
        ```

        ⚠️ Always use this AFTER discover_tools to execute the actual functionality.
        Returns: Tool-specific results (format varies by tool)
        """
        return await execute_tool_impl(server_path, tool_name, arguments, server_id, ctx)
    
    async def read_resource(
        server_id: str = Field(..., description="Server ID from discover_servers (e.g., '6972e222755441652c23090f')"),
        resource_uri: str = Field(..., description="Resource URI to read (e.g., 'tavily://search-results/AI', 'file:///path/to/data')"),
        ctx: Optional[Context] = None
    ) -> Dict[str, Any]:
        """
        📄 Read/access resources from any MCP server.

        **What are resources?**
        Resources are data sources, caches, URIs, or file-like objects exposed by MCP servers.
        Examples: cached search results, configuration files, data streams, API responses.

        **Common use cases:**
        - Access cached data: read_resource(server_id="...", resource_uri="tavily://search-results/AI")
        - Read configuration: read_resource(server_id="...", resource_uri="config://settings")
        - Access files: read_resource(server_id="...", resource_uri="file:///data/export.json")

        **Workflow:**
        1. Use discover_servers to find servers with resources
        2. Review the resources array in server config
        3. Use read_resource with the resource URI

        **Example:**
        ```
        # Discover servers with resources
        servers = discover_servers(query="search")
        
        # Find a resource URI from server config
        resource = servers[0]["config"]["resources"][0]["uri"]
        
        # Read the resource
        data = read_resource(
            server_id=servers[0]["_id"],
            resource_uri=resource
        )
        ```

        Returns: Resource contents (format varies: text, JSON, binary, etc.)
        """
        return await read_resource_impl(server_id, resource_uri, ctx)
    
    async def execute_prompt(
        server_id: str = Field(..., description="Server ID from discover_servers"),
        prompt_name: str = Field(..., description="Name of the prompt to execute (e.g., 'research_assistant', 'fact_checker')"),
        arguments: Optional[Dict[str, Any]] = Field(None, description="Prompt arguments as key-value pairs"),
        ctx: Optional[Context] = None
    ) -> Dict[str, Any]:
        """
        💬 Execute prompts from any MCP server.

        **What are prompts?**
        Prompts are pre-configured, reusable prompt templates provided by MCP servers.
        They help standardize complex workflows and provide expert guidance.

        **Common use cases:**
        - Research workflows: execute_prompt(server_id="...", prompt_name="research_assistant", arguments={"topic": "AI"})
        - Fact checking: execute_prompt(server_id="...", prompt_name="fact_checker", arguments={"claim": "..."})
        - Code review: execute_prompt(server_id="...", prompt_name="code_reviewer", arguments={"language": "python"})

        **Workflow:**
        1. Use discover_servers to find servers with prompts
        2. Review the prompts array in server config
        3. Use execute_prompt with required arguments

        **Example:**
        ```
        # Discover servers with prompts
        servers = discover_servers(query="research")
        
        # Find available prompts
        prompts = servers[0]["config"]["prompts"]
        
        # Execute a prompt
        result = execute_prompt(
            server_id=servers[0]["_id"],
            prompt_name="research_assistant",
            arguments={"topic": "Quantum Computing", "depth": "advanced"}
        )
        
        # Result contains messages ready for LLM
        messages = result["messages"]
        ```

        Returns: Prompt messages ready for LLM consumption (role, content pairs)
        """
        return await execute_prompt_impl(server_id, prompt_name, arguments, ctx)
    
    # Return list of (name, function) tuples
    return [
        ("execute_tool", execute_tool),
        ("read_resource", read_resource),
        ("execute_prompt", execute_prompt),
    ]

