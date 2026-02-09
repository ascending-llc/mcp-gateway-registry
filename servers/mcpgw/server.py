#!/usr/bin/env python3
import logging

from auth.patch_init_exempt import patch_init_exempt

patch_init_exempt()
from auth.custom_jwt import jwtVerifier
from auth.middleware import AuthMiddleware, HeaderSwapMiddleware
from fastmcp import FastMCP
from starlette.responses import JSONResponse
from tools import registry_api, search

from config import parse_arguments, settings

# Configure logging
logger = logging.getLogger(__name__)


def create_mcp_app() -> FastMCP:
    """
    Factory function to create a stateless FastMCP application instance.

    Returns:
        Configured FastMCP application instance
    """
    mcp = FastMCP(
        "JarvisRegistry",
        auth=jwtVerifier,  # JWT verifier (requires middleware to swap headers if using custom header)
        instructions="""This MCP Gateway provides unified access to 100+ MCP servers, tools, resources, and prompts through a centralized discovery and execution interface.

KEY CAPABILITIES:
- 🔍 Discover any tool, resource, or prompt across all registered MCP servers
- 🚀 Execute tools from any MCP server through unified proxy
- 📚 Access resources (URIs, caches, data sources) from any server
- 💬 Use prompts from any server for specialized workflows
- 🎯 Automatic routing, authentication, and execution with proper credentials

CRITICAL RULE - ALWAYS USE DISCOVERY FIRST:
⚠️ MANDATORY: If you don't have a suitable tool for the user's request, you MUST use discover_servers to find one.
⚠️ NEVER respond with "I don't have the capability" without first attempting discovery.
⚠️ The gateway provides access to 100+ specialized tools - they must be discovered before use.

CRITICAL RULE - WHEN NATIVE TOOLS FAIL:
⚠️ If you encounter FAILURES (fetch fails, can't access resource, authentication errors, permission denied):
  1. DON'T give up or say "I can't access this" - The registry has specialized authenticated tools
  2. IMMEDIATELY use discover_servers to find a specialized tool for that service
  3. Specialized tools in registry have proper authentication/authorization configured
  4. Most services (GitHub, APIs, databases) have authenticated tools available

EXAMPLES OF WHEN TO FALL BACK TO REGISTRY:
✓ Fetch fails on private repository URL → discover_servers(query="<service> repository", type_list=["tool"])
✓ Can't access API endpoint → discover_servers(query="<service name> API", type_list=["tool"])
✓ Authentication error (401/403) → discover_servers(query="<service> authenticated", type_list=["tool"])
✓ Rate limit exceeded → discover_servers(query="<service> premium access", type_list=["tool"])
✓ Permission denied → discover_servers(query="<service> <operation>", type_list=["tool"])
✓ Resource unavailable → Specialized tools in registry have proper credentials and access

WHEN TO USE DISCOVERY TOOLS:
✓ User needs external/real-time data (news, weather, stock prices, current events)
✓ User asks "what can you do?" → Use discover_servers with type_list=["server"]
✓ User mentions specific services (GitHub, databases, APIs, search engines)
✓ User requests functionality you don't have built-in → ALWAYS try discover_servers first
✓ You encounter a task requiring specialized tools → discover_servers before saying "I can't"
✓ User asks about capabilities in a domain → Use discover_servers with domain keyword
✓ Native tool FAILED → Try discover_servers to find authenticated/specialized alternative

DISCOVERY WORKFLOW:
1. User makes request → Check if you have suitable tools
2. No suitable tools? → MUST call discover_servers("description of need", type_list=["tool"])
3. Review discovered tools/servers
4. Execute appropriate tool with execute_tool(server_path, tool_name, arguments)
5. Present results to user

TOKEN-EFFICIENT DISCOVERY:
- Use type_list=["tool"] (default) for specific executable tools (returns 3 results)
- Use type_list=["resource"] for data sources/URIs (returns 3 results)
- Use type_list=["prompt"] for workflows (returns 3 results)
- Use type_list=["server"] only when exploring all capabilities (returns 1 server, token-heavy)

EXAMPLES:
- "What's the weather?" → discover_servers(query="weather forecast", type_list=["tool"])
- "Search for news on AI" → discover_servers(query="web search news", type_list=["tool"])
- "What can you do?" → discover_servers(query="", type_list=["server"])
- "Get stock prices" → discover_servers(query="financial data stock market", type_list=["tool"])
- "Send an email" → discover_servers(query="email send message", type_list=["tool"])
- Fetch/access fails → discover_servers(query="<service> <operation>", type_list=["tool"])

RESILIENCE PATTERN:
```
# When you see errors (fetch failed, 403, 401, permission denied):
if error_occurred:
    # Don't give up! Find authenticated tool from registry
    tools = discover_servers(query="<service> <operation>", type_list=["tool"])
    if tools:
        result = execute_tool(tools[0]["server_path"], tools[0]["tool_name"], args)

# For authenticated resources, prefer registry tools proactively:
# - Private repositories → discover_servers("<service> repository", type_list=["tool"])
# - Private APIs → discover_servers("<api name>", type_list=["tool"])
# - Database queries → discover_servers("database <operation>", type_list=["tool"])
# - Authenticated services → discover_servers("<service> authenticated", type_list=["tool"])
```

ALWAYS be proactive: Discover and use available tools automatically. When native tools fail, try registry tools - they often have proper authentication and elevated permissions!""",
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
1. discover_servers(query="<describe what you need>", type_list=["tool"]) → Find relevant tools
2. Review returned tools, their descriptions, and input_schema
3. execute_tool(server_path="...", tool_name="...", arguments={{...}}) → Execute the tool
```

### Resilience Pattern (When You Encounter Failures):
```
1. If you see errors (fetch failed, 403, 401, permission denied, can't access):
   a. DON'T give up or tell user "I can't access this"
   b. discover_servers(query="<service> <operation>", type_list=["tool"])
   c. execute_tool with discovered authenticated tool
2. Registry tools have proper credentials and access that native tools lack
3. This is especially important for: private repositories, private APIs, authenticated databases, premium services
```

### Examples:

**Example 1: Web Search**
```
1. discover_servers(query="search web for current information", type_list=["tool"])
2. execute_tool(server_path="/tavilysearch", tool_name="tavily_search", arguments={{"query": "topic"}})
```

**Example 2: Private Resource Access (When Native Fetch Fails)**
```
# You see error: fetch failed, 403 forbidden, can't access resource
1. DON'T say "I can't access this resource" or "This is private/unavailable"
2. Parse the URL/resource to identify the service
3. discover_servers(query="<service> <resource_type>", type_list=["tool"])
4. Review discovered tools with authentication
5. execute_tool with appropriate tool and parsed parameters
6. Success! Registry tool has proper credentials and access
```

**Example 3: Unknown Capability**
```
1. discover_servers(query="<natural language description of need>", type_list=["tool"])
2. Review what tools are available
3. execute_tool with discovered tool
```

### Exploring Available Services:
```
discover_servers(query="", type_list=["server"]) → Returns ALL MCP servers with:
  - Complete tool catalogs with schemas
  - Available resources (URIs, data sources)
  - Pre-configured prompts
  - Server capabilities and metadata
```

## 🎯 Proactive Usage Guidelines

**Always attempt discovery when:**
- User asks for external/current data (news, weather, stock prices, etc.)
- User mentions specific services (code repositories, databases, APIs, email, calendars)
- User requests functionality you don't have built-in
- User asks "what can you do?" or "what's available?"
- **Native tools FAIL** (fetch fails, auth errors, permission denied, rate limits)
- User pastes URLs to private/authenticated resources

**Resilience Strategy (When You Encounter Errors):**
1. **If native tools fail → IMMEDIATELY use discover_servers** with service-specific query
2. DON'T tell user "I can't access this" or "this is private/unavailable"
3. Registry tools have authentication and specialized access configured
4. Most services (repositories, APIs, databases, email, calendars) have authenticated tools available
5. This applies to: fetch failures, 401/403 errors, permission denied, rate limits

**Workflow:**
1. Identify user intent and service/resource being accessed
2. For authenticated services (repositories, APIs, databases), use registry tools proactively
3. If you encounter errors/failures, immediately use discover_servers
4. Formulate descriptive query for discover_servers based on service and operation
5. Review discovered tools and select best match
6. Execute tool with appropriate arguments
7. Present results to user

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
    logger.info("Configuration:")
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
            host=settings.MCP_SERVER_HOST,
            port=int(settings.MCP_SERVER_LISTEN_PORT),
            stateless_http=True,
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
