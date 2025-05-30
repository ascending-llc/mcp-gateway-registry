#!/usr/bin/env python3
"""
Strands MCP Client

This script demonstrates using Strands Agents with MCP tools to connect to an
MCP-compatible server and query information using a Bedrock-hosted Claude model.

The script accepts command line arguments for:
- Server host and port 
- Model ID to use
- User message to process

Usage:
    python strands_agent.py --mcp-registry-url URL --model model_id --message "your question"

Example:
    python strands_agent.py --mcp-registry-url https://mcpgateway.ddns.net/mcpgw/sse \
        --model us.anthropic.claude-3-5-haiku-20241022-v1:0 --message "what is the current time in Clarksburg, MD"
"""

import asyncio
import argparse
import re
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone

# Strands Imports
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

# MCP Imports  
import mcp
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.sse import sse_client

import logging

# Configure the root strands logger
logging.getLogger("strands").setLevel(logging.WARNING) # change to debug if needed

# Add a handler to see the logs
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", 
    handlers=[logging.StreamHandler()]
)

def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments for the Strands MCP client.
    
    Returns:
        argparse.Namespace: The parsed command line arguments
    """
    parser = argparse.ArgumentParser(description='Strands MCP Client')
    
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
def invoke_mcp_tool(mcp_registry_url: str, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Invoke a tool on an MCP server using the MCP Registry URL and server name.
    
    This tool creates an MCP SSE client and calls the specified tool with the provided arguments.
    
    Args:
        mcp_registry_url (str): The URL of the MCP Registry
        server_name (str): The name of the MCP server to connect to
        tool_name (str): The name of the tool to invoke
        arguments (Dict[str, Any]): Dictionary containing the arguments for the tool
    
    Returns:
        str: The result of the tool invocation as a string
    
    Example:
        invoke_mcp_tool("registry_url", "currenttime", "current_time_by_timezone", {"tz_name": "America/New_York"})
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
    print(f"Attempting to connect to server URL: {server_url}")
    
    async def _async_invoke():
        try:
            # Create an MCP SSE client and call the tool
            async with mcp.client.sse.sse_client(server_url) as (read, write):
                async with mcp.ClientSession(read, write, sampling_callback=None) as session:
                    # Initialize the connection
                    await session.initialize()
                    print(f"Connected to MCP server, calling tool: {tool_name} with args: {arguments}")
                    
                    # Call the specified tool with the provided arguments
                    result = await session.call_tool(tool_name, arguments=arguments)
                    
                    # Format the result as a string
                    response = ""
                    for r in result.content:
                        response += r.text + "\n"
                    
                    return response.strip()
        except Exception as e:
            error_msg = f"Error invoking MCP tool '{tool_name}' on server '{server_name}': {str(e)}"
            print(error_msg)
            return error_msg
    
    # Run the async function synchronously using different approaches
    try:
        # Try to get the current loop
        try:
            loop = asyncio.get_running_loop()
            print("Found running event loop, using thread executor")
            
            # We're already in an event loop, need to run in a separate thread
            import concurrent.futures
            import threading
            
            result_container = []
            error_container = []
            
            def run_in_thread():
                try:
                    # Create a new event loop for this thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(_async_invoke())
                        result_container.append(result)
                    finally:
                        new_loop.close()
                except Exception as e:
                    error_container.append(str(e))
            
            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join(timeout=30)  # 30 second timeout
            
            if error_container:
                return f"Thread execution error: {error_container[0]}"
            elif result_container:
                return result_container[0]
            else:
                return "Tool invocation timed out after 30 seconds"
                
        except RuntimeError:
            # No event loop running, we can use asyncio.run directly
            print("No running event loop found, using asyncio.run")
            return asyncio.run(_async_invoke())
            
    except Exception as e:
        error_msg = f"Error running async MCP tool invocation: {str(e)}"
        print(error_msg)
        return error_msg

def create_mcp_sse_client(server_url: str) -> MCPClient:
    """
    Create an MCP client for connecting to an SSE MCP server endpoint.
    
    This function creates a client that can connect to MCP servers via SSE transport.
    
    Args:
        server_url (str): The URL of the MCP SSE server
    
    Returns:
        MCPClient: The MCP client for SSE connections
    """
    try:
        print(f"Creating MCP SSE client for: {server_url}")
        
        # Create MCP client using SSE transport
        mcp_client = MCPClient(lambda: sse_client(server_url))
        
        return mcp_client
        
    except Exception as e:
        print(f"Failed to create MCP SSE client for {server_url}: {e}")
        raise

async def load_mcp_tools_from_sse_server(server_url: str) -> List[Any]:
    """
    Load tools from MCP server via SSE connection.
    
    Args:
        server_url (str): The URL of the MCP SSE server
    
    Returns:
        List[Any]: List of MCP tools
    """
    try:
        print(f"Connecting to MCP server via SSE: {server_url}")
        
        # Create MCP client for SSE connection
        mcp_client = create_mcp_sse_client(server_url)
        
        # Get tools from the MCP client
        mcp_client.start()
        tools = mcp_client.list_tools_sync()
        
        print(f"Successfully loaded {len(tools)} tools from MCP server")
        
        # Debug: Let's examine the tool objects to understand their structure
        for i, tool_obj in enumerate(tools):
            try:
                # Use the helper functions to get tool name and description
                tool_name = get_tool_name(tool_obj)
                tool_desc = get_tool_description(tool_obj)
                
                print(f"  - {tool_name}: {tool_desc}")
                print(f"    Tool type: {type(tool_obj)}")
                
                # Show key attributes for debugging
                key_attrs = []
                if hasattr(tool_obj, 'tool_name'):
                    key_attrs.append(f"tool_name='{tool_obj.tool_name}'")
                if hasattr(tool_obj, 'mcp_tool'):
                    key_attrs.append(f"mcp_tool={type(tool_obj.mcp_tool)}")
                if hasattr(tool_obj, 'tool_spec'):
                    key_attrs.append(f"tool_spec={type(tool_obj.tool_spec)}")
                    
                if key_attrs:
                    print(f"    Key attributes: {', '.join(key_attrs)}")
                
            except Exception as tool_error:
                print(f"  - Tool {i}: Error examining tool - {tool_error}")
                print(f"    Tool type: {type(tool_obj)}")
        
        return tools
        
    except Exception as e:
        print(f"Error loading MCP tools from SSE server: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        print("Falling back to manual tool invocation via invoke_mcp_tool")
        return []

# Get current UTC time for the system prompt
current_utc_time = str(datetime.now(timezone.utc))

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

def print_agent_response(response: str) -> None:
    """
    Print the agent response with color coding for better readability.

    Args:
        response: The response string from the agent
    """
    # Define ANSI color codes
    blue = "\033[1;34m"  # Blue
    cyan = "\033[1;36m"  # Cyan  
    reset = "\033[0m"    # Reset to default
    
    print(f"\n{blue}=== STRANDS AGENT RESPONSE ==={reset}")
    print(f"{cyan}{response}{reset}")
    print(f"{blue}=== END OF RESPONSE ==={reset}\n")

def get_tool_name(tool_obj) -> str:
    """
    Safely extract the name from a tool object, handling different tool types.
    
    Args:
        tool_obj: The tool object to extract name from
    
    Returns:
        str: The tool name or a fallback name
    """
    try:
        # Method 1: MCPAgentTool with tool_name attribute (most likely for Strands)
        if hasattr(tool_obj, 'tool_name'):
            return str(tool_obj.tool_name)
            
        # Method 2: Direct name attribute
        elif hasattr(tool_obj, 'name'):
            return str(tool_obj.name)
            
        # Method 3: Check if it's an MCPAgentTool with a tool property
        elif hasattr(tool_obj, 'tool') and hasattr(tool_obj.tool, 'name'):
            return str(tool_obj.tool.name)
            
        # Method 4: Check other common attributes
        elif hasattr(tool_obj, '_name'):
            return str(tool_obj._name)
            
        # Method 5: Check if it has a function name
        elif hasattr(tool_obj, '__name__'):
            return str(tool_obj.__name__)
            
        # Fallback: use class name
        else:
            return f"{type(tool_obj).__name__}"
            
    except Exception:
        return f"{type(tool_obj).__name__}_unknown"

def get_tool_description(tool_obj) -> str:
    """
    Safely extract the description from a tool object.
    
    Args:
        tool_obj: The tool object to extract description from
    
    Returns:
        str: The tool description or a fallback description
    """
    try:
        # Method 1: MCPAgentTool with mcp_tool attribute
        if hasattr(tool_obj, 'mcp_tool') and hasattr(tool_obj.mcp_tool, 'description'):
            return str(tool_obj.mcp_tool.description)
            
        # Method 2: Direct description attribute
        elif hasattr(tool_obj, 'description'):
            return str(tool_obj.description)
            
        # Method 3: Check if it's an MCPAgentTool with a tool property
        elif hasattr(tool_obj, 'tool') and hasattr(tool_obj.tool, 'description'):
            return str(tool_obj.tool.description)
            
        # Method 4: Check tool_spec
        elif hasattr(tool_obj, 'tool_spec') and hasattr(tool_obj.tool_spec, 'description'):
            return str(tool_obj.tool_spec.description)
            
        else:
            return "No description available"
            
    except Exception:
        return "Description unavailable"

async def main():
    """
    Main function that:
    1. Parses command line arguments
    2. Sets up the Strands agent with Bedrock model and tools
    3. Loads tools from MCP server via SSE
    4. Invokes the agent with the provided message
    5. Displays the response
    """
    # Parse command line arguments
    args = parse_arguments()
    
    # Display configuration
    print(f"MCP Registry URL: {args.mcp_registry_url}")
    print(f"Using model: {args.model}")
    print(f"Message: {args.message}")
    
    try:
        # Initialize the Bedrock model
        bedrock_model = BedrockModel(
            model_id=args.model,
            region_name='us-east-1'  # You can make this configurable if needed
        )
        
        # Load tools from MCP server via SSE
        print(f"\nConnecting to MCP server via SSE: {args.mcp_registry_url}")
        mcp_tools = await load_mcp_tools_from_sse_server(args.mcp_registry_url)
        
        # Define all available tools for the agent
        all_tools = [calculator, invoke_mcp_tool] + mcp_tools
        
        print(f"\nAvailable tools:")
        print(f"  Built-in tools: calculator, invoke_mcp_tool")
        if mcp_tools:
            tool_names = [get_tool_name(tool) for tool in mcp_tools]
            print(f"  MCP tools loaded: {tool_names}")
            if 'intelligent_tool_finder' in tool_names:
                print(f"  ✅ intelligent_tool_finder available for tool discovery")
        else:
            print(f"  MCP tools: None loaded (using invoke_mcp_tool for manual calls)")
        
        print(f"  Total tools: {len(all_tools)}")
        
        # Load and format the system prompt with the current time and MCP registry URL
        system_prompt_template = load_system_prompt()
        system_prompt = system_prompt_template.format(
            current_utc_time=current_utc_time,
            mcp_registry_url=args.mcp_registry_url
        )
        
        # Create the Strands agent with the model, tools, and system prompt
        agent = Agent(
            model=bedrock_model,
            tools=all_tools,
            system_prompt=system_prompt
        )
        
        print("\nInvoking Strands agent...\n" + "-"*50)
        
        # Invoke the agent with the user message - fix async generator handling
        response_generator = agent.stream_async(args.message)
        
        # Collect and display the streaming response
        full_response = ""
        async for chunk in response_generator:
            if hasattr(chunk, 'content') and chunk.content:
                print(chunk.content, end='', flush=True)
                full_response += chunk.content
            elif hasattr(chunk, 'text') and chunk.text:
                print(chunk.text, end='', flush=True) 
                full_response += chunk.text
            elif isinstance(chunk, str):
                print(chunk, end='', flush=True)
                full_response += chunk
        
        print("\n" + "-"*50)
        print("Agent execution completed successfully!")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
