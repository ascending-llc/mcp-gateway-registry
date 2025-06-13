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


async def get_tools_from_server(base_url: str) -> List[dict] | None:
    """
    Connects to an MCP server via SSE, lists tools, and returns their details
    (name, description, schema).

    Args:
        base_url: The base URL of the MCP server (e.g., http://localhost:8000).

    Returns:
        A list of tool detail dictionaries (keys: name, description, schema),
        or None if connection/retrieval fails.
    """
    # Determine scheme and construct the full /sse URL
    if not base_url:
        logger.error("MCP Check Error: Base URL is empty.")
        return None

    sse_url = base_url.rstrip('/') + "/sse"
    # Simple check for https, might need refinement for edge cases
    secure_prefix = "s" if sse_url.startswith("https://") else ""
    mcp_server_url = f"http{secure_prefix}://{sse_url[len(f'http{secure_prefix}://'):]}" # Ensure correct format for sse_client

    logger.info(f"Attempting to connect to MCP server at {mcp_server_url} to get tool list...")
    
    try:
        # Monkey patch httpx to fix mount path issues
        original_request = httpx.AsyncClient.request
        
        async def patched_request(self, method, url, **kwargs):
            # Fix mount path issues in requests
            if isinstance(url, str) and '/messages/' in url:
                url = normalize_sse_endpoint_url_for_request(url)
            elif hasattr(url, '__str__') and '/messages/' in str(url):
                url = normalize_sse_endpoint_url_for_request(str(url))
            return await original_request(self, method, url, **kwargs)
        
        # Apply the patch
        httpx.AsyncClient.request = patched_request
        
        try:
            # Connect using the standard SSE client
            async with sse_client(mcp_server_url) as (read, write):
                # Use the ClientSession context manager directly
                async with ClientSession(read, write, sampling_callback=None) as session:
                    # Apply timeout to individual operations within the session
                    await asyncio.wait_for(session.initialize(), timeout=10.0) # Timeout for initialize
                    tools_response = await asyncio.wait_for(session.list_tools(), timeout=15.0) # Renamed variable

                    # Extract tool details
                    tool_details_list = []
                    if tools_response and hasattr(tools_response, 'tools'):
                        for tool in tools_response.tools:
                            # Access attributes directly based on MCP documentation
                            tool_name = getattr(tool, 'name', 'Unknown Name') # Direct attribute access
                            tool_desc = getattr(tool, 'description', None) or getattr(tool, '__doc__', None)

                            # --- Parse Docstring into Sections --- START
                            parsed_desc = {
                                "main": "No description available.",
                                "args": None,
                                "returns": None,
                                "raises": None,
                            }
                            if tool_desc:
                                tool_desc = tool_desc.strip()
                                # Simple parsing logic (can be refined)
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
                                        main_desc_lines.append(line.strip()) # Keep leading whitespace for main desc if intended
                                    else:
                                        section_content.append(line.strip())

                                # Add the last collected section
                                if current_section != "main":
                                    parsed_desc[current_section] = "\n".join(section_content).strip()
                                elif not parsed_desc["main"] and main_desc_lines: # Handle case where entire docstring was just main description
                                    parsed_desc["main"] = "\n".join(main_desc_lines).strip()

                                # Ensure main description has content if others were parsed but main was empty
                                if not parsed_desc["main"] and (parsed_desc["args"] or parsed_desc["returns"] or parsed_desc["raises"]):
                                    parsed_desc["main"] = "(No primary description provided)"

                            else:
                                parsed_desc["main"] = "No description available."
                            # --- Parse Docstring into Sections --- END

                            tool_schema = getattr(tool, 'inputSchema', {}) # Use inputSchema attribute

                            tool_details_list.append({
                                "name": tool_name,
                                "parsed_description": parsed_desc, # Store parsed sections
                                "schema": tool_schema
                            })

                    logger.info(f"Successfully retrieved details for {len(tool_details_list)} tools from {mcp_server_url}.")
                    return tool_details_list # Return the list of details
        finally:
            # Restore original httpx behavior
            httpx.AsyncClient.request = original_request
    except asyncio.TimeoutError:
        logger.error(f"MCP Check Error: Timeout during session operation with {mcp_server_url}.")
        return None
    except ConnectionRefusedError:
         logger.error(f"MCP Check Error: Connection refused by {mcp_server_url}.")
         return None
    except Exception as e:
        logger.error(f"MCP Check Error: Failed to get tool list from {mcp_server_url}: {type(e).__name__} - {e}")
        return None


class MCPClientService:
    """Service wrapper for the MCP client function to maintain compatibility."""
    
    async def get_tools_from_server(self, base_url: str) -> Optional[List[Dict]]:
        """Wrapper method to maintain compatibility with existing code."""
        return await get_tools_from_server(base_url)


# Global MCP client service instance  
mcp_client_service = MCPClientService() 