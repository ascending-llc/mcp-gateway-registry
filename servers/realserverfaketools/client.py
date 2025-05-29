"""
This file provides a simple MCP client for the real_server_fake_tools server.
It demonstrates how to access the different MCP server capabilities (prompts, tools, resources)
via the message types supported by the protocol.

Usage:
  python client.py [--host HOSTNAME] [--port PORT]

Example:
  python client.py --host localhost --port 8001
"""

import argparse
import logging
import json
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

            # Example 1: Call the quantum_flux_analyzer tool
            logger.info("\nExample 1: Calling quantum_flux_analyzer tool")
            result = await session.call_tool(
                "quantum_flux_analyzer", 
                arguments={
                    "energy_level": 7,
                    "stabilization_factor": 0.85,
                    "enable_temporal_shift": True
                }
            )
            logger.info("=" * 50)
            logger.info("Results from quantum_flux_analyzer:")
            logger.info("=" * 50)
            for r in result.content:
                logger.info(r.text)
            logger.info("=" * 50)

            # Example 2: Call the neural_pattern_synthesizer tool
            logger.info("\nExample 2: Calling neural_pattern_synthesizer tool")
            result = await session.call_tool(
                "neural_pattern_synthesizer", 
                arguments={
                    "input_patterns": ["alpha", "beta", "gamma"],
                    "coherence_threshold": 0.8,
                    "dimensions": 5
                }
            )
            logger.info("=" * 50)
            logger.info("Results from neural_pattern_synthesizer:")
            logger.info("=" * 50)
            for r in result.content:
                logger.info(r.text)
            logger.info("=" * 50)

            # Example 3: Call the hyper_dimensional_mapper tool
            logger.info("\nExample 3: Calling hyper_dimensional_mapper tool")
            result = await session.call_tool(
                "hyper_dimensional_mapper", 
                arguments={
                    "coordinates": {
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                        "altitude": 10
                    },
                    "dimension_count": 6,
                    "reality_anchoring": 0.9
                }
            )
            logger.info("=" * 50)
            logger.info("Results from hyper_dimensional_mapper:")
            logger.info("=" * 50)
            for r in result.content:
                logger.info(r.text)
            logger.info("=" * 50)

            # Example 4: Call the user_profile_analyzer tool
            logger.info("\nExample 4: Calling user_profile_analyzer tool")
            result = await session.call_tool(
                "user_profile_analyzer", 
                arguments={
                    "profile": {
                        "username": "user123",
                        "email": "user@example.com",
                        "age": 30,
                        "interests": ["technology", "science", "art"]
                    },
                    "analysis_options": {
                        "depth": 5,
                        "include_metadata": True,
                        "filters": {"exclude_inactive": True}
                    }
                }
            )
            logger.info("=" * 50)
            logger.info("Results from user_profile_analyzer:")
            logger.info("=" * 50)
            for r in result.content:
                logger.info(r.text)
            logger.info("=" * 50)

            # Example 5: Access the tools documentation resource
            logger.info("\nExample 5: Accessing tools documentation resource")
            result = await session.access_resource("docs://tools")
            logger.info("=" * 50)
            logger.info("Tools documentation:")
            logger.info("=" * 50)
            for r in result.content:
                logger.info(r.text)
            logger.info("=" * 50)


if __name__ == "__main__":
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(
        description="MCP Client for Real Server Fake Tools"
    )
    parser.add_argument(
        "--host", type=str, default="localhost", help="Hostname of the MCP server"
    )
    parser.add_argument("--port", type=int, default=8001, help="Port of the MCP server")
    parser.add_argument(
        "--server-name",
        type=str,
        default="realserverfaketools",
        help='Name of the MCP server to connect to',
    )
    # Parse the arguments
    args = parser.parse_args()

    # Build the server URL
    secure = ""

    # Automatically turn to https if port is 443
    if args.port == 443:
        secure = "s"
    server_url = f"http{secure}://{args.host}:{args.port}/{args.server_name}/sse"

    # Run the async main function
    import asyncio

    asyncio.run(run(server_url, args))