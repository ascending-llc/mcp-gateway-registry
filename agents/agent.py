#!/usr/bin/env python3
"""
LangGraph MCP Client with Cognito Authentication

This script demonstrates using LangGraph with the MultiServerMCPClient adapter to connect to an
MCP-compatible server with Cognito M2M authentication and query information using an Anthropic Claude model.

The script accepts command line arguments for:
- Server host and port
- Model ID to use
- User message to process
- Cognito authentication parameters

Configuration can be provided via command line arguments or environment variables.
Command line arguments take precedence over environment variables.

Environment Variables:
- COGNITO_CLIENT_ID: Cognito App Client ID
- COGNITO_CLIENT_SECRET: Cognito App Client Secret
- COGNITO_USER_POOL_ID: Cognito User Pool ID
- AWS_REGION: AWS region for Cognito

Usage:
    python agent.py --mcp-registry-url URL --model model_id --message "your question" \
        --client-id CLIENT_ID --client-secret CLIENT_SECRET --user-pool-id USER_POOL_ID --region REGION

Example with command line arguments:
    python agent.py --mcp-registry-url http://localhost/mcpgw/sse \
        --model claude-3-5-haiku-20241022 --message "current time in new delhi" \
        --client-id [REDACTED] --client-secret [REDACTED] \
        --user-pool-id [REDACTED] --region us-east-1

Example with environment variables (create a .env file):
    COGNITO_CLIENT_ID=your_client_id
    COGNITO_CLIENT_SECRET=your_client_secret
    COGNITO_USER_POOL_ID=your_user_pool_id
    AWS_REGION=us-east-1
    
    python agent.py --message "current time in new delhi"

Example with custom environment files:
    python agent.py --user-env-file .env.myuser --agent-env-file .env.myagent --message "your question"
"""

import asyncio
import argparse
import re
import sys
import os
import logging
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, urljoin
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
import mcp
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
import httpx
import re

# Import dotenv for loading environment variables
from dotenv import load_dotenv

# Add the auth_server directory to the path to import cognito_utils
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'auth_server'))
from cognito_utils import generate_token

# Import the httpx patch context manager
from httpx_patch import httpx_mount_path_patch

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

# Get logger
logger = logging.getLogger(__name__)

# Global constant for default MCP tool name to filter and use
DEFAULT_MCP_TOOL_NAME = "intelligent_tool_finder"


def enable_verbose_logging():
    """Enable verbose debug logging for HTTP libraries and main logger."""
    # Set main logger to DEBUG level
    logger.setLevel(logging.DEBUG)
    
    # Enable debug logging for httpx to see request/response details
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.DEBUG)
    httpx_logger.propagate = True

    # Enable debug logging for httpcore (underlying HTTP library)
    httpcore_logger = logging.getLogger("httpcore")
    httpcore_logger.setLevel(logging.DEBUG)
    httpcore_logger.propagate = True

    # Enable debug logging for mcp client libraries
    mcp_logger = logging.getLogger("mcp")
    mcp_logger.setLevel(logging.DEBUG)
    mcp_logger.propagate = True
    
    logger.info("Verbose logging enabled for httpx, httpcore, mcp libraries, and main logger")

def get_auth_mode_from_args() -> tuple[bool, str, str]:
    """
    Parse command line arguments to determine authentication mode and env file names.
    This is done before loading environment variables to choose the correct .env file.
    
    Returns:
        tuple: (use_session_cookie, user_env_file, agent_env_file)
            - use_session_cookie: True if using session cookie authentication, False for M2M authentication
            - user_env_file: Name of the env file for user authentication
            - agent_env_file: Name of the env file for agent authentication
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--use-session-cookie', action='store_true',
                        help='Use session cookie authentication instead of M2M')
    parser.add_argument('--user-env-file', type=str, default='.env.user',
                        help='Name of the environment file for user authentication (default: .env.user)')
    parser.add_argument('--agent-env-file', type=str, default='.env.agent',
                        help='Name of the environment file for agent authentication (default: .env.agent)')
    args, _ = parser.parse_known_args()
    return args.use_session_cookie, args.user_env_file, args.agent_env_file

def print_env_file_banner(env_file_name: str, use_session_cookie: bool, file_found: bool, file_path: str = None):
    """
    Print a prominent banner showing which .env file is being used and why.
    
    Args:
        env_file_name: Name of the .env file being used
        use_session_cookie: Whether session cookie authentication is being used
        file_found: Whether the .env file was found
        file_path: Full path to the .env file if found
    """
    print("\n" + "="*80)
    print("🔧 ENVIRONMENT CONFIGURATION")
    print("="*80)
    
    auth_mode = "Session Cookie Authentication" if use_session_cookie else "M2M Authentication"
    print(f"Authentication Mode: {auth_mode}")
    print(f"Expected .env file: {env_file_name}")
    
    if use_session_cookie:
        print(f"Reason: --use-session-cookie flag specified, using {env_file_name} for user credentials")
    else:
        print(f"Reason: M2M authentication (default), using {env_file_name} for machine credentials")
    
    if file_found and file_path:
        print(f"✅ Found and loaded: {file_path}")
    else:
        print(f"⚠️  File not found: {env_file_name}")
        print("   Falling back to system environment variables")
    
    print("="*80 + "\n")

def load_env_config(use_session_cookie: bool, user_env_file: str = '.env.user', agent_env_file: str = '.env.agent') -> Dict[str, Optional[str]]:
    """
    Load configuration from .env file based on authentication mode.
    Uses .env.user for session cookie auth, .env.agent for M2M auth.
    
    Args:
        use_session_cookie: True for session cookie auth (.env.user), False for M2M auth (.env.agent)
    
    Returns:
        Dict[str, Optional[str]]: Dictionary containing environment variables
    """
    env_config = {
        'client_id': None,
        'client_secret': None,
        'region': None,
        'user_pool_id': None,
        'domain': None,
        'anthropic_api_key': None
    }
    
    # Choose .env file based on authentication mode
    env_file_name = user_env_file if use_session_cookie else agent_env_file
    logger.info(f"Using .env file: {env_file_name}")
    # Load environment variables using dotenv
    file_found = False
    file_path = None
    
    # Try to load from .env file in the current directory
    env_file = os.path.join(os.path.dirname(__file__), env_file_name)
    if os.path.exists(env_file):
        logger.info(f"Found .env file: {env_file}")
        load_dotenv(env_file, override=True)
        file_found = True
        file_path = env_file
        logger.info(f"Loading environment variables from {env_file}")
        logger.info(f"user pool id {os.environ.get('COGNITO_USER_POOL_ID')}")
    else:
        # Try to load from .env file in the parent directory
        env_file = os.path.join(os.path.dirname(__file__), '..', env_file_name)
        if os.path.exists(env_file):
            logger.info(f"Found .env file in parent directory: {env_file}")
            load_dotenv(env_file, override=True)
            logger.info(f"Loading environment variables from {env_file}")
        else:
            # Try to load from current working directory
            env_file = os.path.join(os.getcwd(), env_file_name)
            if os.path.exists(env_file):
                logger.info(f"Found .env file in current working directory: {env_file}")
                load_dotenv(env_file, override=True)
                logger.info(f"Loading environment variables from {env_file}")
            else:
                # Fallback to default .env loading
                load_dotenv(override=True)
                logger.info("Loading environment variables from default .env file")
    
    # Print banner showing which file is being used
    print_env_file_banner(env_file_name, use_session_cookie, file_found, file_path)
    
    # Get values from environment
    env_config['client_id'] = os.getenv('COGNITO_CLIENT_ID')
    env_config['client_secret'] = os.getenv('COGNITO_CLIENT_SECRET')
    env_config['region'] = os.getenv('AWS_REGION')
    env_config['user_pool_id'] = os.getenv('COGNITO_USER_POOL_ID')
    env_config['domain'] = os.getenv('COGNITO_DOMAIN')
    env_config['anthropic_api_key'] = os.getenv('ANTHROPIC_API_KEY')
    
    return env_config

def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments for the LangGraph MCP client with Cognito authentication.
    Command line arguments take precedence over environment variables.
    
    Returns:
        argparse.Namespace: The parsed command line arguments
    """
    # First, determine authentication mode and env file names to choose correct .env file
    use_session_cookie, user_env_file, agent_env_file = get_auth_mode_from_args()
    logger.info(f"Using session cookie authentication: {use_session_cookie}")
    logger.info(f"User env file: {user_env_file}, Agent env file: {agent_env_file}")
    
    # Load environment configuration using the appropriate .env file
    env_config = load_env_config(use_session_cookie, user_env_file, agent_env_file)
    
    parser = argparse.ArgumentParser(description='LangGraph MCP Client with Cognito Authentication')
    
    # Server connection arguments
    parser.add_argument('--mcp-registry-url', type=str, default='https://mcpgateway.ddns.net/mcpgw/sse',
                        help='Hostname of the MCP Registry')
    
    # Model arguments
    parser.add_argument('--model', type=str, default='claude-3-5-haiku-20241022',
                        help='Model ID to use with Anthropic')
    
    # Message arguments
    parser.add_argument('--message', type=str, default='what is the current time in Clarksburg, MD',
                        help='Message to send to the agent')
    
    # MCP tool filtering arguments
    parser.add_argument('--mcp-tool-name', type=str, default=DEFAULT_MCP_TOOL_NAME,
                        help=f'Name of the MCP tool to filter and use (default: {DEFAULT_MCP_TOOL_NAME})')
    
    # Verbose logging argument
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose HTTP debugging output')
    
    # Authentication method arguments
    parser.add_argument('--use-session-cookie', action='store_true',
                        help='Use session cookie authentication instead of M2M')
    parser.add_argument('--session-cookie-file', type=str, default='~/.mcp/session_cookie',
                        help='Path to session cookie file (default: ~/.mcp/session_cookie)')
    parser.add_argument('--jwt-token', type=str,
                        help='Use a pre-generated JWT token instead of generating M2M token')
    
    # Environment file configuration arguments
    parser.add_argument('--user-env-file', type=str, default=user_env_file,
                        help=f'Name of the environment file for user authentication (default: {user_env_file})')
    parser.add_argument('--agent-env-file', type=str, default=agent_env_file,
                        help=f'Name of the environment file for agent authentication (default: {agent_env_file})')
    
    # Cognito authentication arguments - now optional if available in environment
    parser.add_argument('--client-id', type=str, default=env_config['client_id'],
                        help='Cognito App Client ID (can be set via COGNITO_CLIENT_ID env var)')
    parser.add_argument('--client-secret', type=str, default=env_config['client_secret'],
                        help='Cognito App Client Secret (can be set via COGNITO_CLIENT_SECRET env var)')
    parser.add_argument('--user-pool-id', type=str, default=env_config['user_pool_id'],
                        help='Cognito User Pool ID (can be set via COGNITO_USER_POOL_ID env var)')
    parser.add_argument('--region', type=str, default=env_config['region'],
                        help='AWS region for Cognito (can be set via AWS_REGION env var)')
    parser.add_argument('--domain', type=str, default=env_config['domain'],
                        help='Cognito custom domain (can be set via COGNITO_DOMAIN env var)')
    parser.add_argument('--scopes', type=str, nargs='*', default=None,
                        help='Optional scopes for the token request')
    
    args = parser.parse_args()
    
    # Enable verbose logging if requested
    if args.verbose:
        enable_verbose_logging()
    
    # Validate authentication parameters based on method
    if args.use_session_cookie:
        # For session cookie auth, we just need the cookie file
        cookie_path = os.path.expanduser(args.session_cookie_file)
        if not os.path.exists(cookie_path):
            parser.error(f"Session cookie file not found: {cookie_path}\n"
                        f"Run 'python agents/cli_user_auth.py' to authenticate first")
    elif args.jwt_token:
        # For pre-generated JWT token, we only need the token and basic headers
        if not args.user_pool_id:
            args.user_pool_id = 'us-east-1_EXAMPLE'  # Default fallback
        if not args.client_id:
            args.client_id = 'user-generated'  # Default for user-generated tokens
        if not args.region:
            args.region = 'us-east-1'  # Default region
    else:
        # For M2M auth, validate Cognito parameters
        missing_params = []
        if not args.client_id:
            missing_params.append('--client-id (or COGNITO_CLIENT_ID env var)')
        if not args.client_secret:
            missing_params.append('--client-secret (or COGNITO_CLIENT_SECRET env var)')
        if not args.user_pool_id:
            missing_params.append('--user-pool-id (or COGNITO_USER_POOL_ID env var)')
        if not args.region:
            missing_params.append('--region (or AWS_REGION env var)')
        
        if missing_params:
            parser.error(f"Missing required parameters for M2M authentication: {', '.join(missing_params)}")
    
    return args

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
async def invoke_mcp_tool(mcp_registry_url: str, server_name: str, tool_name: str, arguments: Dict[str, Any],
                         supported_transports: List[str] = None) -> str:
    """
    Invoke a tool on an MCP server using the MCP Registry URL and server name with authentication.
    
    This tool creates an MCP client and calls the specified tool with the provided arguments.
    Authentication details are automatically retrieved from the system configuration.
    
    Args:
        mcp_registry_url (str): The URL of the MCP Registry
        server_name (str): The name of the MCP server to connect to
        tool_name (str): The name of the tool to invoke
        arguments (Dict[str, Any]): Dictionary containing the arguments for the tool
        supported_transports (List[str]): Transport protocols supported by the server (["sse"] or ["streamable-http"])
    
    Returns:
        str: The result of the tool invocation as a string
    
    Example:
        invoke_mcp_tool("registry url", "currenttime", "current_time_by_timezone", {"tz_name": "America/New_York"}, ["streamable-http"])
    """
    # Construct the MCP server URL from the registry URL and server name using standard URL parsing
    parsed_url = urlparse(mcp_registry_url)
    
    # Extract the scheme, netloc and path from the parsed URL
    scheme = parsed_url.scheme
    netloc = parsed_url.netloc
    path = parsed_url.path
    
    # Use only the base URL (scheme + netloc) without any path
    base_url = f"{scheme}://{netloc}"
    
    # Create the server URL by joining the base URL with the server name
    # Remove leading slash from server_name if present to avoid double slashes
    if server_name.startswith('/'):
        server_name = server_name[1:]
    server_url = urljoin(base_url + '/', server_name)
    logger.info(f"invoke_mcp_tool, Initial Server URL: {server_url}")
    
    # Use context manager to apply httpx monkey patch
    
    # Get authentication parameters from global agent_settings object
    # These will be populated by the main function when it generates the token
    auth_token = agent_settings.auth_token
    user_pool_id = agent_settings.user_pool_id
    client_id = agent_settings.client_id
    region = agent_settings.region or 'us-east-1'
    session_cookie = agent_settings.session_cookie
    
    # Determine auth method based on what's available
    if session_cookie:
        auth_method = 'session_cookie'
    else:
        auth_method = 'm2m'
    
    # Prepare headers based on authentication method
    headers = {
        'X-User-Pool-Id': user_pool_id or '',
        'X-Client-Id': client_id or '',
        'X-Region': region or 'us-east-1'
    }
    
    # TRACE: Print all parameters received by invoke_mcp_tool
    logger.debug(f"invoke_mcp_tool TRACE - Parameters received:")
    logger.debug(f"  mcp_registry_url: {mcp_registry_url}")
    logger.debug(f"  server_name: {server_name}")
    logger.debug(f"  tool_name: {tool_name}")
    logger.debug(f"  arguments: {arguments}")
    logger.debug(f"  auth_token: {auth_token[:50] if auth_token else 'None'}...")
    logger.debug(f"  user_pool_id: {user_pool_id}")
    logger.debug(f"  client_id: {client_id}")
    logger.debug(f"  region: {region}")
    logger.debug(f"  auth_method: {auth_method}")
    logger.debug(f"  session_cookie: {session_cookie}")
    logger.debug(f"  supported_transports: {supported_transports}")
    logger.debug(f"invoke_mcp_tool TRACE - Headers built: {headers}")
    
    # Check for server-specific AUTH_TOKEN environment variable
    # Convert server_name to env var format: /sre-gateway -> SRE_GATEWAY_AUTH_TOKEN
    server_env_name = server_name.strip('/').upper().replace('-', '_') + '_AUTH_TOKEN'
    server_auth_token = os.environ.get(server_env_name)
    
    if server_auth_token:
        logger.info(f"Found server-specific auth token in environment variable: {server_env_name}")
        # Use the server-specific token for Authorization header
        headers['Authorization'] = f'Bearer {server_auth_token}'
    
    if auth_method == "session_cookie" and session_cookie:
        headers['Cookie'] = f'mcp_gateway_session={session_cookie}'
        redacted_headers = {
            'Cookie': f'mcp_gateway_session={redact_sensitive_value(session_cookie)}',
            'X-User-Pool-Id': redact_sensitive_value(user_pool_id) if user_pool_id else '',
            'X-Client-Id': redact_sensitive_value(client_id) if client_id else '',
            'X-Region': region or 'us-east-1'
        }
        if server_auth_token:
            redacted_headers['Authorization'] = f'Bearer {redact_sensitive_value(server_auth_token)}'
    else:
        headers['X-Authorization'] = f'Bearer {auth_token}'
        # If no server-specific token, use the general auth_token
        if not server_auth_token:
            headers['Authorization'] = f'Bearer {auth_token}'
        redacted_headers = {
            'Authorization': f'Bearer {redact_sensitive_value(server_auth_token or auth_token)}',
            'X-Authorization': f'Bearer {redact_sensitive_value(auth_token)}',
            'X-User-Pool-Id': redact_sensitive_value(user_pool_id) if user_pool_id else '',
            'X-Client-Id': redact_sensitive_value(client_id) if client_id else '',
            'X-Region': region or 'us-east-1'
        }
    
    try:
        # Determine transport based on supported_transports
        use_sse = supported_transports and "sse" in supported_transports
        transport_name = "SSE" if use_sse else "streamable-http"
        
        # For transport through the gateway, we need to append the transport endpoint
        # The nginx gateway expects the full path including the transport endpoint
        if use_sse:
            if not server_url.endswith('/'):
                server_url += '/'
            server_url += 'sse'
            logger.info(f"invoke_mcp_tool, Using SSE transport with gateway URL: {server_url}")
        else:
            if not server_url.endswith('/'):
                server_url += '/'
            server_url += 'mcp'
            logger.info(f"invoke_mcp_tool, Using streamable-http transport with gateway URL: {server_url}")
        
        # Use context manager to apply httpx monkey patch and create MCP client
        async with httpx_mount_path_patch(server_url):
            logger.info(f"invoke_mcp_tool, Connecting to MCP server using {transport_name}: {server_url}, headers: {redacted_headers}")
            
            if use_sse:
                # Create an MCP SSE client
                async with sse_client(server_url, headers=headers) as (read, write):
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
            else:
                # Create an MCP streamable-http client
                async with streamablehttp_client(url=server_url, headers=headers) as (read, write, get_session_id):
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

# Global agent settings to store authentication details
class AgentSettings:
    def __init__(self):
        self.auth_token = None
        self.user_pool_id = None
        self.client_id = None
        self.region = None
        self.session_cookie = None

agent_settings = AgentSettings()

def redact_sensitive_value(value: str, show_chars: int = 4) -> str:
    """Redact sensitive values, showing only the first few characters"""
    if not value or len(value) <= show_chars:
        return "*" * len(value) if value else ""
    return value[:show_chars] + "*" * (len(value) - show_chars)


def load_system_prompt():
    """
    Load the system prompt template from the system_prompt.txt file.
    
    Returns:
        str: The system prompt template
    """
    import os
    try:
        # Get the directory where this Python file is located
        current_dir = os.path.dirname(__file__)
        system_prompt_path = os.path.join(current_dir, "system_prompt.txt")
        with open(system_prompt_path, "r") as f:
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
        logger.warning("No messages found in response")
        return
    
    messages = response_dict['messages']
    blue = "\033[1;34m"  # Blue
    reset = COLORS["RESET"]
    logger.info(f"\n{blue}=== Found {len(messages)} messages ==={reset}\n")
    
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
        
        # Log message with enhanced formatting and color coding - entire message in color
        logger.info(f"\n{color}{'=' * 20} MESSAGE #{i} - TYPE: {msg_type} {'=' * 20}")
        logger.info(f"{'-' * 80}")
        logger.info(f"CONTENT: {content}")
        
        # Log any tool calls
        if tool_calls:
            logger.info(f"\nTOOL CALLS:")
            for tc in tool_calls:
                logger.info(f"  {tc}")
        logger.info(f"{'=' * 20} END OF {msg_type} MESSAGE #{i} {'=' * 20}{reset}")
        logger.info("")

async def main():
    """
    Main function that:
    1. Parses command line arguments
    2. Generates Cognito M2M authentication token OR loads session cookie
    3. Sets up the LangChain MCP client and Bedrock model with authentication
    4. Creates a LangGraph agent with available tools
    5. Invokes the agent with the provided message
    6. Displays the response
    """
    # Parse command line arguments
    args = parse_arguments()
    logger.info(f"Parsed command line arguments successfully, args={args}")
    
    # Display configuration
    server_url = args.mcp_registry_url
    logger.info(f"Connecting to MCP server: {server_url}")
    logger.info(f"Using model: {args.model}")
    logger.info(f"Message: {args.message}")
    if args.jwt_token:
        auth_display = 'Pre-generated JWT Token'
    elif args.use_session_cookie:
        auth_display = 'Session Cookie'
    else:
        auth_display = 'M2M Token'
    logger.info(f"Authentication method: {auth_display}")
    
    # Initialize authentication variables
    access_token = None
    session_cookie = None
    auth_method = "session_cookie" if args.use_session_cookie else "m2m"
    
    if args.jwt_token:
        # Use pre-generated JWT token
        access_token = args.jwt_token
        logger.info("Using pre-generated JWT token")
        
        # Set global auth variables for invoke_mcp_tool (JWT token mode)
        agent_settings.auth_token = access_token
        agent_settings.user_pool_id = args.user_pool_id
        agent_settings.client_id = args.client_id
        agent_settings.region = args.region
    elif args.use_session_cookie:
        # Load session cookie from file
        try:
            cookie_path = os.path.expanduser(args.session_cookie_file)
            with open(cookie_path, 'r') as f:
                session_cookie = f.read().strip()
            logger.info(f"Successfully loaded session cookie from {cookie_path}")
        except Exception as e:
            logger.error(f"Failed to load session cookie: {e}")
            return
            
        # Set global auth variables for invoke_mcp_tool (session cookie mode)
        agent_settings.auth_token = None
        agent_settings.user_pool_id = args.user_pool_id
        agent_settings.client_id = args.client_id
        agent_settings.region = args.region
        agent_settings.session_cookie = session_cookie
    else:
        # Generate Cognito M2M authentication token
        logger.info(f"Cognito User Pool ID: {redact_sensitive_value(args.user_pool_id)}")
        logger.info(f"Cognito User Pool ID: {args.user_pool_id}")
        logger.info(f"Cognito Client ID: {redact_sensitive_value(args.client_id)}")
        logger.info(f"AWS Region: {args.region}")
        
        try:
            logger.info("Generating Cognito M2M authentication token...")
            token_data = generate_token(
                client_id=args.client_id,
                client_secret=args.client_secret,
                user_pool_id=args.user_pool_id,
                region=args.region,
                scopes=args.scopes,
                domain=args.domain
            )
            access_token = token_data.get('access_token')
            if not access_token:
                raise ValueError("No access token received from Cognito")
            logger.info("Successfully generated authentication token")
            
            # Set global auth variables for invoke_mcp_tool
            agent_settings.auth_token = access_token
            agent_settings.user_pool_id = args.user_pool_id
            agent_settings.client_id = args.client_id
            agent_settings.region = args.region
        except Exception as e:
            logger.error(f"Failed to generate authentication token: {e}")
            return
    
    # Get Anthropic API key from environment variables
    anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
    if not anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY not found in environment variables")
        return
    
    # Initialize the model with Anthropic
    model = ChatAnthropic(
        model=args.model,
        api_key=anthropic_api_key,
        temperature=0,
        max_tokens=8192,
    )
    
    try:
        # Prepare headers for MCP client authentication based on method
        if args.use_session_cookie:
            auth_headers = {
                'Cookie': f'mcp_gateway_session={session_cookie}',
                'X-User-Pool-Id': args.user_pool_id or '',
                'X-Client-Id': args.client_id or '',
                'X-Region': args.region or 'us-east-1'
            }
        else:
            # For both M2M and pre-generated JWT tokens
            auth_headers = {
                'X-Authorization': f'Bearer {access_token}',
                'X-User-Pool-Id': args.user_pool_id,
                'X-Client-Id': args.client_id,
                'X-Region': args.region
            }
        
        # Log redacted headers
        redacted_headers = {}
        for k, v in auth_headers.items():
            if k in ['X-Authorization', 'Cookie', 'X-User-Pool-Id', 'X-Client-Id']:
                redacted_headers[k] = redact_sensitive_value(v) if v else ''
            else:
                redacted_headers[k] = v
        logger.info(f"Using authentication headers: {redacted_headers}")
        
        # Use context manager to apply httpx monkey patch
        async with httpx_mount_path_patch(server_url):
                # Initialize MCP client with the server configuration and authentication headers
                client = MultiServerMCPClient(
                    {
                        "mcp_registry": {
                            "url": server_url,
                            "transport": "sse",
                            "headers": auth_headers
                        }
                    }
                )
                logger.info("Connected to MCP server successfully with authentication, server_url: " + server_url)

                # Get available tools from MCP and display them
                mcp_tools = await client.get_tools()
                logger.info(f"Available MCP tools: {[tool.name for tool in mcp_tools]}")
                
                # Filter MCP tools to only include the specified tool
                filtered_tools = [tool for tool in mcp_tools if tool.name == args.mcp_tool_name]
                logger.info(f"Filtered MCP tools ({args.mcp_tool_name} only): {[tool.name for tool in filtered_tools]}")
                
                # Add only the calculator, invoke_mcp_tool, and the specified MCP tool to the tools array
                all_tools = [calculator, invoke_mcp_tool] + filtered_tools
                logger.info(f"All available tools: {[tool.name if hasattr(tool, 'name') else tool.__name__ for tool in all_tools]}")
                
                # Create the agent with the model and all tools
                agent = create_react_agent(
                    model,
                    all_tools
                )
                
                # Load and format the system prompt with the current time and MCP registry URL
                system_prompt_template = load_system_prompt()
                
                # Prepare authentication parameters for system prompt
                if args.use_session_cookie:
                    system_prompt = system_prompt_template.format(
                        current_utc_time=current_utc_time,
                        mcp_registry_url=args.mcp_registry_url,
                        auth_token='',  # Not used for session cookie auth
                        user_pool_id=args.user_pool_id or '',
                        client_id=args.client_id or '',
                        region=args.region or 'us-east-1',
                        auth_method=auth_method,
                        session_cookie=session_cookie
                    )
                else:
                    # For both M2M and pre-generated JWT tokens
                    system_prompt = system_prompt_template.format(
                        current_utc_time=current_utc_time,
                        mcp_registry_url=args.mcp_registry_url,
                        auth_token=access_token,
                        user_pool_id=args.user_pool_id,
                        client_id=args.client_id,
                        region=args.region,
                        auth_method=auth_method,
                        session_cookie=''  # Not used for JWT auth
                    )
                
                # Format the message with system message first
                formatted_messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": args.message}
                ]
                
                logger.info("\nInvoking agent...\n" + "-"*40)
                
                # Invoke the agent with the formatted messages
                response = await agent.ainvoke({"messages": formatted_messages})
                
                logger.info("\nResponse:" + "\n" + "-"*40)
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