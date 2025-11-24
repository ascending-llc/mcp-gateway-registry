"""
Intelligent tool search functionality.

This module provides semantic search capabilities to find the most relevant
tools across all registered services based on natural language queries.

The actual vector search implementation is loaded lazily based on configuration,
ensuring that heavy dependencies (FAISS, sentence-transformers) are only loaded
when needed (embedded mode).
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from fastmcp import Context
from fastmcp.server.dependencies import get_http_request

from core.scopes import extract_user_scopes_from_headers
from db.provider import get_weaviate_search
from models.models import DatabaseQueryRequestBody

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


async def database_query_embeddings_by_text_service(body: DatabaseQueryRequestBody):
    """
    Database cross-collection query service

    Args:
        body: Request body containing query text and parameters

    Returns:
        Dict containing query results with unified format
    """
    # Get user ID from body.entity_id, default to "public" if not provided
    user_authorized = body.entity_id if body.entity_id else "public"
    logger.info(f"User authorized: {user_authorized}")

    weaviate_service = get_weaviate_search()
    collection_name = body.sourceType.collection

    if collection_name:
        collection_names = [collection_name]
    else:
        # TODO: need get all collection
        collection_names = []
    logger.info(f"collection_names: {collection_names}")

    # Query all collections in parallel
    tasks = [
        weaviate_service.search_across_collections(
            collection_name=collection,
            search_type=body.searchType,
            text=body.query,
            limit=body.k * 2
        )
        for collection in collection_names
    ]

    results_per_collection = await asyncio.gather(*tasks)

    # Merge results from all collections
    all_results = []
    for collection_results in results_per_collection:
        for collection_name, documents in collection_results.items():
            for doc in documents:
                if '_collection' not in doc:
                    doc['_collection'] = collection_name
            all_results.extend(documents)

    # Sort by similarity score (using distance, lower value means more similar)
    all_results.sort(key=lambda x: x.get('distance', float('inf')))
    top_k_results = all_results[:body.k]
    results = []
    for idx, doc in enumerate(top_k_results):
        logger.info(f"--- Hit #{idx + 1} (score = {1 - doc.get('distance', 0)}) ---")
        logger.info("Text content (content):")
        logger.info(doc.get('content', ''))
        logger.info("Metadata:")

        # Build document object with enhanced metadata
        metadata = dict(doc)
        metadata['_collection'] = doc.get('_collection', collection_name)

        document_obj = {
            "id": doc.get('id_', ''),
            "metadata": metadata,
            "page_content": doc.get('content', ''),
            "type": doc.get('file_type', ''),
        }
        # Convert distance to score (lower distance means higher score)
        score = doc.get('distance', 0)
        results.append([document_obj, score])

    return {"data": results}
