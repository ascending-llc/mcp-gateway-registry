#!/usr/bin/env python3
"""
LangGraph MCP Client 

This script demonstrates using LangGraph with the MultiServerMCPClient adapter to connect to an
MCP-compatible server and query information using a Bedrock-hosted Claude model.

The script accepts command line arguments for:
- Server host and port
- Model ID to use
- User message to process

Usage:
    python langgraph_mcp_client.py --host hostname --port port --model model_id --message "your question"

Example:
    python langgraph_mcp_sse_client.py --host ec2-44-192-72-20.compute-1.amazonaws.com --port 8000 \
        --model anthropic.claude-3-haiku-20240307-v1:0 --message "my bedrock usage in last 7 days?"
"""

import asyncio
import argparse
import re
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, urljoin
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_aws import ChatBedrock, ChatBedrockConverse
from langchain_core.tools import tool
import mcp
from mcp import ClientSession
from mcp.client.sse import sse_client

def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments for the LangGraph MCP client.
    
    Returns:
        argparse.Namespace: The parsed command line arguments
    """
    parser = argparse.ArgumentParser(description='LangGraph MCP Client')
    
    # Server connection arguments
    parser.add_argument('--mcp-registry-url', type=str, default='https://mcpgateway.ddns.net/mcpgw/sse',
                        help='Hostname of the MCP Registry')
    
    # Model arguments
    parser.add_argument('--model', type=str, default='us.anthropic.claude-3-5-haiku-20241022-v1:0',
                        help='Model ID to use with Bedrock')
    
    # Message arguments
    parser.add_argument('--message', type=str, default='what is the current time in Clarksburg, MD',
                        help='Message to send to the agent')
    
    return parser.parse_args()

@tool
def calculator(expression: str) -> str:
    """
    Evaluate a mathematical expression and return the result.
    
    This tool can perform basic arithmetic operations like addition, subtraction,
    multiplication, division, and exponentiation.
    
    Args:
        expression (str): The mathematical expression to evaluate (e.g., "2 + 2", "5 * 10", "(3 + 4) / 2")
    
    Returns:
        str: The result of the evaluation as a string
    
    Example:
        calculator("2 + 2") -> "4"
        calculator("5 * 10") -> "50"
        calculator("(3 + 4) / 2") -> "3.5"
    """
    # Security check: only allow basic arithmetic operations and numbers
    # Remove all whitespace
    expression = expression.replace(" ", "")
    
    # Check if the expression contains only allowed characters
    if not re.match(r'^[0-9+\-*/().^ ]+$', expression):
        return "Error: Only basic arithmetic operations (+, -, *, /, ^, (), .) are allowed."
    
    try:
        # Replace ^ with ** for exponentiation
        expression = expression.replace('^', '**')
        
        # Evaluate the expression
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"

@tool
async def invoke_mcp_tool(mcp_registry_url: str, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Invoke a tool on an MCP server using the MCP Registry URL and server name. The Registry URL is
    
    This tool creates an MCP SSE client and calls the specified tool with the provided arguments.
    
    Args:
        mcp_registry_url (str): The URL of the MCP Registry
        server_name (str): The name of the MCP server to connect to
        tool_name (str): The name of the tool to invoke
        arguments (Dict[str, Any]): Dictionary containing the arguments for the tool
    
    Returns:
        str: The result of the tool invocation as a string
    
    Example:
        invoke_mcp_tool("registry url", "currenttime", "current_time_by_timezone", {"tz_name": "America/New_York"})
    """
    # Construct the MCP server URL from the registry URL and server name using standard URL parsing
    parsed_url = urlparse(mcp_registry_url)
    
    # Extract the scheme and netloc (hostname:port) from the parsed URL
    scheme = parsed_url.scheme
    netloc = parsed_url.netloc
    
    # Construct the base URL with scheme and netloc
    base_url = f"{scheme}://{netloc}"
    
    # Create the server URL by joining the base URL with the server name and sse path
    server_url = urljoin(base_url, f"{server_name}/sse")
    print(f"Server URL: {server_url}")
    
    try:
        # Create an MCP SSE client and call the tool
        async with mcp.client.sse.sse_client(server_url) as (read, write):
            async with mcp.ClientSession(read, write, sampling_callback=None) as session:
                # Initialize the connection
                await session.initialize()
                
                # Call the specified tool with the provided arguments
                result = await session.call_tool(tool_name, arguments=arguments)
                
                # Format the result as a string
                response = ""
                for r in result.content:
                    response += r.text + "\n"
                
                return response.strip()
    except Exception as e:
        return f"Error invoking MCP tool: {str(e)}"

from datetime import datetime, UTC
current_utc_time = str(datetime.now(UTC))

def load_system_prompt():
    """
    Load the system prompt template from the system_prompt.txt file.
    
    Returns:
        str: The system prompt template
    """
    try:
        with open("agents/system_prompt.txt", "r") as f:
            return f.read()
    except Exception as e:
        print(f"Error loading system prompt: {e}")
        # Provide a minimal fallback prompt in case the file can't be loaded
        return """
        <instructions>
        You are a highly capable AI assistant designed to solve problems for users.
        Current UTC time: {current_utc_time}
        MCP Registry URL: {mcp_registry_url}
        </instructions>
        """

def print_agent_response(response_dict: Dict[str, Any]) -> None:
    """
    Parse and print all messages in the response with color coding

    Args:
        response_dict: Dictionary containing the agent response with 'messages' key
    """
    # Define ANSI color codes for different message types
    COLORS = {
        "SYSTEM": "\033[1;33m",  # Yellow
        "HUMAN": "\033[1;32m",   # Green
        "AI": "\033[1;36m",      # Cyan
        "TOOL": "\033[1;35m",    # Magenta
        "UNKNOWN": "\033[1;37m", # White
        "RESET": "\033[0m"       # Reset to default
    }
    if 'messages' not in response_dict:
        print("No messages found in response")
        return
    
    messages = response_dict['messages']
    blue = "\033[1;34m"  # Blue
    reset = COLORS["RESET"]
    print(f"\n{blue}=== Found {len(messages)} messages ==={reset}\n")
    
    for i, message in enumerate(messages, 1):
        # Determine message type based on class name or type
        message_type = type(message).__name__
        
        if "SystemMessage" in message_type:
            msg_type = "SYSTEM"
        elif "HumanMessage" in message_type:
            msg_type = "HUMAN"
        elif "AIMessage" in message_type:
            msg_type = "AI"
        elif "ToolMessage" in message_type:
            msg_type = "TOOL"
        else:
            # Fallback to string matching if type name doesn't match expected patterns
            message_str = str(message)
            if "SystemMessage" in message_str:
                msg_type = "SYSTEM"
            elif "HumanMessage" in message_str:
                msg_type = "HUMAN"
            elif "AIMessage" in message_str:
                msg_type = "AI"
            elif "ToolMessage" in message_str:
                msg_type = "TOOL"
            else:
                msg_type = "UNKNOWN"
        
        # Get message content
        content = message.content if hasattr(message, 'content') else str(message)
        
        # Check for tool calls
        tool_calls = []
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.get('name', 'unknown')
                tool_args = tool_call.get('args', {})
                tool_calls.append(f"Tool: {tool_name}, Args: {tool_args}")
        
        # Get the color for this message type
        color = COLORS.get(msg_type, COLORS["UNKNOWN"])
        reset = COLORS["RESET"]
        
        # Print message with enhanced formatting and color coding - entire message in color
        print(f"\n{color}{'=' * 20} MESSAGE #{i} - TYPE: {msg_type} {'=' * 20}")
        print(f"{'-' * 80}")
        print(f"CONTENT: {content}")
        
        # Print any tool calls
        if tool_calls:
            print(f"\nTOOL CALLS:")
            for tc in tool_calls:
                print(f"  {tc}")
        print(f"{'=' * 20} END OF {msg_type} MESSAGE #{i} {'=' * 20}{reset}")
        print()

async def main():
    """
    Main function that:
    1. Parses command line arguments
    2. Sets up the LangChain MCP client and Bedrock model
    3. Creates a LangGraph agent with available tools
    4. Invokes the agent with the provided message
    5. Displays the response
    """
    # Parse command line arguments
    args = parse_arguments()
    
    # Display configuration
    server_url = args.mcp_registry_url
    print(f"Connecting to MCP server: {server_url}")
    print(f"Using model: {args.model}")
    print(f"Message: {args.message}")
    
    # Initialize the model
    model = ChatBedrockConverse(model_id=args.model, region_name='us-east-1')
    
    try:
        # Initialize MCP client with the server configuration
        client = MultiServerMCPClient(
            {
                "default_server": {
                    "url": server_url,
                    "transport": "sse",
                }
            }
        )
        print("Connected to MCP server successfully")

        # Get available tools from MCP and display them
        mcp_tools = await client.get_tools()
        print(f"Available MCP tools: {[tool.name for tool in mcp_tools]}")
        
        # Add the calculator and invoke_mcp_tool to the tools array
        all_tools = [calculator, invoke_mcp_tool] + mcp_tools
        print(f"All available tools: {[tool.name if hasattr(tool, 'name') else tool.__name__ for tool in all_tools]}")
        
        # Create the agent with the model and all tools
        agent = create_react_agent(
            model,
            all_tools
        )
        
        # Load and format the system prompt with the current time and MCP registry URL
        system_prompt_template = load_system_prompt()
        system_prompt = system_prompt_template.format(
            current_utc_time=current_utc_time,
            mcp_registry_url=args.mcp_registry_url
        )
        
        # Format the message with system message first
        formatted_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": args.message}
        ]
        
        print("\nInvoking agent...\n" + "-"*40)
        
        # Invoke the agent with the formatted messages
        response = await agent.ainvoke({"messages": formatted_messages})
        
        print("\nResponse:" + "\n" + "-"*40)
        #print(response)
        print_agent_response(response)
        
        # Process and display the response
        if response and "messages" in response and response["messages"]:
            # Get the last message from the response
            last_message = response["messages"][-1]
            
            if isinstance(last_message, dict) and "content" in last_message:
                # Display the content of the response
                print(last_message["content"])
            else:
                print(str(last_message.content))
        else:
            print("No valid response received")
                
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())