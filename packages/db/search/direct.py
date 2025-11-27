import logging
from typing import Any, Dict, List, Optional, Union
from weaviate.classes.query import Filter
from ..core.client import WeaviateClient
from ..core.enums import SearchType
from .base import BaseSearchOperations

logger = logging.getLogger(__name__)


class DirectSearchManager:
    """
    Direct search operations on collections without model abstraction.
    
    This manager allows searching collections by name, without requiring
    a model definition. Perfect for dynamic collections or when you want
    to search without defining a model class.
    
    Usage:
        # Initialize with client
        search_mgr = DirectSearchManager(client)
        
        # Search by collection name
        results = search_mgr.smart_search(
            "MyCollection",
            query="search text",
            limit=10
        )
        
        # Semantic search
        results = search_mgr.near_text(
            "MyCollection",
            text="semantic query"
        )
        
        # Hybrid search
        results = search_mgr.hybrid(
            "MyCollection",
            text="hybrid query",
            alpha=0.7
        )
    """
    
    def __init__(self, client: WeaviateClient):
        self.client = client
        self._search_ops = BaseSearchOperations(client)
    
    def smart_search(
        self,
        collection_name: str,
        query: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        field_filters: Optional[Dict[str, Any]] = None,
        list_filters: Optional[Dict[str, List[Any]]] = None,
        alpha: float = 0.5,
        return_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Smart search with automatic filter building and query selection.
        
        Automatically chooses:
        - Hybrid search (BM25 + semantic) if query provided
        - Filtered fetch if no query
        
        Args:
            collection_name: Name of the collection to search
            query: Search text (None = filtered fetch only)
            limit: Maximum results
            offset: Pagination offset
            field_filters: Exact matches, e.g., {"is_enabled": True}
            list_filters: Contains filters, e.g., {"tags": ["weather", "api"]}
            alpha: Hybrid weight (0-1), higher = more semantic
            return_metadata: Whether to include distance/certainty metadata
            
        Returns:
            List[Dict[str, Any]]: List of result dictionaries
            
        Example:
            >>> mgr = DirectSearchManager(client)
            >>> results = mgr.smart_search(
            ...     "Articles",
            ...     query="machine learning",
            ...     field_filters={"status": "published"},
            ...     limit=5
            ... )
        """
        return self._search_ops.execute_smart_search(
            collection_name=collection_name,
            query=query,
            limit=limit,
            offset=offset,
            field_filters=field_filters,
            list_filters=list_filters,
            alpha=alpha,
            return_metadata=return_metadata
        )
    
    def near_text(
        self,
        collection_name: str,
        text: str,
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Union[Dict[str, Any], Filter]] = None,
        return_distance: bool = True,
        properties: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic text search using vector embeddings.
        
        Args:
            collection_name: Name of the collection to search
            text: Text to search for
            limit: Maximum results
            offset: Pagination offset
            filters: Additional filters
            return_distance: Include distance/certainty metadata
            properties: Specific properties to search (None = all text properties)
            
        Returns:
            List[Dict[str, Any]]: List of result dictionaries
            
        Example:
            >>> results = mgr.near_text(
            ...     "Products",
            ...     text="wireless headphones",
            ...     limit=10
            ... )
        """
        return self._search_ops.execute_near_text(
            collection_name=collection_name,
            text=text,
            limit=limit,
            offset=offset,
            filters=filters,
            return_distance=return_distance,
            properties=properties
        )
    
    def bm25(
        self,
        collection_name: str,
        text: str,
        filters: Optional[Union[Dict[str, Any], Filter]] = None,
        limit: int = 10,
        properties: Optional[List[str]] = None,
        k1: float = 1.2,
        b: float = 0.75
    ) -> List[Dict[str, Any]]:
        """
        BM25 keyword search.
        
        Args:
            collection_name: Name of the collection to search
            text: Text to search for
            filters: Additional filters
            limit: Maximum results
            properties: Properties to search in
            k1: BM25 term frequency saturation parameter
            b: BM25 document length normalization parameter
            
        Returns:
            List[Dict[str, Any]]: List of result dictionaries
            
        Example:
            >>> results = mgr.bm25(
            ...     "Documents",
            ...     text="python tutorial",
            ...     properties=["title", "content"]
            ... )
        """
        return self._search_ops.execute_bm25(
            collection_name=collection_name,
            text=text,
            filters=filters,
            limit=limit,
            properties=properties,
            k1=k1,
            b=b
        )
    
    def hybrid(
        self,
        collection_name: str,
        text: str,
        filters: Optional[Union[Dict[str, Any], Filter]] = None,
        limit: int = 10,
        offset: int = 0,
        alpha: float = 0.5,
        return_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining BM25 and vector search.
        
        Args:
            collection_name: Name of the collection to search
            text: Text to search for
            filters: Additional filters
            limit: Maximum results
            offset: Pagination offset
            alpha: Balance between BM25 (0.0) and vector (1.0)
            return_metadata: Whether to include metadata
            
        Returns:
            List[Dict[str, Any]]: List of result dictionaries
            
        """
        return self._search_ops.execute_hybrid(
            collection_name=collection_name,
            text=text,
            filters=filters,
            limit=limit,
            offset=offset,
            alpha=alpha,
            return_metadata=return_metadata
        )
    
    def near_vector(
        self,
        collection_name: str,
        vector: List[float],
        limit: int = 10,
        offset: int = 0,
        certainty: Optional[float] = None,
        distance: Optional[float] = None,
        filters: Optional[Union[Dict[str, Any], Filter]] = None,
        return_distance: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search with custom vector.
        
        Args:
            collection_name: Name of the collection to search
            vector: Vector to search for
            limit: Maximum results
            offset: Pagination offset
            certainty: Certainty threshold
            distance: Distance threshold
            filters: Additional filters
            return_distance: Include distance metadata
            
        Returns:
            List[Dict[str, Any]]: List of result dictionaries
            
        Example:
            >>> vector = [0.1, 0.2, 0.3, ...]  # Your embedding vector
            >>> results = mgr.near_vector(
            ...     "Images",
            ...     vector=vector,
            ...     limit=10
            ... )
        """
        return self._search_ops.execute_near_vector(
            collection_name=collection_name,
            vector=vector,
            limit=limit,
            offset=offset,
            certainty=certainty,
            distance=distance,
            filters=filters,
            return_distance=return_distance
        )
    
    def fuzzy_search(
        self,
        collection_name: str,
        text: str,
        metadata_fields: Optional[List[str]] = None,
        limit: int = 10,
        offset: int = 0,
        filters: Optional[Union[Dict[str, Any], Filter]] = None,
        alpha: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        Fuzzy search with partial matching capabilities.
        
        Combines BM25 and semantic search optimized for fuzzy matching.
        
        Args:
            collection_name: Name of the collection to search
            text: Search text
            metadata_fields: Fields to search in (None = all fields)
            limit: Maximum results
            offset: Pagination offset
            filters: Additional filters
            alpha: Balance - 0.3 favors keyword/fuzzy matching
            
        Returns:
            List[Dict[str, Any]]: Search results with fuzzy matching
            
        Example:
            >>> results = mgr.fuzzy_search(
            ...     "Users",
            ...     text="john",
            ...     metadata_fields=["name", "email"],
            ...     limit=10
            ... )
        """
        return self._search_ops.execute_fuzzy_search(
            collection_name=collection_name,
            text=text,
            metadata_fields=metadata_fields,
            limit=limit,
            offset=offset,
            filters=filters,
            alpha=alpha
        )
    
    def search_with_suggestions(
        self,
        collection_name: str,
        text: str,
        limit: int = 10,
        include_fuzzy: bool = True,
        include_semantic: bool = True,
        metadata_fields: Optional[List[str]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Comprehensive search returning multiple result types.
        
        Args:
            collection_name: Name of the collection to search
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
            
        Example:
            >>> results = mgr.search_with_suggestions(
            ...     "Products",
            ...     text="laptop",
            ...     limit=5
            ... )
            >>> print(f"Semantic: {len(results['semantic'])}")
            >>> print(f"Fuzzy: {len(results['fuzzy'])}")
            >>> print(f"Combined: {len(results['combined'])}")
        """
        results = {}

        try:
            if include_semantic:
                results["semantic"] = self.near_text(
                    collection_name=collection_name,
                    text=text,
                    limit=limit
                )

            if include_fuzzy:
                results["fuzzy"] = self.fuzzy_search(
                    collection_name=collection_name,
                    text=text,
                    metadata_fields=metadata_fields,
                    limit=limit,
                    alpha=0.2
                )

            results["combined"] = self.hybrid(
                collection_name=collection_name,
                text=text,
                limit=limit,
                alpha=0.5
            )

            logger.info(f"Comprehensive search on {collection_name}: "
                        f"semantic={len(results.get('semantic', []))}, "
                        f"fuzzy={len(results.get('fuzzy', []))}, "
                        f"combined={len(results.get('combined', []))}")

        except Exception as e:
            logger.error(f"Comprehensive search failed on {collection_name}: {e}")
            results["fallback"] = self.bm25(
                collection_name=collection_name,
                text=text,
                limit=limit
            )

        return results
    
    def search_by_type(
        self,
        collection_name: str,
        search_type: Union[SearchType, str],
        **search_params
    ) -> List[Dict[str, Any]]:
        """
        Universal search method that accepts a search type parameter.
        
        This method allows you to specify the search strategy dynamically at runtime,
        making it easier to switch between different search modes without changing code.
        
        Args:
            collection_name: Name of the collection to search
            search_type: Type of search (SearchType enum or string)
            **search_params: Parameters specific to the search type
            
        Returns:
            List[Dict[str, Any]]: Search results
            
        Example:
            >>> # Semantic search
            >>> results = search_mgr.search_by_type(
            ...     "Articles",
            ...     SearchType.NEAR_TEXT,
            ...     text="machine learning",
            ...     limit=10
            ... )
            
            >>> # Using string
            >>> results = search_mgr.search_by_type(
            ...     "Articles",
            ...     "hybrid",
            ...     text="deep learning",
            ...     alpha=0.7
            ... )
        """
        return self._search_ops.search_in_collection(
            collection_name,
            search_type,
            **search_params
        )
    
    def search_multiple_collections(
        self,
        collection_names: List[str],
        search_type: Union[SearchType, str],
        limit_per_collection: Optional[int] = None,
        **search_params
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search across multiple collections concurrently.
        
        Executes the same search across multiple collections and returns results
        grouped by collection name. Each result includes a '_collection' field.
        
        Args:
            collection_names: List of collection names to search
            search_type: Type of search to perform
            limit_per_collection: Optional limit for each collection
            **search_params: Search parameters
            
        Returns:
            Dict[str, List[Dict]]: Results grouped by collection
            {
                "Collection1": [...],
                "Collection2": [...],
            }
            
        Example:
            >>> results = search_mgr.search_multiple_collections(
            ...     ["Articles", "Documents", "Notes"],
            ...     SearchType.NEAR_TEXT,
            ...     text="python programming",
            ...     limit_per_collection=5
            ... )
            >>> 
            >>> for collection, items in results.items():
            ...     print(f"{collection}: {len(items)} results")
        """
        return self._search_ops.search_across_collections(
            collection_names,
            search_type,
            limit_per_collection,
            **search_params
        )
    
    def search_multiple_collections_merged(
        self,
        collection_names: List[str],
        search_type: Union[SearchType, str],
        total_limit: int = 10,
        **search_params
    ) -> List[Dict[str, Any]]:
        """
        Search across multiple collections and return merged, sorted results.
        
        Similar to search_multiple_collections but merges all results into a single list,
        sorted by relevance. Each result includes a '_collection' field to identify its source.
        
        Args:
            collection_names: List of collection names to search
            search_type: Type of search to perform
            total_limit: Total number of results to return (after merging)
            **search_params: Search parameters
            
        Returns:
            List[Dict[str, Any]]: Merged and sorted results from all collections
            
        Example:
            >>> # Get top 10 most relevant results across all collections
            >>> results = search_mgr.search_multiple_collections_merged(
            ...     ["Articles", "Documents", "Notes"],
            ...     SearchType.HYBRID,
            ...     text="machine learning",
            ...     total_limit=10
            ... )
            >>> 
            >>> for result in results:
            ...     print(f"From {result['_collection']}: {result.get('title', 'N/A')}")
        """
        return self._search_ops.search_across_collections_merged(
            collection_names,
            search_type,
            total_limit,
            **search_params
        )

