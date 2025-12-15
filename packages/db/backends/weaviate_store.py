from typing import Dict, Any, List, Optional
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
import logging
from ..adapters.adapter import VectorStoreAdapter
from ..enum.enums import SearchType

logger = logging.getLogger(__name__)


class WeaviateStore(VectorStoreAdapter):
    """
    Weaviate adapter implementation.
    
    Uses LangChain's WeaviateVectorStore as the underlying implementation.
    Extends with Weaviate-specific features.
    """

    def __init__(self, embedding, config: Dict[str, Any], embedding_config: Dict[str, Any] = None):
        """Initialize Weaviate adapter."""
        super().__init__(embedding, config, embedding_config)
        self._client = None

    def _get_client(self):
        """Get or create Weaviate client."""
        if self._client is None:
            import weaviate
            from weaviate.auth import AuthApiKey

            self._client = weaviate.connect_to_local(
                host=self.config.get('host', 'localhost'),
                port=self.config.get('port', 8080),
                grpc_port=self.config.get('grpc_port', 50051),
                auth_credentials=AuthApiKey(self.config.get('api_key')) if self.config.get('api_key') else None
            )
        return self._client

    def _create_vector_store(self, collection_name: str) -> VectorStore:
        """
        Create LangChain WeaviateVectorStore for collection.
        
        Returns:
            WeaviateVectorStore instance
        """
        from langchain_weaviate import WeaviateVectorStore

        return WeaviateVectorStore(
            client=self._get_client(),
            index_name=collection_name,
            text_key='content',
            embedding=self.embedding
        )

    def close(self):
        """Close Weaviate connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._stores.clear()

    # ========================================
    # Filter normalization (Smart conversion)
    # ========================================

    def _is_native_filter(self, filters: Any) -> bool:
        """Check if filters is Weaviate Filter object."""
        try:
            return hasattr(filters, '__class__') and 'Filter' in filters.__class__.__name__
        except Exception as e:
            logger.error(f"_is_native_filter: {e}")
            return False

    def _dict_to_native_filter(self, filters: Dict[str, Any]):
        """
        Convert dict to Weaviate Filter object.
        
        Supports:
        - Simple: {"key": "value"}
        - Operators: {"key": {"$gt": 100}}
        - Combining: {"$and": [...], "$or": [...]}
        """
        from weaviate.classes.query import Filter

        def convert_condition(key: str, value: Any):
            if isinstance(value, dict):
                filter_obj = None
                for op, val in value.items():
                    if op == "$eq":
                        f = Filter.by_property(key).equal(val)
                    elif op == "$ne":
                        f = Filter.by_property(key).not_equal(val)
                    elif op == "$gt":
                        f = Filter.by_property(key).greater_than(val)
                    elif op == "$gte":
                        f = Filter.by_property(key).greater_or_equal(val)
                    elif op == "$lt":
                        f = Filter.by_property(key).less_than(val)
                    elif op == "$lte":
                        f = Filter.by_property(key).less_or_equal(val)
                    elif op == "$in":
                        f = Filter.by_property(key).contains_any(val)
                    else:
                        logger.warning(f"Unsupported operator: {op}")
                        continue
                    filter_obj = f if filter_obj is None else (filter_obj & f)
                return filter_obj
            else:
                return Filter.by_property(key).equal(value)

        def parse_filters(f: Dict[str, Any]):
            if "$and" in f:
                conditions = [parse_filters(c) if isinstance(c, dict) else c for c in f["$and"]]
                result = conditions[0]
                for c in conditions[1:]:
                    result = result & c
                return result
            elif "$or" in f:
                conditions = [parse_filters(c) if isinstance(c, dict) else c for c in f["$or"]]
                result = conditions[0]
                for c in conditions[1:]:
                    result = result | c
                return result
            else:
                filter_objs = []
                for key, value in f.items():
                    if key not in ["$and", "$or", "$not"]:
                        filter_objs.append(convert_condition(key, value))

                if not filter_objs:
                    return None
                result = filter_objs[0]
                for f in filter_objs[1:]:
                    result = result & f
                return result

        return parse_filters(filters)

    # ========================================
    # Extended features implementation
    # ========================================

    def get_collection(self, collection_name):
        """
        Get Weaviate collection by name.
        """
        client = self._get_client()
        if self.collection_exists(collection_name):
            return client.collections.get(collection_name)
        raise Exception(f"Failed to get collection: {collection_name}")

    def get_by_id(
            self,
            doc_id: str,
            collection_name: Optional[str] = None
    ) -> Optional[Document]:
        """
        Get document by ID using Weaviate client.
        
        Args:
            doc_id: Document ID (UUID)
            collection_name: Collection name
            
        Returns:
            LangChain Document or None
        """
        collection = self.get_collection(collection_name)
        try:
            obj = collection.query.fetch_object_by_id(doc_id)
            if obj:
                return Document(
                    page_content=obj.properties.get('content', ''),
                    metadata=obj.properties,
                    id=str(obj.uuid)
                )
        except Exception as e:
            logger.error(f"Failed to get document by ID: {e}")

        return None

    def list_collections(self) -> List[str]:
        """List all Weaviate collections."""
        try:
            client = self._get_client()
            collections = client.collections.list_all()
            if isinstance(collections, dict):
                return list(collections.keys())
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return list(self._stores.keys())

    def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists in Weaviate."""
        try:
            client = self._get_client()
            return client.collections.exists(collection_name)
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            return collection_name in self._stores

    def filter_by_metadata(
            self,
            filters: Any,
            limit: int = 100,
            collection_name: Optional[str] = None,
            **kwargs
    ) -> List[Document]:
        """Implement Weaviate metadata filtering (filters already normalized)."""
        collection = self.get_collection(collection_name)
        try:
            response = collection.query.fetch_objects(
                filters=filters,
                limit=limit
            )
            docs = self.get_document_response(response)
            return docs
        except Exception as e:
            logger.error(f"Filter by metadata failed: {e}")
            return []

    def bm25_search(self,
                    query: str,
                    k: int = 10,
                    filters: Any = None,
                    collection_name: Optional[str] = None,
                    **kwargs
                    ) -> List[Document]:
        collection = self.get_collection(collection_name)
        try:
            response = collection.query.bm25(
                query=query,
                limit=k,
                filters=filters,
                **kwargs
            )
            docs = self.get_document_response(response)
            return docs
        except Exception as e:
            logger.error(f"bm25 text failed: {e}")
            return []

    def hybrid_search(self,
                      query: str,
                      k: int = 10,
                      alpha: float = 0.5,
                      filters: Any = None,
                      collection_name: Optional[str] = None,
                      **kwargs
                      ) -> List[Document]:
        collection = self.get_collection(collection_name)
        try:
            response = collection.query.hybrid(
                query=query,
                limit=k,
                filters=filters,
                **kwargs
            )
            docs = self.get_document_response(response)
            return docs
        except Exception as e:
            logger.error(f"Hybrid text failed: {e}")
            return []

    def near_text(self,
                  query: str,
                  k: int = 10,
                  alpha: float = 0.5,
                  filters: Any = None,
                  collection_name: Optional[str] = None,
                  **kwargs) -> List[Document]:
        collection = self.get_collection(collection_name)
        try:
            response = collection.query.near_text(
                query=query,
                limit=k,
                filters=filters,
                **kwargs
            )
            docs = self.get_document_response(response)
            return docs
        except Exception as e:
            logger.error(f"Near text failed: {e}")
            return []

    def search(self,
               query: str,
               search_type: SearchType = SearchType.NEAR_TEXT,
               k: int = 10,
               filters: Any = None,
               collection_name: Optional[str] = None,
               **kwargs) -> List[Document]:
        if search_type == SearchType.BM25:
            return self.bm25_search(query, k, filters, collection_name, **kwargs)
        elif search_type == SearchType.HYBRID:
            return self.hybrid_search(query, k, filters, collection_name, **kwargs)
        elif search_type == SearchType.NEAR_TEXT:
            return self.near_text(query, k, filters, collection_name, **kwargs)
        else:
            logger.error(f"Unknown search type: {search_type}")

    @staticmethod
    def get_document_response(response):
        docs = []
        for obj in response.objects:
            doc = Document(
                page_content=obj.properties.get('content', ''),
                metadata=obj.properties,
                id=str(obj.uuid)
            )
            docs.append(doc)
        return docs
