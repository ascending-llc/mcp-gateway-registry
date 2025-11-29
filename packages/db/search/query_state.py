"""
Query State Management

Encapsulates all query parameters and state in a single, immutable-like structure.
This separates state management from query building logic.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from ..core.enums import SearchType
from .filters import Q


@dataclass
class QueryState:
    """
    Immutable query state container.
    
    Holds all parameters needed to execute a search query.
    Using dataclass for clean state management and easy copying.
    """
    
    # Target collection
    collection_name: Optional[str] = None
    
    # Search configuration
    search_type: Optional[SearchType] = None
    search_params: Dict[str, Any] = field(default_factory=dict)
    
    # Filters
    filters: Optional[Q] = None
    
    # Pagination
    limit: Optional[int] = None
    offset: Optional[int] = None
    
    # Sorting
    order_by: Optional[str] = None
    order_desc: bool = False
    
    # Metadata
    include_metadata: bool = True
    return_properties: Optional[List[str]] = None
    
    # Cross-collection search
    collection_names: Optional[List[str]] = None
    
    # Advanced features
    rerank_config: Optional[Dict[str, Any]] = None
    generative_config: Optional[Dict[str, Any]] = None
    
    # Performance optimizations
    use_cache: bool = True
    cache_ttl: Optional[int] = None
    
    def clone(self) -> 'QueryState':
        """Create a copy of this state for immutable-style updates."""
        return QueryState(
            collection_name=self.collection_name,
            search_type=self.search_type,
            search_params=self.search_params.copy(),
            filters=self.filters,
            limit=self.limit,
            offset=self.offset,
            order_by=self.order_by,
            order_desc=self.order_desc,
            include_metadata=self.include_metadata,
            return_properties=self.return_properties.copy() if self.return_properties else None,
            collection_names=self.collection_names.copy() if self.collection_names else None,
            rerank_config=self.rerank_config.copy() if self.rerank_config else None,
            generative_config=self.generative_config.copy() if self.generative_config else None,
            use_cache=self.use_cache,
            cache_ttl=self.cache_ttl
        )
    
    def is_cross_collection(self) -> bool:
        """Check if this is a cross-collection search."""
        return self.collection_names is not None and len(self.collection_names) > 1
    
    def has_filters(self) -> bool:
        """Check if filters are present."""
        return self.filters is not None and not self.filters.is_empty()
    
    def __str__(self) -> str:
        """String representation for debugging."""
        parts = []
        
        if self.collection_name:
            parts.append(f"collection={self.collection_name}")
        elif self.collection_names:
            parts.append(f"collections={self.collection_names}")
        
        if self.search_type:
            parts.append(f"type={self.search_type.value}")
        
        if self.has_filters():
            parts.append(f"filters={self.filters}")
        
        if self.limit:
            parts.append(f"limit={self.limit}")
        
        return f"QueryState({', '.join(parts)})"

