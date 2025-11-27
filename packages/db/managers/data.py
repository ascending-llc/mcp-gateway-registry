"""
Direct data operations on collections without model abstraction.

Provides CRUD operations for collections when no model is defined.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional
from weaviate.classes.query import Filter

from ..core.client import WeaviateClient

logger = logging.getLogger(__name__)


class DirectDataManager:
    """Direct data operations without model abstraction"""
    
    def __init__(self, client: WeaviateClient):
        self.client = client
    
    def _ensure_collection_exists(self, collection_name: str):
        """
        Ensure collection exists, raise exception if not.
        
        Args:
            collection_name: Name of the collection
            
        Raises:
            ValueError: If collection does not exist
        """
        with self.client.managed_connection() as client:
            if not client.client.collections.exists(collection_name):
                raise ValueError(f"Collection '{collection_name}' does not exist")
    
    # ===== Create Operations =====
    
    def insert(
        self, 
        collection_name: str, 
        data: Dict[str, Any], 
        object_uuid: Optional[str] = None
    ) -> str:
        """
        Insert data directly into collection.
        
        Args:
            collection_name: Collection name
            data: Data dictionary
            object_uuid: Optional custom UUID
            
        Returns:
            str: UUID of inserted data
            
        Raises:
            ValueError: If collection does not exist
        """
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    raise ValueError(f"Collection {collection_name} does not exist")
                
                collection = client.client.collections.get(collection_name)
                
                # Generate UUID if not provided
                if not object_uuid:
                    object_uuid = str(uuid.uuid4())
                
                # Insert data
                result = collection.data.insert(
                    properties=data,
                    uuid=object_uuid
                )
                logger.info(f"Data inserted successfully into {collection_name} with ID: {str(result)}")
                return str(result)
                
        except Exception as e:
            logger.error(f"Failed to insert data into {collection_name}: {e}")
            raise
    
    def bulk_insert(
        self, 
        collection_name: str, 
        data_list: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Bulk insert data into collection.
        
        Args:
            collection_name: Collection name
            data_list: List of data dictionaries
            
        Returns:
            List[str]: List of inserted UUIDs
            
        Raises:
            ValueError: If collection does not exist
        """
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    raise ValueError(f"Collection {collection_name} does not exist")
                
                collection = client.client.collections.get(collection_name)
                
                objects_to_insert = []
                for data in data_list:
                    object_uuid = str(uuid.uuid4())
                    objects_to_insert.append({
                        'properties': data,
                        'uuid': object_uuid
                    })
                
                # Bulk insert
                results = collection.data.insert_many(objects_to_insert)
                
                # Get inserted UUIDs
                uuids = []
                if hasattr(results, 'uuids') and results.uuids:
                    uuids = [str(uuid_obj) for uuid_obj in results.uuids]
                
                logger.info(f"Bulk inserted {len(data_list)} objects into {collection_name}")
                return uuids
                
        except Exception as e:
            logger.error(f"Failed to bulk insert data into {collection_name}: {e}")
            raise
    
    # ===== Read Operations =====
    
    def get(
        self, 
        collection_name: str, 
        object_uuid: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get single object by UUID.
        
        Args:
            collection_name: Collection name
            object_uuid: UUID of the object
            
        Returns:
            Optional[Dict[str, Any]]: Object data or None if not found
        """
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    raise ValueError(f"Collection {collection_name} does not exist")
                
                collection = client.client.collections.get(collection_name)
                obj = collection.query.fetch_object_by_id(object_uuid)
                
                if obj:
                    data = obj.properties.copy()
                    data['id'] = obj.uuid
                    return data
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to get object from {collection_name}: {e}")
            return None
    
    def query(
        self, 
        collection_name: str, 
        filters: Optional[Dict[str, Any]] = None, 
        limit: Optional[int] = None, 
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Query collection data directly.
        
        Args:
            collection_name: Collection name
            filters: Filter condition dictionary
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List[Dict]: List of data dictionaries
        """
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    raise ValueError(f"Collection {collection_name} does not exist")
                
                collection = client.client.collections.get(collection_name)
                
                # Build filter conditions
                filter_conditions = []
                if filters:
                    for field, value in filters.items():
                        filter_condition = Filter.by_property(field).equal(value)
                        filter_conditions.append(filter_condition)
                
                # Build query parameters
                query_params = {}
                if filter_conditions:
                    if len(filter_conditions) == 1:
                        query_params['filters'] = filter_conditions[0]
                    else:
                        query_params['filters'] = Filter.and_(*filter_conditions)
                
                if limit is not None:
                    query_params['limit'] = limit
                
                if offset is not None:
                    query_params['offset'] = offset
                
                # Execute query
                results = collection.query.fetch_objects(**query_params)
                
                # Convert to dictionary list
                data_list = []
                for obj in results.objects:
                    data = obj.properties.copy()
                    data['id'] = obj.uuid
                    data_list.append(data)
                
                return data_list
                
        except Exception as e:
            logger.error(f"Failed to query data from {collection_name}: {e}")
            raise
    
    def all(
        self, 
        collection_name: str, 
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all objects from collection.
        
        Args:
            collection_name: Collection name
            limit: Maximum number of results
            
        Returns:
            List[Dict[str, Any]]: List of all objects
        """
        return self.query(collection_name, filters=None, limit=limit)
    
    # ===== Update Operations =====
    
    def update(
        self, 
        collection_name: str, 
        object_uuid: str, 
        data: Dict[str, Any]
    ) -> bool:
        """
        Update data by UUID.
        
        Args:
            collection_name: Collection name
            object_uuid: UUID of data to update
            data: Updated data dictionary
            
        Returns:
            bool: True if update successful
        """
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    raise ValueError(f"Collection {collection_name} does not exist")
                
                collection = client.client.collections.get(collection_name)
                collection.data.update(uuid=object_uuid, properties=data)
                
                logger.info(f"Data updated in {collection_name} with ID: {object_uuid}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update data in {collection_name}: {e}")
            return False
    
    def replace(
        self, 
        collection_name: str, 
        object_uuid: str, 
        data: Dict[str, Any]
    ) -> bool:
        """
        Replace entire object by UUID.
        
        Args:
            collection_name: Collection name
            object_uuid: UUID of data to replace
            data: New data dictionary
            
        Returns:
            bool: True if replace successful
        """
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    raise ValueError(f"Collection {collection_name} does not exist")
                
                collection = client.client.collections.get(collection_name)
                collection.data.replace(uuid=object_uuid, properties=data)
                
                logger.info(f"Data replaced in {collection_name} with ID: {object_uuid}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to replace data in {collection_name}: {e}")
            return False
    
    # ===== Delete Operations =====
    
    def delete(
        self, 
        collection_name: str, 
        object_uuid: str
    ) -> bool:
        """
        Delete data by UUID.
        
        Args:
            collection_name: Collection name
            object_uuid: UUID of data to delete
            
        Returns:
            bool: True if deletion successful
        """
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    raise ValueError(f"Collection {collection_name} does not exist")
                
                collection = client.client.collections.get(collection_name)
                collection.data.delete_by_id(object_uuid)
                
                logger.info(f"Data deleted from {collection_name} with ID: {object_uuid}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete data from {collection_name}: {e}")
            return False
    
    def delete_many(
        self, 
        collection_name: str, 
        filters: Dict[str, Any]
    ) -> int:
        """
        Delete multiple objects matching filters.
        
        Args:
            collection_name: Collection name
            filters: Filter conditions
            
        Returns:
            int: Number of deleted objects
        """
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    raise ValueError(f"Collection {collection_name} does not exist")
                
                collection = client.client.collections.get(collection_name)
                
                # Build filter conditions
                filter_conditions = []
                for field, value in filters.items():
                    filter_condition = Filter.by_property(field).equal(value)
                    filter_conditions.append(filter_condition)
                
                if filter_conditions:
                    if len(filter_conditions) == 1:
                        filter_obj = filter_conditions[0]
                    else:
                        filter_obj = Filter.and_(*filter_conditions)
                    
                    result = collection.data.delete_many(where=filter_obj)
                    count = result.deleted if hasattr(result, 'deleted') else 0
                    
                    logger.info(f"Deleted {count} objects from {collection_name}")
                    return count
                
                return 0
                
        except Exception as e:
            logger.error(f"Failed to delete many from {collection_name}: {e}")
            return 0
    
    # ===== Collection Utilities =====
    
    def exists(self, collection_name: str) -> bool:
        """
        Check if collection exists.
        
        Args:
            collection_name: Collection name
            
        Returns:
            bool: True if collection exists
        """
        try:
            with self.client.managed_connection() as client:
                return client.client.collections.exists(collection_name)
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            return False
    
    def get_collection_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """
        Get collection information.
        
        Args:
            collection_name: Collection name
            
        Returns:
            Optional[Dict[str, Any]]: Collection information or None
        """
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    return None
                
                collection = client.client.collections.get(collection_name)
                config = collection.config.get()
                
                # Handle new vector_config structure
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
                
                return {
                    "name": collection_name,
                    "properties": [prop.name for prop in config.properties],
                    "vectorizer": vectorizer,
                    "vector_index_type": vector_index_type,
                    "distance_metric": distance_metric
                }
                
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return None
    
    def count(self, collection_name: str) -> int:
        """
        Count total objects in collection.
        
        Args:
            collection_name: Collection name
            
        Returns:
            int: Number of objects
        """
        try:
            with self.client.managed_connection() as client:
                if not client.client.collections.exists(collection_name):
                    return 0
                
                collection = client.client.collections.get(collection_name)
                result = collection.aggregate.over_all(total_count=True)
                
                return result.total_count if hasattr(result, 'total_count') else 0
                
        except Exception as e:
            logger.error(f"Failed to count objects in {collection_name}: {e}")
            return 0

