import logging
import uuid
from typing import Any, Dict, List, Optional, Type, TypeVar, Union
from ..core.exceptions import DoesNotExist, MultipleObjectsReturned
from ..core.enums import SearchType
from ..search import SearchManager, AdvancedQuerySet
from .queryset import QuerySet

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='Model')


class ObjectManager:
    """Manages CRUD operations and searches for model instances"""
    
    def __init__(self, model_class: Type[T], client: 'WeaviateClient'):
        self.model_class = model_class
        self.client = client
        self._queryset_class = QuerySet
        self._search_manager = SearchManager(model_class, client)
        self._advanced_queryset_class = AdvancedQuerySet
    
    # ===== CRUD Operations =====
    
    def create(self, **kwargs) -> T:
        """
        Create and save a new object.
        
        Args:
            **kwargs: Object field values
            
        Returns:
            T: Created object instance
        """
        instance = self.model_class(**kwargs)
        return self.save(instance)
    
    def save(self, instance: T) -> T:
        """
        Save object instance to Weaviate.
        
        Args:
            instance: Model instance to save
            
        Returns:
            T: Saved instance with ID populated
        """
        try:
            with self.client.managed_connection() as client:
                collection_name = self.model_class.get_collection_name()
                collection = client.client.collections.get(collection_name)
                
                data = instance.to_dict()
                
                # Remove 'id' from property data as it's a reserved field
                data_without_id = {k: v for k, v in data.items() if k != 'id'}
                
                # Generate UUID if not exists
                object_id = getattr(instance, 'id', None)
                if not object_id:
                    object_id = str(uuid.uuid4())
                
                # Insert data using uuid parameter
                result = collection.data.insert(
                    properties=data_without_id,
                    uuid=object_id
                )
                
                # Set instance ID
                instance.id = str(result)
                logger.info(f"Object saved successfully with ID: {str(result)}")
                return instance
                
        except Exception as e:
            logger.error(f"Failed to save object: {e}")
            raise
    
    def bulk_create(self, instances: List[T]) -> List[T]:
        """
        Bulk create multiple objects efficiently.
        
        Args:
            instances: List of model instances
            
        Returns:
            List[T]: List of created instances with IDs populated
        """
        try:
            with self.client.managed_connection() as client:
                collection_name = self.model_class.get_collection_name()
                collection = client.client.collections.get(collection_name)
                
                from weaviate.collections.classes.data import DataObject
                
                objects_to_insert = []
                for instance in instances:
                    data = instance.to_dict()
                    # Remove 'id' as it's a reserved field
                    data_without_id = {k: v for k, v in data.items() if k != 'id'}
                    
                    # Generate UUID if not exists
                    object_id = getattr(instance, 'id', None)
                    if not object_id:
                        object_id = str(uuid.uuid4())
                    
                    # Use DataObject instead of dict to avoid property nesting
                    objects_to_insert.append(DataObject(
                        properties=data_without_id,
                        uuid=object_id
                    ))
                
                # Bulk insert
                results = collection.data.insert_many(objects_to_insert)
                
                # Process results and set IDs
                if hasattr(results, 'uuids') and results.uuids:
                    for i, uuid_obj in enumerate(results.uuids):
                        if i < len(instances):
                            instances[i].id = str(uuid_obj)
                
                logger.info(f"Bulk created {len(instances)} objects successfully")
                return instances
                
        except Exception as e:
            logger.error(f"Failed to bulk create objects: {e}")
            raise
    
    def bulk_create_from_dicts(self, data_list: List[Dict[str, Any]]) -> List[T]:
        """
        Directly create objects from dictionary list (convenience method).
        
        Args:
            data_list: List of dictionaries with field data
            
        Returns:
            List[T]: Created object instances
        """
        instances = [self.model_class(**data) for data in data_list]
        return self.bulk_create(instances)
    
    def get(self, **kwargs) -> T:
        """
        Get a single object matching the criteria.
        
        Args:
            **kwargs: Filter conditions
            
        Returns:
            T: Object instance
            
        Raises:
            DoesNotExist: No matching object found
            MultipleObjectsReturned: Multiple objects match the criteria
        """
        queryset = self.filter(**kwargs)
        results = queryset.all()
        
        if not results:
            raise DoesNotExist(f"Object matching query does not exist")
        if len(results) > 1:
            raise MultipleObjectsReturned(f"get() returned more than one object")
        
        return results[0]
    
    def delete(self, instance: T) -> bool:
        """
        Delete an object instance.
        
        Args:
            instance: Object instance to delete
            
        Returns:
            bool: True if deletion successful
        """
        try:
            with self.client.managed_connection() as client:
                collection_name = self.model_class.get_collection_name()
                collection = client.client.collections.get(collection_name)
                
                if hasattr(instance, 'id') and instance.id:
                    collection.data.delete_by_id(instance.id)
                    logger.info(f"Object deleted successfully with ID: {instance.id}")
                    return True
                else:
                    logger.error("Cannot delete object without ID")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to delete object: {e}")
            return False
    
    def update(self, instance: T, **kwargs) -> T:
        """
        Update an object instance with new values.
        
        Args:
            instance: Object instance to update
            **kwargs: Fields to update
            
        Returns:
            T: Updated object instance
        """
        try:
            with self.client.managed_connection() as client:
                collection_name = self.model_class.get_collection_name()
                collection = client.client.collections.get(collection_name)
                
                # Update instance properties
                for key, value in kwargs.items():
                    if hasattr(instance, key):
                        setattr(instance, key, value)
                
                # Update in database
                if hasattr(instance, 'id') and instance.id:
                    collection.data.update(
                        uuid=instance.id,
                        properties=instance.to_dict()
                    )
                    logger.info(f"Object updated successfully with ID: {instance.id}")
                    return instance
                else:
                    logger.error("Cannot update object without ID")
                    raise ValueError("Object must have an ID to update")
                    
        except Exception as e:
            logger.error(f"Failed to update object: {e}")
            raise
    
    # ===== Query Methods =====
    
    def filter(self, **kwargs) -> QuerySet:
        """
        Filter objects by field values.
        
        Args:
            **kwargs: Filter conditions
            
        Returns:
            QuerySet: Query set instance (chainable)
        """
        queryset = self._queryset_class(self.model_class, self.client)
        return queryset.filter(**kwargs)
    
    def all(self) -> QuerySet:
        """
        Get all objects.
        
        Returns:
            QuerySet: Query set instance (chainable)
        """
        return self._queryset_class(self.model_class, self.client)
    
    def exclude(self, **kwargs) -> QuerySet:
        """
        Exclude objects matching criteria.
        
        Args:
            **kwargs: Field name and value mappings
            
        Returns:
            QuerySet: Query set instance (chainable)
        """
        queryset = self._queryset_class(self.model_class, self.client)
        return queryset.exclude(**kwargs)
    
    # ===== Basic Search Methods =====
    
    def bm25(self, query: str, properties: Optional[List[str]] = None) -> QuerySet:
        """
        BM25 keyword search.
        
        Args:
            query: Search query
            properties: Properties to search in (None = all text properties)
            
        Returns:
            QuerySet: Query set instance
        """
        queryset = self._queryset_class(self.model_class, self.client)
        return queryset.bm25(query, properties)
    
    def vector_search(self, query: str, limit: Optional[int] = None) -> QuerySet:
        """
        Vector semantic search.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            QuerySet: Query set instance
        """
        queryset = self._queryset_class(self.model_class, self.client)
        return queryset.vector_search(query, limit)
    
    def hybrid_search(self, query: str, alpha: float = 0.5, limit: Optional[int] = None) -> QuerySet:
        """
        Hybrid search (BM25 + vector).
        
        Args:
            query: Search query
            alpha: Weight between BM25 (0.0) and vector (1.0)
            limit: Maximum number of results
            
        Returns:
            QuerySet: Query set instance
        """
        queryset = self._queryset_class(self.model_class, self.client)
        return queryset.hybrid_search(query, alpha, limit)
    
    # ===== Advanced Search Methods =====
    
    def near_text_search(self, text: str, **kwargs) -> List[T]:
        """
        Semantic text search using vector embeddings.
        
        Args:
            text: Text to search for
            **kwargs: Additional search parameters
            
        Returns:
            List[T]: List of model instances
        """
        return self._search_manager.near_text(text, **kwargs)
    
    def bm25_search(self, text: str, **kwargs) -> List[T]:
        """
        BM25 keyword search (direct execution).
        
        Args:
            text: Text to search for
            **kwargs: Additional search parameters
            
        Returns:
            List[T]: List of model instances
        """
        return self._search_manager.bm25(text, **kwargs)
    
    def hybrid_search_advanced(self, text: str, **kwargs) -> List[T]:
        """
        Advanced hybrid search combining BM25 and vector search.
        
        Args:
            text: Text to search for
            **kwargs: Additional search parameters
            
        Returns:
            List[T]: List of model instances
        """
        return self._search_manager.hybrid(text, **kwargs)
    
    def fuzzy_search(self, text: str, **kwargs) -> List[T]:
        """
        Fuzzy search with partial matching capabilities.
        
        Args:
            text: Text to search for
            **kwargs: Additional search parameters
            
        Returns:
            List[T]: List of model instances with fuzzy matching
        """
        return self._search_manager.fuzzy_search(text, **kwargs)
    
    def near_vector_search(self, vector: List[float], **kwargs) -> List[T]:
        """
        Vector similarity search with custom vector.
        
        Args:
            vector: Vector to search for
            **kwargs: Additional search parameters
            
        Returns:
            List[T]: List of model instances
        """
        return self._search_manager.near_vector(vector, **kwargs)
    
    def search_with_suggestions(self, text: str, **kwargs) -> Dict[str, List[T]]:
        """
        Comprehensive search returning multiple result types.
        
        Args:
            text: Search text
            **kwargs: Additional search parameters
            
        Returns:
            Dict[str, List[T]]: Dictionary with different search result types
                {
                    "semantic": [...],  # Semantic search results
                    "fuzzy": [...],     # Fuzzy search results
                    "combined": [...]   # Hybrid search results
                }
        """
        return self._search_manager.search_with_suggestions(text, **kwargs)
    
    def smart_search(
        self,
        query: Optional[str] = None,
        limit: int = 10,
        field_filters: Optional[Dict[str, Any]] = None,
        list_filters: Optional[Dict[str, List[Any]]] = None,
        **kwargs
    ) -> List[T]:
        """
        Smart search with automatic query selection and filter building.
        
        Automatically chooses hybrid search (if query) or filtered fetch (no query).
        Simplifies common search patterns with easy filter building.
        
        Args:
            query: Search text (None for filtered fetch only)
            limit: Maximum results
            field_filters: Exact matches, e.g., {"is_enabled": True}
            list_filters: Contains filters, e.g., {"tags": ["weather"]}
            **kwargs: Additional parameters (alpha, offset, return_metadata)
            
        Returns:
            List[T]: Model instances
            
        Example:
            # Semantic search with filters
            tools = MCPTool.objects.smart_search(
                query="weather forecast",
                limit=10,
                field_filters={"is_enabled": True},
                list_filters={"tags": ["weather", "api"]}
            )
            
            # Filtered fetch without semantic search
            tools = MCPTool.objects.smart_search(
                field_filters={"is_enabled": True},
                limit=20
            )
        """
        return self._search_manager.smart_search(
            query=query,
            limit=limit,
            field_filters=field_filters,
            list_filters=list_filters,
            **kwargs
        )
    
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
                - SearchType.NEAR_TEXT or "near_text": Semantic search using text
                - SearchType.NEAR_VECTOR or "near_vector": Semantic search using vector
                - SearchType.BM25 or "bm25": Keyword search (BM25F)
                - SearchType.HYBRID or "hybrid": Hybrid search (BM25 + semantic)
                - SearchType.FUZZY or "fuzzy": Fuzzy search (typo-tolerant)
                - SearchType.FETCH_OBJECTS or "fetch_objects": Filtered fetch
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
            
            >>> # Using string instead of enum
            >>> results = Article.objects.search_by_type(
            ...     "near_text",
            ...     text="AI research",
            ...     limit=10
            ... )
            
            >>> # Dynamic strategy selection
            >>> user_mode = "semantic"
            >>> search_type = SearchType.NEAR_TEXT if user_mode == "semantic" else SearchType.BM25
            >>> results = Article.objects.search_by_type(search_type, text="data science", limit=10)
        """
        return self._search_manager.search_by_type(search_type, **search_params)
    
    def advanced_search(self) -> AdvancedQuerySet:
        """
        Get advanced query set for chainable search operations.
        
        Returns:
            AdvancedQuerySet: Advanced query set instance
        """
        return self._advanced_queryset_class(self.model_class, self.client)

