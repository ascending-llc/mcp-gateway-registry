#!/usr/bin/env python3
import asyncio
import logging
from fastmcp import FastMCP
from starlette.responses import JSONResponse

from auth.custom_jwt import jwtVerifier
from auth.middleware import AuthMiddleware
from config import parse_arguments, settings
from servers.mcpgw.tools import registry_api
from servers.mcpgw.tools import search

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
# Search and Discovery Tools
# ============================================================================

# Register search tools (discover_tools, intelligent_tool_finder) using Pattern 3
for tool_name, tool_func in search.get_tools():
    mcp.tool(name=tool_name)(tool_func)

# ============================================================================
# Registry API Tools
# ============================================================================

for tool_name, tool_func in registry_api.get_tools():
    mcp.tool(name=tool_name)(tool_func)


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
    logger.info(f"  Registry URL: {settings.REGISTRY_URL}")
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
