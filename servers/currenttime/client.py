"""
This file provides a simple MCP client using just the mcp Python package.
It shows how to access the different MCP server capabilities (prompts, tools etc.) via the message types
supported by the protocol. See: https://modelcontextprotocol.io/docs/concepts/architecture.

Usage:
  python mcp_sse_client.py [--host HOSTNAME] [--port PORT]

Example:
  python mcp_sse_client.py --host ec2-44-192-72-20.compute-1.amazonaws.com --port 8000
"""

import argparse
import logging
from mcp import ClientSession
from mcp.client.sse import sse_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - PID:%(process)d - %(filename)s:%(lineno)d - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def run(server_url, args):
    logger.info(f"Connecting to MCP server at: {server_url}")

    async with sse_client(server_url) as (read, write):
        async with ClientSession(read, write, sampling_callback=None) as session:
            # Initialize the connection
            await session.initialize()

            # List available prompts
            prompts = await session.list_prompts()
            logger.info("=" * 50)
            logger.info("Available prompts:")
            logger.info("=" * 50)
            logger.info(f"{prompts}")
            logger.info("=" * 50)

            # List available resources
            resources = await session.list_resources()
            logger.info("=" * 50)
            logger.info("Available resources:")
            logger.info("=" * 50)
            logger.info(f"{resources}")
            logger.info("=" * 50)

            # List available tools
            tools = await session.list_tools()
            logger.info("=" * 50)
            logger.info("Available tools:")
            logger.info("=" * 50)
            logger.info(f"{tools}")
            logger.info("=" * 50)

            # Call the current_time_by_timezone tool
            tz_name = "Africa/Cairo"
            logger.info(f"\nCalling current_time_by_timezone tool with tz_name={tz_name}")
            result = await session.call_tool(
                "current_time_by_timezone", arguments={"tz_name": tz_name}
            )

            # Display the results
            logger.info("=" * 50)
            logger.info("Results:")
            logger.info("=" * 50)
            for r in result.content:
                logger.info(r.text)
            logger.info("=" * 50)


if __name__ == "__main__":
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(
        description="MCP Client for Bedrock Usage Statistics"
    )
    parser.add_argument(
        "--host", type=str, default="localhost", help="Hostname of the MCP server"
    )
    parser.add_argument("--port", type=int, default=8000, help="Port of the MCP server")
    parser.add_argument(
        "--server-name",
        type=str,
        default="currenttime", # Default server name changed
        help='Name of the MCP server to connect to (e.g., "mcpgw")',
    )
    # Parse the arguments
    args = parser.parse_args()

    # Build the server
    secure = ""

    # Automatically turn to https if port is 443
    if args.port == 443:
        secure = "s"
    server_url = f"http{secure}://{args.host}:{args.port}/{args.server_name}/sse"

    # Run the async main function
    import asyncio

    asyncio.run(run(server_url, args))
