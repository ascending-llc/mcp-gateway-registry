from typing import Dict, Any, List, Optional
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
import logging
from ..adapters.adapter import VectorStoreAdapter
from ..enum.enums import SearchType

logger = logging.getLogger(__name__)


class ChromaStore(VectorStoreAdapter):
    """
    Chroma adapter implementation.
    
    Uses LangChain's Chroma as the underlying implementation.
    Extends with Chroma-specific features.
    """

    def __init__(self, embedding, config: Dict[str, Any], embedding_config: Dict[str, Any] = None):
        """Initialize Chroma adapter."""
        super().__init__(embedding, config, embedding_config)
        self._persist_directory = config.get('persist_directory', './chroma_db')
        self._chroma_client = None

    def _get_chroma_client(self):
        """Get or create Chroma client."""
        if self._chroma_client is None:
            import chromadb
            self._chroma_client = chromadb.PersistentClient(
                path=self._persist_directory
            )
        return self._chroma_client

    def _create_vector_store(self, collection_name: str) -> VectorStore:
        """
        Create LangChain Chroma for collection.
        
        Returns:
            Chroma instance
        """
        from langchain_chroma import Chroma

        return Chroma(
            collection_name=collection_name,
            embedding_function=self.embedding,
            persist_directory=self._persist_directory
        )

    def close(self):
        """Close Chroma resources."""
        self._stores.clear()
        self._chroma_client = None

    # ========================================
    # Filter normalization (Smart conversion)
    # ========================================

    def _is_native_filter(self, filters: Any) -> bool:
        """Check if filters is Chroma dict format (always True for dict)."""
        return isinstance(filters, dict)

    def _dict_to_native_filter(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Chroma uses dict natively, no conversion needed."""
        return filters

    # ========================================
    # Extended features implementation
    # ========================================

    def get_by_id(
            self,
            doc_id: str,
            collection_name: Optional[str] = None
    ) -> Optional[Document]:
        """
        Get document by ID using Chroma client.
        
        Args:
            doc_id: Document ID
            collection_name: Collection name
            
        Returns:
            LangChain Document or None
        """
        try:
            client = self._get_chroma_client()
            collection = client.get_collection(
                name=collection_name or self._default_collection
            )

            result = collection.get(
                ids=[doc_id],
                include=['documents', 'metadatas']
            )

            if result and result['documents']:
                return Document(
                    page_content=result['documents'][0],
                    metadata=result['metadatas'][0] if result['metadatas'] else {},
                    id=doc_id
                )
        except Exception as e:
            logger.error(f"Failed to get document by ID: {e}")

        return None

    def list_collections(self) -> List[str]:
        """List all Chroma collections."""
        try:
            client = self._get_chroma_client()
            collections = client.list_collections()
            return [c.name for c in collections]
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return list(self._stores.keys())

    def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists in Chroma."""
        try:
            return collection_name in self.list_collections()
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
        """Implement Chroma metadata filtering (filters already normalized)."""
        client = self._get_chroma_client()
        collection = client.get_collection(
            name=collection_name or self._default_collection
        )

        try:
            result = collection.get(
                where=filters,
                limit=limit,
                include=['documents', 'metadatas']
            )

            docs = []
            if result and result['documents']:
                for i, doc_text in enumerate(result['documents']):
                    doc = Document(
                        page_content=doc_text,
                        metadata=result['metadatas'][i] if result['metadatas'] else {},
                        id=result['ids'][i] if result.get('ids') else None
                    )
                    docs.append(doc)
            return docs
        except Exception as e:
            logger.error(f"Filter by metadata failed: {e}")
            return []

    def bm25_search(self,
                    query: str,
                    k: int = 10,
                    filters: Any = None,
                    collection_name: Optional[str] = None,
                    **kwargs) -> List[Document]:
        raise NotImplementedError(
            "Chroma does not support BM25 search. Use similarity_search instead."
        )

    def hybrid_search(self,
                      query: str,
                      k: int = 10,
                      alpha: float = 0.5,
                      filters: Any = None,
                      collection_name: Optional[str] = None, **kwargs) -> List[Document]:
        raise NotImplementedError(
            "Chroma does not support hybrid search. Use similarity_search instead."
        )

    def near_text(self, **kwargs):
        raise NotImplementedError(
            "Chroma does not support near_text search. Use similarity_search instead."
        )

    def search(self, search_type: SearchType, query: str, k: int = 10, filters: Any = None,
               collection_name: Optional[str] = None, **kwargs) -> List[Document]:
        pass