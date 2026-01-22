import asyncio
import logging
from typing import Optional, List, Dict, Any, TypeVar, Generic, Type, TYPE_CHECKING
from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever

from .batch_result import BatchResult
from .enum.enums import SearchType, RerankerProvider
from .retrievers.adapter_retriever import AdapterRetriever

if TYPE_CHECKING:
    from .client import DatabaseClient

logger = logging.getLogger(__name__)

T = TypeVar('T')


class Repository(Generic[T]):
    """
    Generic repository for model CRUD and search operations.

    """

    def __init__(self, db_client: 'DatabaseClient', model_class: Type[T]):
        """
        Initialize repository with database client and model class.
        
        Args:
            db_client: DatabaseClient instance
            model_class: Model class with to_document/from_document methods
        """
        self.db_client = db_client
        self.adapter = db_client.adapter
        self.model_class = model_class
        self.collection = getattr(model_class, 'COLLECTION_NAME', 'default')

    def save(self, instance: T) -> Optional[str]:
        """
        Save a model instance (synchronous).
        
        Args:
            instance: Model instance to save
            
        Returns:
            Document ID if successful, None otherwise
        """
        try:
            document = instance.to_document()
            ids = self.adapter.add_documents(
                documents=[document],
                collection_name=self.collection
            )
            return ids[0] if ids else None
        except Exception as e:
            logger.error(f"Failed to save {self.model_class.__name__}: {e}")
            return None

    async def asave(self, instance: T) -> Optional[str]:
        """Save a model instance (asynchronous)."""
        return await asyncio.to_thread(self.save, instance)

    def get(self, doc_id: str) -> Optional[T]:
        """
        Get model instance by ID (synchronous).
        
        Args:
            doc_id: Document ID
            
        Returns:
            Model instance if found, None otherwise
        """
        try:
            doc = self.adapter.get_by_id(
                doc_id=doc_id,
                collection_name=self.collection
            )

            if doc:
                return self.model_class.from_document(doc)
            return None
        except Exception as e:
            logger.error(f"Failed to get {self.model_class.__name__} {doc_id}: {e}")
            return None

    async def aget(self, doc_id: str) -> Optional[T]:
        """Get model instance by ID (asynchronous)."""
        return await asyncio.to_thread(self.get, doc_id)

    def update(self, instance: T) -> bool:
        """
        Update model instance (synchronous).
        
        Args:
            instance: Model instance to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.adapter.delete(
                    ids=[instance.id],
                    collection_name=self.collection
            ):
                return False
            # Save new version
            return self.save(instance) is not None
        except Exception as e:
            logger.error(f"Failed to update {self.model_class.__name__}: {e}")
            return False

    async def aupdate(self, instance: T) -> bool:
        """Update model instance (asynchronous)."""
        return await asyncio.to_thread(self.update, instance)

    def delete(self, doc_id: str) -> bool:
        """
        Delete model instance by ID (synchronous).
        
        Args:
            doc_id: Document ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = self.adapter.delete(
                ids=[doc_id],
                collection_name=self.collection
            )
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to delete {self.model_class.__name__} {doc_id}: {e}")
            return False

    async def adelete(self, doc_id: str) -> bool:
        """Delete model instance by ID (asynchronous)."""
        return await asyncio.to_thread(self.delete, doc_id)

    def similarity_search(
            self,
            query: str,
            k: int = 10,
            filters: Optional[Any] = None
    ) -> List[T]:
        """
        Semantic search for model instances (synchronous).
        
        Args:
            query: Search query text
            k: Number of results to return
            filters: Optional database-specific filter object
                - Weaviate: weaviate.classes.query.Filter object
        """
        try:
            docs = self.adapter.similarity_search(
                query=query,
                k=k,
                filters=filters,
                collection_name=self.collection
            )
            return [self.model_class.from_document(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def asimilarity_search(
            self,
            query: str,
            k: int = 10,
            filters: Optional[Any] = None
    ) -> List[T]:
        """Semantic search for model instances (asynchronous)."""
        return await asyncio.to_thread(
            self.similarity_search,
            query,
            k,
            filters
        )

    def search(
            self,
            query: str,
            search_type: SearchType = SearchType.NEAR_TEXT,
            k: int = 10,
            filters: Optional[Any] = None
    ) -> List[T]:
        """
        Search for model instances using specified search type (synchronous).
        
        Args:
            query: Search query text
            search_type: Type of search (NEAR_TEXT, BM25, HYBRID)
            k: Number of results to return
            filters: Optional database-specific filter object
            
        Returns:
            List of model instances
        """
        try:
            docs = self.adapter.search(
                query=query,
                search_type=search_type,
                k=k,
                filters=filters,
                collection_name=self.collection,
            )
            return [self.model_class.from_document(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def asearch(
            self,
            query: str,
            search_type: SearchType = SearchType.NEAR_TEXT,
            k: int = 10,
            filters: Optional[Any] = None
    ) -> List[T]:
        """Search for model instances using specified search type (asynchronous)."""
        return await asyncio.to_thread(
            self.search,
            query,
            search_type,
            k,
            filters
        )

    def filter(
            self,
            filters: Any,
            limit: int = 100
    ) -> List[T]:
        """
        Filter model instances by metadata only (synchronous, no vector search).
        
        Uses database-specific metadata filtering.
        
        Args:
            filters: Database-specific filter object
                - Weaviate: weaviate.classes.query.Filter object
            limit: Maximum number of results
        """
        try:
            docs = self.adapter.filter_by_metadata(
                filters=filters,
                limit=limit,
                collection_name=self.collection
            )

            return [self.model_class.from_document(doc) for doc in docs]
        except Exception as e:
            logger.error(f"Filter failed: {e}")
            return []

    async def afilter(
            self,
            filters: Any,
            limit: int = 100
    ) -> List[T]:
        """Filter model instances by metadata only (asynchronous)."""
        return await asyncio.to_thread(
            self.filter,
            filters,
            limit
        )

    def bulk_save(self, instances: List[T]) -> BatchResult:
        """
        Bulk save model instances (synchronous).
        
        Args:
            instances: List of model instances to save
            
        Returns:
            BatchResult with operation statistics
        """
        try:
            documents = [inst.to_document() for inst in instances]
            ids = self.adapter.add_documents(
                documents=documents,
                collection_name=self.collection
            )

            successful = len(ids) if ids else 0
            failed = len(instances) - successful

            return BatchResult(
                total=len(instances),
                successful=successful,
                failed=failed,
                errors=[]
            )
        except Exception as e:
            logger.error(f"Bulk save failed: {e}")
            return BatchResult(
                total=len(instances),
                successful=0,
                failed=len(instances),
                errors=[{'message': str(e)}]
            )

    async def abulk_save(self, instances: List[T]) -> BatchResult:
        """Bulk save model instances (asynchronous)."""
        return await asyncio.to_thread(self.bulk_save, instances)

    def delete_by_filter(self, filters: Any) -> int:
        """
        Delete model instances by filter conditions (synchronous).
        
        Args:
            filters: Database-specific filter object
                - Weaviate: weaviate.classes.query.Filter object
        """
        try:
            instances = self.filter(filters=filters, limit=1000)
            
            # Use batch delete if adapter supports it
            if hasattr(self.adapter, 'batch_delete_by_ids'):
                doc_ids = [inst.id for inst in instances]
                return self.adapter.batch_delete_by_ids(doc_ids, self.collection)
            else:
                # Fallback to individual deletes
                deleted_count = 0
                for inst in instances:
                    if self.delete(inst.id):
                        deleted_count += 1
                return deleted_count
        except Exception as e:
            logger.error(f"Delete by filter failed: {e}")
            return 0

    async def adelete_by_filter(self, filters: Any) -> int:
        """Delete model instances by filter conditions (asynchronous)."""
        return await asyncio.to_thread(self.delete_by_filter, filters)

    def batch_update_by_filter(
            self,
            filters: Any,
            update_data: Dict[str, Any],
            limit: int = 1000
    ) -> int:
        """
        Batch update fields without triggering re-vectorization (synchronous).
        
        Args:
            filters: Database-specific filter object
            update_data: Dictionary of fields to update (metadata only, not vector fields)
            limit: Maximum number of documents to update
            
        Returns:
            Number of successfully updated documents
        """
        try:
            # 1. Query matching documents
            instances = self.filter(filters=filters, limit=limit)
            
            if not instances:
                logger.info("No documents found matching filters")
                return 0
            
            # 2. Extract IDs
            doc_ids = [inst.id for inst in instances]
            
            # 3. Use adapter's batch update if available
            if hasattr(self.adapter, 'batch_update_properties'):
                updated_count = self.adapter.batch_update_properties(
                    doc_ids=doc_ids,
                    update_data=update_data,
                    collection_name=self.collection
                )
                logger.info(f"Batch updated {updated_count} documents")
                return updated_count
            else:
                # Fallback: update individually (slower but works)
                logger.warning("Adapter doesn't support batch updates, using fallback")
                updated_count = 0
                for inst in instances:
                    # Update instance fields
                    for key, value in update_data.items():
                        if hasattr(inst, key):
                            setattr(inst, key, value)
                    # Save updated instance
                    if self.update(inst):
                        updated_count += 1
                return updated_count
                
        except Exception as e:
            logger.error(f"Batch update by filter failed: {e}")
            return 0

    async def abatch_update_by_filter(
            self,
            filters: Any,
            update_data: Dict[str, Any],
            limit: int = 1000
    ) -> int:
        """Batch update fields without triggering re-vectorization (asynchronous)."""
        return await asyncio.to_thread(
            self.batch_update_by_filter,
            filters,
            update_data,
            limit
        )

    def get_retriever(self,
                      search_type: SearchType = SearchType.NEAR_TEXT,
                      **search_kwargs
                      ):
        """
        Retrieve model instances by search type.
        """
        return AdapterRetriever(
            adapter=self.adapter,
            collection_name=self.collection,
            search_type=search_type,
            search_kwargs=search_kwargs
        )

    def get_compression_retriever(
            self,
                                  reranker_type: RerankerProvider,
                                  search_type: SearchType = SearchType.HYBRID,
                                  search_kwargs: Optional[dict] = None,
                                  reranker_kwargs: Optional[dict] = None,
    ) -> ContextualCompressionRetriever:
        """
        Get a compression retriever with reranking support.
        
        Args:
            reranker_type: Type of reranker to use (FLASHRANK, etc.)
            search_type: Base search type (NEAR_TEXT, HYBRID, BM25)
            search_kwargs: Arguments for base retriever (k, filters, etc.)
            reranker_kwargs: Arguments for reranker (model, top_k, etc.)
            
        Returns:
            ContextualCompressionRetriever for use in LangChain chains
        """
        base_retriever = self.get_retriever(
            search_type=search_type,
            **(search_kwargs or {})
        )
        compressor = self._create_compressor(reranker_type, reranker_kwargs or {})

        compression_retriever = ContextualCompressionRetriever(
            base_compressor=compressor,
            base_retriever=base_retriever
        )
        return compression_retriever

    def _create_compressor(self, reranker_type: RerankerProvider, kwargs: dict):
        """
        Create compressor based on reranker type.

        Note: https://github.com/PrithivirajDamodaran/FlashRank
        """
        try:
            if reranker_type == RerankerProvider.FLASHRANK:
                from langchain_community.document_compressors import FlashrankRerank
                try:
                    FlashrankRerank.model_rebuild()
                except Exception as e:
                    logger.error(f"Flashrank model rebuild failed: {e}")
                return FlashrankRerank(
                    model=kwargs.get("model", "ms-marco-TinyBERT-L-2-v2"),
                    top_n=kwargs.get("top_k", 10),
                    **{k: v for k, v in kwargs.items() if k not in ["model", "top_k"]}
                )
            else:
                raise ValueError(f"Unsupported reranker type: {reranker_type}")
        except ImportError as e:
            logger.error(f"Failed to import reranker {reranker_type}: {e}")
            raise ImportError(
                f"Required package for {reranker_type} not installed. "
                f"For FlashRank: pip install flashrank. "
                f"For Cohere: pip install cohere"
            ) from e

    def search_with_rerank(
            self,
            query: str,
            reranker_type: RerankerProvider = RerankerProvider.FLASHRANK,
            search_type: SearchType = SearchType.HYBRID,
            k: int = 10,
            candidate_k: int = 50,
            filters: Optional[Any] = None,
            reranker_kwargs: Optional[dict] = None
    ) -> List[T]:
        """
        Search with reranking for improved result quality.
        
        Uses a two-stage retrieval:
        1. Initial search retrieves candidate_k documents
        2. Reranker re-scores and returns top k documents
        
        Args:
            query: Search query text
            reranker_type: Type of reranker (default: FLASHRANK)
            search_type: Base search type (NEAR_TEXT, HYBRID, BM25)
            k: Number of final results to return
            candidate_k: Number of candidates for reranking (should be > k)
            filters: Optional database-specific filter object
            reranker_kwargs: Additional reranker parameters
                - model: Model name for FlashRank (default: ms-marco-TinyBERT-L-2-v2)
                - top_k: Override final result count (default: uses k)
                
        Returns:
            List of reranked model instances
        """
        try:
            search_kwargs = {
                "k": candidate_k,
                "filters": filters
            }
            # Build reranker parameters - k parameter takes precedence
            rerank_kwargs = reranker_kwargs or {}
            if "top_k" not in rerank_kwargs:
                rerank_kwargs["top_k"] = k

            compression_retriever = self.get_compression_retriever(
                reranker_type=reranker_type,
                search_type=search_type,
                search_kwargs=search_kwargs,
                reranker_kwargs=rerank_kwargs
            )
            compressed_docs = compression_retriever.invoke(query)
            return [self.model_class.from_document(doc) for doc in compressed_docs]

        except Exception as e:
            logger.error(f"Rerank search failed: {e}")
            return []
