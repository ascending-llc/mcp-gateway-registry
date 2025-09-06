#!/usr/bin/env python3
"""
Interactive LangGraph MCP Client with Cognito Authentication

This script provides an interactive version of the agent with multi-turn conversation support.
It maintains conversation history and allows continuous interaction with the agent.

The script accepts command line arguments for:
- Server host and port
- Model ID to use
- Initial prompt (optional)
- Cognito authentication parameters
- Interactive mode flag

Configuration can be provided via command line arguments or environment variables.
Command line arguments take precedence over environment variables.

Environment Variables:
- COGNITO_CLIENT_ID: Cognito App Client ID
- COGNITO_CLIENT_SECRET: Cognito App Client Secret
- COGNITO_USER_POOL_ID: Cognito User Pool ID
- AWS_REGION: AWS region for Cognito
- ANTHROPIC_API_KEY: Anthropic API key

Usage:
    # Interactive mode with initial prompt
    python agent_interactive.py --prompt "Hello" --interactive
    
    # Interactive mode without initial prompt
    python agent_interactive.py --interactive
    
    # Single-turn mode (like original agent.py)
    python agent_interactive.py --prompt "What time is it?"

Example with environment variables (create a .env file):
    COGNITO_CLIENT_ID=your_client_id
    COGNITO_CLIENT_SECRET=your_client_secret
    COGNITO_USER_POOL_ID=your_user_pool_id
    AWS_REGION=us-east-1
    ANTHROPIC_API_KEY=your_api_key
    
    python agent_interactive.py --interactive
"""

import asyncio
import argparse
import re
import sys
import os
import logging
import yaml
import json
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

# Global config for servers that should not have /mcp suffix added
SERVERS_NO_MCP_SUFFIX = ['/atlassian']

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

# Get logger
logger = logging.getLogger(__name__)

# Global constants for default MCP tools to filter and use
DEFAULT_MCP_TOOL_NAME = "intelligent_tool_finder"
ALLOWED_MCP_TOOLS = ["intelligent_tool_finder"]


def load_server_config(config_file: str = "server_config.yml") -> Dict[str, Any]:
    """
    Load server configuration from YAML file.
    
    Args:
        config_file: Path to the configuration file
        
    Returns:
        Dict containing server configurations
    """
    try:
        # Try to find config file in the same directory as this script
        config_path = os.path.join(os.path.dirname(__file__), config_file)
        if not os.path.exists(config_path):
            # Try current working directory
            config_path = config_file
            if not os.path.exists(config_path):
                logger.warning(f"Server config file not found: {config_file}. Using default configuration.")
                return {"servers": {}}
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            logger.info(f"Loaded server config from: {config_path}")
            return config or {"servers": {}}
    except Exception as e:
        logger.warning(f"Failed to load server config: {e}. Using default configuration.")
        return {"servers": {}}


def resolve_env_vars(value: str, server_name: str = None) -> str:
    """
    Resolve environment variable references in a string.
    Supports ${VAR_NAME} syntax.
    
    Args:
        value: String that may contain environment variable references
        server_name: Name of the server (for error context)
        
    Returns:
        String with environment variables resolved
        
    Raises:
        ValueError: If a required environment variable is not found
    """
    import re
    
    missing_vars = []
    
    def replace_env_var(match):
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            missing_vars.append(var_name)
            return match.group(0)  # Return original if not found
        return env_value
    
    # Find all ${VAR_NAME} patterns and replace them
    pattern = r'\$\{([^}]+)\}'
    resolved_value = re.sub(pattern, replace_env_var, value)
    
    # If any environment variables were missing, raise an error
    if missing_vars:
        server_context = f" for server '{server_name}'" if server_name else ""
        missing_list = "', '".join(missing_vars)
        raise ValueError(
            f"Missing required environment variable(s): '{missing_list}'{server_context}. "
            f"Please set these environment variables and try again."
        )
    
    return resolved_value


def get_server_headers(server_name: str, config: Dict[str, Any]) -> Dict[str, str]:
    """
    Get server-specific headers from configuration with environment variable resolution.
    
    Args:
        server_name: Name of the server (e.g., 'sre-gateway', 'atlassian')
        config: Loaded server configuration
        
    Returns:
        Dictionary of headers for the server
        
    Raises:
        ValueError: If required environment variables for the server are missing
    """
    servers = config.get("servers", {})
    server_config = servers.get(server_name, {})
    raw_headers = server_config.get("headers", {})
    
    if not raw_headers:
        logger.debug(f"No custom headers configured for server '{server_name}'")
        return {}
    
    # Resolve environment variables in header values
    resolved_headers = {}
    try:
        for header_name, header_value in raw_headers.items():
            resolved_value = resolve_env_vars(header_value, server_name)
            if resolved_value != header_value:
                logger.debug(f"Resolved header {header_name} for server {server_name}")
            resolved_headers[header_name] = resolved_value
        
        logger.info(f"Applied {len(resolved_headers)} custom headers for server '{server_name}'")
        return resolved_headers
        
    except ValueError as e:
        # Re-raise with additional context about which server failed
        logger.error(f"Failed to configure headers for server '{server_name}': {e}")
        raise


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
    Parse command line arguments for the Interactive LangGraph MCP client with Cognito authentication.
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
    
    parser = argparse.ArgumentParser(description='Interactive LangGraph MCP Client with Cognito Authentication')
    
    # Server connection arguments
    parser.add_argument('--mcp-registry-url', type=str, default='https://mcpgateway.ddns.net/mcpgw/mcp',
                        help='Hostname of the MCP Registry')
    
    # Model arguments
    parser.add_argument('--model', type=str, default='claude-3-5-haiku-20241022',
                        help='Model ID to use with Anthropic')
    
    # Prompt arguments (changed from --message)
    parser.add_argument('--prompt', type=str, default=None,
                        help='Initial prompt to send to the agent')
    
    # Interactive mode argument
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Enable interactive mode for multi-turn conversations')
    
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
            # No default fallback - require environment variable or command line arg
            pass
        if not args.client_id:
            # No default fallback - require environment variable or command line arg
            pass
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
                         supported_transports: List[str] = None, auth_provider: str = None) -> str:
    """
    Invoke a tool on an MCP server using the MCP Registry URL and server name with authentication.
    
    This tool creates an MCP client and calls the specified tool with the provided arguments.
    Authentication details are automatically retrieved from the system configuration.
    
    Args:
        mcp_registry_url (str): The URL of the MCP Registry
        server_name (str): The name of the MCP server to connect to
        tool_name (str): The name of the tool to invoke
        arguments (Dict[str, Any]): Dictionary containing the arguments for the tool
        supported_transports (List[str]): Transport protocols supported by the server (["streamable_http"] or ["sse"])
        auth_provider (str): The authentication provider for the server (e.g., "atlassian", "bedrock-agentcore")
    
    Returns:
        str: The result of the tool invocation as a string
    
    Example:
        invoke_mcp_tool("registry url", "currenttime", "current_time_by_timezone", {"tz_name": "America/New_York"}, ["streamable_http"])
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
    
    # Use ingress headers if available, otherwise fall back to the original auth
    if agent_settings.ingress_token:
        headers = {
            'X-Authorization': f'Bearer {agent_settings.ingress_token}',
            'X-User-Pool-Id': agent_settings.ingress_user_pool_id or '',
            'X-Client-Id': agent_settings.ingress_client_id or '',
            'X-Region': agent_settings.ingress_region or 'us-east-1'
        }
    else:
        # Fallback to original headers
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
    
    # Get server-specific headers from configuration
    server_name_clean = server_name.strip('/')
    server_headers = get_server_headers(server_name_clean, server_config)
    
    # Apply server-specific headers
    for header_name, header_value in server_headers.items():
        headers[header_name] = header_value
        
    # Check for egress authentication if auth_provider is specified
    if auth_provider:
        # Try to load egress token from {auth_provider}-{server_name}-egress.json
        oauth_tokens_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.oauth-tokens')
        # Convert server_name to lowercase and remove leading slash if present
        server_name_clean = server_name.strip('/').lower()
        egress_file = os.path.join(oauth_tokens_dir, f"{auth_provider.lower()}-{server_name_clean}-egress.json")
        
        # Also try without server name if the first file doesn't exist
        egress_file_alt = os.path.join(oauth_tokens_dir, f"{auth_provider.lower()}-egress.json")
        
        egress_data = None
        if os.path.exists(egress_file):
            logger.info(f"Found egress token file: {egress_file}")
            with open(egress_file, 'r') as f:
                egress_data = json.load(f)
        elif os.path.exists(egress_file_alt):
            logger.info(f"Found alternative egress token file: {egress_file_alt}")
            with open(egress_file_alt, 'r') as f:
                egress_data = json.load(f)
        
        if egress_data:
            # Add egress authorization header
            egress_token = egress_data.get('access_token')
            if egress_token:
                headers['Authorization'] = f'Bearer {egress_token}'
                logger.info(f"Added egress Authorization header for {auth_provider}")
            
            # Add provider-specific headers
            if auth_provider.lower() == 'atlassian':
                cloud_id = egress_data.get('cloud_id')
                if cloud_id:
                    headers['X-Atlassian-Cloud-Id'] = cloud_id
                    logger.info(f"Added X-Atlassian-Cloud-Id header: {cloud_id}")
        else:
            logger.warning(f"No egress token file found for auth_provider: {auth_provider}")
    
    if auth_method == "session_cookie" and session_cookie:
        headers['Cookie'] = f'mcp_gateway_session={session_cookie}'
    else:
        headers['X-Authorization'] = f'Bearer {auth_token}'
        # If no auth header from config and no egress token, use the general auth_token
        if 'Authorization' not in headers:
            headers['Authorization'] = f'Bearer {auth_token}'
    
    # Create redacted headers for logging (redact all sensitive values)
    redacted_headers = {}
    for header_name, header_value in headers.items():
        if header_name in ['Authorization', 'X-Authorization', 'Cookie', 'X-User-Pool-Id', 'X-Client-Id', 'X-Atlassian-Cloud-Id']:
            # Redact sensitive headers
            if header_name == 'Cookie':
                redacted_headers[header_name] = f'mcp_gateway_session={redact_sensitive_value(session_cookie if session_cookie else "")}'
            elif header_name in ['Authorization', 'X-Authorization'] and header_value.startswith('Bearer '):
                token_part = header_value[7:]  # Remove 'Bearer ' prefix
                redacted_headers[header_name] = f'Bearer {redact_sensitive_value(token_part)}'
            else:
                redacted_headers[header_name] = redact_sensitive_value(header_value)
        else:
            # Keep non-sensitive headers as-is
            redacted_headers[header_name] = header_value
    logger.info(f"headers after redaction: {headers}")
    try:
        # Determine transport based on supported_transports
        # Default to streamable_http, only use SSE if explicitly supported and no streamable_http
        use_sse = (supported_transports and 
                   "sse" in supported_transports and 
                   "streamable_http" not in supported_transports)
        transport_name = "SSE" if use_sse else "streamable_http"
        
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
            
            # Check if this server should skip the /mcp suffix
            server_path = '/' + server_name.strip('/')
            if server_path not in SERVERS_NO_MCP_SUFFIX:
                server_url += 'mcp'
                logger.info(f"invoke_mcp_tool, Using streamable_http transport with gateway URL: {server_url}")
            else:
                logger.info(f"invoke_mcp_tool, Using streamable_http transport without /mcp suffix for {server_name}: {server_url}")
        
        # Connect to MCP server and execute tool call
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
        # Ingress auth fields from .oauth-tokens/ingress.json
        self.ingress_token = None
        self.ingress_user_pool_id = None
        self.ingress_client_id = None
        self.ingress_region = None

agent_settings = AgentSettings()

# Global server configuration
server_config = {}

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

def print_agent_response(response_dict: Dict[str, Any], verbose: bool = False) -> None:
    """
    Parse and print the agent's response in a user-friendly way
    
    Args:
        response_dict: Dictionary containing the agent response with 'messages' key
        verbose: Whether to show detailed debug information
    """
    # Debug: Log entry to function
    logger.debug(f"print_agent_response called with verbose={verbose}, response_dict keys: {response_dict.keys() if response_dict else 'None'}")
    if verbose:
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
    
    # Always show the final AI response (both in verbose and non-verbose mode)
    # This section runs regardless of verbose flag
    if not verbose:
        logger.info("=== Attempting to print final response (non-verbose mode) ===")
    
    if response_dict and "messages" in response_dict and response_dict["messages"]:
        # Debug: Log that we're looking for the final AI message
        if not verbose:
            logger.info(f"Found {len(response_dict['messages'])} messages in response")
        
        # Get the last AI message from the response
        for message in reversed(response_dict["messages"]):
            message_type = type(message).__name__
            
            # Debug logging in non-verbose mode to understand what's happening
            if not verbose:
                logger.debug(f"Checking message type: {message_type}")
            
            # Check if this is an AI message
            if "AIMessage" in message_type or "ai" in str(type(message)).lower():
                # Extract and print the content
                content = None
                
                # Try different ways to extract content
                if hasattr(message, 'content'):
                    content = message.content
                elif isinstance(message, dict) and "content" in message:
                    content = message["content"]
                else:
                    # Try to extract content from string representation as last resort
                    try:
                        content = str(message)
                    except:
                        content = None
                
                # Print the content if we found any
                if content:
                    # Force print the final response regardless of any conditions
                    print("\n" + str(content), flush=True)
                    
                    if not verbose:
                        logger.info(f"Final AI Response printed (length: {len(str(content))} chars)")
                else:
                    if not verbose:
                        logger.warning(f"AI message found but no content extracted. Message type: {message_type}, Message attrs: {dir(message) if hasattr(message, '__dict__') else 'N/A'}")
                
                # We found an AI message, stop looking
                break
        else:
            # No AI message found - try to print the last message regardless
            if not verbose:
                logger.warning("No AI message found in response, attempting to print last message")
                logger.debug(f"Messages in response: {[type(m).__name__ for m in response_dict['messages']]}")
            
            # As a fallback, print the last message if it has content
            if response_dict["messages"]:
                last_message = response_dict["messages"][-1]
                content = None
                
                if hasattr(last_message, 'content'):
                    content = last_message.content
                elif isinstance(last_message, dict) and "content" in last_message:
                    content = last_message["content"]
                
                if content:
                    print("\n[Response]\n" + str(content), flush=True)
                    logger.info(f"Printed last message as fallback (type: {type(last_message).__name__})")


class InteractiveAgent:
    """Interactive agent that maintains conversation history"""
    
    def __init__(self, agent, system_prompt: str, verbose: bool = False):
        """
        Initialize the interactive agent
        
        Args:
            agent: The LangGraph agent instance
            system_prompt: The formatted system prompt
            verbose: Whether to show detailed debug output
        """
        self.agent = agent
        self.system_prompt = system_prompt
        self.verbose = verbose
        self.conversation_history = []
        
    async def process_message(self, user_input: str) -> Dict[str, Any]:
        """
        Process a user message and return the agent's response
        
        Args:
            user_input: The user's input message
            
        Returns:
            Dict containing the agent's response
        """
        # Build messages list with conversation history
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # Add conversation history
        for msg in self.conversation_history:
            messages.append(msg)
        
        # Add new user message
        messages.append({"role": "user", "content": user_input})
        
        if self.verbose:
            logger.info(f"\nSending {len(messages)} messages to agent (including system prompt)")
        
        # Invoke the agent
        response = await self.agent.ainvoke({"messages": messages})
        
        # Store the user message and AI response in history
        self.conversation_history.append({"role": "user", "content": user_input})
        
        # Extract the AI's response from the messages
        if response and "messages" in response and response["messages"]:
            for message in reversed(response["messages"]):
                message_type = type(message).__name__
                if "AIMessage" in message_type:
                    ai_content = message.content if hasattr(message, 'content') else str(message)
                    self.conversation_history.append({"role": "assistant", "content": ai_content})
                    break
        
        return response
    
    async def run_interactive_session(self):
        """Run an interactive conversation session"""
        print("\n" + "="*60)
        print("🤖 Interactive Agent Session Started")
        print("="*60)
        print("Type 'exit', 'quit', or 'bye' to end the session")
        print("Type 'clear' or 'reset' to clear conversation history")
        print("Type 'history' to view conversation history")
        print("="*60 + "\n")
        
        while True:
            try:
                # Get user input
                user_input = input("\n💭 You: ").strip()
                
                # Check for exit commands
                if user_input.lower() in ['exit', 'quit', 'bye']:
                    print("\n👋 Goodbye! Thanks for chatting.")
                    break
                
                # Check for clear/reset commands
                if user_input.lower() in ['clear', 'reset']:
                    self.conversation_history = []
                    print("\n🔄 Conversation history cleared.")
                    continue
                
                # Check for history command
                if user_input.lower() == 'history':
                    if not self.conversation_history:
                        print("\n📭 No conversation history yet.")
                    else:
                        print("\n📜 Conversation History:")
                        print("-" * 40)
                        for i, msg in enumerate(self.conversation_history):
                            role = "You" if msg["role"] == "user" else "Agent"
                            print(f"{i+1}. {role}: {msg['content'][:100]}...")
                    continue
                
                # Skip empty input
                if not user_input:
                    continue
                
                # Process the message
                print("\n🤔 Thinking...")
                response = await self.process_message(user_input)
                
                # Print the response
                print("\n🤖 Agent:", end="")
                print_agent_response(response, self.verbose)
                
            except KeyboardInterrupt:
                print("\n\n⚠️  Interrupted. Type 'exit' to quit or continue chatting.")
                continue
            except Exception as e:
                print(f"\n❌ Error: {str(e)}")
                if self.verbose:
                    import traceback
                    print(traceback.format_exc())


async def main():
    """
    Main function that:
    1. Parses command line arguments
    2. Generates Cognito M2M authentication token OR loads session cookie
    3. Sets up the LangChain MCP client and model with authentication
    4. Creates a LangGraph agent with available tools
    5. Either runs in interactive mode or processes a single prompt
    """
    # Parse command line arguments
    args = parse_arguments()
    logger.info(f"Parsed command line arguments successfully, args={args}")
    
    # Load ingress authentication from .oauth-tokens/ingress.json
    oauth_tokens_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.oauth-tokens')
    ingress_file = os.path.join(oauth_tokens_dir, 'ingress.json')
    
    if not os.path.exists(ingress_file):
        logger.error(f"CRITICAL: Ingress authentication file not found: {ingress_file}")
        logger.error("Please run the OAuth authentication flow first to generate ingress.json")
        raise FileNotFoundError(f"Required ingress authentication file not found: {ingress_file}")
    
    try:
        with open(ingress_file, 'r') as f:
            ingress_data = json.load(f)
        
        # Validate required fields
        required_fields = ['access_token', 'user_pool_id', 'client_id', 'region']
        missing_fields = [field for field in required_fields if not ingress_data.get(field)]
        
        if missing_fields:
            logger.error(f"CRITICAL: Missing required fields in ingress.json: {missing_fields}")
            raise ValueError(f"Invalid ingress.json - missing required fields: {missing_fields}")
        
        # Set ingress authentication in agent_settings
        agent_settings.ingress_token = ingress_data['access_token']
        agent_settings.ingress_user_pool_id = ingress_data['user_pool_id']
        agent_settings.ingress_client_id = ingress_data['client_id']
        agent_settings.ingress_region = ingress_data['region']
        
        logger.info("Successfully loaded ingress authentication from .oauth-tokens/ingress.json")
        logger.info(f"Ingress User Pool ID: {agent_settings.ingress_user_pool_id}")
        logger.info(f"Ingress Client ID: {redact_sensitive_value(agent_settings.ingress_client_id)}")
        logger.info(f"Ingress Region: {agent_settings.ingress_region}")
        
    except json.JSONDecodeError as e:
        logger.error(f"CRITICAL: Failed to parse ingress.json: {e}")
        raise ValueError(f"Invalid ingress.json file format: {e}")
    except Exception as e:
        logger.error(f"CRITICAL: Failed to load ingress authentication: {e}")
        raise
    
    # Load server configuration
    global server_config
    server_config = load_server_config()
    
    # Display configuration
    server_url = args.mcp_registry_url
    logger.info(f"Connecting to MCP server: {server_url}")
    logger.info(f"Using model: {args.model}")
    logger.info(f"Interactive mode: {args.interactive}")
    if args.prompt:
        logger.info(f"Initial prompt: {args.prompt}")
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
        # Check if ingress token is available first
        if hasattr(agent_settings, 'ingress_token') and agent_settings.ingress_token:
            logger.info("Using ingress token from .oauth-tokens/ingress.json")
            access_token = agent_settings.ingress_token
            
            # Set global auth variables for invoke_mcp_tool (using ingress settings)
            agent_settings.auth_token = access_token
            agent_settings.user_pool_id = agent_settings.ingress_user_pool_id
            agent_settings.client_id = agent_settings.ingress_client_id
            agent_settings.region = agent_settings.ingress_region
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
    
    # Note: No need to explicitly load server-specific tokens anymore
    # The system now dynamically discovers them from server_config.yml
    
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
        
        # Initialize MCP client with the server configuration and authentication headers
        client = MultiServerMCPClient(
            {
                "mcp_registry": {
                    "url": server_url,
                    "transport": "streamable_http",
                    "headers": auth_headers
                }
            }
        )
        logger.info("Connected to MCP server successfully with authentication, server_url: " + server_url)

        # Get available tools from MCP and display them
        mcp_tools = await client.get_tools()
        logger.info(f"Available MCP tools: {[tool.name for tool in mcp_tools]}")
        
        # Filter MCP tools to only include allowed tools
        filtered_tools = [tool for tool in mcp_tools if tool.name in ALLOWED_MCP_TOOLS]
        logger.info(f"Filtered MCP tools (allowed: {ALLOWED_MCP_TOOLS}): {[tool.name for tool in filtered_tools]}")
        
        # Add only the calculator, invoke_mcp_tool, and the allowed MCP tools to the tools array
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
        
        # Create the interactive agent
        interactive_agent = InteractiveAgent(agent, system_prompt, args.verbose)
        
        # If an initial prompt is provided, process it first
        if args.prompt:
            logger.info("\nProcessing initial prompt...\n" + "-"*40)
            response = await interactive_agent.process_message(args.prompt)
            
            if not args.interactive:
                # Single-turn mode - just show the response and exit
                logger.info("\nResponse:" + "\n" + "-"*40)
                logger.debug(f"Calling print_agent_response with verbose={args.verbose}")
                logger.debug(f"Response has {len(response.get('messages', []))} messages")
                print_agent_response(response, args.verbose)
                return
            else:
                # Interactive mode - show the response and continue
                print("\n🤖 Agent:", end="")
                print_agent_response(response, args.verbose)
        
        # If interactive mode is enabled, start the interactive session
        if args.interactive:
            await interactive_agent.run_interactive_session()
        elif not args.prompt:
            # No prompt and not interactive - show usage
            print("\n⚠️  No prompt provided. Use --prompt to send a message or --interactive for chat mode.")
            print("\nExamples:")
            print('  python agent_interactive.py --prompt "What time is it?"')
            print('  python agent_interactive.py --interactive')
            print('  python agent_interactive.py --prompt "Hello" --interactive')
                
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())