"""
Registry API client for interacting with the MCP Gateway Registry.

This module provides a centralized client for making HTTP requests to the
registry API with proper authentication and error handling.
"""

import logging
import httpx
from typing import Dict, Any
from fastmcp import Context
from fastmcp.server.dependencies import get_http_request

logger = logging.getLogger(__name__)


async def call_registry_api(
    method: str, 
    endpoint: str, 
    ctx: Context = None, 
    **kwargs
) -> Dict[str, Any]:
    """
    Helper function to make async requests to the registry API with auth passthrough.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint path
        ctx: FastMCP Context to extract auth headers from
        **kwargs: Additional arguments to pass to the HTTP request
        
    Returns:
        Dict[str, Any]: JSON response from the API
        
    Raises:
        Exception: If the API call fails
    """
    from config import settings, Constants
    
    url = f"{settings.registry_base_url}{endpoint}"

    # Extract auth headers to pass through to registry
    auth_headers = {}
    if ctx:
        try:
            http_request = get_http_request()
            if http_request:
                # Extract auth-related headers to pass through
                for key, value in http_request.headers.items():
                    key_lower = key.lower()
                    if key_lower in ['authorization', 'x-user-pool-id', 'x-client-id', 
                                    'x-region', 'x-scopes', 'x-user', 'x-username', 
                                    'x-auth-method', 'cookie']:
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

    # Get admin credentials from environment for registry API authentication
    auth = httpx.BasicAuth(
        settings.registry_username, 
        settings.registry_password
    ) if settings.registry_username and settings.registry_password else None

    async with httpx.AsyncClient(timeout=Constants.REQUEST_TIMEOUT, auth=auth) as client:
        try:
            logger.info(f"Calling Registry API: {method} {url}")
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()  # Raise HTTPStatusError for bad responses (4xx or 5xx)

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
        except Exception as e:  # Catch other potential errors during API call
            raise Exception(f"An unexpected error occurred while calling the Registry API at {url}: {e}") from e

