"""
Performance Optimization Components

Provides query optimization and result caching for improved performance.
"""

import logging
import time
import hashlib
from typing import Any, Dict, List, Optional
from collections import OrderedDict

from .query_state import QueryState
from .filters import Q

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """
    Query optimizer for improving search performance.
    
    Applies various optimization strategies:
    - Filter reordering based on selectivity
    - Limit push-down
    - Property projection
    """
    
    @staticmethod
    def optimize(state: QueryState) -> QueryState:
        """
        Optimize a query state for better performance.
        
        Args:
            state: Original query state
            
        Returns:
            Optimized query state
        """
        optimized = state.clone()
        
        # Apply optimization strategies
        optimized = QueryOptimizer._optimize_filters(optimized)
        optimized = QueryOptimizer._apply_limit_pushdown(optimized)
        optimized = QueryOptimizer._optimize_properties(optimized)
        
        return optimized
    
    @staticmethod
    def _optimize_filters(state: QueryState) -> QueryState:
        """
        Optimize filter conditions for better performance.
        
        Strategy:
        1. Equality filters first (fastest)
        2. Range filters second
        3. Complex filters last
        
        Note: This is a placeholder for more sophisticated optimization.
        In practice, we'd analyze filter selectivity based on data distribution.
        """
        # For now, filters are already optimized by Weaviate's query planner
        # This could be extended with custom logic in the future
        return state
    
    @staticmethod
    def _apply_limit_pushdown(state: QueryState) -> QueryState:
        """
        Push limit down to lower layers for efficiency.
        
        If limit is small, mark for early termination.
        """
        if state.limit and state.limit < 100:
            # Enable early termination hint
            # This could be used by strategies to optimize execution
            state.search_params['_early_limit'] = True
        
        return state
    
    @staticmethod
    def _optimize_properties(state: QueryState) -> QueryState:
        """
        Optimize property selection (projection).
        
        If only specific properties are requested, ensure they're included
        in the query to minimize data transfer.
        """
        if state.return_properties:
            # Ensure we're not fetching unnecessary data
            state.search_params['_optimized_projection'] = True
        
        return state


class QueryCache:
    """
    LRU cache for query results.
    
    Caches search results to avoid redundant queries.
    Uses LRU eviction policy when cache is full.
    
    Example:
        cache = QueryCache(max_size=1000, ttl=300)
        
        # Try to get cached result
        result = cache.get(query_hash)
        if result is None:
            result = execute_query()
            cache.set(query_hash, result)
    """
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        """
        Initialize cache.
        
        Args:
            max_size: Maximum number of entries to cache
            ttl: Time-to-live in seconds (0 = no expiration)
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: OrderedDict[str, tuple[List[Any], float]] = OrderedDict()
        self._hits = 0
        self._misses = 0
    
    def get(self, query_hash: str) -> Optional[List[Any]]:
        """
        Get cached results for a query.
        
        Args:
            query_hash: Hash of the query
            
        Returns:
            Cached results or None if not found/expired
        """
        if query_hash not in self._cache:
            self._misses += 1
            return None
        
        result, timestamp = self._cache[query_hash]
        
        # Check if expired
        if self.ttl > 0 and (time.time() - timestamp) > self.ttl:
            del self._cache[query_hash]
            self._misses += 1
            return None
        
        # Move to end (most recently used)
        self._cache.move_to_end(query_hash)
        self._hits += 1
        
        logger.debug(f"Cache hit for query {query_hash[:8]}...")
        return result
    
    def set(self, query_hash: str, result: List[Any]):
        """
        Cache query results.
        
        Args:
            query_hash: Hash of the query
            result: Results to cache
        """
        # Evict oldest if at capacity
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug(f"Evicted oldest cache entry: {oldest_key[:8]}...")
        
        self._cache[query_hash] = (result, time.time())
        logger.debug(f"Cached results for query {query_hash[:8]}...")
    
    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.info("Cache cleared")
    
    def invalidate(self, query_hash: str):
        """
        Invalidate a specific cached entry.
        
        Args:
            query_hash: Hash of the query to invalidate
        """
        if query_hash in self._cache:
            del self._cache[query_hash]
            logger.debug(f"Invalidated cache entry: {query_hash[:8]}...")
    
    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        
        return {
            'size': len(self._cache),
            'max_size': self.max_size,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': f"{hit_rate:.2f}%",
            'ttl': self.ttl
        }
    
    @staticmethod
    def hash_query(state: QueryState) -> str:
        """
        Generate a hash for a query state.
        
        Args:
            state: Query state
            
        Returns:
            MD5 hash string
        """
        # Build a string representation of the query
        query_parts = [
            f"collection:{state.collection_name}",
            f"type:{state.search_type.value if state.search_type else 'none'}",
            f"params:{sorted(state.search_params.items())}",
            f"filters:{str(state.filters) if state.filters else 'none'}",
            f"limit:{state.limit}",
            f"offset:{state.offset}",
        ]
        
        query_str = "|".join(query_parts)
        return hashlib.md5(query_str.encode()).hexdigest()


# Global cache instance
_global_cache: Optional[QueryCache] = None


def get_cache(max_size: int = 1000, ttl: int = 300) -> QueryCache:
    """
    Get or create the global query cache.
    
    Args:
        max_size: Maximum cache size
        ttl: Time-to-live in seconds
        
    Returns:
        QueryCache instance
    """
    global _global_cache
    
    if _global_cache is None:
        _global_cache = QueryCache(max_size=max_size, ttl=ttl)
        logger.info(f"Initialized global query cache (size={max_size}, ttl={ttl}s)")
    
    return _global_cache


def set_cache(cache: QueryCache):
    """
    Set the global cache instance.
    
    Args:
        cache: Cache instance to use globally
    """
    global _global_cache
    _global_cache = cache


def clear_cache():
    """Clear the global cache."""
    global _global_cache
    if _global_cache:
        _global_cache.clear()

