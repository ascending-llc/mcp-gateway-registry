import logging
from typing import Optional, List, Dict, Any, TypeVar, Generic, Type, TYPE_CHECKING
from langchain_core.documents import Document

from .batch_result import BatchResult
from .enum.enums import SearchType

if TYPE_CHECKING:
    from .client import DatabaseClient

logger = logging.getLogger(__name__)

T = TypeVar('T')


class Repository(Generic[T]):
    """
    Generic repository for model CRUD and search operations.
    
    Provides ORM-style API for type-safe model operations.
    Directly uses the adapter for database operations.
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
        Save a model instance.
        
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

    def get(self, doc_id: str) -> Optional[T]:
        """
        Get model instance by ID.
        
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

    def update(self, instance: T) -> bool:
        """
        Update model instance.
        
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

    def delete(self, doc_id: str) -> bool:
        """
        Delete model instance by ID.
        
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

    def similarity_search(
            self,
            query: str,
            k: int = 10,
            filters: Optional[Any] = None
    ) -> List[T]:
        """
        Semantic search for model instances.
        
        Args:
            query: Search query text
            k: Number of results to return
            filters: Optional database-specific filter object
                - Weaviate: weaviate.classes.query.Filter object
                - Chroma: dict with Chroma filter syntax
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

    def search(
            self,
            search_type: SearchType,
            query: str,
            k: int = 10,
            filters: Optional[Any] = None
    ) -> List[T]:
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



    def filter(
            self,
            filters: Any,
            limit: int = 100
    ) -> List[T]:
        """
        Filter model instances by metadata only (no vector search).
        
        Uses database-specific metadata filtering.
        
        Args:
            filters: Database-specific filter object
                - Weaviate: weaviate.classes.query.Filter object
                - Chroma: dict with Chroma filter syntax
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

    def bulk_save(self, instances: List[T]) -> BatchResult:
        """
        Bulk save model instances.
        
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

    def delete_by_filter(self, filters: Any) -> int:
        """
        Delete model instances by filter conditions.
        
        Args:
            filters: Database-specific filter object
                - Weaviate: weaviate.classes.query.Filter object
                - Chroma: dict with Chroma filter syntax
        """
        try:
            instances = self.filter(filters=filters, limit=1000)
            deleted_count = 0
            for inst in instances:
                if self.delete(inst.id):
                    deleted_count += 1
            return deleted_count
        except Exception as e:
            logger.error(f"Delete by filter failed: {e}")
            return 0
