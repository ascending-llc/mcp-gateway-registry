import logging
import weaviate
from typing import Any, Dict, List, Optional, Union

from db.client import WeaviateClient
from models.enums import SearchType

logger = logging.getLogger(__name__)


class WeaviateSearchService:
    """Responsible for Weaviate search functionality"""

    def __init__(self, client: WeaviateClient):
        self.client = client

    async def fetch_objects(self,
                            collection: str,
                            filters: Any = None,
                            limit: int = 10,
                            offset: int = 0,
                            ):
        """Fetch objects by filter without similarity/keyword scoring"""
        await self.client.ensure_connected()
        coll = self.client.client.collections.get(collection)
        return coll.query.fetch_objects(
            limit=limit,
            offset=offset,
            filters=filters,
        )

    async def near_text(self,
                        collection: str,
                        text: str,
                        *,
                        limit: int = 10,
                        offset: int = 0,
                        filters: Optional[Dict[str, Any]] = None,
                        return_distance: bool = True,
                        properties: Optional[List[str]] = None,
                        ) -> List[Dict[str, Any]]:
        """Semantic text search"""
        await self.client.ensure_connected()
        coll = self.client.client.collections.get(collection)

        query_params = {
            "query": text,
            "limit": limit,
            "offset": offset,
            "filters": filters
        }
        # Add return properties
        if properties:
            query_params["properties"] = properties

        if return_distance:
            query_params["return_metadata"] = ["distance", "certainty"]

        logger.info(f"collection: {collection}, Weaviate search params: {query_params}")
        # Execute query
        response = coll.query.near_text(**query_params)

        results = []
        for obj in response.objects:
            item = obj.properties.copy()
            item["distance"] = obj.metadata.distance
            item["certainty"] = obj.metadata.certainty
            results.append(item)
        return results

    async def near_image(self,
                         collection: str,
                         image_data: bytes,
                         filters: Any = None,
                         limit: int = 10,
                         ) -> Any:
        """Image vector search"""
        coll = self.client.client.collections.get(collection)
        return coll.query.near_image(
            image=image_data,
            limit=limit,
            filters=filters
        )

    async def bm25(self,
                   collection: str,
                   text: str,
                   filters: Any = None,
                   limit: int = 10,
                   k1: float = 1.2,
                   b: float = 0.75,
                   ) -> Any:
        """Keyword search based on BM25F algorithm"""
        coll = self.client.client.collections.get(collection)
        return coll.query.bm25(
            query=text,
            limit=limit,
            filters=filters,
            k1=k1,
            b=b
        )

    async def hybrid(self,
                     collection: str,
                     text: str,
                     filters: Any = None,
                     limit: int = 10,
                     alpha: float = 0.5,
                     ) -> Any:
        """Hybrid search"""
        coll = self.client.client.collections.get(collection)
        return coll.query.hybrid(
            query=text,
            limit=limit,
            filters=filters,
            alpha=alpha
        )

    async def near_vector(self,
                          collection: str,
                          vector: List[float],
                          *,
                          limit: int = 10,
                          offset: int = 0,
                          certainty: Optional[float] = None,
                          distance: Optional[float] = None,
                          filters: Optional[Union[Dict[str, Any], weaviate.classes.query.Filter]] = None,
                          return_distance: bool = False,
                          properties: Optional[List[str]] = None,
                          ) -> List[Dict[str, Any]]:
        """Generic vector similarity search"""
        coll = self.client.client.collections.get(collection)

        # Construct base query
        query = coll.query.near_vector(
            near_vector=vector,
            limit=limit,
            offset=offset,
            filters=filters,
        )
        # Set threshold, choose one
        if certainty is not None:
            query = query.with_certainty(certainty)
        elif distance is not None:
            query = query.with_distance(distance)

        # Specify return fields
        if properties:
            query = query.with_properties(properties)

        # Enable client extension if distance needs to be returned
        if return_distance:
            query = query.with_distance()

        logger.info("query: %s", query)
        # Execute query
        response = query.do()

        # Parse and return results
        results = []
        for obj in response.objects:
            item = obj.properties.copy()
            if return_distance and hasattr(obj, "distance"):
                item["distance"] = obj.distance
            results.append(item)

        return results

    async def search_across_collections(self,
                                        search_type: SearchType,
                                        collection_name: str = None,
                                        **search_params) -> Dict[str, List[Dict[str, Any]]]:
        """Cross-collection search method"""
        await self.client.ensure_connected()

        # If collection_name is specified, check if it exists first
        if collection_name:
            collection_configs = self.client.client.collections.list_all(simple=False)
            if collection_name in collection_configs.keys():
                # Remove unnecessary parameters
                if 'collection' in search_params:
                    del search_params['collection']

                # Collection exists, query specified collection directly
                return await self._search_in_collection(collection_name, search_type, **search_params)
            else:
                logger.error(f"Specified collection '{collection_name}' does not exist")
                return {}

        # If collection_name is not specified or specified collection doesn't exist, query all collections
        # Get all collections
        collection_configs = self.client.client.collections.list_all(simple=False)

        # Remove unnecessary parameters
        if 'collection' in search_params:
            del search_params['collection']

        # Save search results for each collection
        all_results = {}

        # Execute search in each collection
        for collection_name in collection_configs.keys():
            try:
                results = await self._search_in_collection(collection_name, search_type, **search_params)
                if results and collection_name in results:
                    all_results[collection_name] = results[collection_name]
            except Exception as e:
                logger.error(f"Error searching in collection {collection_name}: {str(e)}")
                continue

        return all_results

    async def _search_in_collection(self, collection_name: str, search_type: SearchType, **search_params) -> \
            Dict[str, List[Dict[str, Any]]]:
        """Execute search in specified collection"""
        all_results = {}
        try:
            # Call corresponding method based on search type
            if search_type == SearchType.NEAR_VECTOR:
                if 'vector' not in search_params:
                    logger.error("Missing 'vector' parameter for near_vector search")
                    return {}
                results = await self.fetch_objects(collection=collection_name, **search_params)

            elif search_type == SearchType.NEAR_TEXT:
                if 'text' not in search_params:
                    logger.error("Missing 'text' parameter for near_text search")
                    return {}
                results = await self.near_text(collection=collection_name, **search_params)

            elif search_type == SearchType.NEAR_IMAGE:
                if 'image_data' not in search_params:
                    logger.error("Missing 'image_data' parameter for near_image search")
                    return {}
                results = await self.near_image(collection=collection_name, **search_params)

            elif search_type == SearchType.BM25:
                if 'text' not in search_params:
                    logger.error("Missing 'text' parameter for bm25 search")
                    return {}
                results = await self.bm25(collection=collection_name, **search_params)

            elif search_type == SearchType.HYBRID:
                if 'text' not in search_params:
                    logger.error("Missing 'text' parameter for hybrid search")
                    return {}
                results = await self.hybrid(collection=collection_name, **search_params)

            elif search_type == SearchType.FETCH_OBJECTS:
                results = await self.fetch_objects(collection=collection_name, **search_params)

            # Only keep non-empty results
            if results and (
                    hasattr(results, 'objects') and results.objects or isinstance(results, list) and results):
                # Unify return format
                if hasattr(results, 'objects'):
                    formatted_results = []
                    for obj in results.objects:
                        item = obj.properties.copy()
                        # Include UUID in results
                        if hasattr(obj, 'metadata') and hasattr(obj.metadata, 'id'):
                            item['id'] = obj.metadata.id
                        elif hasattr(obj, 'uuid'):
                            item['id'] = obj.uuid
                        if hasattr(obj, 'distance'):
                            item['distance'] = obj.distance
                        # Add collection name information
                        item['_collection'] = collection_name
                        formatted_results.append(item)
                    all_results[collection_name] = formatted_results
                else:
                    # For results that are already lists
                    for item in results:
                        item['_collection'] = collection_name
                    all_results[collection_name] = results

        except Exception as e:
            logger.error(f"Error searching in collection {collection_name}: {str(e)}")

        return all_results

    async def search_all(self,
                         search_type: SearchType,
                         collection_name: str = None,
                         **search_params) -> List[Dict[str, Any]]:
        """Convenience method for cross-collection search with merged results"""
        # Get grouped results across collections
        collection_results = await self.search_across_collections(search_type, collection_name, **search_params)

        # Merge all results
        merged_results = []
        for collection, results in collection_results.items():
            merged_results.extend(results)

        # Sort by distance
        if merged_results and 'distance' in merged_results[0]:
            merged_results.sort(key=lambda x: x.get('distance', float('inf')))

        # If limit is specified, truncate results
        limit = search_params.get('limit', None)
        if limit and isinstance(limit, int):
            merged_results = merged_results[:limit]

        return merged_results

    async def fuzzy_search(self,
                           collection: str,
                           text: str,
                           metadata_fields: List[str] = None,
                           *,
                           limit: int = 10,
                           offset: int = 0,
                           filters: Optional[Dict[str, Any]] = None,
                           alpha: float = 0.3) -> List[Dict[str, Any]]:
        """
        Fuzzy search that combines BM25 and semantic search for optimal results

        Args:
            collection: Collection name
            text: Search text
            metadata_fields: List of metadata fields to search in (if None, searches all fields)
            limit: Maximum number of results
            offset: Offset for pagination
            filters: Additional filters
            alpha: Balance between BM25 (0.0) and semantic search (1.0)
                  0.3 favors keyword/fuzzy matching, 0.7 favors semantic matching

        Returns:
            List[Dict[str, Any]]: Search results with fuzzy matching capabilities
        """
        await self.client.ensure_connected()
        coll = self.client.client.collections.get(collection)

        try:
            # Use hybrid search which combines BM25 (keyword) + semantic search
            # Lower alpha (0.3) gives more weight to BM25 for better fuzzy matching
            response = coll.query.hybrid(
                query=text,
                limit=limit,
                offset=offset,
                filters=filters,
                alpha=alpha,  # 0.3 = more keyword matching, 0.7 = more semantic matching
                return_metadata=["distance", "certainty", "score"]
            )

            results = []
            for obj in response.objects:
                item = obj.properties.copy()

                # Add search metadata
                if hasattr(obj, 'metadata'):
                    if hasattr(obj.metadata, 'distance'):
                        item["distance"] = obj.metadata.distance
                    if hasattr(obj.metadata, 'certainty'):
                        item["certainty"] = obj.metadata.certainty
                    if hasattr(obj.metadata, 'score'):
                        item["score"] = obj.metadata.score

                # Highlight matched metadata fields if specified
                if metadata_fields:
                    matched_fields = {}
                    for field in metadata_fields:
                        if field in item and item[field]:
                            field_value = str(item[field]).lower()
                            search_terms = text.lower().split()

                            # Check for partial matches (fuzzy matching)
                            for term in search_terms:
                                if term in field_value:
                                    matched_fields[field] = item[field]
                                    break

                    if matched_fields:
                        item["_matched_metadata"] = matched_fields

                results.append(item)

            logger.info(f"Fuzzy search in {collection}: '{text}' -> {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Fuzzy search failed in {collection}: {e}")
            # Fallback to BM25 only
            return await self.bm25(collection, text, filters, limit)

    async def search_with_suggestions(self,
                                      collection: str,
                                      text: str,
                                      *,
                                      limit: int = 10,
                                      include_fuzzy: bool = True,
                                      include_semantic: bool = True,
                                      metadata_fields: List[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Comprehensive search that returns multiple result types for better user experience

        Args:
            collection: Collection name
            text: Search text
            limit: Maximum number of results per search type
            include_fuzzy: Whether to include fuzzy/keyword search results
            include_semantic: Whether to include semantic search results
            metadata_fields: Metadata fields to focus fuzzy search on

        Returns:
            Dict with different search result types:
            {
                "semantic": [...],     # Results from semantic search (content field)
                "fuzzy": [...],        # Results from fuzzy search (metadata fields)
                "combined": [...]      # Hybrid search results
            }
        """
        results = {}

        try:
            # Semantic search on content field
            if include_semantic:
                semantic_results = await self.near_text(
                    collection=collection,
                    text=text,
                    limit=limit
                )
                results["semantic"] = semantic_results

            # Fuzzy search for metadata fields
            if include_fuzzy:
                fuzzy_results = await self.fuzzy_search(
                    collection=collection,
                    text=text,
                    metadata_fields=metadata_fields,
                    limit=limit,
                    alpha=0.2  # More emphasis on keyword matching
                )
                results["fuzzy"] = fuzzy_results

            # Combined hybrid search
            combined_results = await self.hybrid(
                collection=collection,
                text=text,
                limit=limit,
                alpha=0.5  # Balanced approach
            )
            results["combined"] = combined_results

            logger.info(f"Comprehensive search in {collection}: "
                        f"semantic={len(results.get('semantic', []))}, "
                        f"fuzzy={len(results.get('fuzzy', []))}, "
                        f"combined={len(results.get('combined', []))}")

        except Exception as e:
            logger.error(f"Comprehensive search failed: {e}")
            # Fallback to basic search
            results["fallback"] = await self.bm25(collection, text, limit=limit)

        return results
