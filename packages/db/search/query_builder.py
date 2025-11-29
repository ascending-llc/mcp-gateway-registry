"""
Query Builder and Executor

Provides a fluent interface for building and executing search queries.
Separates query construction from execution for better testability and maintainability.
"""

import logging
from typing import Any, Dict, List, Optional, TypeVar, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..core.client import WeaviateClient
from ..core.enums import SearchType
from .query_state import QueryState
from .filters import Q
from .strategies import SearchStrategyFactory

logger = logging.getLogger(__name__)
T = TypeVar('T')


class QueryExecutor:
    """
    Executes search queries using the appropriate strategy.
    
    Responsible for:
    - Strategy selection
    - Query execution
    - Cross-collection search coordination
    - Error handling
    """
    
    def __init__(self, state: QueryState, client: WeaviateClient):
        """
        Initialize executor.
        
        Args:
            state: Query state with all parameters
            client: Weaviate client instance
        """
        self.state = state
        self.client = client
    
    def execute(self) -> List[Dict[str, Any]]:
        """
        Execute the query and return results.
        
        Returns:
            List of result dictionaries
        """
        # Handle cross-collection search
        if self.state.is_cross_collection():
            return self._execute_cross_collection()
        
        # Single collection search
        return self._execute_single_collection()
    
    def _execute_single_collection(self) -> List[Dict[str, Any]]:
        """Execute search in a single collection."""
        if not self.state.collection_name:
            logger.error("No collection name specified")
            return []
        
        # Get the appropriate strategy
        strategy = SearchStrategyFactory.get(self.state.search_type)
        
        # Execute with strategy
        try:
            results = strategy.execute(self.state, self.client)
            logger.debug(
                f"Search completed: {self.state.search_type.value if self.state.search_type else 'fetch'}, "
                f"found {len(results)} results"
            )
            return results
        except Exception as e:
            logger.error(f"Search execution failed: {e}")
            return []
    
    def _execute_cross_collection(self) -> List[Dict[str, Any]]:
        """
        Execute search across multiple collections in parallel.
        
        Returns merged and optionally sorted results.
        """
        if not self.state.collection_names:
            return []
        
        all_results = []
        
        # Execute searches in parallel
        with ThreadPoolExecutor(max_workers=min(len(self.state.collection_names), 10)) as executor:
            # Submit all collection searches
            future_to_collection = {}
            for collection_name in self.state.collection_names:
                # Create a new state for this collection
                collection_state = self.state.clone()
                collection_state.collection_name = collection_name
                collection_state.collection_names = None  # Prevent recursion
                
                future = executor.submit(self._search_single_collection, collection_state)
                future_to_collection[future] = collection_name
            
            # Collect results as they complete
            for future in as_completed(future_to_collection):
                collection_name = future_to_collection[future]
                try:
                    results = future.result()
                    # Add collection name to each result
                    for result in results:
                        result['_collection'] = collection_name
                    all_results.extend(results)
                except Exception as e:
                    logger.error(f"Search failed for collection {collection_name}: {e}")
        
        # Sort by relevance score if available
        if all_results and '_score' in all_results[0]:
            all_results.sort(key=lambda x: x.get('_score', 0), reverse=True)
        elif all_results and '_distance' in all_results[0]:
            all_results.sort(key=lambda x: x.get('_distance', float('inf')))
        
        # Apply global limit
        if self.state.limit and len(all_results) > self.state.limit:
            all_results = all_results[:self.state.limit]
        
        return all_results
    
    def _search_single_collection(self, state: QueryState) -> List[Dict[str, Any]]:
        """Helper to search a single collection (for parallel execution)."""
        strategy = SearchStrategyFactory.get(state.search_type)
        return strategy.execute(state, self.client)


class QueryBuilder:
    """
    Fluent interface for building search queries.
    
    Provides a chainable API for constructing complex search queries with:
    - Filtering
    - Different search types
    - Pagination
    - Sorting
    - Cross-collection search
    
    Example:
        results = (QueryBuilder(Article, client)
            .filter(category="tech")
            .search("AI", SearchType.HYBRID)
            .limit(10)
            .execute())
    """
    
    def __init__(self, target: Any, client: WeaviateClient):
        """
        Initialize query builder.
        
        Args:
            target: Search target (Model class, collection name, or SearchTarget)
            client: Weaviate client instance
        """
        self.client = client
        self.state = QueryState()
        self._executed = False
        self._cached_results: Optional[List] = None
        
        # Set collection name from target
        self._set_target(target)
    
    def _set_target(self, target: Any):
        """Set the search target (model or collection)."""
        if isinstance(target, str):
            # Direct collection name
            self.state.collection_name = target
        elif hasattr(target, 'get_collection_name'):
            # Model class
            self.state.collection_name = target.get_collection_name()
            self._model_class = target
        else:
            raise ValueError(f"Invalid target type: {type(target)}")
    
    def filter(self, *args, **kwargs) -> 'QueryBuilder':
        """
        Add filter conditions.
        
        Args:
            *args: Q objects
            **kwargs: Field filters
            
        Returns:
            Self for chaining
            
        Example:
            .filter(category="tech", published=True)
            .filter(Q(category="tech") | Q(category="science"))
            .filter(views__gt=1000)
        """
        self._ensure_not_executed()
        
        # Build Q object from args and kwargs
        if args or kwargs:
            new_filter = Q(*args, **kwargs)
            
            if self.state.filters is None:
                self.state.filters = new_filter
            else:
                # Combine with existing filters using AND
                self.state.filters = self.state.filters & new_filter
        
        return self
    
    def exclude(self, *args, **kwargs) -> 'QueryBuilder':
        """
        Add exclusion filters (NOT).
        
        Args:
            *args: Q objects to exclude
            **kwargs: Field filters to exclude
            
        Returns:
            Self for chaining
        """
        self._ensure_not_executed()
        
        if args or kwargs:
            exclude_filter = ~Q(*args, **kwargs)
            
            if self.state.filters is None:
                self.state.filters = exclude_filter
            else:
                self.state.filters = self.state.filters & exclude_filter
        
        return self
    
    def search(
        self, 
        query: str, 
        search_type: Optional[SearchType] = None,
        **kwargs
    ) -> 'QueryBuilder':
        """
        Set search query and type.
        
        Args:
            query: Search query text
            search_type: Type of search (defaults to HYBRID)
            **kwargs: Additional search parameters
            
        Returns:
            Self for chaining
        """
        self._ensure_not_executed()
        
        self.state.search_type = search_type or SearchType.HYBRID
        self.state.search_params = {'query': query, **kwargs}
        
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
        self.state.search_type = SearchType.NEAR_VECTOR
        self.state.search_params = {'vector': vector, **kwargs}
        return self
    
    def hybrid(self, query: str, alpha: float = 0.7, **kwargs) -> 'QueryBuilder':
        """Hybrid search (BM25 + semantic)."""
        return self.search(query, SearchType.HYBRID, alpha=alpha, **kwargs)
    
    def fuzzy(self, query: str, **kwargs) -> 'QueryBuilder':
        """Fuzzy search (typo-tolerant)."""
        return self.search(query, SearchType.FUZZY, **kwargs)
    
    def limit(self, n: int) -> 'QueryBuilder':
        """Set result limit."""
        self._ensure_not_executed()
        self.state.limit = n
        return self
    
    def offset(self, n: int) -> 'QueryBuilder':
        """Set pagination offset."""
        self._ensure_not_executed()
        self.state.offset = n
        return self
    
    def order_by(self, field: str, desc: bool = False) -> 'QueryBuilder':
        """Set ordering field."""
        self._ensure_not_executed()
        self.state.order_by = field
        self.state.order_desc = desc
        return self
    
    def across_collections(self, collection_names: List[str]) -> 'QueryBuilder':
        """Search across multiple collections."""
        self._ensure_not_executed()
        self.state.collection_names = collection_names
        self.state.collection_name = None
        return self
    
    def only(self, *fields: str) -> 'QueryBuilder':
        """Select only specific fields to return."""
        self._ensure_not_executed()
        self.state.return_properties = list(fields)
        return self
    
    # Execution methods
    
    def execute(self) -> List[Any]:
        """
        Execute the query and return results.
        
        Returns:
            List of results (model instances or dicts)
        """
        if not self._executed:
            executor = QueryExecutor(self.state, self.client)
            self._cached_results = executor.execute()
            self._executed = True
            
            # Convert to model instances if applicable
            if hasattr(self, '_model_class') and self._cached_results:
                self._cached_results = self._to_instances(self._cached_results)
        
        return self._cached_results or []
    
    def all(self) -> List[Any]:
        """Alias for execute()."""
        return self.execute()
    
    def first(self) -> Optional[Any]:
        """Get first result or None."""
        results = self.limit(1).execute()
        return results[0] if results else None
    
    def count(self) -> int:
        """Count results (executes the query)."""
        return len(self.execute())
    
    def exists(self) -> bool:
        """Check if any results exist."""
        return self.count() > 0
    
    # Helper methods
    
    def _ensure_not_executed(self):
        """Raise error if trying to modify after execution."""
        if self._executed:
            raise RuntimeError(
                "Cannot modify query after execution. "
                "Create a new QueryBuilder instead."
            )
    
    def _to_instances(self, data_list: List[Dict]) -> List[T]:
        """Convert dictionaries to model instances."""
        if not hasattr(self, '_model_class'):
            return data_list
        
        instances = []
        for data in data_list:
            instance = self._model_class()
            
            # Set ID
            if 'id' in data:
                instance.id = data['id']
            
            # Set field values
            if hasattr(self._model_class, '_fields'):
                for field_name in self._model_class._fields.keys():
                    if field_name in data:
                        setattr(instance, field_name, data[field_name])
            
            # Set metadata
            for key, value in data.items():
                if key.startswith('_') and not hasattr(instance, key):
                    setattr(instance, key, value)
            
            instances.append(instance)
        
        return instances
    
    # Magic methods
    
    def __iter__(self):
        """Make QueryBuilder iterable."""
        return iter(self.execute())
    
    def __len__(self):
        """Get count of results."""
        return self.count()
    
    def __str__(self):
        return str(self.state)


def create_query(target: Any, client: WeaviateClient) -> QueryBuilder:
    """
    Convenience function to create a query builder.
    
    Args:
        target: Model class or collection name
        client: Weaviate client
        
    Returns:
        QueryBuilder instance
    """
    return QueryBuilder(target, client)

