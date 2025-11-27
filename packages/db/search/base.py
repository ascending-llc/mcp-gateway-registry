"""
Base search operations shared across different search managers.

Provides core search functionality that can be used by both model-based
and collection-based search managers.
"""
import logging
from typing import Any, Dict, List, Optional, Union
from weaviate.classes.query import Filter

from ..core.client import WeaviateClient
from ..core.enums import SearchType

logger = logging.getLogger(__name__)


class BaseSearchOperations:
    """Core search operations that can be shared across search managers"""
    
    def __init__(self, client: WeaviateClient):
        self.client = client
    
    def _build_combined_filter(
        self,
        field_filters: Optional[Dict[str, Any]] = None,
        list_filters: Optional[Dict[str, List[Any]]] = None
    ) -> Optional[Filter]:
        """
        Build combined Weaviate filter from field and list filters.
        
        Args:
            field_filters: Exact matches, e.g., {"is_enabled": True}
            list_filters: Contains filters, e.g., {"tags": ["weather", "api"]}
            
        Returns:
            Optional[Filter]: Combined filter or None
        """
        filter_parts = []
        
        if field_filters:
            for field, value in field_filters.items():
                filter_parts.append(Filter.by_property(field).equal(value))
        
        if list_filters:
            for field, values in list_filters.items():
                if values:
                    filter_parts.append(Filter.by_property(field).contains_any(values))
        
        if not filter_parts:
            return None
        elif len(filter_parts) == 1:
            return filter_parts[0]
        else:
            combined = filter_parts[0]
            for f in filter_parts[1:]:
                combined = combined & f
            return combined
    
    def execute_smart_search(
        self,
        collection_name: str,
        query: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        field_filters: Optional[Dict[str, Any]] = None,
        list_filters: Optional[Dict[str, List[Any]]] = None,
        alpha: float = 0.7,
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
        """
        try:
            with self.client.managed_connection() as client:
                collection = client.client.collections.get(collection_name)
                
                filters = self._build_combined_filter(field_filters, list_filters)
                
                if query:
                    # Hybrid search
                    query_params = {
                        "query": query,
                        "limit": limit,
                        "offset": offset,
                        "alpha": alpha
                    }
                    if filters:
                        query_params["filters"] = filters
                    if return_metadata:
                        query_params["return_metadata"] = ["distance", "certainty", "score"]
                    
                    response = collection.query.hybrid(**query_params)
                else:
                    # Filtered fetch
                    query_params = {"limit": limit, "offset": offset}
                    if filters:
                        query_params["filters"] = filters
                    
                    response = collection.query.fetch_objects(**query_params)
                
                return self._response_to_dicts(response, return_metadata)
                
        except Exception as e:
            logger.error(f"Smart search failed on {collection_name}: {e}")
            return []
    
    def execute_near_text(
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
        """
        try:
            with self.client.managed_connection() as client:
                collection = client.client.collections.get(collection_name)

                query_params = {
                    "query": text,
                    "limit": limit,
                    "offset": offset,
                }
                
                if filters:
                    query_params["filters"] = filters
                if properties:
                    query_params["properties"] = properties
                if return_distance:
                    query_params["return_metadata"] = ["distance", "certainty"]
                
                response = collection.query.near_text(**query_params)
                return self._response_to_dicts(response, return_distance)
                
        except Exception as e:
            logger.error(f"Failed to perform near_text search on {collection_name}: {e}")
            return []

    def execute_bm25(
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
            k1: BM25 term frequency saturation parameter (may not be supported)
            b: BM25 document length normalization parameter (may not be supported)
            
        Returns:
            List[Dict[str, Any]]: List of result dictionaries
        """
        try:
            with self.client.managed_connection() as client:
                collection = client.client.collections.get(collection_name)

                query_params = {
                    "query": text,
                    "limit": limit,
                }
                
                if filters:
                    query_params["filters"] = filters
                if properties:
                    query_params["query_properties"] = properties
                
                # Note: k1 and b parameters may not be supported in all Weaviate versions
                # Try to include them, but fall back if not supported
                try:
                    response = collection.query.bm25(**query_params, k1=k1, b=b)
                except TypeError:
                    # If k1/b not supported, try without them
                    response = collection.query.bm25(**query_params)
                
                return self._response_to_dicts(response, False)
                
        except Exception as e:
            logger.error(f"Failed to perform BM25 search on {collection_name}: {e}")
            return []

    def execute_hybrid(
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
        try:
            with self.client.managed_connection() as client:
                collection = client.client.collections.get(collection_name)

                query_params = {
                    "query": text,
                    "limit": limit,
                    "offset": offset,
                    "alpha": alpha
                }
                
                if filters:
                    query_params["filters"] = filters
                if return_metadata:
                    query_params["return_metadata"] = ["distance", "certainty", "score"]
                
                response = collection.query.hybrid(**query_params)
                return self._response_to_dicts(response, return_metadata)
                
        except Exception as e:
            logger.error(f"Failed to perform hybrid search on {collection_name}: {e}")
            return []

    def execute_near_vector(
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
        """
        try:
            with self.client.managed_connection() as client:
                collection = client.client.collections.get(collection_name)

                query = collection.query.near_vector(
                    near_vector=vector,
                    limit=limit,
                    offset=offset,
                    filters=filters,
                )
                
                if certainty is not None:
                    query = query.with_certainty(certainty)
                elif distance is not None:
                    query = query.with_distance(distance)

                if return_distance:
                    query = query.with_distance()

                response = query.do()
                return self._response_to_dicts(response, return_distance)
                
        except Exception as e:
            logger.error(f"Failed to perform near_vector search on {collection_name}: {e}")
            return []

    def execute_fuzzy_search(
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
        """
        try:
            with self.client.managed_connection() as client:
                collection = client.client.collections.get(collection_name)

                response = collection.query.hybrid(
                    query=text,
                    limit=limit,
                    offset=offset,
                    filters=filters,
                    alpha=alpha,
                    return_metadata=["distance", "certainty", "score"]
                )

                results = []
                for obj in response.objects:
                    data = obj.properties.copy()
                    data['id'] = obj.uuid

                    # Add search metadata
                    if hasattr(obj, 'metadata'):
                        if hasattr(obj.metadata, 'distance'):
                            data["_distance"] = obj.metadata.distance
                        if hasattr(obj.metadata, 'certainty'):
                            data["_certainty"] = obj.metadata.certainty
                        if hasattr(obj.metadata, 'score'):
                            data["_score"] = obj.metadata.score

                    # Highlight matched metadata fields
                    if metadata_fields:
                        matched_fields = {}
                        for field in metadata_fields:
                            if field in data and data[field]:
                                field_value = str(data[field]).lower()
                                search_terms = text.lower().split()

                                for term in search_terms:
                                    if term in field_value:
                                        matched_fields[field] = data[field]
                                        break

                        if matched_fields:
                            data["_matched_metadata"] = matched_fields

                    results.append(data)

                logger.info(f"Fuzzy search on {collection_name}: '{text}' -> {len(results)} results")
                return results

        except Exception as e:
            logger.error(f"Fuzzy search failed on {collection_name}: {e}")
            return self.execute_bm25(collection_name, text, filters, limit)
    
    def search_in_collection(
        self,
        collection_name: str,
        search_type: Union[SearchType, str],
        **search_params
    ) -> List[Dict[str, Any]]:
        """
        Execute search in specified collection based on search type.
        
        This is the universal search method that delegates to specific search functions
        based on the search_type parameter.
        
        Args:
            collection_name: Name of the collection to search
            search_type: Type of search to perform (SearchType enum or string)
            **search_params: Search parameters specific to the search type
                For NEAR_TEXT: text, limit, offset, filters, return_distance, properties
                For NEAR_VECTOR: vector, limit, offset, certainty, distance, filters, return_distance
                For BM25: text, filters, limit, properties, k1, b
                For HYBRID: text, filters, limit, offset, alpha, return_metadata
                For FUZZY: text, metadata_fields, limit, offset, filters, alpha
                For FETCH_OBJECTS: limit, offset, field_filters, list_filters
                
        Returns:
            List[Dict[str, Any]]: Search results
            
        Raises:
            ValueError: If search_type is invalid or required parameters are missing
            
        Example:
            >>> # Semantic search
            >>> results = base.search_in_collection(
            ...     "Articles",
            ...     SearchType.NEAR_TEXT,
            ...     text="machine learning",
            ...     limit=10
            ... )
            
            >>> # Hybrid search
            >>> results = base.search_in_collection(
            ...     "Articles",
            ...     SearchType.HYBRID,
            ...     text="deep learning",
            ...     alpha=0.7,
            ...     limit=5
            ... )
        """
        # Convert string to SearchType enum if needed
        if isinstance(search_type, str):
            try:
                search_type = SearchType(search_type.lower())
            except ValueError:
                raise ValueError(f"Invalid search_type: {search_type}")
        
        try:
            # Route to appropriate search method based on type
            if search_type == SearchType.NEAR_TEXT:
                if 'text' not in search_params:
                    raise ValueError("Missing 'text' parameter for NEAR_TEXT search")
                return self.execute_near_text(collection_name, **search_params)
            
            elif search_type == SearchType.NEAR_VECTOR:
                if 'vector' not in search_params:
                    raise ValueError("Missing 'vector' parameter for NEAR_VECTOR search")
                return self.execute_near_vector(collection_name, **search_params)
            
            elif search_type == SearchType.BM25:
                if 'text' not in search_params:
                    raise ValueError("Missing 'text' parameter for BM25 search")
                return self.execute_bm25(collection_name, **search_params)
            
            elif search_type == SearchType.HYBRID:
                if 'text' not in search_params:
                    raise ValueError("Missing 'text' parameter for HYBRID search")
                return self.execute_hybrid(collection_name, **search_params)
            
            elif search_type == SearchType.FUZZY:
                if 'text' not in search_params:
                    raise ValueError("Missing 'text' parameter for FUZZY search")
                return self.execute_fuzzy_search(collection_name, **search_params)
            
            elif search_type == SearchType.FETCH_OBJECTS:
                # For FETCH_OBJECTS, use smart_search without query
                return self.execute_smart_search(
                    collection_name,
                    query=None,
                    **search_params
                )
            else:
                raise ValueError(f"Unsupported search_type: {search_type}")
                
        except Exception as e:
            logger.error(f"Search failed in collection {collection_name} with type {search_type}: {e}")
            raise
    
    def search_across_collections(
        self,
        collection_names: List[str],
        search_type: Union[SearchType, str],
        limit_per_collection: Optional[int] = None,
        **search_params
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search across multiple collections concurrently.
        
        Executes the same search across multiple collections in parallel and returns
        results grouped by collection name.
        
        Args:
            collection_names: List of collection names to search
            search_type: Type of search to perform
            limit_per_collection: Optional limit for each collection (overrides search_params limit)
            **search_params: Search parameters to use for all collections
            
        Returns:
            Dict[str, List[Dict[str, Any]]]: Results grouped by collection name
            {
                "Collection1": [...],
                "Collection2": [...],
                ...
            }
            
        Example:
            >>> # Search across multiple collections
            >>> results = base.search_across_collections(
            ...     ["Articles", "Documents", "Notes"],
            ...     SearchType.NEAR_TEXT,
            ...     text="machine learning",
            ...     limit_per_collection=5
            ... )
            >>> 
            >>> # Access results
            >>> for collection, items in results.items():
            ...     print(f"{collection}: {len(items)} results")
        """
        # Override limit if limit_per_collection is specified
        if limit_per_collection is not None:
            search_params['limit'] = limit_per_collection
        
        all_results = {}
        
        for collection_name in collection_names:
            try:
                # Check if collection exists
                with self.client.managed_connection() as client:
                    if not client.client.collections.exists(collection_name):
                        logger.warning(f"Collection '{collection_name}' does not exist, skipping")
                        continue
                
                # Execute search
                results = self.search_in_collection(
                    collection_name,
                    search_type,
                    **search_params
                )
                
                # Add collection name to each result
                for result in results:
                    result['_collection'] = collection_name
                
                # Only include non-empty results
                if results:
                    all_results[collection_name] = results
                    
            except Exception as e:
                logger.error(f"Error searching in collection {collection_name}: {e}")
                continue
        
        return all_results
    
    def search_across_collections_merged(
        self,
        collection_names: List[str],
        search_type: Union[SearchType, str],
        total_limit: int = 10,
        **search_params
    ) -> List[Dict[str, Any]]:
        """
        Search across multiple collections and return merged, sorted results.
        
        Similar to search_across_collections but merges all results into a single list,
        sorted by relevance score/distance.
        
        Args:
            collection_names: List of collection names to search
            search_type: Type of search to perform
            total_limit: Total number of results to return (after merging and sorting)
            **search_params: Search parameters to use for all collections
            
        Returns:
            List[Dict[str, Any]]: Merged and sorted results from all collections
            
        Example:
            >>> # Get top 10 results across all collections
            >>> results = base.search_across_collections_merged(
            ...     ["Articles", "Documents", "Notes"],
            ...     SearchType.HYBRID,
            ...     text="python programming",
            ...     total_limit=10
            ... )
        """
        # Search with higher limit per collection to ensure we get enough results
        limit_per_collection = total_limit * 2
        
        # Get grouped results
        grouped_results = self.search_across_collections(
            collection_names,
            search_type,
            limit_per_collection=limit_per_collection,
            **search_params
        )
        
        # Merge all results
        merged_results = []
        for collection, results in grouped_results.items():
            merged_results.extend(results)
        
        # Sort by relevance (lower distance/higher certainty is better)
        if merged_results:
            # Sort by distance if available
            if '_distance' in merged_results[0]:
                merged_results.sort(key=lambda x: x.get('_distance', float('inf')))
            # Or by score if available (higher is better)
            elif '_score' in merged_results[0]:
                merged_results.sort(key=lambda x: x.get('_score', 0), reverse=True)
            # Or by certainty (higher is better)
            elif '_certainty' in merged_results[0]:
                merged_results.sort(key=lambda x: x.get('_certainty', 0), reverse=True)
        
        # Return top results
        return merged_results[:total_limit]
    
    def _response_to_dicts(
        self, 
        response, 
        return_metadata: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Convert Weaviate response to list of dictionaries.
        
        Args:
            response: Weaviate query response
            return_metadata: Whether to include metadata
            
        Returns:
            List[Dict[str, Any]]: List of result dictionaries
        """
        results = []
        for obj in response.objects:
            data = obj.properties.copy()
            data['id'] = obj.uuid
            
            if return_metadata and hasattr(obj, 'metadata'):
                if hasattr(obj.metadata, 'distance'):
                    data['_distance'] = obj.metadata.distance
                if hasattr(obj.metadata, 'certainty'):
                    data['_certainty'] = obj.metadata.certainty
                if hasattr(obj.metadata, 'score'):
                    data['_score'] = obj.metadata.score
            
            results.append(data)
        
        return results

