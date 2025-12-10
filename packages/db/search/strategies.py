"""Search strategies for Weaviate."""

import logging
from typing import Any, Dict, List, Optional
from ..core.client import WeaviateClient
from ..core.enums import SearchType

logger = logging.getLogger(__name__)


def execute_search(state: Any, client: WeaviateClient) -> List[Dict[str, Any]]:
    """Execute search based on search type."""
    try:
        with client.managed_connection() as conn:
            collection = conn.client.collections.get(state.collection_name)
            params = _build_query_params(state)
            
            if state.search_type == SearchType.FETCH_OBJECTS:
                response = collection.query.fetch_objects(**params)
            elif state.search_type == SearchType.BM25:
                if 'query' not in params and 'text' in params:
                    params['query'] = params.pop('text')
                response = collection.query.bm25(**params)
            elif state.search_type == SearchType.NEAR_TEXT:
                if 'query' not in params and 'text' in params:
                    params['query'] = params.pop('text')
                response = collection.query.near_text(**params)
            elif state.search_type == SearchType.NEAR_VECTOR:
                response = collection.query.near_vector(**params)
            elif state.search_type == SearchType.HYBRID:
                if 'query' not in params and 'text' in params:
                    params['query'] = params.pop('text')
                if 'alpha' not in params:
                    params['alpha'] = 0.7
                response = collection.query.hybrid(**params)
            elif state.search_type == SearchType.NEAR_IMAGE:
                response = collection.query.near_image(**params)
            else:
                logger.error(f"Unknown search type: {state.search_type}")
                return []
            
            return _parse_response(response)
            
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []


def _build_query_params(state: Any) -> Dict[str, Any]:
    """Build common query parameters from state."""
    params = state.search_params.copy()
    
    # Check for filters
    has_filters = False
    if hasattr(state, 'has_filters'):
        has_filters = state.has_filters()
    elif hasattr(state, 'filters') and state.filters is not None:
        has_filters = True
    
    if has_filters:
        weaviate_filter = state.filters.to_weaviate_filter()
        if weaviate_filter:
            params['filters'] = weaviate_filter
    
    # Get limit - try _limit first, then limit
    limit = None
    if hasattr(state, '_limit'):
        limit = state._limit
    elif hasattr(state, 'limit') and not callable(getattr(state, 'limit', None)):
        limit = state.limit
    
    if limit is not None:
        params['limit'] = limit
    
    # Get offset - try _offset first, then offset
    offset = None
    if hasattr(state, '_offset'):
        offset = state._offset
    elif hasattr(state, 'offset') and not callable(getattr(state, 'offset', None)):
        offset = state.offset
    
    if offset is not None:
        params['offset'] = offset
    
    # Get return_properties - try _return_properties first
    return_properties = None
    if hasattr(state, '_return_properties'):
        return_properties = state._return_properties
    elif hasattr(state, 'return_properties'):
        return_properties = state.return_properties
    
    if return_properties:
        params['return_properties'] = return_properties
    
    if 'return_metadata' not in params:
        include_metadata = True
        if hasattr(state, 'include_metadata'):
            include_metadata = state.include_metadata
        
        if include_metadata:
            from weaviate.classes.query import MetadataQuery
            params['return_metadata'] = MetadataQuery.full()
    
    return params


def _parse_response(response) -> List[Dict[str, Any]]:
    """Parse Weaviate response into list of dictionaries."""
    results = []
    
    for obj in response.objects:
        data = obj.properties.copy() if hasattr(obj, 'properties') else {}
        data['id'] = str(obj.uuid)
        
        if hasattr(obj, 'metadata'):
            metadata = obj.metadata
            if hasattr(metadata, 'distance') and metadata.distance is not None:
                data['_distance'] = metadata.distance
            if hasattr(metadata, 'certainty') and metadata.certainty is not None:
                data['_certainty'] = metadata.certainty
            if hasattr(metadata, 'score') and metadata.score is not None:
                data['_score'] = metadata.score
        
        results.append(data)
    
    return results
