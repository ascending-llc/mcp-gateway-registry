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


async def intelligent_tool_finder_impl(
        natural_language_query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        top_k_services: int = 3,
        top_n_tools: int = 1,
        ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Finds the most relevant MCP tool(s) across all registered and enabled services
    based on a natural language query and/or tag filtering, using semantic search.
    """
    # Extract user scopes from headers
    user_scopes = []
    if  hasattr(ctx,"user_auth"):
        user_scopes: List[str] = ctx.user_auth.get('scopes', [])
    try:
        results = await vector_search_service.search_tools(
            query=natural_language_query,
            tags=tags,
            user_scopes=user_scopes,
            top_k_services=top_k_services,
            top_n_tools=top_n_tools
        )
        logger.info(f"intelligent_tool_finder returned {len(results)} tools")
        return results
    except Exception as e:
        logger.error(f"Error in intelligent_tool_finder: {e}", exc_info=True)
        raise Exception(f"Tool search failed: {str(e)}")


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
    
    # async def intelligent_tool_finder(
    #     natural_language_query: Optional[str] = Field(None, description="Your query in natural language describing the task you want to perform. Optional if tags are provided."),
    #     tags: Optional[List[str]] = Field(None, description="List of tags to filter tools by using AND logic. IMPORTANT: AI agents should ONLY use this if the user explicitly provides specific tags. DO NOT infer tags - incorrect tags will exclude valid results."),
    #     top_k_services: int = Field(3, description="Number of top services to consider from initial FAISS search (ignored if only tags provided)."),
    #     top_n_tools: int = Field(1, description="Number of best matching tools to return."),
    #     ctx: Optional[Context] = None
    # ) -> List[Dict[str, Any]]:
    #     """
    #     Finds the most relevant MCP tool(s) across all registered and enabled services
    #     based on a natural language query and/or tag filtering, using semantic search.

    #     IMPORTANT FOR AI AGENTS:
    #     - Only fill in the 'tags' parameter if the user explicitly provides specific tags to filter by
    #     - DO NOT infer or guess tags from the natural language query
    #     - Tags act as a strict filter - incorrect tags will exclude valid results
    #     - When tags are provided with a query, results must match BOTH the semantic search AND all tags
    #     - If unsure about tags, use natural_language_query alone for best results
        
    #     Args:
    #         natural_language_query: The user's natural language query. Optional if tags are provided.
    #         tags: List of tags to filter by using AND logic. All tags must match a server's tags for its tools to be included.
    #               CAUTION: Only use this parameter if explicitly provided by the user. Incorrect tags will filter out valid results.
    #         top_k_services: How many top-matching services to analyze for tools from search (ignored if only tags provided).
    #         top_n_tools: How many best tools to return from the combined list.
    #         ctx: Optional context to pass to services_mgmt as an argument.

    #     Returns:
    #         A list of dictionaries, each describing a recommended tool, its parent service, and similarity score (if semantic search used).

    #     Examples:
    #         # Semantic search only (RECOMMENDED for AI agents unless user specifies tags)
    #         tools = await intelligent_tool_finder(natural_language_query="find files", top_n_tools=5)

    #         # Semantic search + tag filtering (ONLY use when user explicitly provides tags)
    #         tools = await intelligent_tool_finder(
    #             natural_language_query="find files",
    #             tags=["file-system", "search"],  # User explicitly said: "use tags file-system and search"
    #             top_n_tools=5
    #         )

    #         # Pure tag-based filtering (ONLY when user provides tags without a query)
    #         tools = await intelligent_tool_finder(tags=["database", "analytics"], top_n_tools=10)
    #     """
    #     return await intelligent_tool_finder_impl(natural_language_query, tags, top_k_services, top_n_tools, ctx)
    
    # Return list of (name, function) tuples
    return [
        # ("discover_tools", discover_tools),
        ("discover_servers", discover_servers),
        # ("intelligent_tool_finder", intelligent_tool_finder),
    ]
