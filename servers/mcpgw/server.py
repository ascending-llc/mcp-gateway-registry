"""
This server provides tools to interact with the MCP Gateway Registry API.
"""

import os
import httpx # Use httpx for async requests
import argparse
import asyncio # Added for locking
import logging
import json
import websockets # For WebSocket connections
from pathlib import Path # Added Path
from pydantic import BaseModel, Field
from fastmcp import FastMCP, Context  # Updated import for FastMCP 2.0
from fastmcp.server.dependencies import get_http_request  # New dependency function for HTTP access
from typing import Dict, Any, Optional, ClassVar, List
from dotenv import load_dotenv
import os
from sentence_transformers import SentenceTransformer # Added
import numpy as np # Added
from sklearn.metrics.pairwise import cosine_similarity # Added
import faiss # Added
import yaml # Added for scopes.yml parsing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()  # Load environment variables from .env file

# Get Registry URL from environment variable (keep this one)
REGISTRY_BASE_URL = os.environ.get("REGISTRY_BASE_URL", "http://localhost:7860") # Default to localhost

if not REGISTRY_BASE_URL:
    raise ValueError("REGISTRY_BASE_URL environment variable is not set.")

# Global variable to cache loaded scopes
_scopes_config = None


# --- Scopes Management Helper Functions ---
async def load_scopes_config() -> Dict[str, Any]:
    """
    Load and parse the scopes.yml configuration file.
    
    Returns:
        Dict containing the parsed scopes configuration
    """
    global _scopes_config
    
    if _scopes_config is not None:
        return _scopes_config
    
    try:
        # Look for scopes.yml in the auth_server directory
        # First try the docker container path, then fallback to local development path
        scopes_path = Path("/app/auth_server/scopes.yml")
        if not scopes_path.exists():
            scopes_path = Path(__file__).parent.parent / "auth_server" / "scopes.yml"
        
        if not scopes_path.exists():
            logger.warning(f"Scopes file not found at {scopes_path}")
            return {}
        
        with open(scopes_path, 'r') as f:
            _scopes_config = yaml.safe_load(f)
        
        logger.info(f"Successfully loaded scopes configuration from {scopes_path}")
        return _scopes_config
        
    except Exception as e:
        logger.error(f"Failed to load scopes configuration: {e}")
        return {}


def extract_user_scopes_from_headers(headers: Dict[str, str]) -> List[str]:
    """
    Extract user scopes from HTTP headers.
    
    Args:
        headers: Dictionary of HTTP headers
        
    Returns:
        List of scopes the user has access to
    """
    scopes = []
    
    # Check for scopes in various header formats
    scope_headers = ['x-scopes', 'x-user-scopes', 'scopes']
    
    for header_name in scope_headers:
        header_value = headers.get(header_name) or headers.get(header_name.lower())
        if header_value:
            # Scopes might be comma-separated or space-separated
            if ',' in header_value:
                scopes.extend([s.strip() for s in header_value.split(',')])
            else:
                scopes.extend([s.strip() for s in header_value.split()])
            break
    
    logger.info(f"Extracted scopes from headers: {scopes}")
    return scopes


def check_tool_access(server_name: str, tool_name: str, user_scopes: List[str], scopes_config: Dict[str, Any]) -> bool:
    """
    Check if a user has access to a specific tool based on their scopes.
    
    Args:
        server_name: Name of the server (e.g., 'mcpgw', 'fininfo')
        tool_name: Name of the tool 
        user_scopes: List of scopes the user has
        scopes_config: Parsed scopes configuration
        
    Returns:
        True if user has access, False otherwise
    """
    if not scopes_config or not user_scopes:
        logger.debug(f"Access denied: {server_name}.{tool_name} - no scopes config or user scopes")
        return False
    
    logger.debug(f"Checking access for {server_name}.{tool_name} with user scopes: {user_scopes}")
    logger.debug(f"Available scope keys in config: {list(scopes_config.keys())}")
    
    # Check direct scope access
    for user_scope in user_scopes:
        logger.debug(f"Checking user scope: {user_scope}")
        if user_scope in scopes_config:
            scope_data = scopes_config[user_scope]
            logger.debug(f"Found scope data for {user_scope}: {type(scope_data)}")
            if isinstance(scope_data, list):
                # This is a server scope (like mcp-servers-unrestricted/read)
                for server_config in scope_data:
                    logger.debug(f"Checking server config: {server_config.get('server')} vs {server_name}")
                    if server_config.get('server') == server_name:
                        tools = server_config.get('tools', [])
                        logger.debug(f"Available tools for {server_name}: {tools}")
                        if tool_name in tools:
                            logger.info(f"Access granted: {server_name}.{tool_name} via scope {user_scope}")
                            return True
    
    # Check group mappings for additional access
    group_mappings = scopes_config.get('group_mappings', {})
    logger.debug(f"Checking group mappings: {group_mappings}")
    for group, mapped_scopes in group_mappings.items():
        if group in user_scopes:
            logger.debug(f"User is in group {group}, checking mapped scopes: {mapped_scopes}")
            # User is in this group, check the mapped scopes
            for mapped_scope in mapped_scopes:
                if mapped_scope in scopes_config:
                    scope_data = scopes_config[mapped_scope]
                    if isinstance(scope_data, list):
                        for server_config in scope_data:
                            if server_config.get('server') == server_name:
                                tools = server_config.get('tools', [])
                                if tool_name in tools:
                                    logger.info(f"Access granted: {server_name}.{tool_name} via group {group} -> {mapped_scope}")
                                    return True
    
    logger.debug(f"Access denied: {server_name}.{tool_name} for scopes {user_scopes}")
    return False


# --- Authentication Context Helper Functions ---
async def extract_auth_context(ctx: Context) -> Dict[str, Any]:
    """
    Extract authentication context from the MCP Context.
    FastMCP 2.0 version with improved HTTP header access.
    
    Args:
        ctx: FastMCP Context object
        
    Returns:
        Dict containing authentication information
    """
    try:
        # Basic context information we can reliably access
        auth_context = {
            "request_id": ctx.request_id,
            "client_id": ctx.client_id,
            "session_available": ctx.session is not None,
            "request_context_available": ctx.request_context is not None,
        }
        
        # Try to get HTTP request information using FastMCP 2.0 dependency system
        try:
            http_request = get_http_request()
            if http_request:
                auth_context["http_request_available"] = True
                
                # Access HTTP headers directly
                headers = dict(http_request.headers)
                auth_headers = {}
                
                # Extract auth-related headers
                for key, value in headers.items():
                    key_lower = key.lower()
                    if key_lower in ['authorization', 'x-user-pool-id', 'x-client-id', 'x-region', 'x-scopes', 'x-user', 'x-username', 'x-auth-method', 'cookie']:
                        if key_lower == 'authorization':
                            # Don't log full auth token, just indicate presence
                            auth_headers[key] = "Bearer Token Present" if value.startswith('Bearer ') else "Auth Header Present"
                        elif key_lower == 'cookie' and 'mcp_gateway_session=' in value:
                            # Extract session cookie safely
                            import re
                            match = re.search(r'mcp_gateway_session=([^;]+)', value)
                            if match:
                                cookie_value = match.group(1)
                                auth_headers["session_cookie"] = cookie_value[:20] + "..." if len(cookie_value) > 20 else cookie_value
                        else:
                            auth_headers[key] = str(value)[:100]  # Truncate long values
                
                if auth_headers:
                    auth_context["auth_headers"] = auth_headers
                else:
                    auth_context["auth_headers"] = "No auth headers found"
                
                # Additional HTTP request info
                auth_context["http_info"] = {
                    "method": http_request.method,
                    "url": str(http_request.url),
                    "client_host": http_request.client.host if http_request.client else "Unknown",
                    "user_agent": headers.get("user-agent", "Unknown")
                }
            else:
                auth_context["http_request_available"] = False
                auth_context["auth_headers"] = "No HTTP request context"
                
        except RuntimeError as e:
            # get_http_request() raises RuntimeError when not in HTTP context
            auth_context["http_request_available"] = False
            auth_context["auth_headers"] = f"Not in HTTP context: {str(e)}"
        except Exception as http_error:
            logger.debug(f"Could not access HTTP request: {http_error}")
            auth_context["http_request_available"] = False
            auth_context["auth_headers"] = f"HTTP access error: {str(http_error)}"
        
        # Try to inspect the session for transport-level information (fallback)
        session_info = {}
        try:
            session = ctx.session
            if session:
                session_info["session_type"] = type(session).__name__
                
                # Check if session has transport
                if hasattr(session, 'transport'):
                    transport = session.transport
                    if transport:
                        session_info["transport_type"] = type(transport).__name__
                        
                        # Try to access any available transport attributes
                        transport_attrs = [attr for attr in dir(transport) if not attr.startswith('_')]
                        session_info["transport_attributes"] = transport_attrs[:10]  # Limit to avoid spam
                        
        except Exception as session_error:
            logger.debug(f"Could not access session info: {session_error}")
            session_info["error"] = str(session_error)
        
        auth_context["session_info"] = session_info
        
        # Try to access request context metadata
        request_info = {}
        try:
            request_context = ctx.request_context
            if request_context:
                request_info["request_context_type"] = type(request_context).__name__
                
                if hasattr(request_context, 'meta') and request_context.meta:
                    meta = request_context.meta
                    meta_info = {}
                    
                    # Check for standard meta attributes
                    for attr in ['client_id', 'user_pool_id', 'region', 'progressToken']:
                        if hasattr(meta, attr):
                            value = getattr(meta, attr)
                            meta_info[attr] = str(value) if value is not None else None
                    
                    request_info["meta"] = meta_info
                    
        except Exception as request_error:
            logger.debug(f"Could not access request context info: {request_error}")
            request_info["error"] = str(request_error)
        
        auth_context["request_info"] = request_info
        
        return auth_context
        
    except Exception as e:
        logger.error(f"Failed to extract auth context: {e}")
        return {
            "error": f"Failed to extract auth context: {str(e)}",
            "request_id": getattr(ctx, 'request_id', 'unknown'),
            "client_id": getattr(ctx, 'client_id', None)
        }


async def log_auth_context(tool_name: str, ctx: Context) -> Dict[str, Any]:
    """
    Log authentication context for a tool call and return the context.
    
    Args:
        tool_name: Name of the tool being called
        ctx: FastMCP Context object
        
    Returns:
        Dict containing the auth context
    """
    auth_context = await extract_auth_context(ctx)
    
    # Log the context for debugging via MCP logging
    await ctx.info(f"🔐 Auth Context for {tool_name}:")
    await ctx.info(f"   Request ID: {auth_context.get('request_id', 'Unknown')}")
    await ctx.info(f"   Client ID: {auth_context.get('client_id', 'Not present')}")
    await ctx.info(f"   Session Available: {auth_context.get('session_available', False)}")
    
    # Log auth headers if found
    auth_headers = auth_context.get('auth_headers', {})
    if auth_headers:
        await ctx.info(f"   Auth Headers Found:")
        for key, value in auth_headers.items():
            await ctx.info(f"     {key}: {value}")
    else:
        await ctx.info(f"   No auth headers detected")
    
    # Log session info if available
    session_info = auth_context.get('session_info', {})
    if session_info.get('session_type'):
        await ctx.info(f"   Session Type: {session_info['session_type']}")
        if session_info.get('transport_type'):
            await ctx.info(f"   Transport Type: {session_info['transport_type']}")
    
    # Log request info if available
    request_info = auth_context.get('request_info', {})
    if request_info.get('meta'):
        await ctx.info(f"   Request Meta: {request_info['meta']}")
    
    # Also log to server logs for debugging
    logger.info(f"AUTH_CONTEXT for {tool_name}: {json.dumps(auth_context, indent=2, default=str)}")
    
    return auth_context


async def validate_session_cookie_with_auth_server(session_cookie: str, auth_server_url: str = "http://localhost:8888") -> Dict[str, Any]:
    """
    Validate a session cookie with the auth server and return user context.
    
    Args:
        session_cookie: The session cookie value
        auth_server_url: URL of the auth server
        
    Returns:
        Dict containing user context information including username, groups, scopes, etc.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Call the auth server to validate the session cookie
            response = await client.post(
                f"{auth_server_url}/validate",
                headers={
                    "Cookie": f"mcp_gateway_session={session_cookie}",
                    "Content-Type": "application/json"
                },
                json={"action": "validate_session"}  # Indicate we want session validation
            )
            
            if response.status_code == 200:
                user_context = response.json()
                logger.info(f"Session validation successful for user: {user_context.get('username', 'unknown')}")
                return user_context
            else:
                logger.warning(f"Session validation failed: HTTP {response.status_code}")
                return {"valid": False, "error": f"HTTP {response.status_code}"}
                
    except Exception as e:
        logger.error(f"Error validating session cookie: {e}")
        return {"valid": False, "error": str(e)}


async def extract_user_scopes_from_auth_context(auth_context: Dict[str, Any]) -> List[str]:
    """
    Extract user scopes from the authentication context.
    
    Args:
        auth_context: Authentication context from extract_auth_context()
        
    Returns:
        List of user scopes
    """
    # Try to get scopes from auth headers (set by nginx from auth server)
    auth_headers = auth_context.get("auth_headers", {})
    if isinstance(auth_headers, dict) and "x-scopes" in auth_headers:
        scopes_header = auth_headers["x-scopes"]
        if scopes_header and scopes_header.strip():
            # Scopes are space-separated in the header
            scopes = scopes_header.split()
            logger.info(f"Extracted scopes from auth headers: {scopes}")
            return scopes
    
    logger.warning("No scopes found in auth context")
    return []


async def validate_user_access_to_tool(ctx: Context, tool_name: str, server_name: str = "mcpgw", action: str = "execute") -> bool:
    """
    Validate if the authenticated user has access to execute a specific tool.
    
    Args:
        ctx: FastMCP Context object
        tool_name: Name of the tool being accessed
        server_name: Name of the server (default: "mcpgw")  
        action: Action being performed ("read" or "execute")
        
    Returns:
        True if access is granted, False otherwise
        
    Raises:
        Exception: If access is denied
    """
    # Extract authentication context
    auth_context = await extract_auth_context(ctx)
    
    # Get user info
    auth_headers = auth_context.get("auth_headers", {})
    username = auth_headers.get("x-user", "unknown") or auth_headers.get("x-username", "unknown")
    
    # Extract scopes
    user_scopes = await extract_user_scopes_from_auth_context(auth_context)
    
    if not user_scopes:
        logger.error(f"FGAC: Access denied for user '{username}' to tool '{tool_name}' - no scopes available")
        raise Exception(f"Access denied: No scopes configured for user")
    
    logger.info(f"FGAC: Validating access for user '{username}' to tool '{tool_name}' on server '{server_name}' with action '{action}'")
    logger.info(f"FGAC: User scopes: {user_scopes}")
    
    # Check for server-specific scopes that allow this action
    required_scope_patterns = [
        f"mcp-servers-unrestricted/{action}",  # Unrestricted access for this action
        f"mcp-servers-restricted/{action}",    # Restricted access for this action
    ]
    
    for scope in user_scopes:
        if scope in required_scope_patterns:
            logger.info(f"FGAC: Access granted - user '{username}' has scope '{scope}' for tool '{tool_name}'")
            return True
    
    # If no matching scope found, deny access
    logger.error(f"FGAC: Access denied for user '{username}' to tool '{tool_name}' - insufficient permissions")
    logger.error(f"FGAC: Required one of: {required_scope_patterns}")
    logger.error(f"FGAC: User has: {user_scopes}")
    
    raise Exception(f"Access denied: Insufficient permissions to execute '{tool_name}'. Required scopes: {required_scope_patterns}")


async def check_user_permission_for_tool(auth_context: Dict[str, Any], tool_name: str, action: str = "execute") -> bool:
    """
    DEPRECATED: Legacy function for backward compatibility.
    Use validate_user_access_to_tool() instead for proper FGAC.
    """
    logger.warning(f"Using deprecated check_user_permission_for_tool - consider upgrading to validate_user_access_to_tool")
    
    if not auth_context.get("valid", False):
        logger.warning(f"Access denied for {tool_name}: Invalid auth context")
        return False
    
    username = auth_context.get("username", "unknown")
    scopes = auth_context.get("scopes", [])
    groups = auth_context.get("groups", [])
    
    # Example permission logic - you can customize this based on your needs
    
    # Admin users can access everything
    if "mcp-registry-admin" in groups:
        logger.info(f"Access granted for {tool_name}: Admin user {username}")
        return True
    
    # Check for specific tool permissions in scopes
    # You could implement more sophisticated scope checking here
    tool_permission = f"mcp-tools/{tool_name}/{action}"
    if tool_permission in scopes:
        logger.info(f"Access granted for {tool_name}: User {username} has scope {tool_permission}")
        return True
    
    # Check for wildcard permissions
    wildcard_permission = f"mcp-tools/*/{action}"
    if wildcard_permission in scopes:
        logger.info(f"Access granted for {tool_name}: User {username} has wildcard scope")
        return True
    
    # Deny access by default
    logger.warning(f"Access denied for {tool_name}: User {username} lacks required permissions. Available scopes: {scopes}")
    return False


# --- FAISS and Sentence Transformer Integration for mcpgw --- START
_faiss_data_lock = asyncio.Lock()
_embedding_model_mcpgw: Optional[SentenceTransformer] = None
_faiss_index_mcpgw: Optional[faiss.Index] = None
_faiss_metadata_mcpgw: Optional[Dict[str, Any]] = None # This will store the content of service_index_metadata.json
_last_faiss_index_mtime: Optional[float] = None
_last_faiss_metadata_mtime: Optional[float] = None

# Determine base path for mcpgw server to find registry's server data
# When running in Docker, server.py is at /app/server.py and registry files are at /app/registry/servers/
_registry_server_data_path = Path(__file__).resolve().parent / "registry" / "servers"
FAISS_INDEX_PATH_MCPGW = _registry_server_data_path / "service_index.faiss"
FAISS_METADATA_PATH_MCPGW = _registry_server_data_path / "service_index_metadata.json"
EMBEDDING_DIMENSION_MCPGW = 384 # Should match the one used in main registry

# Get configuration from environment variables
EMBEDDINGS_MODEL_NAME = os.environ.get('EMBEDDINGS_MODEL_NAME', 'all-MiniLM-L6-v2')
EMBEDDINGS_MODEL_DIR = _registry_server_data_path.parent / "models" / EMBEDDINGS_MODEL_NAME

async def load_faiss_data_for_mcpgw():
    """Loads the FAISS index, metadata, and embedding model for the mcpgw server.
       Reloads data if underlying files have changed since last load.
    """
    global _embedding_model_mcpgw, _faiss_index_mcpgw, _faiss_metadata_mcpgw
    global _last_faiss_index_mtime, _last_faiss_metadata_mtime
    
    async with _faiss_data_lock:
        # Load embedding model if not already loaded (model doesn't change on disk typically)
        if _embedding_model_mcpgw is None:
            try:
                model_cache_path = _registry_server_data_path.parent / ".cache"
                model_cache_path.mkdir(parents=True, exist_ok=True)
                
                # Set SENTENCE_TRANSFORMERS_HOME to use the defined cache path
                original_st_home = os.environ.get('SENTENCE_TRANSFORMERS_HOME')
                os.environ['SENTENCE_TRANSFORMERS_HOME'] = str(model_cache_path)
                
                # Check if the model path exists and is not empty
                model_path = Path(EMBEDDINGS_MODEL_DIR)
                model_exists = model_path.exists() and any(model_path.iterdir()) if model_path.exists() else False
                
                if model_exists:
                    logger.info(f"MCPGW: Loading SentenceTransformer model from local path: {EMBEDDINGS_MODEL_DIR}")
                    _embedding_model_mcpgw = await asyncio.to_thread(SentenceTransformer, str(EMBEDDINGS_MODEL_DIR))
                else:
                    logger.info(f"MCPGW: Local model not found at {EMBEDDINGS_MODEL_DIR}, downloading from Hugging Face")
                    _embedding_model_mcpgw = await asyncio.to_thread(SentenceTransformer, str(EMBEDDINGS_MODEL_NAME))
                
                # Restore original environment variable if it was set
                if original_st_home:
                    os.environ['SENTENCE_TRANSFORMERS_HOME'] = original_st_home
                else:
                    del os.environ['SENTENCE_TRANSFORMERS_HOME'] # Remove if not originally set
                    
                logger.info("MCPGW: SentenceTransformer model loaded successfully.")
            except Exception as e:
                logger.error(f"MCPGW: Failed to load SentenceTransformer model: {e}", exc_info=True)
                return # Cannot proceed without the model for subsequent logic

        # Check FAISS index file
        index_file_changed = False
        if FAISS_INDEX_PATH_MCPGW.exists():
            try:
                current_index_mtime = await asyncio.to_thread(os.path.getmtime, FAISS_INDEX_PATH_MCPGW)
                if _faiss_index_mcpgw is None or _last_faiss_index_mtime is None or current_index_mtime > _last_faiss_index_mtime:
                    logger.info(f"MCPGW: FAISS index file {FAISS_INDEX_PATH_MCPGW} has changed or not loaded. Reloading...")
                    _faiss_index_mcpgw = await asyncio.to_thread(faiss.read_index, str(FAISS_INDEX_PATH_MCPGW))
                    _last_faiss_index_mtime = current_index_mtime
                    index_file_changed = True # Mark that it was reloaded
                    logger.info(f"MCPGW: FAISS index loaded. Total vectors: {_faiss_index_mcpgw.ntotal}")
                    if _faiss_index_mcpgw.d != EMBEDDING_DIMENSION_MCPGW:
                        logger.warning(f"MCPGW: Loaded FAISS index dimension ({_faiss_index_mcpgw.d}) differs from expected ({EMBEDDING_DIMENSION_MCPGW}). Search might be compromised.")
                else:
                    logger.debug("MCPGW: FAISS index file unchanged since last load.")
            except Exception as e:
                logger.error(f"MCPGW: Failed to load or check FAISS index: {e}", exc_info=True)
                _faiss_index_mcpgw = None # Ensure it's None on error
        else:
            logger.warning(f"MCPGW: FAISS index file {FAISS_INDEX_PATH_MCPGW} does not exist.")
            _faiss_index_mcpgw = None
            _last_faiss_index_mtime = None

        # Check FAISS metadata file
        metadata_file_changed = False
        if FAISS_METADATA_PATH_MCPGW.exists():
            try:
                current_metadata_mtime = await asyncio.to_thread(os.path.getmtime, FAISS_METADATA_PATH_MCPGW)
                if _faiss_metadata_mcpgw is None or _last_faiss_metadata_mtime is None or current_metadata_mtime > _last_faiss_metadata_mtime or index_file_changed:
                    logger.info(f"MCPGW: FAISS metadata file {FAISS_METADATA_PATH_MCPGW} has changed, not loaded, or index changed. Reloading...")
                    with open(FAISS_METADATA_PATH_MCPGW, "r") as f:
                        content = await asyncio.to_thread(f.read)
                        _faiss_metadata_mcpgw = await asyncio.to_thread(json.loads, content)
                    _last_faiss_metadata_mtime = current_metadata_mtime
                    metadata_file_changed = True
                    logger.info(f"MCPGW: FAISS metadata loaded. Paths: {len(_faiss_metadata_mcpgw.get('metadata', {})) if _faiss_metadata_mcpgw else 'N/A'}")
                else:
                    logger.debug("MCPGW: FAISS metadata file unchanged since last load.")
            except Exception as e:
                logger.error(f"MCPGW: Failed to load or check FAISS metadata: {e}", exc_info=True)
                _faiss_metadata_mcpgw = None # Ensure it's None on error
        else:
            logger.warning(f"MCPGW: FAISS metadata file {FAISS_METADATA_PATH_MCPGW} does not exist.")
            _faiss_metadata_mcpgw = None
            _last_faiss_metadata_mtime = None

# Call it once at startup, but allow lazy loading if it fails initially
# This direct call might be problematic if server.py is imported elsewhere before app runs.
# A better approach would be a startup event if FastMCP supports it.
# For now, it will attempt to load on first tool call if still None.
# asyncio.create_task(load_faiss_data_for_mcpgw()) # Consider FastMCP startup hook

# --- FAISS and Sentence Transformer Integration for mcpgw --- END


class Constants(BaseModel):
    # Using ClassVar to define class-level constants
    DESCRIPTION: ClassVar[str] = "MCP Gateway Registry Interaction Server (mcpgw)"
    DEFAULT_MCP_TRANSPORT: ClassVar[str] = "sse"
    DEFAULT_MCP_SEVER_LISTEN_PORT: ClassVar[str] = "8003" # Default to a different port
    REQUEST_TIMEOUT: ClassVar[float] = 15.0 # Timeout for HTTP requests

    # Disable instance creation - optional but recommended for constants
    class Config:
        frozen = True  # Make instances immutable


def parse_arguments():
    """Parse command line arguments with defaults matching environment variables."""
    parser = argparse.ArgumentParser(description=Constants.DESCRIPTION)

    parser.add_argument(
        "--port",
        type=str,
        default=os.environ.get(
            "MCP_SERVER_LISTEN_PORT", Constants.DEFAULT_MCP_SEVER_LISTEN_PORT
        ),
        help=f"Port for the MCP server to listen on (default: {Constants.DEFAULT_MCP_SEVER_LISTEN_PORT})",
    )

    parser.add_argument(
        "--transport",
        type=str,
        default=os.environ.get("MCP_TRANSPORT", Constants.DEFAULT_MCP_TRANSPORT),
        help=f"Transport type for the MCP server (default: {Constants.DEFAULT_MCP_TRANSPORT})",
    )

    return parser.parse_args()


# Parse arguments at module level to make them available
args = parse_arguments()

# Initialize FastMCP 2.0 server
mcp = FastMCP("MCPGateway")
# Note: FastMCP 2.0 handles host/port differently - set in run() method
# Mount path is now handled directly in the run() method for HTTP transports


# --- Helper function for making requests to the registry ---
async def _call_registry_api(method: str, endpoint: str, ctx: Context = None, **kwargs) -> Dict[str, Any]:
    """
    Helper function to make async requests to the registry API with auth passthrough.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint path
        ctx: FastMCP Context to extract auth headers from
        **kwargs: Additional arguments to pass to the HTTP request
        
    Returns:
        Dict[str, Any]: JSON response from the API
    """
    url = f"{REGISTRY_BASE_URL.rstrip('/')}{endpoint}"

    # Extract auth headers to pass through to registry
    auth_headers = {}
    if ctx:
        try:
            http_request = get_http_request()
            if http_request:
                # Extract auth-related headers to pass through
                for key, value in http_request.headers.items():
                    key_lower = key.lower()
                    if key_lower in ['authorization', 'x-user-pool-id', 'x-client-id', 'x-region', 'x-scopes', 'x-user', 'x-username', 'x-auth-method', 'cookie']:
                        auth_headers[key] = value
                        
                if auth_headers:
                    logger.info(f"Passing through auth headers to registry: {list(auth_headers.keys())}")
                else:
                    logger.info("No auth headers found to pass through")
            else:
                logger.info("No HTTP request context available for auth passthrough")
        except RuntimeError:
            # Not in HTTP context, no auth headers to pass through
            logger.info("Not in HTTP context, no auth headers to pass through")
        except Exception as e:
            logger.warning(f"Could not extract auth headers for passthrough: {e}")

    # Merge auth headers with any existing headers in kwargs
    if 'headers' in kwargs:
        kwargs['headers'].update(auth_headers)
    else:
        kwargs['headers'] = auth_headers

    # Use a single client instance for potential connection pooling benefits
    async with httpx.AsyncClient(timeout=Constants.REQUEST_TIMEOUT) as client:
        try:
            logger.info(f"Calling Registry API: {method} {url}") # Log the actual call
            response = await client.request(method, url, **kwargs)
            response.raise_for_status() # Raise HTTPStatusError for bad responses (4xx or 5xx)

            # Handle cases where response might be empty (e.g., 204 No Content)
            if response.status_code == 204:
                return {"status": "success", "message": "Operation successful, no content returned."}
            return response.json()

        except httpx.HTTPStatusError as e:
            # Handle HTTP errors
            error_detail = "No specific error detail provided."
            try:
                error_detail = e.response.json().get("detail", error_detail)
            except Exception as json_error:
                # Log that we couldn't get detailed error from JSON, but continue with existing error info
                logger.debug(f"MCPGW: Could not extract detailed error from response: {json_error}")
            raise Exception(f"Registry API Error ({e.response.status_code}): {error_detail} for {method} {url}") from e
        except httpx.RequestError as e:
            # Network or connection error during the API call
            raise Exception(f"Registry API Request Error: Failed to connect or communicate with {url}. Details: {e}") from e
        except Exception as e: # Catch other potential errors during API call
             raise Exception(f"An unexpected error occurred while calling the Registry API at {url}: {e}") from e


# --- MCP Tools ---

@mcp.tool()
async def debug_auth_context(ctx: Context = None) -> Dict[str, Any]:
    """
    Debug tool to explore what authentication context is available.
    This tool helps understand what auth information can be accessed through the MCP Context.
    
    Returns:
        Dict[str, Any]: Detailed debug information about available auth context
    """
    if not ctx:
        return {"error": "No context available"}
    
    debug_info = {
        "context_type": type(ctx).__name__,
        "available_attributes": sorted([attr for attr in dir(ctx) if not attr.startswith('_')]),
        "context_properties": {}
    }
    
    # Try to access each property safely
    for prop in ['client_id', 'request_id', 'session', 'request_context', 'fastmcp']:
        try:
            value = getattr(ctx, prop, "NOT_AVAILABLE")
            if value == "NOT_AVAILABLE":
                debug_info["context_properties"][prop] = "NOT_AVAILABLE"
            elif value is None:
                debug_info["context_properties"][prop] = "None"
            else:
                debug_info["context_properties"][prop] = {
                    "type": type(value).__name__,
                    "available": True
                }
                
                # For session, explore further
                if prop == "session" and value:
                    session_attrs = [attr for attr in dir(value) if not attr.startswith('_')]
                    debug_info["context_properties"][prop]["attributes"] = session_attrs[:20]
                    
                    # Check for transport
                    if hasattr(value, 'transport') and value.transport:
                        transport = value.transport
                        transport_attrs = [attr for attr in dir(transport) if not attr.startswith('_')]
                        debug_info["context_properties"][prop]["transport"] = {
                            "type": type(transport).__name__,
                            "attributes": transport_attrs[:20]
                        }
                
                # For request_context, explore further
                if prop == "request_context" and value:
                    rc_attrs = [attr for attr in dir(value) if not attr.startswith('_')]
                    debug_info["context_properties"][prop]["attributes"] = rc_attrs[:20]
                    
                    if hasattr(value, 'meta') and value.meta:
                        meta = value.meta
                        meta_attrs = [attr for attr in dir(meta) if not attr.startswith('_')]
                        debug_info["context_properties"][prop]["meta"] = {
                            "type": type(meta).__name__,
                            "attributes": meta_attrs[:20]
                        }
                        
        except Exception as e:
            debug_info["context_properties"][prop] = f"ERROR: {str(e)}"
    
    # Log the full auth context
    auth_context = await log_auth_context("debug_auth_context", ctx)
    debug_info["extracted_auth_context"] = auth_context
    
    return debug_info


@mcp.tool()
async def get_http_headers(ctx: Context = None) -> Dict[str, Any]:
    """
    FastMCP 2.0 tool to access HTTP headers directly using the new dependency system.
    This tool demonstrates how to get HTTP request information including auth headers.
    
    Returns:
        Dict[str, Any]: HTTP request information including headers
    """
    if not ctx:
        return {"error": "No context available"}
    
    result = {
        "fastmcp_version": "2.0",
        "tool_name": "get_http_headers",
        "timestamp": str(asyncio.get_event_loop().time())
    }
    
    try:
        # Use FastMCP 2.0's dependency function to get HTTP request
        http_request = get_http_request()
        
        if http_request:
            # Extract all headers
            all_headers = dict(http_request.headers)
            
            # Separate auth-related headers for easy viewing
            auth_headers = {}
            other_headers = {}
            
            for key, value in all_headers.items():
                key_lower = key.lower()
                if key_lower in ['authorization', 'x-user-pool-id', 'x-client-id', 'x-region', 'cookie', 'x-api-key']:
                    if key_lower == 'authorization':
                        # Show type of auth but not full token
                        if value.startswith('Bearer '):
                            auth_headers[key] = f"Bearer <TOKEN_HIDDEN> (length: {len(value)})"
                        else:
                            auth_headers[key] = f"<AUTH_HIDDEN> (length: {len(value)})"
                    elif key_lower == 'cookie':
                        # Show cookie names but hide values
                        cookies = [c.split('=')[0] for c in value.split(';')]
                        auth_headers[key] = f"Cookies: {', '.join(cookies)}"
                    else:
                        auth_headers[key] = value
                else:
                    other_headers[key] = value
            
            result.update({
                "http_request_available": True,
                "method": http_request.method,
                "url": str(http_request.url),
                "path": http_request.url.path,
                "query_params": dict(http_request.query_params),
                "client_info": {
                    "host": http_request.client.host if http_request.client else "Unknown",
                    "port": http_request.client.port if http_request.client else "Unknown"
                },
                "auth_headers": auth_headers,
                "other_headers": other_headers,
                "total_headers_count": len(all_headers)
            })
            
            # Log the auth headers for server-side debugging
            await ctx.info(f"🔐 HTTP Headers Debug - Auth Headers Found: {list(auth_headers.keys())}")
            if auth_headers:
                for key, value in auth_headers.items():
                    await ctx.info(f"   {key}: {value}")
            else:
                await ctx.info("   No auth-related headers found")
                
        else:
            result.update({
                "http_request_available": False,
                "error": "No HTTP request context available"
            })
            await ctx.warning("No HTTP request context available - may be running in non-HTTP transport mode")
            
    except RuntimeError as e:
        # This happens when not in HTTP context (e.g., stdio transport)
        result.update({
            "http_request_available": False,
            "error": f"Not in HTTP context: {str(e)}",
            "transport_mode": "Likely STDIO or other non-HTTP transport"
        })
        await ctx.info(f"Not in HTTP context - this is expected for STDIO transport: {e}")
        
    except Exception as e:
        result.update({
            "http_request_available": False,
            "error": f"Error accessing HTTP request: {str(e)}"
        })
        await ctx.error(f"Error accessing HTTP request: {e}")
        logger.error(f"Error in get_http_headers: {e}", exc_info=True)
    
    return result


@mcp.tool()
async def toggle_service(
    service_path: str = Field(..., description="The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'."),
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Toggles the enabled/disabled state of a registered MCP server in the gateway.

    Args:
        service_path: The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'.

    Returns:
        Dict[str, Any]: Response from the registry API indicating success or failure.

    Raises:
        Exception: If the API call fails.
    """
    endpoint = f"/toggle/{service_path.lstrip('/')}" # Ensure path doesn't have double slash
        
    return await _call_registry_api("POST", endpoint, ctx)


@mcp.tool()
async def register_service(
    server_name: str = Field(..., description="Display name for the server."),
    path: str = Field(..., description="Unique URL path prefix for the server (e.g., '/my-service'). Must start with '/'."),
    proxy_pass_url: str = Field(..., description="The internal URL where the actual MCP server is running (e.g., 'http://localhost:8001')."),
    description: Optional[str] = Field("", description="Description of the server."),
    tags: Optional[List[str]] = Field(None, description="Optional list of tags for categorization."),
    num_tools: Optional[int] = Field(0, description="Number of tools provided by the server."),
    num_stars: Optional[int] = Field(0, description="Number of stars/rating for the server."),
    is_python: Optional[bool] = Field(False, description="Whether the server is implemented in Python."),
    license: Optional[str] = Field("N/A", description="License information for the server."),
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Registers a new MCP server with the gateway.
    
    Args:
        server_name: Display name for the server.
        path: Unique URL path prefix for the server (e.g., '/my-service'). Must start with '/'.
        proxy_pass_url: The internal URL where the actual MCP server is running (e.g., 'http://localhost:8001').
        description: Description of the server.
        tags: Optional list of tags for categorization.
        num_tools: Number of tools provided by the server.
        num_stars: Number of stars/rating for the server.
        is_python: Whether the server is implemented in Python.
        license: License information for the server.
        
    Returns:
        Dict[str, Any]: Response from the registry API, likely including the registered server details.
        
    Raises:
        Exception: If the API call fails.
    """
    endpoint = "/register"
    
    # Convert tags list to comma-separated string if it's a list
    tags_str = ",".join(tags) if isinstance(tags, list) and tags is not None else tags
    
    # Create form data to send to the API
    form_data = {
        "name": server_name,  # Use 'name' as expected by the registry API
        "path": path,
        "proxy_pass_url": proxy_pass_url,
        "description": description if description is not None else "",
        "tags": tags_str if tags_str is not None else "",
        "num_tools": num_tools,
        "num_stars": num_stars,
        "is_python": is_python,
        "license": license  # The registry API uses alias="license" for license_str
    }
    # Remove None values
    form_data = {k: v for k, v in form_data.items() if v is not None}
    
    # Send as form data instead of JSON
    return await _call_registry_api("POST", endpoint, ctx, data=form_data)

@mcp.tool()
async def get_service_tools(
    service_path: str = Field(..., description="The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'. Use '/all' to get tools from all registered servers."),
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Lists the tools provided by a specific registered MCP server.

    Args:
        service_path: The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'.
                      Use '/all' to get tools from all registered servers.

    Returns:
        Dict[str, Any]: A list of tools exposed by the specified server.

    Raises:
        Exception: If the API call fails or the server cannot be reached.
    """
    endpoint = f"/api/tools/{service_path.lstrip('/')}"
        
    return await _call_registry_api("GET", endpoint, ctx)

@mcp.tool()
async def refresh_service(
    service_path: str = Field(..., description="The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'."),
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Triggers a refresh of the tool list for a specific registered MCP server.
    The registry will re-connect to the target server to get its latest tools.

    Args:
        service_path: The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'.

    Returns:
        Dict[str, Any]: Response from the registry API indicating the result of the refresh attempt.

    Raises:
        Exception: If the API call fails.
    """
    endpoint = f"/api/refresh/{service_path.lstrip('/')}"
        
    return await _call_registry_api("POST", endpoint, ctx)


@mcp.tool()
async def get_server_details(
    service_path: str = Field(..., description="The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'. Use '/all' to get details for all registered servers."),
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Retrieves detailed information about a registered MCP server.
    
    Args:
        service_path: The unique path identifier for the service (e.g., '/fininfo'). Must start with '/'.
                      Use '/all' to get details for all registered servers.
        
    Returns:
        Dict[str, Any]: Detailed information about the specified server or all servers if '/all' is specified.
        
    Raises:
        Exception: If the API call fails or the server is not registered.
    """
    endpoint = f"/api/server_details/{service_path.lstrip('/')}"
        
    return await _call_registry_api("GET", endpoint, ctx)


@mcp.tool()
async def healthcheck(ctx: Context = None) -> Dict[str, Any]:
    """
    Retrieves health status information from all registered MCP servers via the registry's WebSocket endpoint.
    
    Returns:
        Dict[str, Any]: Health status information for all registered servers, including:
            - status: 'healthy' or 'disabled'
            - last_checked_iso: ISO timestamp of when the server was last checked
            - num_tools: Number of tools provided by the server
            
    Raises:
        Exception: If the WebSocket connection fails or the data cannot be retrieved.
    """
    try:
        # Connect to the WebSocket endpoint
        registry_ws_url = f"ws://localhost:7860/ws/health_status"
        logger.info(f"Connecting to WebSocket endpoint: {registry_ws_url}")
        
        async with websockets.connect(registry_ws_url) as websocket:
            # WebSocket connection established, wait for the health status data
            logger.info("WebSocket connection established, waiting for health status data...")
            response = await websocket.recv()
            
            # Parse the JSON response
            health_data = json.loads(response)
            logger.info(f"Received health status data for {len(health_data)} servers")
            
            return health_data
            
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"WebSocket error: {e}")
        raise Exception(f"Failed to connect to health status WebSocket: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        raise Exception(f"Failed to parse health status data: {e}")
    except Exception as e:
        logger.error(f"Unexpected error retrieving health status: {e}")
        raise Exception(f"Unexpected error retrieving health status: {e}")


@mcp.tool()
async def intelligent_tool_finder(
    natural_language_query: str = Field(..., description="Your query in natural language describing the task you want to perform."),
    top_k_services: int = Field(3, description="Number of top services to consider from initial FAISS search."),
    top_n_tools: int = Field(1, description="Number of best matching tools to return."),
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Finds the most relevant MCP tool(s) across all registered and enabled services
    based on a natural language query, using semantic search on the registry's FAISS index.

    Args:
        natural_language_query: The user's natural language query.
        top_k_services: How many top-matching services to analyze for tools.
        top_n_tools: How many best tools to return from the combined list.

    Returns:
        A list of dictionaries, each describing a recommended tool, its parent service, and similarity.
    """
    # Load scopes configuration and extract user scopes from headers
    scopes_config = await load_scopes_config()
    user_scopes = []
    
    if ctx:
        try:
            http_request = get_http_request()
            if http_request:
                headers = dict(http_request.headers)
                user_scopes = extract_user_scopes_from_headers(headers)
            else:
                logger.warning("No HTTP request context available for scope extraction")
        except RuntimeError:
            logger.warning("Not in HTTP context, no scopes to extract")
        except Exception as e:
            logger.warning(f"Could not extract scopes from headers: {e}")
    
    if not user_scopes:
        logger.warning("No user scopes found - user may not have access to any tools")
        return []
    
    global _embedding_model_mcpgw, _faiss_index_mcpgw, _faiss_metadata_mcpgw

    # Ensure FAISS data and model are loaded
    if _embedding_model_mcpgw is None or _faiss_index_mcpgw is None or _faiss_metadata_mcpgw is None:
        logger.info("MCPGW: FAISS data or model not yet loaded. Attempting to load now for intelligent_tool_finder...")
        await load_faiss_data_for_mcpgw()

    if _embedding_model_mcpgw is None:
        raise Exception("MCPGW: Sentence embedding model is not available. Cannot perform intelligent search.")
    if _faiss_index_mcpgw is None:
        raise Exception("MCPGW: FAISS index is not available. Cannot perform intelligent search.")
    if _faiss_metadata_mcpgw is None or "metadata" not in _faiss_metadata_mcpgw:
        raise Exception("MCPGW: FAISS metadata is not available or in unexpected format. Cannot perform intelligent search.")

    registry_faiss_metadata = _faiss_metadata_mcpgw["metadata"] # This is {service_path: {id, text, full_server_info}}

    # 1. Embed the natural language query
    try:
        query_embedding = await asyncio.to_thread(_embedding_model_mcpgw.encode, [natural_language_query])
        query_embedding_np = np.array(query_embedding, dtype=np.float32)
    except Exception as e:
        logger.error(f"MCPGW: Error encoding natural language query: {e}", exc_info=True)
        raise Exception(f"MCPGW: Error encoding query: {e}")

    # 2. Search FAISS for top_k_services
    # The FAISS index in registry/main.py stores SERVICE embeddings.
    try:
        logger.info(f"MCPGW: Searching FAISS index for top {top_k_services} services matching query.")
        distances, faiss_ids = await asyncio.to_thread(_faiss_index_mcpgw.search, query_embedding_np, top_k_services)
    except Exception as e:
        logger.error(f"MCPGW: Error searching FAISS index: {e}", exc_info=True)
        raise Exception(f"MCPGW: Error searching FAISS index: {e}")

    candidate_tools = []
    tools_before_scope_filter = 0
    
    # Create a reverse map from FAISS internal ID to service_path for quick lookup
    id_to_service_path_map = {}
    for Svc_path, meta_item in registry_faiss_metadata.items():
        if "id" in meta_item:
            id_to_service_path_map[meta_item["id"]] = Svc_path
        else:
            logger.warning(f"MCPGW: Metadata for service {Svc_path} missing 'id' field. Skipping.")


    # 3. Filter and Collect Tools from top services
    logger.info(f"MCPGW: Processing {len(faiss_ids[0])} services from FAISS search results.")
    for i in range(len(faiss_ids[0])):
        faiss_id = faiss_ids[0][i]
        if faiss_id == -1: # FAISS uses -1 for no more results or if k > ntotal
            continue

        service_path = id_to_service_path_map.get(faiss_id)
        if not service_path:
            logger.warning(f"MCPGW: Could not find service_path for FAISS ID {faiss_id}. Skipping.")
            continue
            
        service_metadata = registry_faiss_metadata.get(service_path)
        if not service_metadata or "full_server_info" not in service_metadata:
            logger.warning(f"MCPGW: Metadata or full_server_info not found for service path {service_path}. Skipping.")
            continue
            
        full_server_info = service_metadata["full_server_info"]

        if not full_server_info.get("is_enabled", False):
            logger.info(f"MCPGW: Service {service_path} is disabled. Skipping its tools.")
            continue

        service_name = full_server_info.get("server_name", "Unknown Service")
        tool_list = full_server_info.get("tool_list", [])

        for tool_info in tool_list:
            tool_name = tool_info.get("name", "Unknown Tool")
            parsed_desc = tool_info.get("parsed_description", {})
            main_desc = parsed_desc.get("main", "No description.")
            
            tools_before_scope_filter += 1
            
            # Check if user has access to this tool based on scopes
            # Map service_path to server name for scope checking
            server_name = service_path.lstrip('/') if service_path.startswith('/') else service_path
            
            if not check_tool_access(server_name, tool_name, user_scopes, scopes_config):
                logger.debug(f"User does not have access to tool {server_name}.{tool_name}, skipping")
                continue
            
            # Create descriptive text for this specific tool
            tool_text_for_embedding = f"Service: {service_name}. Tool: {tool_name}. Description: {main_desc}"
            
            candidate_tools.append({
                "text_for_embedding": tool_text_for_embedding,
                "tool_name": tool_name,
                "tool_parsed_description": parsed_desc,
                "tool_schema": tool_info.get("schema", {}),
                "service_path": service_path,
                "service_name": service_name,
            })

    logger.info(f"MCPGW: Scope filtering results - {tools_before_scope_filter} tools found, {len(candidate_tools)} accessible after filtering")
    
    if not candidate_tools:
        logger.info("MCPGW: No accessible tools found in the top services from FAISS search after scope filtering.")
        return []

    # 4. Embed all candidate tool descriptions
    logger.info(f"MCPGW: Embedding {len(candidate_tools)} candidate tools (after scope filtering) for secondary ranking.")
    try:
        tool_texts = [tool["text_for_embedding"] for tool in candidate_tools]
        tool_embeddings = await asyncio.to_thread(_embedding_model_mcpgw.encode, tool_texts)
        tool_embeddings_np = np.array(tool_embeddings, dtype=np.float32)
    except Exception as e:
        logger.error(f"MCPGW: Error encoding tool descriptions: {e}", exc_info=True)
        raise Exception(f"MCPGW: Error encoding tool descriptions: {e}")

    # 5. Calculate cosine similarity between query and each tool embedding
    similarities = cosine_similarity(query_embedding_np, tool_embeddings_np)[0] # Get the first row (query vs all tools)

    # 6. Add similarity score to each tool and sort
    ranked_tools = []
    for i, tool_data in enumerate(candidate_tools):
        ranked_tools.append({
            **tool_data,
            "overall_similarity_score": float(similarities[i])
        })
    
    ranked_tools.sort(key=lambda x: x["overall_similarity_score"], reverse=True)

    # 7. Select top N tools
    final_results = ranked_tools[:top_n_tools]
    logger.info(f"MCPGW: Top {len(final_results)} tools found after scope filtering and ranking")
    
    # Log which tools were returned for debugging
    for i, tool in enumerate(final_results):
        logger.info(f"  {i+1}. {tool['service_name']}.{tool['tool_name']} (similarity: {tool['overall_similarity_score']:.3f})")
    
    # Remove the temporary 'text_for_embedding' field from results
    for res in final_results:
        del res["text_for_embedding"]
        
    return final_results


# --- Main Execution ---

def main():
    # Run the server with the specified transport from command line args
    # FastMCP 2.0 supports different transport types
    mcp.run(transport="sse", host="0.0.0.0", port=int(args.port), path="/sse")
if __name__ == "__main__":
    main()