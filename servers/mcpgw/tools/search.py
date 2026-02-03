import logging
from collections.abc import Callable
from typing import Any

from core.registry import call_registry_api
from fastmcp import Context
from pydantic import Field

from config import settings

logger = logging.getLogger(__name__)


async def discover_tools_impl(
    query: str,
    top_n: int = 5,
    ctx: Context = None
) -> list[dict[str, Any]]:
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
        raise Exception(f"Tool discovery failed: {e!s}")


async def discover_servers_impl(
    query: str,
    top_n: int = 1,
    search_type: str = "hybrid",
    ctx: Context = None
) -> list[dict[str, Any]]:
    """
    🔍 Discover available MCP servers and their capabilities.
    
    This tool searches across all registered MCP servers to find servers matching your query.
    Returns comprehensive server information including tools, resources, and prompts.
    
    Args:
        query: Natural language description or keywords to search for servers
               (e.g., "github", "search engines", "database tools")
        top_n: Maximum number of servers to return (default: 1, optimized for token efficiency)
        search_type: Search strategy to use:
                    - "hybrid" (default): Combines semantic + keyword for best accuracy
                    - "near_text": Pure semantic/vector search (best for concept matching)
                    - "bm25": Pure keyword search (best for exact term matching)
                    - "similarity_store": Alternative similarity algorithm
        ctx: FastMCP context with user auth
    
    Returns:
        List of matching servers with their complete metadata:
        - serverName: Name of the server
        - path: Server path (e.g., '/github')
        - config: Server configuration including tools, resources, prompts
        - tags: Server tags for categorization
        - numTools: Number of tools available
    """


    logger.info(f"🔍 Discovering servers for query: '{query}' (search_type={search_type})")

    try:
        # Use centralized registry API call with automatic auth header extraction
        result = await call_registry_api(
            method="POST",
            endpoint=f"/api/{settings.API_VERSION}/search/servers",
            ctx=ctx,
            json={
                "query": query,
                "top_n": top_n,
                "search_type": search_type
            }
        )

        servers = result.get("servers", [])
        total = result.get("total", 0)

        logger.info(f"✅ Discovered {total} server(s) for query: '{query}'")

        return servers

    except Exception as e:
        logger.error(f"Server discovery failed: {e}")
        raise Exception(f"Server discovery failed: {e!s}")



# ============================================================================
# Tool Factory Functions for Registration
# ============================================================================

def get_tools() -> list[tuple[str, Callable]]:
    """
    Export tools for registration in server.py.
    
    Returns:
        List of (tool_name, tool_function) tuples ready for registration
    """

    # Define tool wrapper functions with proper signatures and decorators
    async def discover_tools(
        query: str = Field(..., description="Natural language description of what you want to accomplish (e.g., 'find latest news', 'search GitHub repositories', 'get weather data', 'analyze code')"),
        top_n: int = Field(5, description="Maximum number of tools to return (default: 5)"),
        ctx: Context | None = None
    ) -> list[dict[str, Any]]:
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
        top_n: int = Field(1, description="Maximum number of servers to return (default: 1, optimized for token efficiency)"),
        search_type: str = Field("hybrid", description="Search strategy: 'hybrid' (semantic+keyword, best overall), 'near_text' (pure semantic/vector), 'bm25' (pure keyword), or 'similarity_store' (alternative)"),
        ctx: Context | None = None
    ) -> list[dict[str, Any]]:
        """
        🔍 Discover available MCP servers using semantic search with multiple search strategies.

        **When to use:**
        - User asks "what can you do?" or "what services are available?"
        - Exploring capabilities before finding specific tools
        - User mentions a service category (web search, code management, productivity)
        - Need to understand server capabilities and available tools

        **Search Type Strategies:**
        The tool supports 4 different search algorithms - try different ones if results aren't optimal:
        
        1. **"hybrid" (default, recommended)** - Combines semantic + keyword search
           - Best for: General queries, balanced accuracy
           - Example: "web search news" → finds Tavily, web search servers
           - Uses AI reranking for highest precision
        
        2. **"near_text"** - Pure semantic/vector search
           - Best for: Concept matching, related functionality
           - Example: "find information online" → matches search engines semantically
           - Understands intent even with different wording
        
        3. **"bm25"** - Pure keyword/lexical search
           - Best for: Exact term matching, specific names
           - Example: "github" → finds servers with "github" in name/description
           - Fast and deterministic
        
        4. **"similarity_store"** - Alternative similarity algorithm
           - Best for: Alternative ranking when other methods fail
           - Experimental alternative approach

        **Query Tips for Best Results:**
        - Use descriptive phrases: "web search and news" (not just "search")
        - Specify use case: "code repository management", "email automation"
        - Include domain keywords: "productivity", "development", "communication"
        - Leave empty ("") to browse all available servers
        - Try different search_type values if results aren't what you expect

        **Example Queries:**
        - "" (empty) → Returns ALL available servers (browsing mode)
        - "web search real-time news" → Finds Tavily, web search servers
        - "github code repository" → Finds GitHub Copilot server
        - "email calendar productivity" → Finds Google Workspace server
        - "cloud infrastructure AWS" → Finds AWS-related servers
        - "database operations" → Finds database integration servers

        **Token Optimization:**
        - Default top_n=1 to reduce response size (servers contain many tools)
        - Increase top_n only if you need to compare multiple servers
        - Each server includes full tool/resource/prompt definitions

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
        return await discover_servers_impl(query, top_n, search_type, ctx)

    return [
        # ("discover_tools", discover_tools),
        ("discover_servers", discover_servers),
    ]
