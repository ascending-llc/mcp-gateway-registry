from typing import Optional, Dict, Any
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field, SkipValidation
from ..adapters.adapter import VectorStoreAdapter
from ..enum.enums import SearchType
import logging

logger = logging.getLogger(__name__)


class AdapterRetriever(BaseRetriever):
    """
    Custom retriever that uses VectorStoreAdapter with configurable search types.
    
    Supports multiple search strategies: NEAR_TEXT, BM25, HYBRID.
    """

    adapter: SkipValidation[VectorStoreAdapter]
    collection_name: Optional[str] = None
    search_type: SearchType = SearchType.NEAR_TEXT
    search_kwargs: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True  # Allow VectorStoreAdapter type

    def _get_relevant_documents(self,
                                query: str,
                                *,
                                run_manager: CallbackManagerForRetrieverRun
                                ) -> list[Document]:
        try:
            if self.search_type == SearchType.NEAR_TEXT:
                return self.adapter.similarity_search(
                    query=query,
                    collection_name=self.collection_name,
                    **self.search_kwargs
                )
            elif self.search_type == SearchType.BM25:
                return self.adapter.bm25_search(
                    query=query,
                    collection_name=self.collection_name,
                    **self.search_kwargs
                )
            elif self.search_type == SearchType.HYBRID:
                return self.adapter.hybrid_search(
                    query=query,
                    collection_name=self.collection_name,
                    **self.search_kwargs
                )
            else:
                return self.adapter.search(
                    query=query,
                    search_type=self.search_type,
                    collection_name=self.collection_name,
                    **self.search_kwargs
                )
        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            run_manager.on_retriever_error(e)
            return []

    @property
    def vectorstore(self):
        return self.adapter.get_vector_store(self.collection_name)
