import logging
from typing import Any, Dict, List, Optional, Type, TypeVar, Union
from weaviate.classes.query import Filter

from ..core.client import WeaviateClient
from ..core.enums import SearchType
from .base import BaseSearchOperations

logger = logging.getLogger(__name__)
T = TypeVar('T', bound='Model')


class SearchManager:
    """Advanced search manager integrating multiple search functionalities"""

    def __init__(self, model_class: Type[T], client: WeaviateClient):
        self.model_class = model_class
        self.client = client
        self._search_ops = BaseSearchOperations(client)
    
    def smart_search(
        self,
        query: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        field_filters: Optional[Dict[str, Any]] = None,
        list_filters: Optional[Dict[str, List[Any]]] = None,
        alpha: float = 0.7,
        return_metadata: bool = True
    ) -> List[T]:
        """
        Smart search with automatic filter building and query selection.
        
        Automatically chooses:
        - Hybrid search (BM25 + semantic) if query provided
        - Filtered fetch if no query
        
        Args:
            query: Search text (None = filtered fetch only)
            limit: Maximum results
            offset: Pagination offset
            field_filters: Exact matches, e.g., {"is_enabled": True}
            list_filters: Contains filters, e.g., {"tags": ["weather", "api"]}
            alpha: Hybrid weight (0-1), higher = more semantic
            return_metadata: Whether to include distance/certainty metadata
            
        Returns:
            List[T]: Model instances matching the search
        """
        collection_name = self.model_class.get_collection_name()
        results = self._search_ops.execute_smart_search(
            collection_name=collection_name,
            query=query,
            limit=limit,
            offset=offset,
            field_filters=field_filters,
            list_filters=list_filters,
            alpha=alpha,
            return_metadata=return_metadata
        )
        return self._dicts_to_instances(results)
    
    def near_text(
        self,
        text: str,
        *,
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        return_distance: bool = True,
        properties: Optional[List[str]] = None
    ) -> List[T]:
        """
        Semantic text search using vector embeddings.
        
        Args:
            text: Text to search for
            limit: Maximum results
            offset: Pagination offset
            filters: Additional filters
            return_distance: Include distance/certainty metadata
            properties: Specific properties to search (None = all text properties)
            
        Returns:
            List[T]: Model instances matching the search
        """
        collection_name = self.model_class.get_collection_name()
        results = self._search_ops.execute_near_text(
            collection_name=collection_name,
            text=text,
            limit=limit,
            offset=offset,
            filters=filters,
            return_distance=return_distance,
            properties=properties
        )
        return self._dicts_to_instances(results)

    def bm25(
        self,
        text: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        k1: float = 1.2,
        b: float = 0.75
    ) -> List[T]:
        """
        BM25 keyword search.
        
        Args:
            text: Text to search for
            filters: Additional filters
            limit: Maximum results
            k1: BM25 term frequency saturation parameter
            b: BM25 document length normalization parameter
            
        Returns:
            List[T]: Model instances matching the search
        """
        collection_name = self.model_class.get_collection_name()
        results = self._search_ops.execute_bm25(
            collection_name=collection_name,
            text=text,
            filters=filters,
            limit=limit,
            k1=k1,
            b=b
        )
        return self._dicts_to_instances(results)

    def hybrid(
        self,
        text: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        alpha: float = 0.5
    ) -> List[T]:
        """
        Hybrid search combining BM25 and vector search.
        
        Args:
            text: Text to search for
            filters: Additional filters
            limit: Maximum results
            alpha: Balance between BM25 (0.0) and vector (1.0)
            
        Returns:
            List[T]: Model instances matching the search
        """
        collection_name = self.model_class.get_collection_name()
        results = self._search_ops.execute_hybrid(
            collection_name=collection_name,
            text=text,
            filters=filters,
            limit=limit,
            alpha=alpha
        )
        return self._dicts_to_instances(results)

    def near_vector(
        self,
        vector: List[float],
        *,
        limit: int = 10,
        offset: int = 0,
        certainty: Optional[float] = None,
        distance: Optional[float] = None,
        filters: Optional[Union[Dict[str, Any], Filter]] = None,
        return_distance: bool = False
    ) -> List[T]:
        """
        Vector similarity search with custom vector.
        
        Args:
            vector: Vector to search for
            limit: Maximum results
            offset: Pagination offset
            certainty: Certainty threshold
            distance: Distance threshold
            filters: Additional filters
            return_distance: Include distance metadata
            
        Returns:
            List[T]: Model instances matching the search
        """
        collection_name = self.model_class.get_collection_name()
        results = self._search_ops.execute_near_vector(
            collection_name=collection_name,
            vector=vector,
            limit=limit,
            offset=offset,
            certainty=certainty,
            distance=distance,
            filters=filters,
            return_distance=return_distance
        )
        return self._dicts_to_instances(results)

    def fuzzy_search(
        self,
        text: str,
        metadata_fields: List[str] = None,
        *,
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        alpha: float = 0.3
    ) -> List[T]:
        """
        Fuzzy search with partial matching capabilities.
        
        Combines BM25 and semantic search optimized for fuzzy matching.
        
        Args:
            text: Search text
            metadata_fields: Fields to search in (None = all fields)
            limit: Maximum results
            offset: Pagination offset
            filters: Additional filters
            alpha: Balance - 0.3 favors keyword/fuzzy matching
            
        Returns:
            List[T]: Search results with fuzzy matching
        """
        collection_name = self.model_class.get_collection_name()
        results = self._search_ops.execute_fuzzy_search(
            collection_name=collection_name,
            text=text,
            metadata_fields=metadata_fields,
            limit=limit,
            offset=offset,
            filters=filters,
            alpha=alpha
        )
        return self._dicts_to_instances(results)

    def search_with_suggestions(
        self,
        text: str,
        *,
        limit: int = 10,
        include_fuzzy: bool = True,
        include_semantic: bool = True,
        metadata_fields: List[str] = None
    ) -> Dict[str, List[T]]:
        """
        Comprehensive search returning multiple result types.
        
        Args:
            text: Search text
            limit: Maximum results per search type
            include_fuzzy: Include fuzzy/keyword results
            include_semantic: Include semantic results
            metadata_fields: Fields for fuzzy search
            
        Returns:
            Dict with different search result types:
            {
                "semantic": [...],   # Semantic search results
                "fuzzy": [...],      # Fuzzy search results
                "combined": [...]    # Hybrid search results
            }
        """
        results = {}

        try:
            if include_semantic:
                results["semantic"] = self.near_text(text=text, limit=limit)

            if include_fuzzy:
                results["fuzzy"] = self.fuzzy_search(
                    text=text,
                    metadata_fields=metadata_fields,
                    limit=limit,
                    alpha=0.2
                )

            results["combined"] = self.hybrid(text=text, limit=limit, alpha=0.5)

            collection_name = self.model_class.get_collection_name()
            logger.info(f"Comprehensive search on {collection_name}: "
                        f"semantic={len(results.get('semantic', []))}, "
                        f"fuzzy={len(results.get('fuzzy', []))}, "
                        f"combined={len(results.get('combined', []))}")

        except Exception as e:
            logger.error(f"Comprehensive search failed: {e}")
            results["fallback"] = self.bm25(text, limit=limit)

        return results

    # Helper methods
    
    def _dicts_to_instances(self, data_list: List[Dict[str, Any]]) -> List[T]:
        """
        Convert list of dictionaries to model instances.
        
        Args:
            data_list: List of data dictionaries
            
        Returns:
            List[T]: List of model instances
        """
        return [self._create_instance_from_data(data) for data in data_list]

    def _create_instance_from_data(self, data: Dict[str, Any]) -> T:
        """
        Create model instance from data dictionary.
        
        Args:
            data: Data dictionary
            
        Returns:
            T: Model instance
        """
        instance = self.model_class()
        
        if 'id' in data:
            instance.id = data['id']
        
        for field_name in self.model_class._fields.keys():
            if field_name in data:
                setattr(instance, field_name, data[field_name])
        
        # Store metadata (fields starting with _)
        for key, value in data.items():
            if key.startswith('_') and not hasattr(instance, key):
                setattr(instance, key, value)
        
        return instance
    
    def search_by_type(
        self,
        search_type: Union[SearchType, str],
        **search_params
    ) -> List[T]:
        """
        Universal search method that accepts a search type parameter.
        
        This method allows you to specify the search strategy dynamically at runtime,
        making it easier to switch between different search modes without changing code.
        
        Args:
            search_type: Type of search (SearchType enum or string)
            **search_params: Parameters specific to the search type
                For NEAR_TEXT: text, limit, offset, filters, return_distance, properties
                For NEAR_VECTOR: vector, limit, offset, certainty, distance, filters, return_distance
                For BM25: text, filters, limit, properties, k1, b
                For HYBRID: text, filters, limit, offset, alpha, return_metadata
                For FUZZY: text, metadata_fields, limit, offset, filters, alpha
                For FETCH_OBJECTS: limit, offset, field_filters, list_filters
                
        Returns:
            List[T]: List of model instances matching the search
            
        Example:
            >>> # Semantic search
            >>> results = Article.objects.search_by_type(
            ...     SearchType.NEAR_TEXT,
            ...     text="machine learning",
            ...     limit=10
            ... )
            
            >>> # Hybrid search
            >>> results = Article.objects.search_by_type(
            ...     SearchType.HYBRID,
            ...     text="deep learning",
            ...     alpha=0.7,
            ...     limit=5
            ... )
            
            >>> # Using string
            >>> results = Article.objects.search_by_type(
            ...     "near_text",
            ...     text="AI research",
            ...     limit=10
            ... )
        """
        collection_name = self.model_class.get_collection_name()
        results = self._search_ops.search_in_collection(
            collection_name,
            search_type,
            **search_params
        )
        return self._dicts_to_instances(results)

