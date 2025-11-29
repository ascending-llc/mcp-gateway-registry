"""
Search Strategy Pattern Implementation

Provides different search strategies that can be plugged in dynamically.
Each strategy knows how to execute a specific type of search against Weaviate.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type
from ..core.client import WeaviateClient
from ..core.enums import SearchType
from .query_state import QueryState

logger = logging.getLogger(__name__)


class SearchStrategy(ABC):
    """
    Abstract base class for search strategies.
    
    Each concrete strategy implements a specific search type (BM25, semantic, hybrid, etc.)
    This allows for easy extension and testing of individual search methods.
    """
    
    @abstractmethod
    def execute(self, state: QueryState, client: WeaviateClient) -> List[Dict[str, Any]]:
        """
        Execute the search with the given state.
        
        Args:
            state: Query state containing all search parameters
            client: Weaviate client instance
            
        Returns:
            List of result dictionaries
        """
        pass
    
    def _build_query_params(self, state: QueryState) -> Dict[str, Any]:
        """
        Build common query parameters from state.
        
        This extracts parameters that are common across most search types.
        """
        params = state.search_params.copy()
        
        # Add filters
        if state.has_filters():
            weaviate_filter = state.filters.to_weaviate_filter()
            if weaviate_filter:
                params['filters'] = weaviate_filter
        
        # Add pagination
        if state.limit is not None:
            params['limit'] = state.limit
        if state.offset is not None:
            params['offset'] = state.offset
        
        # Add metadata inclusion
        # Note: return_metadata should be MetadataQuery object, not bool
        if 'return_metadata' not in params and state.include_metadata:
            from weaviate.classes.query import MetadataQuery
            params['return_metadata'] = MetadataQuery.full()
        
        # Add property selection
        if state.return_properties:
            params['return_properties'] = state.return_properties
        
        return params
    
    def _parse_response(self, response) -> List[Dict[str, Any]]:
        """
        Parse Weaviate response into list of dictionaries.
        
        Extracts properties and metadata from response objects.
        """
        results = []
        
        for obj in response.objects:
            data = obj.properties.copy() if hasattr(obj, 'properties') else {}
            data['id'] = str(obj.uuid)
            
            # Add metadata if available
            if hasattr(obj, 'metadata'):
                metadata = obj.metadata
                if hasattr(metadata, 'distance') and metadata.distance is not None:
                    data['_distance'] = metadata.distance
                if hasattr(metadata, 'certainty') and metadata.certainty is not None:
                    data['_certainty'] = metadata.certainty
                if hasattr(metadata, 'score') and metadata.score is not None:
                    data['_score'] = metadata.score
                if hasattr(metadata, 'explain_score') and metadata.explain_score is not None:
                    data['_explain_score'] = metadata.explain_score
            
            results.append(data)
        
        return results


class FetchObjectsStrategy(SearchStrategy):
    """Strategy for simple object fetching with filters (no search)."""
    
    def execute(self, state: QueryState, client: WeaviateClient) -> List[Dict[str, Any]]:
        """Fetch objects with optional filtering."""
        try:
            with client.managed_connection() as conn:
                collection = conn.client.collections.get(state.collection_name)
                params = self._build_query_params(state)
                
                response = collection.query.fetch_objects(**params)
                return self._parse_response(response)
                
        except Exception as e:
            logger.error(f"FetchObjects failed: {e}")
            return []


class BM25Strategy(SearchStrategy):
    """Strategy for BM25 keyword search."""
    
    def execute(self, state: QueryState, client: WeaviateClient) -> List[Dict[str, Any]]:
        """Execute BM25 keyword search."""
        try:
            with client.managed_connection() as conn:
                collection = conn.client.collections.get(state.collection_name)
                params = self._build_query_params(state)
                
                # BM25 requires 'query' parameter
                if 'query' not in params and 'text' in params:
                    params['query'] = params.pop('text')
                
                response = collection.query.bm25(**params)
                return self._parse_response(response)
                
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []


class NearTextStrategy(SearchStrategy):
    """Strategy for semantic text search using vector embeddings."""
    
    def execute(self, state: QueryState, client: WeaviateClient) -> List[Dict[str, Any]]:
        """Execute semantic near_text search."""
        try:
            with client.managed_connection() as conn:
                collection = conn.client.collections.get(state.collection_name)
                params = self._build_query_params(state)
                
                # near_text requires 'query' parameter
                if 'query' not in params and 'text' in params:
                    params['query'] = params.pop('text')
                
                response = collection.query.near_text(**params)
                return self._parse_response(response)
                
        except Exception as e:
            logger.error(f"NearText search failed: {e}")
            return []


class NearVectorStrategy(SearchStrategy):
    """Strategy for vector similarity search with custom vectors."""
    
    def execute(self, state: QueryState, client: WeaviateClient) -> List[Dict[str, Any]]:
        """Execute near_vector search."""
        try:
            with client.managed_connection() as conn:
                collection = conn.client.collections.get(state.collection_name)
                params = self._build_query_params(state)
                
                response = collection.query.near_vector(**params)
                return self._parse_response(response)
                
        except Exception as e:
            logger.error(f"NearVector search failed: {e}")
            return []


class HybridStrategy(SearchStrategy):
    """Strategy for hybrid search combining BM25 and vector search."""
    
    def execute(self, state: QueryState, client: WeaviateClient) -> List[Dict[str, Any]]:
        """Execute hybrid search."""
        try:
            with client.managed_connection() as conn:
                collection = conn.client.collections.get(state.collection_name)
                params = self._build_query_params(state)
                
                # Hybrid requires 'query' parameter
                if 'query' not in params and 'text' in params:
                    params['query'] = params.pop('text')
                
                # Default alpha if not specified (0.7 = 70% semantic, 30% keyword)
                if 'alpha' not in params:
                    params['alpha'] = 0.7
                
                response = collection.query.hybrid(**params)
                return self._parse_response(response)
                
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []


class FuzzyStrategy(SearchStrategy):
    """Strategy for fuzzy search (hybrid with lower alpha for typo tolerance)."""
    
    def execute(self, state: QueryState, client: WeaviateClient) -> List[Dict[str, Any]]:
        """Execute fuzzy search using hybrid with BM25-favoring alpha."""
        try:
            with client.managed_connection() as conn:
                collection = conn.client.collections.get(state.collection_name)
                params = self._build_query_params(state)
                
                # Fuzzy uses hybrid with lower alpha for better keyword matching
                if 'query' not in params and 'text' in params:
                    params['query'] = params.pop('text')
                
                # Lower alpha = more keyword-based (better for typos)
                if 'alpha' not in params:
                    params['alpha'] = 0.3
                
                response = collection.query.hybrid(**params)
                return self._parse_response(response)
                
        except Exception as e:
            logger.error(f"Fuzzy search failed: {e}")
            return []


class NearImageStrategy(SearchStrategy):
    """Strategy for image similarity search."""
    
    def execute(self, state: QueryState, client: WeaviateClient) -> List[Dict[str, Any]]:
        """Execute near_image search."""
        try:
            with client.managed_connection() as conn:
                collection = conn.client.collections.get(state.collection_name)
                params = self._build_query_params(state)
                
                response = collection.query.near_image(**params)
                return self._parse_response(response)
                
        except Exception as e:
            logger.error(f"NearImage search failed: {e}")
            return []


class SearchStrategyFactory:
    """
    Factory for creating search strategies.
    
    Provides a registry of search strategies that can be extended at runtime.
    Users can register custom strategies for new search types.
    """
    
    _strategies: Dict[SearchType, SearchStrategy] = {
        SearchType.FETCH_OBJECTS: FetchObjectsStrategy(),
        SearchType.BM25: BM25Strategy(),
        SearchType.NEAR_TEXT: NearTextStrategy(),
        SearchType.NEAR_VECTOR: NearVectorStrategy(),
        SearchType.HYBRID: HybridStrategy(),
        SearchType.FUZZY: FuzzyStrategy(),
        SearchType.NEAR_IMAGE: NearImageStrategy(),
    }
    
    @classmethod
    def register(cls, search_type: SearchType, strategy: SearchStrategy):
        """
        Register a custom search strategy.
        
        Args:
            search_type: The search type enum value
            strategy: Strategy instance to handle this search type
        """
        cls._strategies[search_type] = strategy
        logger.debug(f"Registered search strategy: {search_type.value}")
    
    @classmethod
    def get(cls, search_type: Optional[SearchType]) -> SearchStrategy:
        """
        Get the strategy for a search type.
        
        Args:
            search_type: The search type, or None for default (FetchObjects)
            
        Returns:
            The strategy instance
            
        Raises:
            ValueError: If search type is not registered
        """
        if search_type is None:
            search_type = SearchType.FETCH_OBJECTS
        
        strategy = cls._strategies.get(search_type)
        if not strategy:
            raise ValueError(
                f"No strategy registered for search type: {search_type.value}. "
                f"Available types: {list(cls._strategies.keys())}"
            )
        
        return strategy
    
    @classmethod
    def list_strategies(cls) -> List[SearchType]:
        """List all registered search types."""
        return list(cls._strategies.keys())

