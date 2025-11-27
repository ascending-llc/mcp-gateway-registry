"""
QuerySet for chainable query building and execution.

Provides Django-like ORM interface for building and executing
Weaviate queries with support for filtering, pagination, and search.
"""

import logging
from typing import List, Optional, Type, TypeVar
from weaviate.classes.query import Filter, MetadataQuery

from ..core.client import WeaviateClient

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='Model')


class QuerySet:
    """Chainable query builder for Weaviate collections"""
    
    def __init__(self, model_class: Type[T], client: WeaviateClient):
        self.model_class = model_class
        self.client = client
        self._filters: List[Filter] = []
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._order_by: Optional[str] = None
        self._include_vector: bool = False
        self._include_metadata: bool = True
    
    def filter(self, **kwargs) -> 'QuerySet':
        """
        Add equality filter conditions.
        
        Args:
            **kwargs: Field name and value mappings
            
        Returns:
            QuerySet: Current query set instance (chainable)
        """
        for field, value in kwargs.items():
            # Check if field exists in model's _fields dictionary
            if field in self.model_class._fields:
                filter_condition = Filter.by_property(field).equal(value)
                self._filters.append(filter_condition)
                logger.debug(f"Added filter: {field}={value}")
            else:
                logger.warning(f"Field '{field}' not found in {self.model_class.__name__}._fields")
        return self
    
    def exclude(self, **kwargs) -> 'QuerySet':
        """
        Add exclusion filter conditions.
        
        Args:
            **kwargs: Field name and value mappings
            
        Returns:
            QuerySet: Current query set instance (chainable)
        """
        for field, value in kwargs.items():
            # Check if field exists in model's _fields dictionary
            if field in self.model_class._fields:
                filter_condition = Filter.by_property(field).not_equal(value)
                self._filters.append(filter_condition)
        return self
    
    def limit(self, limit: int) -> 'QuerySet':
        """
        Set maximum number of results to return.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            QuerySet: Current query set instance (chainable)
        """
        self._limit = limit
        return self
    
    def offset(self, offset: int) -> 'QuerySet':
        """
        Set offset for pagination.
        
        Args:
            offset: Number of results to skip
            
        Returns:
            QuerySet: Current query set instance (chainable)
        """
        self._offset = offset
        return self
    
    def order_by(self, field: str) -> 'QuerySet':
        """
        Set field for ordering results.
        
        Args:
            field: Field name to order by
            
        Returns:
            QuerySet: Current query set instance (chainable)
        """
        self._order_by = field
        return self
    
    def include_vector(self, include: bool = True) -> 'QuerySet':
        """
        Set whether to include vector data in results.
        
        Args:
            include: Whether to include vectors
            
        Returns:
            QuerySet: Current query set instance (chainable)
        """
        self._include_vector = include
        return self
    
    def include_metadata(self, include: bool = True) -> 'QuerySet':
        """
        Set whether to include metadata in results.
        
        Args:
            include: Whether to include metadata
            
        Returns:
            QuerySet: Current query set instance (chainable)
        """
        self._include_metadata = include
        return self
    
    def _build_query(self):
        """Build query parameters from current state"""
        query_params = {}
        
        if self._filters:
            logger.debug(f"Building query with {len(self._filters)} filters")
            if len(self._filters) == 1:
                query_params['filters'] = self._filters[0]
            else:
                query_params['filters'] = Filter.and_(*self._filters)
        else:
            logger.debug("No filters in query")
        
        if self._limit is not None:
            query_params['limit'] = self._limit
        
        if self._offset is not None:
            query_params['offset'] = self._offset
        
        # Metadata query - handle API compatibility
        metadata_query = MetadataQuery()
        if self._include_vector:
            if hasattr(metadata_query, 'include_vector'):
                metadata_query = metadata_query.include_vector()
            elif hasattr(metadata_query, 'vector'):
                metadata_query = metadata_query.vector()
        if self._include_metadata:
            if hasattr(metadata_query, 'include_metadata'):
                metadata_query = metadata_query.include_metadata()
            elif hasattr(metadata_query, 'metadata'):
                metadata_query = metadata_query.metadata()

        query_params['return_metadata'] = metadata_query
        
        return query_params
    
    def all(self) -> List[T]:
        """
        Execute query and return all matching objects.
        
        Returns:
            List[T]: List of model instances
        """
        return self._execute_query()
    
    def first(self) -> Optional[T]:
        """
        Execute query and return first matching object.
        
        Returns:
            Optional[T]: First matching object or None
        """
        results = self.limit(1)._execute_query()
        return results[0] if results else None
    
    def count(self) -> int:
        """
        Get count of matching objects.
        
        Returns:
            int: Number of matching objects
        """
        try:
            with self.client.managed_connection() as client:
                collection_name = self.model_class.get_collection_name()
                collection = client.client.collections.get(collection_name)
                
                query_params = self._build_query()
                # Remove parameters not suitable for aggregation queries
                if 'return_metadata' in query_params:
                    del query_params['return_metadata']
                if 'limit' in query_params:
                    del query_params['limit']
                if 'offset' in query_params:
                    del query_params['offset']
                
                result = collection.aggregate.over_all(**query_params)
                return result.total_count
                
        except Exception as e:
            logger.error(f"Failed to count objects: {e}")
            return 0
    
    def bm25(self, query: str, properties: Optional[List[str]] = None) -> 'QuerySet':
        """
        Add BM25 keyword search.
        
        Args:
            query: Search query string
            properties: Properties to search in (None = all text properties)
            
        Returns:
            QuerySet: Current query set instance (chainable)
        """
        self._bm25_query = query
        self._bm25_properties = properties
        return self
    
    def vector_search(self, query: str, limit: Optional[int] = None) -> 'QuerySet':
        """
        Add vector semantic search.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            QuerySet: Current query set instance (chainable)
        """
        self._vector_query = query
        if limit is not None:
            self._limit = limit
        return self
    
    def hybrid_search(self, query: str, alpha: float = 0.5, limit: Optional[int] = None) -> 'QuerySet':
        """
        Add hybrid search (BM25 + vector).
        
        Args:
            query: Search query string
            alpha: Weight between BM25 (0.0) and vector (1.0)
            limit: Maximum number of results
            
        Returns:
            QuerySet: Current query set instance (chainable)
        """
        self._hybrid_query = query
        self._hybrid_alpha = alpha
        if limit is not None:
            self._limit = limit
        return self
    
    def _execute_query(self) -> List[T]:
        """Execute the built query and return model instances"""
        try:
            with self.client.managed_connection() as client:
                collection_name = self.model_class.get_collection_name()
                collection = client.client.collections.get(collection_name)
                
                query_params = self._build_query()
                logger.debug(f"Executing query for {collection_name} with params: {list(query_params.keys())}")
                
                # Execute different query types
                if hasattr(self, '_bm25_query'):
                    logger.debug("Using BM25 query")
                    results = collection.query.bm25(
                        query=self._bm25_query,
                        query_properties=self._bm25_properties,
                        **query_params
                    )
                elif hasattr(self, '_vector_query'):
                    logger.debug("Using vector query")
                    results = collection.query.near_text(
                        query=self._vector_query,
                        **query_params
                    )
                elif hasattr(self, '_hybrid_query'):
                    logger.debug("Using hybrid query")
                    results = collection.query.hybrid(
                        query=self._hybrid_query,
                        alpha=self._hybrid_alpha,
                        **query_params
                    )
                else:
                    logger.debug(f"Using fetch_objects with filters: {query_params.get('filters')}")
                    results = collection.query.fetch_objects(**query_params)
                
                logger.debug(f"Query returned {len(results.objects)} objects")
                
                # Convert to model instances
                instances = []
                for obj in results.objects:
                    instance_data = obj.properties
                    instance_data['id'] = obj.uuid
                    
                    # Create model instance and set properties manually
                    instance = self.model_class()
                    instance.id = instance_data.get('id')
                    
                    # Set all field properties
                    for field_name in self.model_class._fields.keys():
                        if field_name in instance_data:
                            setattr(instance, field_name, instance_data[field_name])
                    
                    instances.append(instance)
                
                return instances
                
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            return []

