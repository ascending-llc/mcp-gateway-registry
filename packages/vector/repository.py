import asyncio
import logging
from typing import Optional, List, Dict, Any, TypeVar, Generic, Type, Set, Callable, Awaitable
from functools import wraps
from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever
from .batch_result import BatchResult
from .enum.enums import SearchType, RerankerProvider
from .retrievers.adapter_retriever import AdapterRetriever
from .client import DatabaseClient
from .protocols import VectorStorable, ContentGenerator
from .exceptions import RepositoryError

logger = logging.getLogger(__name__)

# Type variables
T = TypeVar('T', bound=VectorStorable)
P = TypeVar('P')
R = TypeVar('R')


def async_wrapper(func: Callable[..., R]) -> Callable[..., Awaitable[R]]:
    """
    Decorator to auto-generate async version of sync method.

    Eliminates boilerplate async methods that just wrap sync calls with asyncio.to_thread.

    """

    @wraps(func)
    async def wrapper(*args, **kwargs) -> R:
        return await asyncio.to_thread(func, *args, **kwargs)

    wrapper.__name__ = f"a{func.__name__}"  # asave, aget, etc.
    wrapper.__doc__ = f"Async version of {func.__name__} (auto-generated)"
    return wrapper


class Repository(Generic[T]):
    """
    Generic repository for vector database operations with smart update detection.

    Type-safe, ORM-style API for model operations with automatic vectorization
    and intelligent change detection to avoid unnecessary re-vectorization.

    Type Parameters:
        T: Model class implementing VectorStorable protocol
    """

    def __init__(self, db_client: DatabaseClient, model_class: Type[T]):
        """
        Initialize repository with database client and model class.

        Args:
            model_class: Model class implementing VectorStorable protocol

        Raises:
            TypeError: If model_class doesn't implement VectorStorable
        """
        # Validate that model_class implements VectorStorable protocol
        if not isinstance(model_class, type):
            raise TypeError(f"model_class must be a class, got {type(model_class)}")

        # Runtime check for VectorStorable protocol
        required_attrs = ['COLLECTION_NAME', 'to_document', 'from_document', 'get_safe_metadata_fields']
        missing_attrs = [attr for attr in required_attrs if not hasattr(model_class, attr)]
        if missing_attrs:
            raise TypeError(
                f"{model_class.__name__} must implement VectorStorable protocol. "
                f"Missing: {', '.join(missing_attrs)}"
            )

        self.db_client = db_client
        self.adapter = db_client.adapter
        self.model_class = model_class
        self.collection = model_class.COLLECTION_NAME

        logger.debug(f"Repository initialized for {model_class.__name__} -> {self.collection}")

    # ========================================
    # CRUD Operations with Smart Update Detection
    # ========================================

    def save(self, instance: T) -> Optional[str]:
        """
        Save a model instance to vector database.

        Args:
            instance: Model instance to save

        Returns:
            Document ID if successful, None if failed

        Raises:
            RepositoryError: If save operation fails critically
        """
        try:
            doc = instance.to_document()
            doc_id = self.adapter.add_documents(
                documents=[doc],
                collection_name=self.collection
            )

            if doc_id and len(doc_id) > 0:
                logger.debug(f"Saved {self.model_class.__name__} with ID: {doc_id[0]}")
                return doc_id[0]

            logger.warning(f"Save returned empty ID for {self.model_class.__name__}")
            return None

        except Exception as e:
            logger.error(f"Save failed for {self.model_class.__name__}: {e}", exc_info=True)
            raise RepositoryError(f"Failed to save {self.model_class.__name__}") from e

    def get(self, doc_id: str) -> Optional[T]:
        """
        Get a model instance by ID.

        Args:
            doc_id: Document ID

        Returns:
            Model instance if found, None otherwise
        """
        try:
            docs = self.adapter.get_by_ids(
                ids=[doc_id],
                collection_name=self.collection
            )
            if docs and len(docs) > 0:
                data = self.model_class.from_document(docs[0])
                logger.debug(f"Retrieved {self.model_class.__name__} with ID: {doc_id}")
                return data

            logger.debug(f"{self.model_class.__name__} not found: {doc_id}")
            return None

        except Exception as e:
            logger.error(f"Get failed for ID {doc_id}: {e}")
            return None

    def update(
            self,
            instance: T,
            fields_changed: Optional[Set[str]] = None,
            create_if_missing: bool = False
    ) -> bool:
        """
        Update model instance with smart re-vectorization detection.

        Optimizes updates by:
        1. Checking if only metadata fields changed (no re-vectorization needed)
        2. Comparing generated content to detect actual content changes
        3. Optionally creating document if it doesn't exist (upsert behavior)

        Args:
            instance: Model instance to update
            fields_changed: Set of field names that changed (optional, for optimization)
            create_if_missing: If True, create the document if it doesn't exist (upsert behavior)

        Returns:
            True if updated/created successfully, False otherwise
        """
        try:
            mongo_id = str(instance.id)

            vector_docs = self.adapter.filter_by_metadata(
                filters={"server_id": mongo_id},
                limit=1,
                collection_name=self.collection
            )

            if not vector_docs:
                logger.warning(f"{self.model_class.__name__} not found in vector DB: {mongo_id}")
                if create_if_missing:
                    logger.info(f"Creating new document for {self.model_class.__name__} {mongo_id}")
                    self.save(instance)
                return True

            weaviate_uuid = vector_docs[0].id
            logger.debug(f"Found {self.model_class.__name__} MongoDB ID: {mongo_id}, Weaviate UUID: {weaviate_uuid}")

            # Check if only safe metadata fields changed
            safe_fields = instance.get_safe_metadata_fields()

            if fields_changed and fields_changed.issubset(safe_fields):
                # Metadata-only update (no re-vectorization needed)
                logger.info(f"Metadata-only update for {self.model_class.__name__} {mongo_id}")

                if hasattr(self.adapter, 'update_metadata'):
                    new_doc = instance.to_document()
                    metadata = new_doc.metadata
                    result = self.adapter.update_metadata(
                        doc_id=weaviate_uuid,
                        metadata=metadata,
                        collection_name=self.collection
                    )
                    logger.info(f"Metadata updated for {self.model_class.__name__} {mongo_id}")
                    return result
                else:
                    logger.warning("Adapter doesn't support metadata-only updates, falling back to full update")

            # Check if content actually changed (smart detection)
            if isinstance(instance, ContentGenerator):
                # Get old content from existing instance
                old_content = vector_docs[0].metadata.get("content")
                new_content = instance.generate_content()

                if old_content and old_content == new_content:
                    logger.info(
                        f"Content unchanged for {self.model_class.__name__} {mongo_id}, "
                        f"skipping re-vectorization"
                    )
                    # Still update metadata in case it changed
                    if hasattr(self.adapter, 'update_metadata'):
                        new_doc = instance.to_document()
                        result = self.adapter.update_metadata(
                            doc_id=weaviate_uuid,
                            metadata=new_doc.metadata,
                            collection_name=self.collection
                        )
                        if result:
                            logger.info(f"Metadata updated (content unchanged) for"
                                        f" {self.model_class.__name__} {mongo_id}")
                        return result
                    return True

            # Full update with re-vectorization (atomic operation)
            logger.info(f"Full update with re-vectorization for {self.model_class.__name__} {mongo_id}")

            # 1: Delete old version (use Weaviate UUID)
            if not self.delete(weaviate_uuid):
                logger.warning(f"Delete failed during update for MongoDB ID {mongo_id}, Weaviate UUID {weaviate_uuid}")
                return False

            # 2: Save new version
            new_weaviate_id = self.save(instance)
            if new_weaviate_id:
                logger.info(f"Updated {self.model_class.__name__} MongoDB ID {mongo_id} successfully "
                            f"(old Weaviate UUID: {weaviate_uuid}, new: {new_weaviate_id})")
                return True
            else:
                logger.error(f"Save failed during update for MongoDB ID {mongo_id}")
                return False

        except Exception as e:
            logger.error(f"Update failed for {self.model_class.__name__}: {e}", exc_info=True)
            return False

    def upsert(
            self,
            instance: T,
            fields_changed: Optional[Set[str]] = None
    ) -> bool:
        """
        Upsert (Update or Insert) model instance.
        
        This is a convenience method that always creates the document if it doesn't exist.
        Equivalent to: update(instance, fields_changed=fields_changed, create_if_missing=True)
        
        Args:
            instance: Model instance to upsert
            fields_changed: Set of field names that changed (optional, for optimization)
        """
        return self.update(instance, fields_changed=fields_changed, create_if_missing=True)

    def delete(self, doc_id: str) -> bool:
        """
        Delete a model instance by ID.

        Args:
            doc_id: Document ID to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            self.adapter.delete(
                ids=[doc_id],
                collection_name=self.collection
            )
            logger.debug(f"Deleted {self.model_class.__name__} with ID: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Delete failed for ID {doc_id}: {e}")
            return False

    # ========================================
    # Bulk Operations
    # ========================================

    def bulk_save(self, instances: List[T]) -> BatchResult:
        """
        Bulk save model instances for better performance.

        Args:
            instances: List of model instances

        Returns:
            BatchResult with success/failure counts
        """
        if not instances:
            return BatchResult(total=0, successful=0, failed=0)

        try:
            docs = [inst.to_document() for inst in instances]
            doc_ids = self.adapter.add_documents(
                documents=docs,
                collection_name=self.collection
            )

            successful = len(doc_ids) if doc_ids else 0
            total = len(instances)
            failed = total - successful

            logger.info(
                f"Bulk saved {successful}/{total} {self.model_class.__name__} instances "
                f"(success rate: {successful / total * 100:.1f}%)"
            )

            return BatchResult(total=total, successful=successful, failed=failed)

        except Exception as e:
            logger.error(f"Bulk save failed: {e}", exc_info=True)
            return BatchResult(total=len(instances), successful=0, failed=len(instances))

    def delete_by_filter(self, filters: Any) -> Optional[int]:
        """
        Delete model instances by filter conditions.

        Args:
            filters: Database-specific filter object or dict
                - Dict: {"field": "value"} or {"field": {"$in": ["val1", "val2"]}}
                - Weaviate: weaviate.classes.query.Filter object

        Returns:
            Number of deleted documents, or None if operation failed
        """
        try:
            if hasattr(self.adapter, 'delete_by_filter'):
                deleted = self.adapter.delete_by_filter(
                    filters=filters,
                    collection_name=self.collection
                )
                logger.info(f"Deleted {deleted} {self.model_class.__name__} instances by filter")
                return deleted
            else:
                logger.warning(f"Adapter {type(self.adapter).__name__} does not support delete_by_filter")
                return 0
        except Exception as e:
            logger.error(f"Delete by filter failed: {e}", exc_info=True)
            raise RepositoryError(f"Failed to delete by filter") from e

    def batch_update_by_filter(
            self,
            filters: Any,
            update_data: Dict[str, Any],
            limit: int = 1000
    ) -> int:
        """
        Batch update instances matching filter conditions.

        Intelligently detects if only metadata fields are being updated
        to avoid unnecessary re-vectorization.

        Args:
            filters: Filter conditions
            update_data: Dictionary of fields to update
            limit: Maximum number of instances to update

        Returns:
            Number of updated instances
        """
        try:
            # Check if only safe metadata fields are being updated
            safe_fields = self.model_class.get_safe_metadata_fields()
            update_fields = set(update_data.keys())

            if update_fields.issubset(safe_fields):
                # Metadata-only batch update (fast path)
                logger.info(f"Batch metadata-only update for {self.model_class.__name__}")

                if hasattr(self.adapter, 'batch_update_properties'):
                    # Get matching instances to extract IDs
                    instances = self.filter(filters=filters, limit=limit)
                    if not instances:
                        logger.info("No documents found matching filters")
                        return 0

                    doc_ids = [str(inst.id) for inst in instances]

                    return self.adapter.batch_update_properties(
                        doc_ids=doc_ids,
                        properties=update_data,
                        collection_name=self.collection
                    )

            # Full update with re-vectorization (slow path)
            logger.info(f"Batch full update with re-vectorization for {self.model_class.__name__}")
            instances = self.filter(filters=filters, limit=limit)

            if not instances:
                logger.info("No documents found matching filters")
                return 0

            # Apply updates to instances
            for inst in instances:
                for key, value in update_data.items():
                    setattr(inst, key, value)

            # Bulk save updated instances
            result = self.bulk_save(instances)
            return result.successful

        except Exception as e:
            logger.error(f"Batch update by filter failed: {e}", exc_info=True)
            return 0

    # ========================================
    # Search Operations
    # ========================================

    def search(
            self,
            query: str,
            search_type: SearchType = SearchType.HYBRID,
            k: int = 10,
            filters: Optional[Any] = None
    ) -> List[T]:
        """
        Search for model instances using natural language query.

        Args:
            query: Search query text
            search_type: Type of search (NEAR_TEXT, BM25, HYBRID)
            k: Number of results to return
            filters: Optional filter conditions

        Returns:
            List of model instances ranked by relevance
        """
        try:
            results = self.adapter.search(
                query=query,
                search_type=search_type,
                k=k,
                filters=filters,
                collection_name=self.collection
            )

            instances = []
            for doc in results:
                try:
                    data = self.model_class.from_document(doc)
                    # Reconstruct model instance (may be partial)
                    instances.append(data)
                except Exception as e:
                    logger.warning(f"Failed to convert document to model: {e}")

            logger.info(f"Search returned {len(instances)} {self.model_class.__name__} instances")
            return instances

        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return []

    def filter(
            self,
            filters: Any,
            limit: int = 10
    ) -> List[T]:
        """
        Filter model instances by metadata conditions (no semantic search).

        Args:
            filters: Filter conditions (dict or native format)
            limit: Maximum results to return

        Returns:
            List of matching model instances
        """
        try:
            results = self.adapter.filter_by_metadata(
                filters=filters,
                limit=limit,
                collection_name=self.collection
            )

            instances = []
            for doc in results:
                try:
                    data = self.model_class.from_document(doc)
                    instances.append(data)
                except Exception as e:
                    logger.warning(f"Failed to convert document: {e}")

            logger.debug(f"Filter returned {len(instances)} {self.model_class.__name__} instances")
            return instances

        except Exception as e:
            logger.error(f"Filter failed: {e}")
            return []

    def search_with_rerank(
            self,
            query: str,
            k: int = 10,
            candidate_k: Optional[int] = None,
            search_type: SearchType = SearchType.HYBRID,
            filters: Optional[Any] = None,
            reranker_type: RerankerProvider = RerankerProvider.FLASHRANK,
            reranker_kwargs: Optional[Dict[str, Any]] = None
    ) -> List[T]:
        """
        Search with reranking for improved relevance.

        Fetches candidate_k results, reranks them, returns top k.

        Args:
            query: Search query
            k: Final number of results
            candidate_k: Number of candidates for reranking (default: k*3)
            search_type: Type of search
            filters: Filter conditions
            reranker_type: Reranker to use
            reranker_kwargs: Additional reranker parameters

        Returns:
            List of reranked model instances
        """
        try:
            if candidate_k is None:
                candidate_k = min(k * 3, 100)

            results = self.adapter.search_with_rerank(
                query=query,
                k=k,
                candidate_k=candidate_k,
                search_type=search_type,
                filters=filters,
                reranker_type=reranker_type,
                reranker_kwargs=reranker_kwargs or {},
                collection_name=self.collection
            )

            instances = []
            for doc in results:
                try:
                    data = self.model_class.from_document(doc)
                    instances.append(data)
                except Exception as e:
                    logger.warning(f"Failed to convert document: {e}")

            logger.info(f"Rerank search returned {len(instances)} {self.model_class.__name__} instances")
            return instances

        except Exception as e:
            logger.error(f"Rerank search failed: {e}", exc_info=True)
            return []

    # ========================================
    # Retriever Methods (for LangChain integration)
    # ========================================

    def get_retriever(
            self,
            search_type: SearchType = SearchType.HYBRID,
            k: int = 10
    ):
        """
        Get a LangChain retriever for RAG applications.

        Args:
            search_type: Type of search
            k: Number of results

        Returns:
            AdapterRetriever instance
        """
        return AdapterRetriever(
            adapter=self.adapter,
            collection_name=self.collection,
            search_type=search_type,
            search_kwargs={"k": k}
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
            reranker_type: Reranker provider
            search_type: Type of search
            search_kwargs: Search parameters
            reranker_kwargs: Reranker parameters

        Returns:
            ContextualCompressionRetriever with reranking
        """
        from .retrievers.reranker import create_reranker

        base_retriever = self.get_retriever(
            search_type=search_type,
            k=search_kwargs.get("k", 10) if search_kwargs else 10
        )

        reranker = create_reranker(
            reranker_type=reranker_type,
            **(reranker_kwargs or {})
        )

        return ContextualCompressionRetriever(
            base_compressor=reranker,
            base_retriever=base_retriever
        )

    # ========================================
    # Auto-generated Async Methods
    # ========================================
    asave = async_wrapper(save)
    aget = async_wrapper(get)
    aupdate = async_wrapper(update)
    aupsert = async_wrapper(upsert)
    adelete = async_wrapper(delete)
    abulk_save = async_wrapper(bulk_save)
    adelete_by_filter = async_wrapper(delete_by_filter)
    abatch_update_by_filter = async_wrapper(batch_update_by_filter)
    asearch = async_wrapper(search)
    afilter = async_wrapper(filter)
    asearch_with_rerank = async_wrapper(search_with_rerank)
