"""Query builder for Weaviate search."""

import logging
from typing import Any, Dict, List, Optional, TypeVar

from ..core.client import WeaviateClient
from ..core.enums import SearchType
from .filters import Q
from .strategies import execute_search

logger = logging.getLogger(__name__)
T = TypeVar('T')


class QueryBuilder:
    """
    Fluent interface for building search queries.
    
    Example:
        results = (QueryBuilder(Article, client)
            .filter(category="tech")
            .search("AI", SearchType.HYBRID)
            .limit(10)
            .execute())
    """
    
    def __init__(self, target: Any, client: WeaviateClient):
        self.client = client
        self._executed = False
        self._cached_results: Optional[List] = None
        
        # Set collection name from target
        if isinstance(target, str):
            self.collection_name = target
        elif hasattr(target, 'get_collection_name'):
            self.collection_name = target.get_collection_name()
            self._model_class = target
        else:
            raise ValueError(f"Invalid target type: {type(target)}")
        
        # Query parameters
        self.search_type: Optional[SearchType] = None
        self.search_params: Dict[str, Any] = {}
        self.filters: Optional[Q] = None
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._order_by: Optional[str] = None
        self._order_desc: bool = False
        self._return_properties: Optional[List[str]] = None
    
    def filter(self, *args, **kwargs) -> 'QueryBuilder':
        """Add filter conditions."""
        self._ensure_not_executed()
        
        if args or kwargs:
            new_filter = Q(*args, **kwargs)
            
            if self.filters is None:
                self.filters = new_filter
            else:
                self.filters = self.filters & new_filter
        
        return self
    
    def exclude(self, *args, **kwargs) -> 'QueryBuilder':
        """Add exclusion filters (NOT)."""
        self._ensure_not_executed()
        
        if args or kwargs:
            exclude_filter = ~Q(*args, **kwargs)
            
            if self.filters is None:
                self.filters = exclude_filter
            else:
                self.filters = self.filters & exclude_filter
        
        return self
    
    def search(self, query: str, search_type: Optional[SearchType] = None, **kwargs) -> 'QueryBuilder':
        """Set search query and type."""
        self._ensure_not_executed()
        
        self.search_type = search_type or SearchType.HYBRID
        self.search_params = {'query': query, **kwargs}
        
        return self
    
    def bm25(self, query: str, **kwargs) -> 'QueryBuilder':
        """BM25 keyword search."""
        return self.search(query, SearchType.BM25, **kwargs)
    
    def near_text(self, text: str, **kwargs) -> 'QueryBuilder':
        """Semantic text search."""
        return self.search(text, SearchType.NEAR_TEXT, **kwargs)
    
    def near_vector(self, vector: List[float], **kwargs) -> 'QueryBuilder':
        """Vector similarity search."""
        self._ensure_not_executed()
        self.search_type = SearchType.NEAR_VECTOR
        self.search_params = {'vector': vector, **kwargs}
        return self
    
    def hybrid(self, query: str, alpha: float = 0.7, **kwargs) -> 'QueryBuilder':
        """Hybrid search (BM25 + semantic)."""
        return self.search(query, SearchType.HYBRID, alpha=alpha, **kwargs)
    
    
    def search_by_type(self, search_type: SearchType, query: Optional[str] = None, **kwargs) -> 'QueryBuilder':
        """Execute search by type."""
        self._ensure_not_executed()
        
        if search_type == SearchType.BM25:
            return self.bm25(query, **kwargs)
        elif search_type == SearchType.NEAR_TEXT:
            return self.near_text(query, **kwargs)
        elif search_type == SearchType.NEAR_VECTOR:
            return self.near_vector(kwargs.get('vector', []), **kwargs)
        elif search_type == SearchType.HYBRID:
            return self.hybrid(query, **kwargs)
        elif search_type == SearchType.FETCH_OBJECTS:
            self.search_type = SearchType.FETCH_OBJECTS
            self.search_params = kwargs
            return self
        else:
            logger.warning(f"Unknown search type {search_type}, defaulting to HYBRID")
            return self.hybrid(query, **kwargs)
    
    def limit(self, n: int) -> 'QueryBuilder':
        """Set result limit."""
        self._ensure_not_executed()
        self._limit = n
        return self
    
    def offset(self, n: int) -> 'QueryBuilder':
        """Set pagination offset."""
        self._ensure_not_executed()
        self._offset = n
        return self
    
    def order_by(self, field: str, desc: bool = False) -> 'QueryBuilder':
        """Set ordering field."""
        self._ensure_not_executed()
        self._order_by = field
        self._order_desc = desc
        return self
    
    def only(self, *fields: str) -> 'QueryBuilder':
        """Select only specific fields to return."""
        self._ensure_not_executed()
        self._return_properties = list(fields)
        return self
    
    def execute(self) -> List[Any]:
        """Execute the query and return results."""
        if not self._executed:
            results = execute_search(self, self.client)
            self._cached_results = results
            self._executed = True
            
            if hasattr(self, '_model_class') and results:
                self._cached_results = self._to_instances(results)
        
        return self._cached_results or []
    
    def all(self) -> List[Any]:
        """Alias for execute()."""
        return self.execute()
    
    def first(self) -> Optional[Any]:
        """Get first result or None."""
        results = self.limit(1).execute()
        return results[0] if results else None
    
    def count(self) -> int:
        """Count results."""
        return len(self.execute())
    
    def exists(self) -> bool:
        """Check if any results exist."""
        return self.count() > 0
    
    def _ensure_not_executed(self):
        """Raise error if trying to modify after execution."""
        if self._executed:
            raise RuntimeError("Cannot modify query after execution.")
    
    def _to_instances(self, data_list: List[Dict]) -> List[T]:
        """Convert dictionaries to model instances."""
        if not hasattr(self, '_model_class'):
            return data_list
        
        instances = []
        for data in data_list:
            instance = self._model_class()
            
            if 'id' in data:
                instance.id = data['id']
            
            if hasattr(self._model_class, '_fields'):
                for field_name in self._model_class._fields.keys():
                    if field_name in data:
                        setattr(instance, field_name, data[field_name])
            
            for key, value in data.items():
                if key.startswith('_') and not hasattr(instance, key):
                    setattr(instance, key, value)
            
            instances.append(instance)
        
        return instances
    
    def __iter__(self):
        """Make QueryBuilder iterable."""
        return iter(self.execute())
    
    def __len__(self):
        """Get count of results."""
        return self.count()
    
    # Note: We don't define limit, offset, etc. as properties here
    # because they would conflict with the limit(), offset() methods.
    # Strategies.py should access _limit, _offset, etc. directly.
    
    def has_filters(self) -> bool:
        """Check if query has filters."""
        return self.filters is not None and not self.filters.is_empty()
    
    def __str__(self):
        parts = []
        if self.collection_name:
            parts.append(f"collection={self.collection_name}")
        if self.search_type:
            parts.append(f"type={self.search_type.value}")
        if self.filters:
            parts.append(f"filters={self.filters}")
        if self._limit:
            parts.append(f"limit={self._limit}")
        return f"QueryBuilder({', '.join(parts)})"


def create_query(target: Any, client: WeaviateClient) -> QueryBuilder:
    """Convenience function to create a query builder."""
    return QueryBuilder(target, client)
