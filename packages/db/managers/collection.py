"""
Collection Manager for Weaviate Collections

Enhanced with caching, batch operations, and dynamic property support
following Weaviate's official best practices.

Reference: https://docs.weaviate.io/weaviate/manage-collections
"""

import logging
import time
from typing import Any, Dict, List, Optional, Type, TypeVar
from weaviate.classes.config import Property, DataType

from ..core.client import WeaviateClient
from ..core.exceptions import CollectionNotFound, CollectionAlreadyExists, CollectionCreationFailed

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='Model')


class CollectionManager:
    """
    Manages Weaviate collection lifecycle and configuration with caching.
    
    Features:
    - Collection info caching (5-minute TTL)
    - Batch collection operations
    - Better error handling
    """
    
    def __init__(self, client: WeaviateClient, cache_ttl: int = 300):
        """
        Initialize collection manager.
        
        Args:
            client: Weaviate client instance
            cache_ttl: Cache time-to-live in seconds (default: 300 = 5 minutes)
        """
        self.client = client
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = cache_ttl
    
    def create_collection(self, model_class: Type[T], if_not_exists: bool = True) -> bool:
        """
        Create a Weaviate collection from model definition.
        
        Args:
            model_class: Model class with schema definition
            if_not_exists: If True, skip creation if collection exists (default: True)
            
        Returns:
            bool: True if creation successful
            
        Raises:
            CollectionAlreadyExists: If collection exists and if_not_exists=False
            CollectionCreationFailed: If creation fails
        """
        collection_name = model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as client:
                properties = model_class.get_properties()
                vectorizer_config = model_class.get_vectorizer_config()
                vector_index_config = model_class.get_vector_index_config()
                generative_config = model_class.get_generative_config()
                
                # Check if collection already exists
                if client.client.collections.exists(collection_name):
                    if not if_not_exists:
                        raise CollectionAlreadyExists(collection_name)
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
                
        except CollectionAlreadyExists:
            raise
        except Exception as e:
            logger.error(f"Failed to create collection {collection_name}: {e}")
            raise CollectionCreationFailed(collection_name, str(e))
    
    def delete_collection(self, model_class: Type[T], if_exists: bool = True) -> bool:
        """
        Delete a Weaviate collection.
        
        Args:
            model_class: Model class
            if_exists: If True, don't raise error if collection doesn't exist
            
        Returns:
            bool: True if deletion successful
            
        Raises:
            CollectionNotFound: If collection doesn't exist and if_exists=False
        """
        collection_name = model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    if not if_exists:
                        raise CollectionNotFound(collection_name)
                    logger.info(f"Collection {collection_name} does not exist, skipping")
                    return True
                
                client.client.collections.delete(collection_name)
                logger.info(f"✅ Collection {collection_name} deleted")
                
                # Invalidate cache
                self._invalidate_cache(collection_name)
                return True
                
        except CollectionNotFound:
            raise
        except Exception as e:
            logger.error(f"Failed to delete collection {collection_name}: {e}")
            return False
    
    def collection_exists(self, model_class: Type[T]) -> bool:
        """
        Check if a collection exists in Weaviate.
        
        Args:
            model_class: Model class
            
        Returns:
            bool: True if collection exists, False otherwise
        """
        try:
            with self.client.managed_connection() as client:
                collection_name = model_class.get_collection_name()
                return client.client.collections.exists(collection_name)
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            return False
    
    def get_collection_info(
        self, 
        model_class: Type[T],
        use_cache: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get collection configuration and metadata with caching.
        
        Args:
            model_class: Model class
            use_cache: Whether to use cached info (default: True)
            
        Returns:
            Optional[Dict]: Collection information or None if not found
        """
        collection_name = model_class.get_collection_name()
        
        # Check cache
        if use_cache and self._is_cached(collection_name):
            logger.debug(f"Returning cached info for {collection_name}")
            return self._cache[collection_name]
        
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
                self._cache[collection_name] = info
                self._cache_timestamps[collection_name] = time.time()
                logger.debug(f"Cached info for {collection_name}")
                
                return info
                
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return None
    
    def batch_create_collections(self, model_classes: List[Type[T]]) -> Dict[str, bool]:
        """
        Create multiple collections in batch.
        
        Args:
            model_classes: List of model classes to create collections for
        
        Returns:
            Dict mapping collection names to success status
        """
        results = {}
        
        for model_class in model_classes:
            collection_name = model_class.get_collection_name()
            try:
                success = self.create_collection(model_class, if_not_exists=True)
                results[collection_name] = success
            except Exception as e:
                logger.error(f"Failed to create {collection_name}: {e}")
                results[collection_name] = False
        
        return results
    
    def _is_cached(self, collection_name: str) -> bool:
        """
        Check if collection info is in cache and not expired.
        
        Args:
            collection_name: Collection name
        
        Returns:
            True if cached and fresh
        """
        if collection_name not in self._cache:
            return False
        
        timestamp = self._cache_timestamps.get(collection_name, 0)
        age = time.time() - timestamp
        
        return age < self._cache_ttl
    
    def _invalidate_cache(self, collection_name: str):
        """
        Invalidate cache for a collection.
        
        Args:
            collection_name: Collection name
        """
        if collection_name in self._cache:
            del self._cache[collection_name]
            logger.debug(f"Invalidated cache for {collection_name}")
        
        if collection_name in self._cache_timestamps:
            del self._cache_timestamps[collection_name]
    
    def clear_cache(self):
        """Clear all cached collection info."""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("Cleared collection info cache")
    
    # ===== Additional Collection Operations =====
    
    def add_property(
        self,
        model_class: Type[T],
        property_name: str,
        data_type: DataType,
        description: Optional[str] = None,
        index_filterable: bool = True,
        index_searchable: Optional[bool] = None,
        **options
    ) -> bool:
        """
        Add a new property to an existing collection.
        
        Important: Pre-existing objects won't be indexed for this property.
        Weaviate recommends adding all properties before importing data.
        
        Args:
            model_class: Model class
            property_name: Name of the new property
            data_type: Weaviate DataType (e.g., DataType.TEXT, DataType.INT)
            description: Property description
            index_filterable: Whether property should be filterable
            index_searchable: Whether property should be searchable
            **options: Additional Weaviate property options
        
        Returns:
            True if successful
        
        Raises:
            CollectionNotFound: If collection doesn't exist
        
        Example:
            from weaviate.classes.config import DataType
            from db.managers import CollectionManager
            
            manager = CollectionManager(client)
            manager.add_property(
                Article,
                "featured",
                DataType.BOOL,
                description="Whether article is featured"
            )
        
        Warning:
            Objects created before adding the property won't be indexed
            for the new property. Plan your schema before data import.
        
        Reference:
            https://docs.weaviate.io/weaviate/manage-collections/collection-operations#add-a-property
        """
        collection_name = model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as conn:
                # Check collection exists
                if not conn.client.collections.exists(collection_name):
                    raise CollectionNotFound(collection_name)
                
                collection = conn.client.collections.get(collection_name)
                
                # Create property configuration
                # Note: index_searchable only valid for TEXT/TEXT_ARRAY types
                property_kwargs = {
                    'name': property_name,
                    'data_type': data_type,
                    'description': description,
                    'index_filterable': index_filterable,
                    **options
                }
                
                # Only set index_searchable for text types
                if index_searchable is not None:
                    if data_type in (DataType.TEXT, DataType.TEXT_ARRAY):
                        property_kwargs['index_searchable'] = index_searchable
                    # For other types, omit index_searchable
                
                new_property = Property(**property_kwargs)
                
                # Add property to collection
                collection.config.add_property(new_property)
                
                logger.info(
                    f"✅ Added property '{property_name}' ({data_type.value}) "
                    f"to collection {collection_name}"
                )
                
                # Invalidate cache since schema changed
                self._invalidate_cache(collection_name)
                
                return True
                
        except CollectionNotFound:
            raise
        except Exception as e:
            logger.error(f"Failed to add property '{property_name}': {e}")
            return False
    
    def list_all_collections(self) -> List[str]:
        """
        List all collections in Weaviate instance.
        
        Returns:
            List of collection names
        
        Example:
            from db.managers import CollectionManager
            
            manager = CollectionManager(client)
            collections = manager.list_all_collections()
            print(f"Total collections: {len(collections)}")
            for name in collections:
                print(f"  - {name}")
        
        Reference:
            https://docs.weaviate.io/weaviate/manage-collections/collection-operations
        """
        try:
            with self.client.managed_connection() as conn:
                collections = conn.client.collections.list_all()
                # Handle both dict and object response
                if isinstance(collections, dict):
                    names = list(collections.keys())
                else:
                    names = [c.name if hasattr(c, 'name') else str(c) for c in collections]
                logger.debug(f"Found {len(names)} collections")
                return names
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
    
    def get_collection_stats(self, model_class: Type[T]) -> Optional[Dict[str, Any]]:
        """
        Get collection statistics including object count.
        
        Args:
            model_class: Model class
        
        Returns:
            Dict with statistics or None
        
        Example:
            stats = manager.get_collection_stats(Article)
            print(f"Objects: {stats['object_count']}")
        """
        collection_name = model_class.get_collection_name()
        
        try:
            with self.client.managed_connection() as conn:
                if not conn.client.collections.exists(collection_name):
                    return None
                
                collection = conn.client.collections.get(collection_name)
                
                # Get object count
                agg_result = collection.aggregate.over_all(total_count=True)
                object_count = agg_result.total_count if hasattr(agg_result, 'total_count') else 0
                
                # Get collection info
                info = self.get_collection_info(model_class, use_cache=True)
                
                if info:
                    info['object_count'] = object_count
                
                return info
                
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return None

