"""
Advanced queryset for chainable search operations.

Provides enhanced search capabilities with chainable filters
and multiple search methods.
"""

import logging
from typing import List, Optional, Type, TypeVar
from weaviate.classes.query import Filter

from ..core.client import WeaviateClient
from .manager import SearchManager

logger = logging.getLogger(__name__)
T = TypeVar('T', bound='Model')


class AdvancedQuerySet:
    """Advanced query set with enhanced search capabilities and chainable filters"""
    
    def __init__(self, model_class: Type[T], client: WeaviateClient):
        self.model_class = model_class
        self.client = client
        self._search_manager = SearchManager(model_class, client)
        self._filters: List[Filter] = []
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None

    def filter(self, **kwargs) -> 'AdvancedQuerySet':
        """
        Add filter conditions (chainable).
        
        Args:
            **kwargs: Field name and value mappings
            
        Returns:
            AdvancedQuerySet: Current instance (chainable)
        """
        for field, value in kwargs.items():
            # Check if field exists in model's _fields dictionary
            if field in self.model_class._fields:
                filter_condition = Filter.by_property(field).equal(value)
                self._filters.append(filter_condition)
        return self

    def limit(self, limit: int) -> 'AdvancedQuerySet':
        """
        Set result limit (chainable).
        
        Args:
            limit: Maximum number of results
            
        Returns:
            AdvancedQuerySet: Current instance (chainable)
        """
        self._limit = limit
        return self

    def offset(self, offset: int) -> 'AdvancedQuerySet':
        """
        Set pagination offset (chainable).
        
        Args:
            offset: Number of results to skip
            
        Returns:
            AdvancedQuerySet: Current instance (chainable)
        """
        self._offset = offset
        return self

    def _build_filters(self):
        """Build filter conditions for search."""
        if not self._filters:
            return None
        
        if len(self._filters) == 1:
            return self._filters[0]
        else:
            return Filter.and_(*self._filters)

    def near_text(self, text: str, **kwargs) -> List[T]:
        """
        Semantic text search with current filters and limits.
        
        Args:
            text: Text to search for
            **kwargs: Additional search parameters
            
        Returns:
            List[T]: Model instances matching the search
        """
        filters = self._build_filters()
        limit = self._limit if self._limit is not None else kwargs.get('limit', 10)
        
        return self._search_manager.near_text(
            text=text,
            filters=filters,
            limit=limit,
            **kwargs
        )

    def bm25(self, text: str, **kwargs) -> List[T]:
        """
        BM25 keyword search with current filters and limits.
        
        Args:
            text: Text to search for
            **kwargs: Additional search parameters
            
        Returns:
            List[T]: Model instances matching the search
        """
        filters = self._build_filters()
        limit = self._limit if self._limit is not None else kwargs.get('limit', 10)
        
        return self._search_manager.bm25(
            text=text,
            filters=filters,
            limit=limit,
            **kwargs
        )

    def hybrid(self, text: str, **kwargs) -> List[T]:
        """
        Hybrid search (BM25 + vector) with current filters and limits.
        
        Args:
            text: Text to search for
            **kwargs: Additional search parameters
            
        Returns:
            List[T]: Model instances matching the search
        """
        filters = self._build_filters()
        limit = self._limit if self._limit is not None else kwargs.get('limit', 10)
        
        return self._search_manager.hybrid(
            text=text,
            filters=filters,
            limit=limit,
            **kwargs
        )

    def fuzzy_search(self, text: str, **kwargs) -> List[T]:
        """
        Fuzzy search with current filters and limits.
        
        Args:
            text: Text to search for
            **kwargs: Additional search parameters
            
        Returns:
            List[T]: Model instances with fuzzy matching
        """
        filters = self._build_filters()
        limit = self._limit if self._limit is not None else kwargs.get('limit', 10)
        
        return self._search_manager.fuzzy_search(
            text=text,
            filters=filters,
            limit=limit,
            **kwargs
        )

