"""
MCP Client Service

Handles connections to MCP servers and tool list retrieval.
Copied directly from main_old.py working implementation.
"""

import asyncio
import json
import logging
from typing import List, Dict, Optional
import re
from urllib.parse import urlparse

# MCP Client imports
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


def normalize_sse_endpoint_url(endpoint_url: str) -> str:
    """
    Normalize SSE endpoint URLs by removing mount path prefixes.
    
    For example:
    - Input: "/fininfo/messages/?session_id=123"
    - Output: "/messages/?session_id=123"
    
    Args:
        endpoint_url: The endpoint URL from the SSE event data
        
    Returns:
        The normalized URL with mount path stripped
    """
    if not endpoint_url:
        return endpoint_url
    
    # Pattern to match mount paths like /fininfo/, /currenttime/, etc.
    # We look for paths that start with /word/ followed by messages/
    mount_path_pattern = r'^(/[^/]+)(/messages/.*)'
    
    match = re.match(mount_path_pattern, endpoint_url)
    if match:
        mount_path = match.group(1)  # e.g., "/fininfo"
        rest_of_url = match.group(2)  # e.g., "/messages/?session_id=123"
        
        logger.debug(f"Stripping mount path '{mount_path}' from endpoint URL: {endpoint_url}")
        return rest_of_url
    
    # If no mount path pattern detected, return as-is
    return endpoint_url


import httpx


def _build_headers_for_server(server_info: dict = None) -> Dict[str, str]:
    """
    Build HTTP headers for server requests by merging server-specific headers
    and processing apiKey authentication.

    Args:
        server_info: Server configuration dictionary

    Returns:
        Headers dictionary with server-specific headers and authentication
    """
    # Start with default MCP headers (required by some servers like Cloudflare)
    headers = {
        'Accept': 'application/json, text/event-stream',
        'Content-Type': 'application/json'
    }

    if not server_info:
        return headers

    # Process apiKey authentication if present
    api_key_config = server_info.get("apiKey")
    if api_key_config and isinstance(api_key_config, dict):
        key_value = api_key_config.get("key")
        authorization_type = api_key_config.get("authorization_type", "bearer").lower()
        
        if key_value:
            if authorization_type == "bearer":
                # Bearer token: Authorization: Bearer <key>
                # Ignore custom_header field for bearer type
                headers['Authorization'] = f'Bearer {key_value}'
                logger.debug("Added Bearer authentication header")
            elif authorization_type == "basic":
                # Basic auth: Authorization: Basic <base64(key)>
                # Ignore custom_header field for basic type
                # Note: The key should already be base64 encoded or in username:password format
                import base64
                # Check if key is already base64 encoded by trying to decode it
                try:
                    base64.b64decode(key_value, validate=True)
                    # Already base64 encoded
                    headers['Authorization'] = f'Basic {key_value}'
                    logger.debug("Added Basic authentication header (pre-encoded)")
                except Exception:
                    # Not base64 encoded, encode it
                    encoded_key = base64.b64encode(key_value.encode()).decode()
                    headers['Authorization'] = f'Basic {encoded_key}'
                    logger.debug("Added Basic authentication header (auto-encoded)")
            elif authorization_type == "custom":
                # Custom header: use custom_header field as header name
                # Only use custom_header when authorization_type is "custom"
                custom_header = api_key_config.get("custom_header")
                if custom_header:
                    headers[custom_header] = key_value
                    logger.debug(f"Added custom authentication header: {custom_header}")
                else:
                    logger.warning("apiKey with authorization_type='custom' but no custom_header specified")
            else:
                logger.warning(f"Unknown authorization_type: {authorization_type}, defaulting to Bearer")
                headers['Authorization'] = f'Bearer {key_value}'

    # Merge server-specific headers if present (these can override auth headers if needed)
    server_headers = server_info.get("headers", [])
    if server_headers and isinstance(server_headers, list):
        for header_dict in server_headers:
            if isinstance(header_dict, dict):
                headers.update(header_dict)
                logger.debug(f"Added server headers to MCP client: {header_dict}")

    return headers


def normalize_sse_endpoint_url_for_request(url_str: str) -> str:
    """
    Normalize URLs in HTTP requests by removing mount paths.
    Example: http://localhost:8000/currenttime/messages/... -> http://localhost:8000/messages/...
    """
    if '/messages/' not in url_str:
        return url_str
    
    # Pattern to match URLs like http://host:port/mount_path/messages/...
    import re
    pattern = r'(https?://[^/]+)/([^/]+)(/messages/.*)'
    match = re.match(pattern, url_str)
    
    if match:
        base_url = match.group(1)  # http://host:port
        mount_path = match.group(2)  # currenttime, fininfo, etc.
        messages_path = match.group(3)  # /messages/...
        
        # Skip common paths that aren't mount paths
        if mount_path in ['api', 'static', 'health']:
            return url_str
            
        normalized = f"{base_url}{messages_path}"
        logger.debug(f"Normalized request URL: {url_str} -> {normalized}")
        return normalized
    
    return url_str


async def detect_server_transport_aware(base_url: str, server_info: dict = None) -> str:
    """
    Detect which transport a server supports by checking configuration and testing endpoints.
    Uses server_info type if available, otherwise falls back to auto-detection.
    
    Args:
        base_url: The base URL of the MCP server
        server_info: Optional server configuration dict containing type
        
    Returns:
        The preferred transport type ("sse" or "streamable-http")
    """
    # If URL already has a transport endpoint, detect from it
    if base_url.endswith('/sse') or '/sse/' in base_url:
        logger.debug(f"Server URL {base_url} already has SSE endpoint")
        return "sse"
    elif base_url.endswith('/mcp') or '/mcp/' in base_url:
        logger.debug(f"Server URL {base_url} already has MCP endpoint")
        return "streamable-http"
    
    # Use server configuration if available
    if server_info:
        transport_type = server_info.get("type")
        if transport_type:
            logger.debug(f"Server configuration specifies transport type: {transport_type}")
            return transport_type
    
    # Fall back to auto-detection
    return await detect_server_transport(base_url)


async def detect_server_transport(base_url: str) -> str:
    """
    Detect which transport a server supports by testing endpoints.
    Returns the preferred transport type.
    """
    # If URL already has a transport endpoint, detect from it
    if base_url.endswith('/sse') or '/sse/' in base_url:
        logger.debug(f"Server URL {base_url} already has SSE endpoint")
        return "sse"
    elif base_url.endswith('/mcp') or '/mcp/' in base_url:
        logger.debug(f"Server URL {base_url} already has MCP endpoint")
        return "streamable-http"
    
    # Test streamable-http first (default preference)
    try:
        mcp_url = base_url.rstrip('/') + "/mcp/"
        async with streamablehttp_client(url=mcp_url) as connection:
            logger.debug(f"Server at {base_url} supports streamable-http transport")
            return "streamable-http"
    except Exception as e:
        logger.debug(f"Streamable-HTTP test failed for {base_url}: {e}")
    
    # Fallback to SSE
    try:
        sse_url = base_url.rstrip('/') + "/sse"
        async with sse_client(sse_url) as connection:
            logger.debug(f"Server at {base_url} supports SSE transport")
            return "sse"
    except Exception as e:
        logger.debug(f"SSE test failed for {base_url}: {e}")
    
    # Default to streamable-http if detection fails
    logger.warning(f"Could not detect transport for {base_url}, defaulting to streamable-http")
    return "streamable-http"


async def get_tools_from_server_with_transport(base_url: str, transport: str = "auto") -> List[dict] | None:
    """
    Connects to an MCP server using the specified transport, lists tools, and returns their details.
    
    Args:
        base_url: The base URL of the MCP server (e.g., http://localhost:8000).
        transport: Transport type ("streamable-http", "sse", or "auto")
        
    Returns:
        A list of tool detail dictionaries, or None if connection/retrieval fails.
    """
    if not base_url:
        logger.error("MCP Check Error: Base URL is empty.")
        return None

    # Auto-detect transport if needed
    if transport == "auto":
        transport = await detect_server_transport(base_url)
    
    logger.info(f"Attempting to connect to MCP server at {base_url} using {transport} transport...")
    
    try:
        if transport == "streamable-http":
            return await _get_tools_streamable_http(base_url)
        elif transport == "sse":
            return await _get_tools_sse(base_url)
        else:
            logger.error(f"Unsupported transport type: {transport}")
            return None
            
    except Exception as e:
        logger.error(f"MCP Check Error: Failed to get tool list from {base_url} with {transport}: {type(e).__name__} - {e}")
        return None


async def _get_tools_and_capabilities_streamable_http(base_url: str, server_info: dict = None) -> tuple[List[dict] | None, dict | None]:
    """
    Get tools and capabilities using streamable-http transport.
    
    The URL should contain everything needed. If we can't retrieve capabilities,
    the server is considered failed. This also serves as a sanity check.
    
    Returns:
        Tuple of (tool_list, capabilities_dict)
        Returns (None, None) if connection fails or capabilities cannot be retrieved
    """
    # Build headers for the server
    headers = _build_headers_for_server(server_info)
    
    # Use the URL as provided - it should contain everything needed
    mcp_url = base_url
    
    # Handle special case for anthropic-registry servers
    if server_info and 'tags' in server_info and 'anthropic-registry' in server_info.get('tags', []):
        if '?' not in mcp_url:
            mcp_url += '?instance_id=default'
        elif 'instance_id=' not in mcp_url:
            mcp_url += '&instance_id=default'
    
    logger.info(f"Connecting to MCP server: {mcp_url}")
    
    try:
        async with streamablehttp_client(url=mcp_url, headers=headers) as (read, write, get_session_id):
            async with ClientSession(read, write) as session:
                init_result = await asyncio.wait_for(session.initialize(), timeout=10.0)
                tools_response = await asyncio.wait_for(session.list_tools(), timeout=15.0)
                
                # Extract capabilities from init_result - REQUIRED
                capabilities = {}
                if hasattr(init_result, 'capabilities'):
                    capabilities_obj = init_result.capabilities
                    # Convert to dict if it's a Pydantic model or similar
                    if hasattr(capabilities_obj, 'model_dump'):
                        capabilities = capabilities_obj.model_dump()
                    elif hasattr(capabilities_obj, '__dict__'):
                        capabilities = capabilities_obj.__dict__
                    else:
                        capabilities = capabilities_obj if isinstance(capabilities_obj, dict) else {}
                elif isinstance(init_result, dict) and 'capabilities' in init_result:
                    capabilities = init_result['capabilities']
                
                # If no capabilities retrieved, consider it a failed server
                if not capabilities:
                    logger.error(f"Failed to retrieve capabilities from {mcp_url} - server considered failed")
                    return None, None
                
                logger.info(f"Successfully retrieved capabilities from {mcp_url}: {capabilities}")
                
                result = _extract_tool_details(tools_response)
                return result, capabilities
                
    except asyncio.TimeoutError:
        logger.error(f"Timeout connecting to {mcp_url}")
        return None, None
    except Exception as e:
        logger.error(f"Failed to connect to {mcp_url}: {type(e).__name__} - {e}")
        return None, None


async def _get_tools_streamable_http(base_url: str, server_info: dict = None) -> List[dict] | None:
    """Get tools using streamable-http transport (legacy, without capabilities)"""
    # Build headers for the server
    headers = _build_headers_for_server(server_info)
    
    # If URL already has MCP endpoint, use it directly
    if base_url.endswith('/mcp') or '/mcp/' in base_url:
        mcp_url = base_url
        # Don't add trailing slash - some servers like Cloudflare reject it

        # Handle streamable-http and sse servers imported from anthropinc by adding required query parameter
        if server_info and 'tags' in server_info and 'anthropic-registry' in server_info.get('tags', []):
            if '?' not in mcp_url:
                mcp_url += '?instance_id=default'
            elif 'instance_id=' not in mcp_url:
                mcp_url += '&instance_id=default'
        else:
            logger.info(f"DEBUG: Not a Strata server, URL unchanged: {mcp_url}")
        
        logger.info(f"DEBUG: About to connect to: {mcp_url}")
        try:
            async with streamablehttp_client(url=mcp_url, headers=headers) as (read, write, get_session_id):
                async with ClientSession(read, write) as session:
                    init_result = await asyncio.wait_for(session.initialize(), timeout=10.0)
                    tools_response = await asyncio.wait_for(session.list_tools(), timeout=15.0)
                    
                    # Extract capabilities from init_result
                    capabilities = {}
                    if hasattr(init_result, 'capabilities'):
                        capabilities = init_result.capabilities
                        logger.info(f"Extracted server capabilities: {capabilities}")
                    elif isinstance(init_result, dict) and 'capabilities' in init_result:
                        capabilities = init_result['capabilities']
                        logger.info(f"Extracted server capabilities from dict: {capabilities}")
                    
                    # Store capabilities in the result for later retrieval
                    result = _extract_tool_details(tools_response)
                    # Attach capabilities as metadata (will be handled by caller)
                    if result is not None:
                        # Add capabilities to a global context or return as tuple
                        pass
                    return result
        except Exception as e:
            logger.error(f"MCP Check Error: Streamable-HTTP connection failed to {base_url}: {e}")
            import traceback
            return None
    else:
        # Try with /mcp suffix first, then without if it fails
        endpoints_to_try = [
            base_url.rstrip('/') + "/mcp/",
            base_url.rstrip('/') + "/"
        ]
        
        for mcp_url in endpoints_to_try:
            try:
                logger.info(f"MCP Client: Trying streamable-http endpoint: {mcp_url}")
                async with streamablehttp_client(url=mcp_url, headers=headers) as (read, write, get_session_id):
                    async with ClientSession(read, write) as session:
                        await asyncio.wait_for(session.initialize(), timeout=10.0)
                        tools_response = await asyncio.wait_for(session.list_tools(), timeout=15.0)
                        
                        logger.info(f"MCP Client: Successfully connected to {mcp_url}")
                        return _extract_tool_details(tools_response)
                        
            except asyncio.TimeoutError:
                logger.error(f"MCP Check Error: Timeout during streamable-http session with {mcp_url}.")
                if mcp_url == endpoints_to_try[0]:
                    continue
                return None
            except Exception as e:
                logger.error(f"MCP Check Error: Streamable-HTTP connection failed to {mcp_url}: {e}")
                if mcp_url == endpoints_to_try[0]:
                    continue
                return None
    
    return None


async def _get_tools_and_capabilities_sse(base_url: str, server_info: dict = None) -> tuple[List[dict] | None, dict | None]:
    """
    Get tools and capabilities using SSE transport.
    
    The URL should contain everything needed. If we can't retrieve capabilities,
    the server is considered failed. This also serves as a sanity check.
    
    Returns:
        Tuple of (tool_list, capabilities_dict)
        Returns (None, None) if connection fails or capabilities cannot be retrieved
    """
    # Use the URL as provided - it should contain everything needed
    sse_url = base_url
    
    secure_prefix = "s" if sse_url.startswith("https://") else ""
    mcp_server_url = f"http{secure_prefix}://{sse_url[len(f'http{secure_prefix}://'):]}"
    
    # Build headers for the server
    headers = _build_headers_for_server(server_info)
    
    logger.info(f"Connecting to SSE server: {mcp_server_url}")

    try:
        # Monkey patch httpx to fix mount path issues (legacy SSE support)
        original_request = httpx.AsyncClient.request
        
        async def patched_request(self, method, url, **kwargs):
            if isinstance(url, str) and '/messages/' in url:
                url = normalize_sse_endpoint_url_for_request(url)
            elif hasattr(url, '__str__') and '/messages/' in str(url):
                url = normalize_sse_endpoint_url_for_request(str(url))
            return await original_request(self, method, url, **kwargs)
        
        httpx.AsyncClient.request = patched_request
        
        try:
            async with sse_client(mcp_server_url, headers=headers) as (read, write):
                async with ClientSession(read, write, sampling_callback=None) as session:
                    init_result = await asyncio.wait_for(session.initialize(), timeout=10.0)
                    tools_response = await asyncio.wait_for(session.list_tools(), timeout=15.0)
                    
                    # Extract capabilities from init_result - REQUIRED
                    capabilities = {}
                    if hasattr(init_result, 'capabilities'):
                        capabilities_obj = init_result.capabilities
                        # Convert to dict if it's a Pydantic model or similar
                        if hasattr(capabilities_obj, 'model_dump'):
                            capabilities = capabilities_obj.model_dump()
                        elif hasattr(capabilities_obj, '__dict__'):
                            capabilities = capabilities_obj.__dict__
                        else:
                            capabilities = capabilities_obj if isinstance(capabilities_obj, dict) else {}
                    elif isinstance(init_result, dict) and 'capabilities' in init_result:
                        capabilities = init_result['capabilities']
                    
                    # If no capabilities retrieved, consider it a failed server
                    if not capabilities:
                        logger.error(f"Failed to retrieve capabilities from {mcp_server_url} - server considered failed")
                        return None, None
                    
                    logger.info(f"Successfully retrieved capabilities from {mcp_server_url}: {capabilities}")
                    
                    return _extract_tool_details(tools_response), capabilities
        finally:
            httpx.AsyncClient.request = original_request
            
    except asyncio.TimeoutError:
        logger.error(f"Timeout connecting to {mcp_server_url}")
        return None, None
    except Exception as e:
        logger.error(f"Failed to connect to {mcp_server_url}: {type(e).__name__} - {e}")
        return None, None


async def _get_tools_sse(base_url: str, server_info: dict = None) -> List[dict] | None:
    """Get tools using SSE transport (legacy method with patches, without capabilities)"""
    # If URL already has SSE endpoint, use it directly
    if base_url.endswith('/sse') or '/sse/' in base_url:
        sse_url = base_url
    else:
        sse_url = base_url.rstrip('/') + "/sse"
    
    secure_prefix = "s" if sse_url.startswith("https://") else ""
    mcp_server_url = f"http{secure_prefix}://{sse_url[len(f'http{secure_prefix}://'):]}"
    
    # Build headers for the server
    headers = _build_headers_for_server(server_info)

    try:
        # Monkey patch httpx to fix mount path issues (legacy SSE support)
        original_request = httpx.AsyncClient.request
        
        async def patched_request(self, method, url, **kwargs):
            if isinstance(url, str) and '/messages/' in url:
                url = normalize_sse_endpoint_url_for_request(url)
            elif hasattr(url, '__str__') and '/messages/' in str(url):
                url = normalize_sse_endpoint_url_for_request(str(url))
            return await original_request(self, method, url, **kwargs)
        
        httpx.AsyncClient.request = patched_request
        
        try:
            async with sse_client(mcp_server_url, headers=headers) as (read, write):
                async with ClientSession(read, write, sampling_callback=None) as session:
                    await asyncio.wait_for(session.initialize(), timeout=10.0)
                    tools_response = await asyncio.wait_for(session.list_tools(), timeout=15.0)
                    
                    return _extract_tool_details(tools_response)
        finally:
            httpx.AsyncClient.request = original_request
            
    except asyncio.TimeoutError:
        logger.error(f"MCP Check Error: Timeout during SSE session with {base_url}.")
        return None
    except Exception as e:
        logger.error(f"MCP Check Error: SSE connection failed to {base_url}: {e}")
        return None


def _extract_tool_details(tools_response) -> List[dict]:
    """Extract tool details from MCP tools response"""
    tool_details_list = []
    
    if tools_response and hasattr(tools_response, 'tools'):
        for tool in tools_response.tools:
            tool_name = getattr(tool, 'name', 'Unknown Name')
            tool_desc = getattr(tool, 'description', None) or getattr(tool, '__doc__', None)

            # Parse docstring into sections
            parsed_desc = {
                "main": "No description available.",
                "args": None,
                "returns": None,
                "raises": None,
            }
            if tool_desc:
                tool_desc = tool_desc.strip()
                lines = tool_desc.split('\n')
                main_desc_lines = []
                current_section = "main"
                section_content = []

                for line in lines:
                    stripped_line = line.strip()
                    if stripped_line.startswith("Args:"):
                        parsed_desc["main"] = "\n".join(main_desc_lines).strip()
                        current_section = "args"
                        section_content = [stripped_line[len("Args:"):].strip()]
                    elif stripped_line.startswith("Returns:"):
                        if current_section != "main": 
                            parsed_desc[current_section] = "\n".join(section_content).strip()
                        else: 
                            parsed_desc["main"] = "\n".join(main_desc_lines).strip()
                        current_section = "returns"
                        section_content = [stripped_line[len("Returns:"):].strip()]
                    elif stripped_line.startswith("Raises:"):
                        if current_section != "main": 
                            parsed_desc[current_section] = "\n".join(section_content).strip()
                        else: 
                            parsed_desc["main"] = "\n".join(main_desc_lines).strip()
                        current_section = "raises"
                        section_content = [stripped_line[len("Raises:"):].strip()]
                    elif current_section == "main":
                        main_desc_lines.append(line.strip())
                    else:
                        section_content.append(line.strip())

                # Add the last collected section
                if current_section != "main":
                    parsed_desc[current_section] = "\n".join(section_content).strip()
                elif not parsed_desc["main"] and main_desc_lines:
                    parsed_desc["main"] = "\n".join(main_desc_lines).strip()

                # Ensure main description has content
                if not parsed_desc["main"] and (parsed_desc["args"] or parsed_desc["returns"] or parsed_desc["raises"]):
                    parsed_desc["main"] = "(No primary description provided)"
            else:
                parsed_desc["main"] = "No description available."

            tool_schema = getattr(tool, 'inputSchema', {})

            tool_details_list.append({
                "name": tool_name,
                "parsed_description": parsed_desc,
                "schema": tool_schema
            })

    tool_names = [tool["name"] for tool in tool_details_list]
    logger.info(f"Successfully retrieved details for {len(tool_details_list)} tools: {', '.join(tool_names)}")
    return tool_details_list


async def get_tools_from_server_with_server_info(base_url: str, server_info: dict = None) -> List[dict] | None:
    """
    Get tools from server using server configuration to determine optimal transport.
    
    Args:
        base_url: The base URL of the MCP server (e.g., http://localhost:8000).
        server_info: Optional server configuration dict containing supported_transports
        
    Returns:
        A list of tool detail dictionaries (keys: name, description, schema),
        or None if connection/retrieval fails.
    """
    
    if not base_url:
        logger.error("MCP Check Error: Base URL is empty.")
        return None

    # Use transport-aware detection
    transport = await detect_server_transport_aware(base_url, server_info)
    
    logger.info(f"Attempting to connect to MCP server at {base_url} using {transport} transport (server-info aware)...")
    
    try:
        if transport == "streamable-http":
            return await _get_tools_streamable_http(base_url, server_info)
        elif transport == "sse":
            return await _get_tools_sse(base_url, server_info)
        else:
            logger.error(f"Unsupported transport type: {transport}")
            return None
            
    except Exception as e:
        logger.error(f"MCP Check Error: Failed to get tool list from {base_url} with {transport}: {type(e).__name__} - {e}")
        return None


async def get_tools_and_capabilities_from_server(base_url: str, server_info: dict = None) -> tuple[List[dict] | None, dict | None]:
    """
    Get tools and capabilities from server using server configuration.
    
    Args:
        base_url: The base URL of the MCP server (e.g., http://localhost:8000).
        server_info: Optional server configuration dict containing supported_transports
        
    Returns:
        Tuple of (tool_list, capabilities_dict):
        - tool_list: List of tool dictionaries or None if failed
        - capabilities_dict: Server capabilities dictionary or None if failed
    """
    
    if not base_url:
        logger.error("MCP Check Error: Base URL is empty.")
        return None, None

    # Use transport-aware detection
    transport = await detect_server_transport_aware(base_url, server_info)
    
    logger.info(f"Attempting to connect to MCP server at {base_url} using {transport} transport (server-info aware)...")
    
    try:
        if transport == "streamable-http":
            return await _get_tools_and_capabilities_streamable_http(base_url, server_info)
        elif transport == "sse":
            return await _get_tools_and_capabilities_sse(base_url, server_info)
        else:
            logger.error(f"Unsupported transport type: {transport}")
            return None, None
            
    except Exception as e:
        logger.error(f"MCP Check Error: Failed to get tools and capabilities from {base_url} with {transport}: {type(e).__name__} - {e}")
        return None, None


async def get_oauth_metadata_from_server(base_url: str, server_info: dict = None) -> dict | None:
    """
    Get OAuth metadata from MCP server's well-known endpoint.
    
    According to MCP OAuth specification, OAuth metadata can be retrieved from:
    - /.well-known/oauth-protected-resource (RFC 8725)
    - /.well-known/oauth-authorization-server (RFC 8414)
    
    Args:
        base_url: The base URL of the MCP server (e.g., http://localhost:8000).
        server_info: Optional server configuration dict
        
    Returns:
        OAuth metadata dictionary or None if failed/not available
    """
    if not base_url:
        logger.error("OAuth metadata retrieval: Base URL is empty.")
        return None
    
    # Remove trailing slashes and path segments to get the base domain
    from urllib.parse import urlparse
    parsed = urlparse(base_url.rstrip('/'))
    base_domain = f"{parsed.scheme}://{parsed.netloc}"
    
    # Try different well-known endpoints
    wellknown_endpoints = [
        f"{base_domain}/.well-known/oauth-protected-resource",
        f"{base_domain}/.well-known/oauth-authorization-server",
    ]
    
    # Build basic headers (no authentication needed for OAuth metadata)
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'MCP-Gateway-Registry/1.0'
    }
    
    import httpx
    
    for endpoint in wellknown_endpoints:
        try:
            logger.info(f"Attempting to retrieve OAuth metadata from {endpoint}")
            
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(endpoint, headers=headers)
                
                if response.status_code == 200:
                    try:
                        metadata = response.json()
                        logger.info(f"Successfully retrieved OAuth metadata from {endpoint}")
                        logger.debug(f"OAuth metadata: {metadata}")
                        return metadata
                    except Exception as e:
                        logger.warning(f"Failed to parse OAuth metadata JSON from {endpoint}: {e}")
                        continue
                else:
                    logger.debug(f"OAuth metadata endpoint returned {response.status_code}: {endpoint}")
                    
        except httpx.RequestError as e:
            logger.debug(f"Failed to connect to OAuth metadata endpoint {endpoint}: {e}")
            continue
        except Exception as e:
            logger.warning(f"Unexpected error retrieving OAuth metadata from {endpoint}: {e}")
            continue
    
    logger.info(f"No OAuth metadata found for {base_url} (this is normal for servers without OAuth autodiscovery)")
    return None




class MCPClientService:
    """Service wrapper for the MCP client function to maintain compatibility."""
    
    async def get_tools_from_server_with_server_info(self, base_url: str, server_info: dict = None) -> Optional[List[Dict]]:
        """Wrapper method that uses server configuration for transport selection."""
        return await get_tools_from_server_with_server_info(base_url, server_info)


# Global MCP client service instance  
mcp_client_service = MCPClientService() 