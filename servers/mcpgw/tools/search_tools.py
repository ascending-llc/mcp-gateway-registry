"""
Intelligent tool search functionality.

This module provides semantic search capabilities to find the most relevant
tools across all registered services based on natural language queries.

The actual vector search implementation is loaded lazily based on configuration,
ensuring that heavy dependencies (FAISS, sentence-transformers) are only loaded
when needed (embedded mode).
"""

import logging
from typing import Dict, Any, Optional, List
from fastmcp import Context
from fastmcp.server.dependencies import get_http_request

from core.scopes import extract_user_scopes_from_headers

logger = logging.getLogger(__name__)


async def intelligent_tool_finder_impl(
    natural_language_query: Optional[str] = None,
    tags: Optional[List[str]] = None,
    top_k_services: int = 3,
    top_n_tools: int = 1,
    ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    Finds the most relevant MCP tool(s) across all registered and enabled services
    based on a natural language query and/or tag filtering, using semantic search.
    """
    # Extract user scopes from headers
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
    
    # Use the vector search service (lazy loaded based on configuration)
    try:
        from search import vector_search_service
        results = await vector_search_service.search_tools(
            query=natural_language_query,
            tags=tags,
            user_scopes=user_scopes,
            top_k_services=top_k_services,
            top_n_tools=top_n_tools
        )
        
        logger.info(f"intelligent_tool_finder returned {len(results)} tools")
        return results
        
    except Exception as e:
        logger.error(f"Error in intelligent_tool_finder: {e}", exc_info=True)
        raise Exception(f"Tool search failed: {str(e)}")

