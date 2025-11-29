#!/usr/bin/env python3
import asyncio
import logging
from typing import Dict, Any, Optional, List
from fastmcp import FastMCP, Context
from pydantic import Field
from starlette.responses import JSONResponse

from auth.custom_jwt import jwtVerifier
from auth.middleware import AuthMiddleware
from config import parse_arguments, settings
from tools import auth_tools, service_mgmt, scopes_mgmt, search_tools

# Configure logging
logger = logging.getLogger(__name__)

mcp = FastMCP("MCPGateway", auth=jwtVerifier)
mcp.add_middleware(AuthMiddleware())


# ============================================================================
# Vector Search Initialization
# ============================================================================

async def initialize_vector_search():
    """Initialize the vector search service."""
    try:
        from search import vector_search_service
        await vector_search_service.initialize()
        logger.info("Vector search service initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize vector search service: {e}", exc_info=True)
        logger.warning("Server will continue but intelligent_tool_finder may not work")


# ============================================================================
# Custom HTTP Routes
# ============================================================================

@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def _health_check_route(request):
    """Health check endpoint for the MCP Gateway server."""
    logger.debug("Health check endpoint called.")
    return JSONResponse({"status": "ok"})


# ============================================================================
# Authentication Debugging Tools
# ============================================================================

@mcp.tool()
async def debug_auth_context(ctx: Context = None) -> Dict[str, Any]:
    """
    Debug tool to explore what authentication context is available.
    This tool helps understand what auth information can be accessed through the MCP Context.
    """
    return await auth_tools.debug_auth_context_impl(ctx)


@mcp.tool()
async def get_http_headers(ctx: Context = None) -> Dict[str, Any]:
    """
    FastMCP 2.0 tool to access HTTP headers directly.
    This tool demonstrates how to get HTTP request information including auth headers.
    """
    return await auth_tools.get_http_headers_impl(ctx)


# ============================================================================
# Service Management Tools
# ============================================================================

@mcp.tool()
async def toggle_service(
        service_path: str = Field(...,
                                  description="The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'."),
        ctx: Context = None
) -> Dict[str, Any]:
    """
    Toggles the enabled/disabled state of a registered MCP server in the gateway.
    """
    return await service_mgmt.toggle_service_impl(service_path, ctx)


@mcp.tool()
async def register_service(
        server_name: str = Field(..., description="Display name for the server."),
        path: str = Field(...,
                          description="Unique URL path prefix for the server (e.g., '/my-service'). Must start with '/'."),
        proxy_pass_url: str = Field(...,
                                    description="The internal URL where the actual MCP server is running (e.g., 'http://localhost:8001')."),
        description: Optional[str] = Field("", description="Description of the server."),
        tags: Optional[List[str]] = Field(None, description="Optional list of tags for categorization."),
        num_tools: Optional[int] = Field(0, description="Number of tools provided by the server."),
        num_stars: Optional[int] = Field(0, description="Number of stars/rating for the server."),
        is_python: Optional[bool] = Field(False, description="Whether the server is implemented in Python."),
        license: Optional[str] = Field("N/A", description="License information for the server."),
        auth_provider: Optional[str] = Field(None, description="Authentication provider."),
        auth_type: Optional[str] = Field(None, description="Authentication type."),
        supported_transports: Optional[List[str]] = Field(None, description="List of supported transports."),
        headers: Optional[List[Dict[str, str]]] = Field(None, description="List of header dictionaries."),
        tool_list: Optional[List[Dict[str, Any]]] = Field(None, description="List of tools with their schemas."),
        ctx: Context = None
) -> Dict[str, Any]:
    """
    Registers a new MCP server with the gateway.
    """
    return await service_mgmt.register_service_impl(
        server_name, path, proxy_pass_url, description, tags, num_tools,
        num_stars, is_python, license, auth_provider, auth_type,
        supported_transports, headers, tool_list, ctx
    )


@mcp.tool()
async def list_services(ctx: Context = None) -> Dict[str, Any]:
    """
    Lists all registered MCP services in the gateway.
    """
    return await service_mgmt.list_services_impl(ctx)


@mcp.tool()
async def remove_service(
        service_path: str = Field(..., description="The unique path identifier for the service"
                                                   " to remove (e.g., '/fininfo'). Must start with '/'."),
        ctx: Context = None
) -> Dict[str, Any]:
    """
    Removes a registered MCP server from the gateway.
    """
    return await service_mgmt.remove_service_impl(service_path, ctx)


@mcp.tool()
async def refresh_service(
        service_path: str = Field(..., description="The unique path identifier for the service"
                                                   " (e.g., '/fininfo'). Must start with '/'."),
        ctx: Context = None
) -> Dict[str, Any]:
    """
    Triggers a refresh of the tool list for a specific registered MCP server.
    """
    return await service_mgmt.refresh_service_impl(service_path, ctx)


@mcp.tool()
async def healthcheck(ctx: Context = None) -> Dict[str, Any]:
    """
    Retrieves health status information from all registered MCP servers.
    """
    return await service_mgmt.healthcheck_impl(ctx)


# ============================================================================
# Scopes and Groups Management Tools
# ============================================================================

@mcp.tool()
async def add_server_to_scopes_groups(
        server_name: str = Field(..., description="Name of the server to add to groups"
                                                  " (e.g., 'example-server'). Should not include leading slash."),
        group_names: List[str] = Field(..., description="List of scopes group names to add the server to."),
        ctx: Context = None
) -> Dict[str, Any]:
    """
    Add a server and all its known tools/methods to specific scopes groups.
    """
    return await scopes_mgmt.add_server_to_scopes_groups_impl(server_name, group_names, ctx)


@mcp.tool()
async def remove_server_from_scopes_groups(
        server_name: str = Field(..., description="Name of the server to remove from groups."),
        group_names: List[str] = Field(..., description="List of scopes group names to remove the server from."),
        ctx: Context = None
) -> Dict[str, Any]:
    """
    Remove a server from specific scopes groups.
    """
    return await scopes_mgmt.remove_server_from_scopes_groups_impl(server_name, group_names, ctx)


@mcp.tool()
async def create_group(
        group_name: str = Field(..., description="Name of the group to create (e.g., 'mcp-servers-finance/read')"),
        description: Optional[str] = Field("", description="Optional description for the group"),
        ctx: Context = None
) -> Dict[str, Any]:
    """
    Create a new group in both Keycloak and scopes.yml.
    """
    return await scopes_mgmt.create_group_impl(group_name, description, ctx)


@mcp.tool()
async def delete_group(
        group_name: str = Field(..., description="Name of the group to delete"),
        ctx: Context = None
) -> Dict[str, Any]:
    """
    Delete a group from both Keycloak and scopes.yml.
    """
    return await scopes_mgmt.delete_group_impl(group_name, ctx)


@mcp.tool()
async def list_groups(ctx: Context = None) -> Dict[str, Any]:
    """
    List all groups from Keycloak and scopes.yml with synchronization status.
    """
    return await scopes_mgmt.list_groups_impl(ctx)


# ============================================================================
# Intelligent Tool Finder
# ============================================================================

@mcp.tool()
async def intelligent_tool_finder(
        natural_language_query: Optional[str] = Field(None,
                                                      description="Your query in natural language describing the task you want to perform."
                                                                  " Optional if tags are provided."),
        tags: Optional[List[str]] = Field(None, description="List of tags to filter tools by using AND logic. "
                                                            "IMPORTANT: AI agents should ONLY use this if the user explicitly provides specific tags. "
                                                            "DO NOT infer tags - incorrect tags will exclude valid results."),
        top_k_services: int = Field(3, description="Number of top services to consider "
                                                   "from initial FAISS search (ignored if only tags provided)."),
        top_n_tools: int = Field(1, description="Number of best matching tools to return."),
        ctx: Optional[Context] = None
) -> List[Dict[str, Any]]:
    """
    Finds the most relevant MCP tool(s) across all registered and enabled services
    based on a natural language query and/or tag filtering, using semantic search.

    IMPORTANT FOR AI AGENTS:
    - Only fill in the 'tags' parameter if the user explicitly provides specific tags to filter by
    - DO NOT infer or guess tags from the natural language query
    - Tags act as a strict filter - incorrect tags will exclude valid results
    - When tags are provided with a query, results must match BOTH the semantic search AND all tags
    - If unsure about tags, use natural_language_query alone for best results

    Args:
        natural_language_query: The user's natural language query. Optional if tags are provided.
        tags: List of tags to filter by using AND logic. All tags must match a server's tags for its tools to be included.
              CAUTION: Only use this parameter if explicitly provided by the user. Incorrect tags will filter out valid results.
        top_k_services: How many top-matching services to analyze for tools from search (ignored if only tags provided).
        top_n_tools: How many best tools to return from the combined list.
        ctx: Optional context to pass to services_mgmt as an argument.

    Returns:
        A list of dictionaries, each describing a recommended tool, its parent service, and similarity score (if semantic search used).

    Examples:
        # Semantic search only (RECOMMENDED for AI agents unless user specifies tags)
        tools = await intelligent_tool_finder(natural_language_query="find files", top_n_tools=5)

        # Semantic search + tag filtering (ONLY use when user explicitly provides tags)
        tools = await intelligent_tool_finder(
            natural_language_query="find files",
            tags=["file-system", "search"],  # User explicitly said: "use tags file-system and search"
            top_n_tools=5
        )

        # Pure tag-based filtering (ONLY when user provides tags without a query)
        tools = await intelligent_tool_finder(tags=["database", "analytics"], top_n_tools=10)
    """
    return await search_tools.intelligent_tool_finder_impl(
        natural_language_query, tags, top_k_services, top_n_tools, ctx
    )


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """
    Main entry point for the MCPGW server.
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
    logger.info(f"  Registry URL: {settings.REGISTRY_BASE_URL}")
    logger.info(f"  Tool Discovery Mode: {settings.TOOL_DISCOVERY_MODE}")
    logger.info(f"  Endpoint: http://0.0.0.0:{settings.MCP_SERVER_LISTEN_PORT}/mcp")
    logger.info("=" * 80)

    # Initialize services
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(initialize_vector_search())
    except Exception as e:
        logger.warning(f"Startup initialization encountered issues: {e}")
        logger.warning("Server will continue but some features may not work until initialized")

    # Run the server
    logger.info("Starting server...")
    try:
        mcp.run(
            transport=settings.MCP_TRANSPORT,
            host="0.0.0.0",
            port=int(settings.MCP_SERVER_LISTEN_PORT)
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
