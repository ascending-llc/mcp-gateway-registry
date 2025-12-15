import logging
from typing import Dict, Any, Optional, List
from fastmcp import Context
from search import vector_search_service

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
    if  hasattr(ctx,"user_auth"):
        user_scopes: List[str] = ctx.user_auth.get('scopes', [])
    try:
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
