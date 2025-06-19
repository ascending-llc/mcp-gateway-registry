"""
HTTPX Monkey Patch Context Manager

This module provides a context manager for applying and restoring httpx monkey patches
to fix mount path issues in MCP SSE requests.
"""

import httpx
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


def normalize_sse_endpoint_url_for_request(url_str: str, original_sse_url: str) -> str:
    """
    Normalize URLs in HTTP requests by preserving mount paths for non-mounted servers.
    
    This function only applies fixes when the request is for the same server as the original SSE URL.
    It should NOT modify requests to different servers (like currenttime, fininfo, etc.)
    
    Example: 
    - Original SSE: http://localhost/mcpgw2/sse
    - Request to same server: http://localhost/messages/?session_id=123 -> http://localhost/mcpgw2/messages/?session_id=123
    - Request to different server: http://localhost/currenttime/messages/?session_id=123 -> unchanged (already correct)
    """
    if '/messages/' not in url_str:
        return url_str
    
    # Parse the original SSE URL to extract the base path
    from urllib.parse import urlparse
    parsed_original = urlparse(original_sse_url)
    parsed_current = urlparse(url_str)
    
    # Only apply fixes if this is the same host/port as the original SSE URL
    if parsed_current.netloc != parsed_original.netloc:
        return url_str
    
    original_path = parsed_original.path
    
    # Remove /sse from the original path to get the base mount path
    if original_path.endswith('/sse'):
        base_mount_path = original_path[:-4]  # Remove '/sse'
    else:
        base_mount_path = original_path
    
    # Only apply the fix if:
    # 1. There is a base mount path (non-empty)
    # 2. The current path is exactly /messages/... (indicating it's missing the mount path)
    # 3. The current path doesn't already contain a mount path
    if (base_mount_path and 
        parsed_current.path.startswith('/messages/') and
        not parsed_current.path.startswith(base_mount_path)):
        
        # The mount path is missing, we need to add it back
        # Reconstruct the URL with the mount path
        new_path = base_mount_path + parsed_current.path
        fixed_url = f"{parsed_current.scheme}://{parsed_current.netloc}{new_path}"
        if parsed_current.query:
            fixed_url += f"?{parsed_current.query}"
        if parsed_current.fragment:
            fixed_url += f"#{parsed_current.fragment}"
        
        logger.debug(f"Fixed mount path in request URL: {url_str} -> {fixed_url}")
        return fixed_url
    
    return url_str


@asynccontextmanager
async def httpx_mount_path_patch(server_url: str) -> AsyncGenerator[None, None]:
    """
    Context manager that applies httpx monkey patch to fix mount path issues.
    
    This patches httpx.AsyncClient.request to normalize SSE endpoint URLs
    for requests that are missing mount paths.
    
    Args:
        server_url: The original SSE server URL to use for normalization
        
    Usage:
        async with httpx_mount_path_patch(server_url):
            # Your code that makes httpx requests
            pass
    """
    # Store the original request method
    original_request = httpx.AsyncClient.request
    
    async def patched_request(self, method, url, **kwargs):
        """Patched request method that fixes mount path issues"""
        logger.debug(f"patched_request: {method} {url}")
        
        # Fix mount path issues in requests
        if isinstance(url, str) and '/messages/' in url:
            logger.debug(f"Normalizing SSE endpoint URL: {url} -> server_url: {server_url}")
            url = normalize_sse_endpoint_url_for_request(url, server_url)
        elif hasattr(url, '__str__') and '/messages/' in str(url):
            logger.debug(f"Normalizing SSE endpoint URL (str): {url} -> server_url: {server_url}")
            url = normalize_sse_endpoint_url_for_request(str(url), server_url)
            
        return await original_request(self, method, url, **kwargs)
    
    try:
        # Apply the patch
        httpx.AsyncClient.request = patched_request
        logger.info("Applied httpx monkey patch to fix mount path issues")
        yield
    finally:
        # Restore original behavior
        httpx.AsyncClient.request = original_request
        logger.info("Restored original httpx behavior")