"""
Example MCP Server demonstrating basic functionality.
This server provides simple tools for demonstration purposes.
"""

import os
import argparse
import logging
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from typing import Annotated, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s'
)
logger = logging.getLogger(__name__)


def _parse_arguments():
    """Parse command line arguments with defaults matching environment variables."""
    parser = argparse.ArgumentParser(description="Example MCP Server")

    parser.add_argument(
        "--port",
        type=str,
        default=os.environ.get("MCP_SERVER_LISTEN_PORT", "9000"),
        help="Port for the MCP server to listen on (default: 9000)",
    )

    parser.add_argument(
        "--transport",
        type=str,
        default=os.environ.get("MCP_TRANSPORT", "streamable-http"),
        choices=["sse", "streamable-http"],
        help="Transport type for the MCP server (default: streamable-http)",
    )

    return parser.parse_args()


# Parse arguments at module level to make them available
args = _parse_arguments()

# Log parsed arguments for debugging
logger.info(f"Parsed arguments - port: {args.port}, transport: {args.transport}")
logger.info(f"Environment variables - MCP_TRANSPORT: {os.environ.get('MCP_TRANSPORT', 'NOT SET')}, MCP_SERVER_LISTEN_PORT: {os.environ.get('MCP_SERVER_LISTEN_PORT', 'NOT SET')}")

# Initialize FastMCP server
mcp = FastMCP("ExampleMCPServer", host="0.0.0.0", port=int(args.port))
mcp.settings.mount_path = "/example-server"


@mcp.prompt()
def system_prompt_for_agent(task: str) -> str:
    """
    Generates a system prompt for an AI Agent that wants to use the example MCP server.

    This function creates a specialized prompt for an AI agent that wants to demonstrate
    basic MCP functionality using the example tools provided by this server.

    Args:
        task (str): The task or operation the agent wants to perform.

    Returns:
        str: A formatted system prompt for the AI Agent.
    """

    system_prompt = f"""
You are an expert AI agent that wants to use the Example MCP server. You will be provided with a task to perform.
You can use the available tools to demonstrate basic MCP functionality.

The task you need to perform is: {task}

Available tools:
- example_tool: Process a message and return a formatted response
- echo_tool: Echo back the input with additional metadata
- status_tool: Get the current status of the example server
"""
    return system_prompt


def _process_message(message: str) -> Dict[str, Any]:
    """
    Internal function to process a message.

    Args:
        message: The message to process

    Returns:
        Dict containing processed message information
    """
    processed = {
        "original_message": message,
        "processed_message": message.upper(),
        "message_length": len(message),
        "word_count": len(message.split()),
        "timestamp": "2025-09-26T23:00:00Z"
    }
    return processed


@mcp.tool()
def example_tool(
    message: Annotated[str, Field(
        description="Example message to process"
    )]
) -> Dict[str, Any]:
    """
    An example tool that demonstrates MCP functionality.

    This tool takes a message as input, processes it, and returns a structured
    response containing various information about the message.

    Args:
        message: Example message to process

    Returns:
        Dict[str, Any]: Result of the example operation containing processed message info

    Raises:
        Exception: If the operation fails
    """
    try:
        logger.info(f"Processing message: {message}")
        result = _process_message(message)
        logger.info(f"Successfully processed message")
        return result
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        raise Exception(f"Failed to process message: {str(e)}")


@mcp.tool()
def echo_tool(
    input_text: Annotated[str, Field(
        description="Text to echo back"
    )],
    include_metadata: Annotated[bool, Field(
        default=True,
        description="Whether to include metadata in the response"
    )] = True
) -> Dict[str, Any]:
    """
    A simple echo tool that returns the input with optional metadata.

    Args:
        input_text: Text to echo back
        include_metadata: Whether to include metadata in the response

    Returns:
        Dict[str, Any]: Echo response with optional metadata

    Raises:
        Exception: If the operation fails
    """
    try:
        logger.info(f"Echoing text: {input_text}")
        response = {
            "echo": input_text,
            "success": True
        }

        if include_metadata:
            response.update({
                "metadata": {
                    "character_count": len(input_text),
                    "server": "Example MCP Server",
                    "version": "0.1.0"
                }
            })

        return response
    except Exception as e:
        logger.error(f"Error in echo tool: {str(e)}")
        raise Exception(f"Echo operation failed: {str(e)}")


@mcp.tool()
def status_tool() -> Dict[str, Any]:
    """
    Get the current status of the example server.

    Returns:
        Dict[str, Any]: Server status information

    Raises:
        Exception: If unable to get status
    """
    try:
        logger.info("Getting server status")
        status = {
            "server_name": "Example MCP Server",
            "version": "0.1.0",
            "status": "running",
            "port": args.port,
            "transport": args.transport,
            "available_tools": ["example_tool", "echo_tool", "status_tool"],
            "health": "healthy"
        }
        return status
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        raise Exception(f"Failed to get server status: {str(e)}")


@mcp.resource("config://app")
def get_config() -> str:
    """Static configuration data for the example server"""
    return """
Example MCP Server Configuration:
- Server Name: Example MCP Server
- Version: 0.1.0
- Available Tools: example_tool, echo_tool, status_tool
- Transport: streamable-http
- Description: Demonstrates basic MCP functionality
"""


def main():
    # Log transport and endpoint information
    endpoint = "/mcp" if args.transport == "streamable-http" else "/sse"
    logger.info(f"Starting Example MCP server on port {args.port} with transport {args.transport}")
    logger.info(f"Server will be available at: http://localhost:{args.port}{endpoint}")

    # Run the server with the specified transport from command line args
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()