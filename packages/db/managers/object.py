import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

from ..core.exceptions import DoesNotExist, MultipleObjectsReturned, InsertFailed
from ..search.query_builder import QueryBuilder

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='Model')


@dataclass
class BatchResult:
    """
    Result of a batch operation with success/failure tracking.
    
    Attributes:
        total: Total number of operations attempted
        successful: Number of successful operations
        failed: Number of failed operations
        errors: List of error dictionaries with 'uuid' and 'message'
    """
    total: int
    successful: int
    failed: int
    errors: List[Dict[str, Any]]
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        return (self.successful / self.total * 100) if self.total > 0 else 0.0
    
    @property
    def has_errors(self) -> bool:
        """Check if any operations failed."""
        return self.failed > 0
    
    def __str__(self) -> str:
        return (
            f"BatchResult(total={self.total}, "
            f"successful={self.successful}, "
            f"failed={self.failed}, "
            f"success_rate={self.success_rate:.1f}%)"
        )


class ObjectManager:
    """
    Manager for CRUD operations and collection management.
    
    Follows Weaviate best practices:
    - Uses batch.dynamic() or batch.fixed_size() for optimal performance
    - Provides complete error reporting via BatchResult
    - Supports progress tracking for large imports
    - Optimized get_by_id for fast lookups
    
    Example:
        # CRUD
        article = Article.objects.create(title="Test")
        article = Article.objects.get_by_id("uuid")
        Article.objects.update(article, title="Updated")
        article.delete()
        
        # Batch operations
        result = Article.objects.bulk_create(articles, batch_size=200)
        result = Article.objects.bulk_import(data_list, on_progress=callback)
        count = Article.objects.delete_where(status="draft")
        
        # Collection management
        Article.objects.create_collection()
        Article.objects.delete_collection()
    """
    
    def __init__(self, model_class: Type[T], client: 'WeaviateClient'):
        """
        Initialize object manager.
        
        Args:
            model_class: The model class this manager operates on
            client: Weaviate client instance
        """
        self.model_class = model_class
        self.client = client
        self._collection_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, float] = {}
    
    # ===== Single Object Operations =====
    
    def create(self, **kwargs) -> T:
        """
        Create and save a new object.
        
        Args:
            **kwargs: Field values for the new object
            
        Returns:
            Created and saved model instance
            
        Example:
            article = Article.objects.create(
                title="Hello World",
                content="Test content"
            )
        """
        instance = self.model_class(**kwargs)
        return self.save(instance)
    
    def save(self, instance: T) -> T:
        """
        Save an object instance to Weaviate.
        
        Args:
            instance: Model instance to save
            
        Returns:
            Saved instance with ID populated
            
        Raises:
            InsertFailed: If save operation fails
        """
        collection_name = self.model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as conn:
                collection = conn.client.collections.get(collection_name)
                
                data = instance.to_dict()
                data_without_id = {k: v for k, v in data.items() if k != 'id'}
                
                # Generate UUID if not exists
                object_id = getattr(instance, 'id', None)
                if not object_id:
                    object_id = str(uuid.uuid4())
                
                # Insert data
                result = collection.data.insert(
                    properties=data_without_id,
                    uuid=object_id
                )
                
                instance.id = str(result)
                logger.info(f"Object saved: {collection_name}/{str(result)}")
                return instance
                
        except Exception as e:
            logger.error(f"Failed to save object: {e}")
            raise InsertFailed(collection_name, str(e))
    
    def get_by_id(self, object_id: str) -> T:
        """
        Get object by ID directly (optimized).
        
        Uses Weaviate's fetch_object_by_id for fast direct lookup.
        Much faster than filter-based queries.
        
        Args:
            object_id: Object UUID
        
        Returns:
            Model instance
        
        Raises:
            DoesNotExist: If object not found
        
        Example:
            article = Article.objects.get_by_id("uuid-123")
        
        Reference:
            https://docs.weaviate.io/weaviate/manage-objects/read
        """
        collection_name = self.model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as conn:
                collection = conn.client.collections.get(collection_name)
                
                obj = collection.query.fetch_object_by_id(object_id)
                
                if not obj:
                    raise DoesNotExist(
                        self.model_class.__name__,
                        {"id": object_id}
                    )
                
                # Convert to instance
                data = obj.properties.copy()
                data['id'] = str(obj.uuid)
                
                instance = self.model_class()
                instance.id = data['id']
                
                for field_name in self.model_class._fields.keys():
                    if field_name in data:
                        setattr(instance, field_name, data[field_name])
                
                return instance
                
        except DoesNotExist:
            raise
        except Exception as e:
            logger.error(f"Failed to get object by ID: {e}")
            raise DoesNotExist(self.model_class.__name__, {"id": object_id})
    
    def get(self, **kwargs) -> T:
        """
        Get single object by criteria.
        
        Optimized: If only 'id' or 'uuid' is provided, uses get_by_id (fast path).
        Otherwise uses filter-based query (slower but supports any field).
        
        Args:
            **kwargs: Filter criteria
        
        Returns:
            Single model instance
        
        Raises:
            DoesNotExist: No matching object found
            MultipleObjectsReturned: Multiple objects match the criteria
            
        Example:
            # Fast: direct ID/UUID lookup
            article = Article.objects.get(id="uuid-123")
            article = Article.objects.get(uuid="uuid-123")
            
            # Slow: filter-based
            article = Article.objects.get(title="Hello World")
        
        Note:
            'id' and 'uuid' are special fields in Weaviate (not schema properties).
            They are used for direct object lookup, not filtering.
        """
        # Fast path: direct ID/UUID lookup
        if len(kwargs) == 1:
            if 'id' in kwargs:
                return self.get_by_id(kwargs['id'])
            elif 'uuid' in kwargs:
                return self.get_by_id(kwargs['uuid'])
        
        # Slow path: filter-based query
        # Note: Cannot use 'id' or 'uuid' in filter as they're not schema properties
        if 'id' in kwargs or 'uuid' in kwargs:
            raise ValueError(
                "Cannot filter by 'id' or 'uuid' with other fields. "
                "Use get(id='uuid') or get(uuid='uuid') for direct lookup, "
                "or filter by schema properties only."
            )
        
        results = self.filter(**kwargs).limit(2).all()
        
        if not results:
            raise DoesNotExist(self.model_class.__name__, kwargs)
        if len(results) > 1:
            raise MultipleObjectsReturned(
                self.model_class.__name__,
                len(results),
                kwargs
            )
        
        return results[0]
    
    def update(self, instance: T, **kwargs) -> T:
        """
        Update an object with new values.
        
        Args:
            instance: Instance to update
            **kwargs: Fields to update
            
        Returns:
            Updated instance
            
        Raises:
            Exception: If update operation fails
            
        Example:
            Article.objects.update(article, title="New Title", views=100)
        """
        collection_name = self.model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as conn:
                collection = conn.client.collections.get(collection_name)
                
                # Update instance attributes
                for key, value in kwargs.items():
                    if hasattr(instance, key):
                        setattr(instance, key, value)
                
                # Update in database
                if hasattr(instance, 'id') and instance.id:
                    collection.data.update(
                        uuid=instance.id,
                        properties=instance.to_dict()
                    )
                    logger.info(f"Object updated: {instance.id}")
                    return instance
                else:
                    raise ValueError("Object must have an ID to update")
                    
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to update object: {e}")
            raise Exception(f"Failed to update object in {collection_name}: {str(e)}")
    
    def delete(self, instance: T) -> bool:
        """
        Delete an object instance.
        
        Args:
            instance: Instance to delete
            
        Returns:
            True if deletion successful
            
        Raises:
            Exception: If deletion fails
        """
        collection_name = self.model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as conn:
                collection = conn.client.collections.get(collection_name)
                
                if not hasattr(instance, 'id') or not instance.id:
                    raise ValueError("Cannot delete object without ID")
                
                collection.data.delete_by_id(instance.id)
                logger.info(f"Object deleted: {instance.id}")
                return True
                    
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to delete object: {e}")
            raise Exception(f"Failed to delete object from {collection_name}: {str(e)}")
    
    # ===== Batch Operations =====
    
    def bulk_create(
        self,
        instances: List[T],
        batch_size: int = 100,
        on_error: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> BatchResult:
        """
        Bulk create with error handling using Weaviate Batch API.
        
        Uses Weaviate's batch.fixed_size() for efficient bulk insertion
        with complete error reporting.
        
        Args:
            instances: List of model instances
            batch_size: Objects per batch (default: 100, Weaviate recommended)
            on_error: Optional callback for each error: callback(error_dict)
        
        Returns:
            BatchResult with success/failure statistics
        
        Example:
            # Simple usage
            result = Article.objects.bulk_create(articles)
            print(f"Created {result.successful}/{result.total}")
            
            # With error handling
            def log_error(error):
                logger.error(f"Failed {error['uuid']}: {error['message']}")
            
            result = Article.objects.bulk_create(
                articles,
                batch_size=200,
                on_error=log_error
            )
            
            if result.has_errors:
                print(f"Errors: {result.errors}")
        
        Reference:
            https://docs.weaviate.io/weaviate/manage-objects/import
        """
        collection_name = self.model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as conn:
                collection = conn.client.collections.get(collection_name)
                
                from weaviate.collections.classes.data import DataObject
                
                # Prepare objects for insertion
                objects_to_insert = []
                uuid_to_instance = {}
                
                for instance in instances:
                    data = instance.to_dict()
                    data_without_id = {k: v for k, v in data.items() if k != 'id'}
                    
                    object_id = getattr(instance, 'id', None) or str(uuid.uuid4())
                    
                    objects_to_insert.append(DataObject(
                        properties=data_without_id,
                        uuid=object_id
                    ))
                    uuid_to_instance[object_id] = instance
                
                # Use batch API with fixed size
                errors = []
                
                with collection.batch.fixed_size(batch_size=batch_size) as batch:
                    for obj in objects_to_insert:
                        batch.add_object(
                            properties=obj.properties,
                            uuid=obj.uuid
                        )
                
                # Check for errors
                failed_objects = batch.failed_objects if hasattr(batch, 'failed_objects') else []
                failed_count = len(failed_objects)
                
                # Process errors
                for failed_obj in failed_objects:
                    error_dict = {
                        'uuid': str(getattr(failed_obj, 'uuid', None)),
                        'message': str(getattr(failed_obj, 'message', failed_obj))
                    }
                    errors.append(error_dict)
                    
                    if on_error:
                        on_error(error_dict)
                
                # Set IDs on successfully created instances
                # Note: failed instances won't have IDs set
                successful_count = len(instances) - failed_count
                
                logger.info(
                    f"Bulk create: {successful_count}/{len(instances)} successful "
                    f"({successful_count/len(instances)*100:.1f}%)"
                )
                
                return BatchResult(
                    total=len(instances),
                    successful=successful_count,
                    failed=failed_count,
                    errors=errors
                )
                
        except Exception as e:
            logger.error(f"Bulk create failed: {e}")
            raise InsertFailed(collection_name, str(e))
    
    def bulk_create_from_dicts(self, data_list: List[Dict[str, Any]], **kwargs) -> BatchResult:
        """
        Create objects from list of dictionaries.
        
        Convenience method that converts dicts to instances then calls bulk_create.
        
        Args:
            data_list: List of dictionaries with field data
            **kwargs: Additional arguments passed to bulk_create
            
        Returns:
            BatchResult
            
        Example:
            result = Article.objects.bulk_create_from_dicts([
                {"title": "Article 1", "content": "..."},
                {"title": "Article 2", "content": "..."},
            ], batch_size=200)
        """
        instances = [self.model_class(**data) for data in data_list]
        return self.bulk_create(instances, **kwargs)
    
    def bulk_import(
        self,
        data_list: List[Dict[str, Any]],
        batch_size: int = 100,
        use_dynamic: bool = False,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_error: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> BatchResult:
        """
        Bulk import from dictionaries with progress tracking.
        
        Recommended for large data imports (1000+ objects).
        Supports dynamic batching for automatic performance optimization.
        
        Args:
            data_list: List of data dictionaries
            batch_size: Batch size (default: 100, ignored if use_dynamic=True)
            use_dynamic: Use dynamic batching for auto-optimization (default: False)
            on_progress: Progress callback(current, total)
            on_error: Error callback(error_dict)
        
        Returns:
            BatchResult with statistics
        
        Example:
            # Large import with progress
            def show_progress(current, total):
                pct = (current / total) * 100
                print(f"\\rProgress: {current}/{total} ({pct:.1f}%)", end="")
            
            result = Article.objects.bulk_import(
                data_list,
                batch_size=200,
                use_dynamic=True,
                on_progress=show_progress
            )
            
            print(f"\\n✅ Imported {result.successful}/{result.total}")
        
        Reference:
            https://docs.weaviate.io/weaviate/manage-objects/import
        """
        collection_name = self.model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as conn:
                collection = conn.client.collections.get(collection_name)
                
                total = len(data_list)
                processed = 0
                errors = []
                
                # Choose batch mode
                batch_context = (
                    collection.batch.dynamic() if use_dynamic 
                    else collection.batch.fixed_size(batch_size=batch_size)
                )
                
                with batch_context as batch:
                    for data in data_list:
                        # Extract or generate UUID
                        object_id = data.pop('id', None) or str(uuid.uuid4())
                        
                        batch.add_object(
                            properties=data,
                            uuid=object_id
                        )
                        
                        processed += 1
                        
                        # Progress callback every 100 items
                        if on_progress and processed % 100 == 0:
                            on_progress(processed, total)
                
                # Final progress
                if on_progress:
                    on_progress(total, total)
                
                # Collect errors
                failed_objects = batch.failed_objects if hasattr(batch, 'failed_objects') else []
                failed_count = len(failed_objects)
                
                for failed_obj in failed_objects:
                    error_dict = {
                        'uuid': str(getattr(failed_obj, 'uuid', None)),
                        'message': str(getattr(failed_obj, 'message', failed_obj))
                    }
                    errors.append(error_dict)
                    
                    if on_error:
                        on_error(error_dict)
                
                logger.info(
                    f"Bulk import: {total - failed_count}/{total} successful"
                )
                
                return BatchResult(
                    total=total,
                    successful=total - failed_count,
                    failed=failed_count,
                    errors=errors
                )
                
        except Exception as e:
            logger.error(f"Bulk import failed: {e}")
            raise InsertFailed(collection_name, str(e))
    
    def bulk_update(
        self,
        updates: List[Dict[str, Any]],
        batch_size: int = 100,
        on_error: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> BatchResult:
        """
        Bulk update multiple objects.
        
        Each dict must contain 'id' and the fields to update.
        
        Args:
            updates: List of dicts with 'id' and update fields
            batch_size: Batch size (default: 100)
            on_error: Optional error callback
        
        Returns:
            BatchResult
        
        Example:
            updates = [
                {'id': 'uuid-1', 'views': 100, 'published': True},
                {'id': 'uuid-2', 'views': 200, 'published': False},
            ]
            result = Article.objects.bulk_update(updates, batch_size=200)
            print(f"Updated {result.successful}/{result.total}")
        
        Reference:
            https://docs.weaviate.io/weaviate/manage-objects/update
        """
        collection_name = self.model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as conn:
                collection = conn.client.collections.get(collection_name)
                
                errors = []
                successful = 0
                
                with collection.batch.fixed_size(batch_size=batch_size) as batch:
                    for update_data in updates:
                        if 'id' not in update_data:
                            error_dict = {
                                'uuid': None,
                                'message': "Missing 'id' field in update data"
                            }
                            errors.append(error_dict)
                            if on_error:
                                on_error(error_dict)
                            continue
                        
                        object_id = update_data.pop('id')
                        
                        try:
                            batch.update_object(
                                uuid=object_id,
                                properties=update_data
                            )
                            successful += 1
                        except Exception as e:
                            error_dict = {
                                'uuid': object_id,
                                'message': str(e)
                            }
                            errors.append(error_dict)
                            if on_error:
                                on_error(error_dict)
                
                failed = len(errors)
                
                logger.info(f"Bulk update: {successful}/{len(updates)} successful")
                
                return BatchResult(
                    total=len(updates),
                    successful=successful,
                    failed=failed,
                    errors=errors
                )
                
        except Exception as e:
            logger.error(f"Bulk update failed: {e}")
            raise Exception(f"Bulk update failed in {collection_name}: {str(e)}")
    
    def bulk_delete(
        self,
        object_ids: List[str],
        batch_size: int = 100,
        on_error: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> BatchResult:
        """
        Bulk delete objects by ID.
        
        Args:
            object_ids: List of object UUIDs
            batch_size: Batch size (default: 100)
            on_error: Optional error callback
        
        Returns:
            BatchResult
        
        Example:
            ids = ['uuid-1', 'uuid-2', 'uuid-3']
            result = Article.objects.bulk_delete(ids)
            print(f"Deleted {result.successful}/{result.total}")
        
        Reference:
            https://docs.weaviate.io/weaviate/manage-objects/delete
        """
        collection_name = self.model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as conn:
                collection = conn.client.collections.get(collection_name)
                
                errors = []
                successful = 0
                
                with collection.batch.fixed_size(batch_size=batch_size) as batch:
                    for object_id in object_ids:
                        try:
                            batch.delete_object(uuid=object_id)
                            successful += 1
                        except Exception as e:
                            error_dict = {
                                'uuid': object_id,
                                'message': str(e)
                            }
                            errors.append(error_dict)
                            if on_error:
                                on_error(error_dict)
                
                logger.info(f"Bulk delete: {successful}/{len(object_ids)} successful")
                
                return BatchResult(
                    total=len(object_ids),
                    successful=successful,
                    failed=len(errors),
                    errors=errors
                )
                
        except Exception as e:
            logger.error(f"Bulk delete failed: {e}")
            raise Exception(f"Bulk delete failed in {collection_name}: {str(e)}")
    
    def delete_where(self, **filters) -> int:
        """
        Delete multiple objects matching filters.
        
        Uses Weaviate's delete_many for efficient bulk deletion.
        
        Args:
            **filters: Filter conditions (Django-style field lookups)
        
        Returns:
            Number of deleted objects
        
        Example:
            # Delete all draft articles
            count = Article.objects.delete_where(status="draft")
            print(f"Deleted {count} drafts")
            
            # Delete with complex filters
            count = Article.objects.delete_where(
                status="old",
                views__lt=10,
                created_at__lt="2020-01-01"
            )
        
        Reference:
            https://docs.weaviate.io/weaviate/manage-objects/delete
        """
        collection_name = self.model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as conn:
                collection = conn.client.collections.get(collection_name)
                
                # Build filter from kwargs
                from ..search.filters import Q
                q = Q(**filters)
                weaviate_filter = q.to_weaviate_filter()
                
                if not weaviate_filter:
                    logger.warning("delete_where called without filters, skipping")
                    return 0
                
                # Delete matching objects
                result = collection.data.delete_many(where=weaviate_filter)
                
                deleted_count = result.deleted if hasattr(result, 'deleted') else 0
                logger.info(f"Deleted {deleted_count} objects from {collection_name}")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Delete where failed: {e}")
            raise Exception(f"Delete where failed in {collection_name}: {str(e)}")
    
    # ===== Collection Management Methods =====
    
    def create_collection(self, if_not_exists: bool = True) -> bool:
        """
        Create a Weaviate collection from model definition.
        
        Args:
            if_not_exists: If True, skip creation if collection exists (default: True)
            
        Returns:
            bool: True if creation successful
        """
        collection_name = self.model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as client:
                properties = self.model_class.get_properties()
                vectorizer_config = self.model_class.get_vectorizer_config()
                vector_index_config = self.model_class.get_vector_index_config()
                generative_config = self.model_class.get_generative_config()
                
                # Check if collection already exists
                if client.client.collections.exists(collection_name):
                    if not if_not_exists:
                        logger.info(f"Collection {collection_name} already exists")
                        return False
                    logger.info(f"Collection {collection_name} already exists, skipping")
                    return True
                
                # Create collection
                create_kwargs = {
                    "name": collection_name,
                    "properties": properties,
                }
                
                # Configure vector settings
                if vectorizer_config or vector_index_config:
                    vector_config = [{
                        "name": "default",
                        "vectorizer": vectorizer_config,
                        "vector_index_config": vector_index_config
                    }]
                    create_kwargs["vector_config"] = vector_config
                
                if generative_config:
                    create_kwargs["generative_config"] = generative_config
                
                collection = client.client.collections.create(**create_kwargs)
                logger.info(f"✅ Collection {collection_name} created")
                
                # Invalidate cache
                self._invalidate_cache(collection_name)
                return True
                
        except Exception as e:
            logger.error(f"Failed to create collection {collection_name}: {e}")
            return False
    
    def delete_collection(self, if_exists: bool = True) -> bool:
        """
        Delete a Weaviate collection.
        
        Args:
            if_exists: If True, don't raise error if collection doesn't exist
            
        Returns:
            bool: True if deletion successful
        """
        collection_name = self.model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    if not if_exists:
                        raise Exception(f"Collection {collection_name} does not exist")
                    logger.info(f"Collection {collection_name} does not exist, skipping")
                    return True
                
                client.client.collections.delete(collection_name)
                logger.info(f"✅ Collection {collection_name} deleted")
                
                # Invalidate cache
                self._invalidate_cache(collection_name)
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete collection {collection_name}: {e}")
            return False
    
    def collection_exists(self) -> bool:
        """
        Check if a collection exists in Weaviate.
        
        Returns:
            bool: True if collection exists, False otherwise
        """
        try:
            with self.client.managed_connection() as client:
                collection_name = self.model_class.get_collection_name()
                return client.client.collections.exists(collection_name)
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            return False
    
    def get_collection_info(self, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get collection configuration and metadata with caching.
        
        Args:
            use_cache: Whether to use cached info (default: True)
            
        Returns:
            Optional[Dict]: Collection information or None if not found
        """
        collection_name = self.model_class.get_collection_name()
        
        # Check cache
        if use_cache and self._is_cached(collection_name):
            logger.debug(f"Returning cached info for {collection_name}")
            return self._collection_cache[collection_name]
        
        # Fetch from Weaviate
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    return None
                
                collection = client.client.collections.get(collection_name)
                config = collection.config.get()
                
                # Parse vector configuration
                vectorizer = None
                distance_metric = "cosine"
                vector_index_type = "hnsw"
                
                if config.vector_config and 'default' in config.vector_config:
                    vector_config = config.vector_config['default']
                    if hasattr(vector_config, 'vectorizer') and vector_config.vectorizer:
                        vectorizer = vector_config.vectorizer.vectorizer.value if hasattr(vector_config.vectorizer, 'vectorizer') else str(vector_config.vectorizer)
                    
                    if hasattr(vector_config, 'vector_index_config') and vector_config.vector_index_config:
                        if hasattr(vector_config.vector_index_config, 'distance_metric'):
                            distance_metric = vector_config.vector_index_config.distance_metric.value
                
                info = {
                    "name": collection_name,
                    "properties": [prop.name for prop in config.properties],
                    "property_count": len(config.properties),
                    "vectorizer": vectorizer,
                    "vector_index_type": vector_index_type,
                    "distance_metric": distance_metric
                }
                
                # Cache it
                self._collection_cache[collection_name] = info
                self._cache_timestamps[collection_name] = time.time()
                logger.debug(f"Cached info for {collection_name}")
                
                return info
                
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return None
    
    def _is_cached(self, collection_name: str) -> bool:
        """
        Check if collection info is in cache and not expired.
        
        Args:
            collection_name: Collection name
        
        Returns:
            True if cached and fresh
        """
        if collection_name not in self._collection_cache:
            return False
        
        timestamp = self._cache_timestamps.get(collection_name, 0)
        age = time.time() - timestamp
        
        return age < 300  # 5 minutes TTL
    
    def _invalidate_cache(self, collection_name: str):
        """
        Invalidate cache for a collection.
        
        Args:
            collection_name: Collection name
        """
        if collection_name in self._collection_cache:
            del self._collection_cache[collection_name]
            logger.debug(f"Invalidated cache for {collection_name}")
        
        if collection_name in self._cache_timestamps:
            del self._cache_timestamps[collection_name]
    
    # ===== Query Methods (delegate to QueryBuilder) =====
    
    def filter(self, *args, **kwargs) -> QueryBuilder:
        """
        Filter objects by criteria.
        
        Returns a QueryBuilder for chaining additional operations.
        
        Args:
            *args: Q objects
            **kwargs: Field filters
            
        Returns:
            QueryBuilder instance
            
        Example:
            Article.objects.filter(category="tech", published=True)
        """
        return QueryBuilder(self.model_class, self.client).filter(*args, **kwargs)
    
    def exclude(self, *args, **kwargs) -> QueryBuilder:
        """
        Exclude objects matching criteria.
        
        Args:
            *args: Q objects
            **kwargs: Field filters
            
        Returns:
            QueryBuilder instance
        """
        return QueryBuilder(self.model_class, self.client).exclude(*args, **kwargs)
    
    def all(self) -> QueryBuilder:
        """
        Get all objects.
        
        Returns:
            QueryBuilder instance
        """
        return QueryBuilder(self.model_class, self.client)
    
    # ===== Search Methods (delegate to QueryBuilder) =====
    
    def search(self, query: str, **kwargs) -> QueryBuilder:
        """Perform hybrid search (default)."""
        return QueryBuilder(self.model_class, self.client).hybrid(query, **kwargs)
    
    def bm25(self, query: str, **kwargs) -> QueryBuilder:
        """BM25 keyword search."""
        return QueryBuilder(self.model_class, self.client).bm25(query, **kwargs)
    
    def near_text(self, text: str, **kwargs) -> QueryBuilder:
        """Semantic text search."""
        return QueryBuilder(self.model_class, self.client).near_text(text, **kwargs)
    
    def near_vector(self, vector: List[float], **kwargs) -> QueryBuilder:
        """Vector similarity search."""
        return QueryBuilder(self.model_class, self.client).near_vector(vector, **kwargs)
    
    def hybrid(self, query: str, alpha: float = 0.7, **kwargs) -> QueryBuilder:
        """Hybrid search (BM25 + semantic)."""
        return QueryBuilder(self.model_class, self.client).hybrid(query, alpha=alpha, **kwargs)
    
    def fuzzy(self, query: str, **kwargs) -> QueryBuilder:
        """Fuzzy search (typo-tolerant)."""
        return QueryBuilder(self.model_class, self.client).fuzzy(query, **kwargs)
    
    def search_by_type(self, search_type, query: Optional[str] = None, **kwargs) -> QueryBuilder:
        """
        Execute search by type (unified method).
        
        Simplifies search type selection by delegating to QueryBuilder.search_by_type().
        
        Args:
            search_type: SearchType enum value
            query: Search query
            **kwargs: Additional search parameters
        
        Returns:
            QueryBuilder instance
        
        Example:
            from db import SearchType
            
            # Use any search type
            results = Article.objects.search_by_type(
                SearchType.HYBRID,
                query="machine learning"
            ).all()
            
            # With filters
            results = Article.objects.filter(category="tech").search_by_type(
                SearchType.BM25,
                query="python"
            ).all()
        """
        return QueryBuilder(self.model_class, self.client).search_by_type(
            search_type,
            query=query,
            **kwargs
        )
    
    def aggregate(self):
        """
        Create an aggregation builder for this model.
        
        Returns:
            AggregationBuilder instance
            
        Example:
            stats = Article.objects.aggregate()\
                .group_by("category")\
                .count()\
                .avg("views")\
                .execute()
        """
        from ..search.aggregation import AggregationBuilder
        return AggregationBuilder(self.model_class, self.client)
