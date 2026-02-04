#!/usr/bin/env python3
import logging
from fastmcp import FastMCP
from starlette.responses import JSONResponse
from auth.custom_jwt import jwtVerifier
from auth.middleware import HeaderSwapMiddleware, AuthMiddleware
from config import parse_arguments, settings
from tools import registry_api, search

# Configure logging
logger = logging.getLogger(__name__)


def create_mcp_app() -> FastMCP:
    """
    Factory function to create a stateless FastMCP application instance.
    
    Returns:
        Configured FastMCP application instance
    """
    mcp = FastMCP(
        "RegistryGateway",
        auth=jwtVerifier,  # JWT verifier (requires middleware to swap headers if using custom header)
        instructions="""This MCP Gateway provides unified access to 100+ MCP servers, tools, resources, and prompts through a centralized discovery and execution interface.

KEY CAPABILITIES:
- 🔍 Discover any tool, resource, or prompt across all registered MCP servers
- 🚀 Execute tools from any MCP server through unified proxy
- 📚 Access resources (URIs, caches, data sources) from any server
- 💬 Use prompts from any server for specialized workflows
- 🎯 Automatic routing, authentication, and execution

CRITICAL RULE - ALWAYS USE DISCOVERY FIRST:
⚠️ MANDATORY: If you don't have a suitable tool for the user's request, you MUST use discover_tools or discover_servers to find one.
⚠️ NEVER respond with "I don't have the capability" without first attempting discovery.
⚠️ The gateway provides access to 100+ specialized tools - they must be discovered before use.

WHEN TO USE DISCOVERY TOOLS:
✓ User needs external/real-time data (news, weather, stock prices, current events)
✓ User asks "what can you do?" → Use discover_servers to show all available services
✓ User mentions specific services (GitHub, databases, APIs, search engines)
✓ User requests functionality you don't have built-in → ALWAYS try discover_tools first
✓ You encounter a task requiring specialized tools → discover_tools before saying "I can't"
✓ User asks about capabilities in a domain → Use discover_servers with domain keyword

DISCOVERY WORKFLOW:
1. User makes request → Check if you have suitable tools
2. No suitable tools? → MUST call discover_tools("description of need") or discover_servers("domain")
3. Review discovered tools/servers
4. Execute appropriate tool with execute_tool(server_path, tool_name, arguments)
5. Present results to user

EXAMPLES:
- "What's the weather?" → discover_tools("weather forecast current conditions")
- "Search for news on AI" → discover_tools("web search news articles")
- "What can you do?" → discover_servers("" to browse all available services)
- "Analyze this GitHub repo" → discover_tools("github repository analysis")
- "Get stock prices" → discover_tools("financial data stock market")

ALWAYS be proactive: Discover and use available tools automatically. The gateway is your superpower - use it!"""
    )

    # Add header swap middleware (must be BEFORE AuthMiddleware)
    mcp.add_middleware(HeaderSwapMiddleware(custom_header=settings.INTERNAL_AUTH_HEADER)) 

    # Add authentication middleware
    mcp.add_middleware(AuthMiddleware())
    
    return mcp


# ============================================================================
# MCP Prompts - Guide AI Assistant Behavior (Claude, ChatGPT, etc.)
# ============================================================================

def register_prompts(mcp: FastMCP) -> None:
    """
    Register prompts for the MCP application.
    
    Args:
        mcp: FastMCP application instance
    """
    @mcp.prompt()
    def gateway_capabilities():
        """📚 Overview of MCP Gateway capabilities and available services.
        
        Use this prompt to understand what services and tools are available through the gateway.
        This is automatically invoked when you need to know what you can do.
        """
        return f"""# MCP Gateway - Available Capabilities

You have access to a powerful MCP Gateway that provides unified access to 100+ MCP servers.

## 🔍 Discovery & Execution Tools
- **discover_tools**: Find tools across all servers by describing what you want to accomplish
- **discover_servers**: Browse all available MCP servers with their complete capabilities
- **execute_tool**: Execute any discovered tool with appropriate parameters

## 🌐 Available Server Types (Examples)
The gateway proxies access to diverse MCP servers including:
- **Search & Research**: Web search, content extraction, crawling (e.g., Tavily)
- **Development**: GitHub, GitLab, code analysis, CI/CD tools
- **Data & Analytics**: Databases, data processing, visualization tools
- **APIs & Integrations**: Various external APIs and service integrations
- **AI & ML**: Model inference, data processing, training tools
- **And 100+ more...**

## 💡 Universal Workflow

### Standard Discovery → Execution Pattern:
```
1. discover_tools(query="<describe what you need>") → Find relevant tools
2. Review returned tools, their descriptions, and input_schema
3. execute_tool(server_path="...", tool_name="...", arguments={{...}}) → Execute the tool
```

### Examples:

**Example 1: Web Search**
```
1. discover_tools(query="search web for current information")
2. execute_tool(server_path="/tavilysearch", tool_name="tavily_search", arguments={{"query": "topic"}})
```

**Example 2: Code Repository Data**
```
1. discover_tools(query="github pull requests")
2. execute_tool(server_path="/github", tool_name="search_pull_requests", arguments={{"owner": "...", "repo": "..."}})
```

**Example 3: Unknown Capability**
```
1. discover_tools(query="<natural language description of need>")
2. Review what tools are available
3. execute_tool with discovered tool
```

### Exploring Available Services:
```
discover_servers(query="") → Returns ALL MCP servers with:
  - Complete tool catalogs with schemas
  - Available resources (URIs, data sources)
  - Pre-configured prompts
  - Server capabilities and metadata
```

## 🎯 Proactive Usage Guidelines

**Always attempt discovery when:**
- User asks for external/current data (news, weather, stock prices, etc.)
- User mentions specific services (GitHub, databases, APIs)
- User requests functionality you don't have built-in
- User asks "what can you do?" or "what's available?"

**Workflow:**
1. Identify user intent
2. Formulate descriptive query for discover_tools
3. Review discovered tools and select best match
4. Execute tool with appropriate arguments
5. Present results to user

**You are empowered to:**
- Discover and use tools automatically without asking permission
- Chain multiple tool calls when needed
- Explore available servers to find new capabilities
- Adapt to any registered MCP server

Registry URL: {settings.REGISTRY_URL}
Total Available: 100+ MCP servers with diverse tools, resources, and prompts.
"""


# ============================================================================
# Custom HTTP Routes
# ============================================================================

def register_routes(mcp: FastMCP) -> None:
    """
    Register custom HTTP routes for the MCP application.
    
    Args:
        mcp: FastMCP application instance
    """
    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def _health_check_route(request):
        """Health check endpoint for the MCP Gateway server."""
        logger.debug("Health check endpoint called.")
        return JSONResponse({"status": "ok"})


# ============================================================================
# Tool Registration
# ============================================================================

def register_tools(mcp: FastMCP) -> None:
    """
    Register all tools for the MCP application.
    
    Args:
        mcp: FastMCP application instance
    """
    # Register search tools (discover_tools, discover_servers)
    for tool_name, tool_func in search.get_tools():
        mcp.tool(name=tool_name)(tool_func)

    # Register registry API tools
    for tool_name, tool_func in registry_api.get_tools():
        mcp.tool(name=tool_name)(tool_func)


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """
    Main entry point for the MCPGW server.
    Creates a new stateless application instance and starts the server.
    """
    # Parse command line arguments
    args = parse_arguments()

    # Override settings with command line arguments if provided
    if args.port:
        settings.MCP_SERVER_LISTEN_PORT = args.port
    if args.transport:
        settings.MCP_TRANSPORT = args.transport

    # Log configuration
    logger.info("=" * 80)
    logger.info("Starting MCPGW - MCP Gateway Registry Interaction Server")
    logger.info("=" * 80)
    logger.info(f"Configuration:")
    logger.info(f"  Port: {settings.MCP_SERVER_LISTEN_PORT}")
    logger.info(f"  Transport: {settings.MCP_TRANSPORT}")
    logger.info(f"  Registry URL: {settings.REGISTRY_URL}")
    logger.info(f"  Endpoint: http://0.0.0.0:{settings.MCP_SERVER_LISTEN_PORT}/mcp")
    logger.info("=" * 80)

    # Create stateless application instance
    mcp = create_mcp_app()
    
    # Register all components
    register_prompts(mcp)
    register_routes(mcp)
    register_tools(mcp)

    logger.info("Starting server...")
    try:
        mcp.run(
            transport=settings.MCP_TRANSPORT,
            host="0.0.0.0",
            port=int(settings.MCP_SERVER_LISTEN_PORT),
            stateless_http=True
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
