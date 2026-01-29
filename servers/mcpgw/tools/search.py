import logging
from typing import Dict, Any, Optional, List, Callable, Tuple
from fastmcp import Context
from pydantic import Field
from core.registry import call_registry_api

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
        query: str = Field(..., description="Natural language description of what you want to accomplish (e.g., 'find latest news', 'search GitHub repositories', 'get weather data', 'analyze code')"),
        top_n: int = Field(5, description="Maximum number of tools to return (default: 5)"),
        ctx: Optional[Context] = None
    ) -> List[Dict[str, Any]]:
        """
        🔍 AUTO-USE: Discover tools to accomplish any task using semantic search.

        **When to use this tool:**
        - User asks for current information, news, or real-time data
        - User needs web search, research, or fact-checking
        - User requests GitHub operations (repos, PRs, issues, code)
        - User needs email, calendar, or productivity features
        - User wants database operations or cloud services
        - Any request requiring external services or APIs

        **Query Tips for Best Results:**
        - Use descriptive phrases: "find latest news about AI" (not just "news")
        - Include action verbs: "search", "find", "get", "create", "update"
        - Specify domain: "GitHub pull requests", "web search", "calendar events"
        - Be specific about intent: "search for Donald Trump news" vs "news"

        **Example Queries:**
        - "search web for current events" → Finds Tavily search tools
        - "find latest news articles" → Finds web search and research tools
        - "manage GitHub pull requests" → Finds GitHub PR management tools
        - "schedule calendar meeting" → Finds Google Calendar tools
        - "send email message" → Finds Gmail/email tools
        - "analyze code repository" → Finds GitHub code analysis tools

        **Search Technology:**
        Uses hybrid semantic + keyword search with AI reranking for high precision.
        Matches your query against tool descriptions, names, and capabilities.

        **After discovering tools:**
        Use execute_tool with the discovered tool_name and server_path.

        **Returns:** List of tools with:
        - tool_name: Name to use with execute_tool
        - server_path: Server location (e.g., '/tavilysearch', '/github-copilot')
        - description: What the tool does
        - input_schema: Required and optional parameters
        - discovery_score: Relevance score (0.0-1.0, higher is better)

        ⚠️ ALWAYS use this proactively when users ask questions requiring external data or real-time information!
        """
        return await discover_tools_impl(query, top_n, ctx)

    async def discover_servers(
        query: str = Field("", description="Natural language query or keywords to find servers (e.g., 'web search', 'github integration', 'productivity tools', 'email and calendar') - leave empty to see all servers"),
        top_n: int = Field(3, description="Maximum number of servers to return (default: 3)"),
        ctx: Optional[Context] = None
    ) -> List[Dict[str, Any]]:
        """
        🔍 Discover available MCP servers using semantic search.

        **When to use:**
        - User asks "what can you do?" or "what services are available?"
        - Exploring capabilities before finding specific tools
        - User mentions a service category (web search, code management, productivity)
        - Need to understand server capabilities and available tools

        **Query Tips for Best Results:**
        - Use descriptive phrases: "web search and news" (not just "search")
        - Specify use case: "code repository management", "email automation"
        - Include domain keywords: "productivity", "development", "communication"
        - Leave empty ("") to browse all available servers

        **Example Queries:**
        - "" (empty) → Returns ALL available servers (browsing mode)
        - "web search real-time news" → Finds Tavily, web search servers
        - "github code repository" → Finds GitHub Copilot server
        - "email calendar productivity" → Finds Google Workspace server
        - "cloud infrastructure AWS" → Finds AWS-related servers
        - "database operations" → Finds database integration servers

        **Search Technology:**
        Uses hybrid semantic + keyword search with AI reranking.
        Searches server descriptions, tags, tool names, and capabilities.

        **Key Differences from discover_tools:**
        - discover_servers: Browse server catalogs and capabilities (broader)
        - discover_tools: Find specific tools for immediate tasks (narrower)
        
        Use discover_tools when you know what task to accomplish.
        Use discover_servers when exploring what's available.

        **Returns:** Comprehensive server information:
        - serverName: Display name (e.g., "github-copilot", "travily")
        - path: Server routing path (e.g., '/github-copilot', '/tavilysearch')
        - description: What the server does (rich semantic description)
        - tags: Categorization tags (e.g., ["search", "web", "news"])
        - numTools: Total number of tools available
        - config.toolFunctions: All tools with full schemas
        - config.tools: Comma-separated tool names
        - config.resources: Available resources (URIs, caches)
        - config.prompts: Pre-configured prompts
        - status: Server status (active/inactive)

        **Pro Tip:** After discovering servers, use discover_tools with specific
        task descriptions to find the exact tool you need to execute.
        """
        return await discover_servers_impl(query, top_n, ctx)

    return [
        # ("discover_tools", discover_tools),
        ("discover_servers", discover_servers),
        # ("intelligent_tool_finder", intelligent_tool_finder),
    ]
