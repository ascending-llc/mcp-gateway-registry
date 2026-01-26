import logging
from typing import Dict, Any, Optional, List, Callable, Tuple
from fastmcp import Context
from pydantic import Field
from core.registry import call_registry_api
from search import vector_search_service

logger = logging.getLogger(__name__)


async def discover_tools_impl(
    query: str,
    top_n: int = 5,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    🔍 Discover available tools to accomplish any user request.
    
    This tool searches across all registered MCP servers to find the best tools for the job.
    After discovering tools, use execute_tool to actually run the selected tool.
    
    Args:
        query: Natural language description of the user's request or task
               (e.g., "search for news", "get GitHub data", "find information about X")
        top_n: Maximum number of tools to return (default: 5)
        ctx: FastMCP context with user auth
    
    Returns:
        List of matching tools with their metadata, including:
        - tool_name: Exact name to use with execute_tool
        - server_path: Server location for the tool
        - description: What the tool does
        - input_schema: Required and optional parameters
        - discovery_score: Relevance score (0.0-1.0)
    """
    from config import settings

    logger.info(f"🔍 Discovering tools for query: '{query}'")

    try:
        # Use centralized registry API call with automatic auth header extraction
        result = await call_registry_api(
            method="POST",
            endpoint=f"/api/{settings.API_VERSION}/search/tools",
            ctx=ctx,
            json={
                "query": query,
                "top_n": top_n
            }
        )

        matches = result.get("matches", [])
        total = result.get("total_matches", 0)

        logger.info(f"✅ Discovered {total} tool(s) for query: '{query}'")

        return matches

    except Exception as e:
        logger.error(f"Tool discovery failed: {e}")
        raise Exception(f"Tool discovery failed: {str(e)}")


async def discover_servers_impl(
    query: str,
    top_n: int = 10,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    🔍 Discover available MCP servers and their capabilities.
    
    This tool searches across all registered MCP servers to find servers matching your query.
    Returns comprehensive server information including tools, resources, and prompts.
    
    Args:
        query: Natural language description or keywords to search for servers
               (e.g., "github", "search engines", "database tools")
        top_n: Maximum number of servers to return (default: 10)
        ctx: FastMCP context with user auth
    
    Returns:
        List of matching servers with their complete metadata:
        - serverName: Name of the server
        - path: Server path (e.g., '/github')
        - config: Server configuration including tools, resources, prompts
        - tags: Server tags for categorization
        - numTools: Number of tools available
    """
    from config import settings

    logger.info(f"🔍 Discovering servers for query: '{query}'")

    try:
        # Use centralized registry API call with automatic auth header extraction
        result = await call_registry_api(
            method="POST",
            endpoint=f"/api/{settings.API_VERSION}/search/servers",
            ctx=ctx,
            json={
                "query": query,
                "top_n": top_n
            }
        )

        servers = result.get("servers", [])
        total = result.get("total", 0)

        logger.info(f"✅ Discovered {total} server(s) for query: '{query}'")

        return servers

    except Exception as e:
        logger.error(f"Server discovery failed: {e}")
        raise Exception(f"Server discovery failed: {str(e)}")



# ============================================================================
# Tool Factory Functions for Registration
# ============================================================================

def get_tools() -> List[Tuple[str, Callable]]:
    """
    Export tools for registration in server.py.
    
    Returns:
        List of (tool_name, tool_function) tuples ready for registration
    """

    # Define tool wrapper functions with proper signatures and decorators
    async def discover_tools(
        query: str = Field(..., description="What you want to accomplish (e.g., 'search for current news', 'get weather data', 'analyze GitHub repos')"),
        top_n: int = Field(5, description="Maximum number of tools to return (default: 5)"),
        ctx: Optional[Context] = None
    ) -> List[Dict[str, Any]]:
        """
        🔍 AUTO-USE: Find and discover tools to accomplish any task.

        **When to use this tool:**
        - User asks for current information, news, or web search
        - User needs data from external services (GitHub, databases, APIs)
        - User requests functionality you don't have built-in
        - You're unsure if a tool exists for a task

        **Examples of queries:**
        - "search web" or "search news" → Finds web search tools (Tavily)
        - "github pull requests" → Finds GitHub-related tools
        - "weather information" → Finds weather tools
        - "analyze code" → Finds code analysis tools

        **After discovering tools:**
        Use execute_tool with the discovered tool_name and server_path.

        **Returns:** List of tools with:
        - tool_name: Name to use with execute_tool
        - server_path: Server location (e.g., '/tavilysearch')
        - description: What the tool does
        - input_schema: Required parameters
        - discovery_score: Relevance score (0.0-1.0)

        ⚠️ Use this proactively when users ask questions requiring external data!
        """
        return await discover_tools_impl(query, top_n, ctx)

    async def discover_servers(
        query: str = Field("", description="Keywords to filter servers (e.g., 'github', 'search', 'database') - leave empty to see all servers"),
        top_n: int = Field(10, description="Maximum number of servers to return (default: 10)"),
        ctx: Optional[Context] = None
    ) -> List[Dict[str, Any]]:
        """
        🔍 Discover available MCP servers with complete capabilities.

        **When to use:**
        - User asks "what can you do?" or "what services do you have?"
        - You want to see all available tools, resources, and prompts
        - User mentions a service by name (e.g., "GitHub", "Tavily")

        **Query examples:**
        - "" (empty) → Returns ALL available servers
        - "search" → Finds search-related servers (Tavily, etc.)
        - "github" → Finds GitHub integration servers
        - "database" → Finds database servers

        **Returns:** Comprehensive server information:
        - serverName: Display name
        - path: Server routing path (e.g., '/tavilysearch')
        - config.toolFunctions: All available tools with full schemas
        - config.resources: Available resources (URIs, caches, etc.)
        - config.prompts: Pre-configured prompts
        - tags: Categorization tags
        - numTools: Total tool count

        Use this when you need a comprehensive view of available services.

        Examples:
        - 'github' - Find GitHub-related servers
        - 'search engines' - Find search and web scraping servers
        - 'database' - Find database integration servers

        Returns:
            List of discovered servers with complete metadata:
            - serverName: Display name of the server
            - path: Server path for routing (e.g., '/github')
            - config: Full configuration including:
              * toolFunctions: All available tools with schemas
              * resources: Available resources (URIs, cache, etc.)
              * prompts: Pre-configured prompts
              * capabilities: Server capabilities (tools, resources, prompts)
            - tags: Categorization tags
            - numTools: Total number of tools
            - status: Server status (active/inactive)
        """
        return await discover_servers_impl(query, top_n, ctx)

    return [
        # ("discover_tools", discover_tools),
        ("discover_servers", discover_servers),
        # ("intelligent_tool_finder", intelligent_tool_finder),
    ]
