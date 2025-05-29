"""
Example MCP client for the mcpgw server.

This client connects to the mcpgw MCP server, lists its capabilities,
and demonstrates calling the 'get_server_details' and 'register_service' tools.

Usage:
  python client.py [--host HOSTNAME] [--port PORT] [--server-name SERVER_NAME]

Example:
  # Connect to mcpgw server running locally on default port 8001
  python client.py

  # Connect to mcpgw server running on a specific host/port
  python client.py --host myregistry.com --port 8001
"""

import argparse
import json # Import json for pretty printing
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

            # List available prompts (mcpgw server likely has none)
            prompts = await session.list_prompts()
            logger.info("=" * 50)
            logger.info("Available prompts:")
            logger.info("=" * 50)
            logger.info(f"{prompts}")
            logger.info("=" * 50)

            # List available resources (mcpgw server likely has none)
            resources = await session.list_resources()
            logger.info("=" * 50)
            logger.info("Available resources:")
            logger.info("=" * 50)
            logger.info(f"{resources}")
            logger.info("=" * 50)

            # List available tools (should show the registry interaction tools)
            tools = await session.list_tools()
            logger.info("=" * 50)
            logger.info("Available tools:")
            logger.info("=" * 50)
            logger.info(f"{tools}")
            logger.info("=" * 50)

            # --- Example: Call the get_server_details tool ---
            # Let's try to get details for the '/current_time' server (assuming it's registered)
            target_service_path = "/all"
            logger.info(f"\nCalling 'get_server_details' tool for service_path='{target_service_path}'")

            try:
                # Pass parameters directly to the get_server_details tool
                result = await session.call_tool(
                    "get_server_details", arguments={
                        "service_path": target_service_path,
                        "username": args.username,
                        "password": args.password
                    }
                )

                # Display the results (which should be the JSON response from the registry)
                logger.info("=" * 50)
                logger.info(f"Result for get_server_details('{target_service_path}'):")
                logger.info("=" * 50)
                # The result content is usually a list of MessagePart objects
                full_response_text = "".join(part.text for part in result.content if hasattr(part, 'text'))
                try:
                    # Attempt to parse and pretty-print if it's JSON
                    parsed_json = json.loads(full_response_text)
                    logger.info(json.dumps(parsed_json, indent=2))
                except json.JSONDecodeError:
                    # Otherwise, just log the raw text
                    logger.info(full_response_text)
                logger.info("=" * 50)

            except Exception as e:
                logger.error(f"Error calling 'get_server_details': {e}")
            # --- End Example ---

            # --- Example: Call the register_service tool (if enabled) ---
            if args.test_register_service and args.test_register_service.lower() in ["true", "yes"]:
                logger.info("\nCalling 'register_service' tool with hardcoded parameters")

                try:
                    # Pass hardcoded parameters to the register_service tool
                    result = await session.call_tool(
                        "register_service", arguments={
                            "server_name": "Example Service",
                            "path": "/example-service",
                            "proxy_pass_url": "http://localhost:9000",
                            "description": "An example MCP service for demonstration purposes",
                            "tags": ["example", "demo", "test"],
                            "num_tools": 3,
                            "num_stars": 5,
                            "is_python": True,
                            "license": "MIT",
                            "username": args.username,
                            "password": args.password
                        }
                    )

                    # Display the results
                    logger.info("=" * 50)
                    logger.info("Result for register_service:")
                    logger.info("=" * 50)
                    # The result content is usually a list of MessagePart objects
                    full_response_text = "".join(part.text for part in result.content if hasattr(part, 'text'))
                    try:
                        # Attempt to parse and pretty-print if it's JSON
                        parsed_json = json.loads(full_response_text)
                        logger.info(json.dumps(parsed_json, indent=2))
                    except json.JSONDecodeError:
                        # Otherwise, just log the raw text
                        logger.info(full_response_text)
                    logger.info("=" * 50)

                except Exception as e:
                    logger.error(f"Error calling 'register_service': {e}")
                # --- End Example ---
            else:
                logger.info("\nSkipping 'register_service' tool example (use --test-register-service=true to enable)")


if __name__ == "__main__":
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(
        description="MCP Client for the MCP Gateway Interaction Server (mcpgw)" # Updated description
    )
    parser.add_argument(
        "--host", type=str, default="localhost", help="Hostname of the MCP server"
    )
    # Default port changed to 8001 as per server.py Constants
    parser.add_argument("--port", type=int, default=8001, help="Port of the MCP server")
    parser.add_argument(
        "--server-name",
        type=str,
        default="mcpgw", # Default server name changed
        help='Name of the MCP server to connect to (e.g., "mcpgw")',
    )
    parser.add_argument(
        "--username",
        type=str,
        default="admin", # Default server name changed
        help='Username for the MCP Gateway (default: "admin")',
    )
    parser.add_argument(
        "--password",
        type=str,        
        help='Password for the MCP Gateway',
    )
    parser.add_argument(
        "--test-register-service",
        type=str,   
        default="false",
        help='Set to "true" to test the register_service tool (default: "false")',
    )

    # Parse the arguments
    args = parser.parse_args()

    # Build the server URL
    secure = ""
    # Automatically turn to https if port is 443
    if args.port == 443:
        secure = "s"

    # Construct URL based on whether server_name is provided (it defaults to mcpgw now)
    # The server itself doesn't expect the server name in the path for /sse
    server_url = f"http{secure}://{args.host}:{args.port}/{args.server_name}/sse"

    # Run the async main function
    import asyncio

    asyncio.run(run(server_url, args))
