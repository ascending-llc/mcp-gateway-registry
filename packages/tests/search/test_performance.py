"""
Tests for performance optimization components.
"""

import pytest
import time
from db.search.performance import (
    QueryOptimizer,
    QueryCache,
    get_cache,
    set_cache,
    clear_cache
)
from db.search.query_state import QueryState
from db.search.filters import Q
from db.core.enums import SearchType


class TestQueryOptimizer:
    """Test QueryOptimizer functionality."""
    
    def test_optimize_returns_state(self):
        """Test that optimize returns a QueryState."""
        state = QueryState(
            collection_name="Articles",
            search_type=SearchType.HYBRID,
            limit=10
        )
        
        optimized = QueryOptimizer.optimize(state)
        
        assert isinstance(optimized, QueryState)
        assert optimized.collection_name == "Articles"
    
    def test_optimize_preserves_filters(self):
        """Test that optimization preserves filters."""
        state = QueryState(
            collection_name="Articles",
            filters=Q(category="tech", published=True),
            limit=10
        )
        
        optimized = QueryOptimizer.optimize(state)
        
        assert optimized.filters is not None
        assert not optimized.filters.is_empty()
    
    def test_limit_pushdown_for_small_limits(self):
        """Test limit push-down optimization for small limits."""
        state = QueryState(
            collection_name="Articles",
            limit=50
        )
        
        optimized = QueryOptimizer.optimize(state)
        
        # Should have early limit hint
        assert optimized.search_params.get('_early_limit') is True
    
    def test_no_limit_pushdown_for_large_limits(self):
        """Test no limit push-down for large limits."""
        state = QueryState(
            collection_name="Articles",
            limit=200
        )
        
        optimized = QueryOptimizer.optimize(state)
        
        # Should not have early limit hint
        assert optimized.search_params.get('_early_limit') is not True
    
    def test_property_projection_optimization(self):
        """Test property projection optimization."""
        state = QueryState(
            collection_name="Articles",
            return_properties=["title", "content"]
        )
        
        optimized = QueryOptimizer.optimize(state)
        
        # Should have projection optimization flag
        assert optimized.search_params.get('_optimized_projection') is True


class TestQueryCache:
    """Test QueryCache functionality."""
    
    def test_initialization(self):
        """Test cache initialization."""
        cache = QueryCache(max_size=100, ttl=60)
        
        assert cache.max_size == 100
        assert cache.ttl == 60
        assert len(cache._cache) == 0
    
    def test_set_and_get(self):
        """Test setting and getting cached values."""
        cache = QueryCache()
        
        test_data = [{'id': '1', 'title': 'Test'}]
        cache.set("hash1", test_data)
        
        retrieved = cache.get("hash1")
        assert retrieved == test_data
    
    def test_get_nonexistent_key(self):
        """Test getting non-existent key returns None."""
        cache = QueryCache()
        
        result = cache.get("nonexistent")
        assert result is None
    
    def test_cache_hit_increments_counter(self):
        """Test that cache hits increment the counter."""
        cache = QueryCache()
        
        cache.set("hash1", [])
        initial_hits = cache._hits
        
        cache.get("hash1")
        assert cache._hits == initial_hits + 1
    
    def test_cache_miss_increments_counter(self):
        """Test that cache misses increment the counter."""
        cache = QueryCache()
        
        initial_misses = cache._misses
        cache.get("nonexistent")
        
        assert cache._misses == initial_misses + 1
    
    def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = QueryCache(ttl=1)  # 1 second TTL
        
        cache.set("hash1", [])
        
        # Should be available immediately
        assert cache.get("hash1") is not None
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Should be expired
        assert cache.get("hash1") is None
    
    def test_max_size_eviction(self):
        """Test that oldest entries are evicted when max size reached."""
        cache = QueryCache(max_size=2)
        
        cache.set("hash1", [1])
        cache.set("hash2", [2])
        cache.set("hash3", [3])  # Should evict hash1
        
        assert cache.get("hash1") is None  # Evicted
        assert cache.get("hash2") is not None
        assert cache.get("hash3") is not None
    
    def test_lru_behavior(self):
        """Test LRU (Least Recently Used) behavior."""
        cache = QueryCache(max_size=2)
        
        cache.set("hash1", [1])
        cache.set("hash2", [2])
        
        # Access hash1 to make it recently used
        cache.get("hash1")
        
        # Add hash3, should evict hash2 (least recently used)
        cache.set("hash3", [3])
        
        assert cache.get("hash1") is not None  # Still there
        assert cache.get("hash2") is None  # Evicted
        assert cache.get("hash3") is not None
    
    def test_clear(self):
        """Test clearing the cache."""
        cache = QueryCache()
        
        cache.set("hash1", [1])
        cache.set("hash2", [2])
        
        cache.clear()
        
        assert len(cache._cache) == 0
        assert cache._hits == 0
        assert cache._misses == 0
    
    def test_invalidate(self):
        """Test invalidating a specific entry."""
        cache = QueryCache()
        
        cache.set("hash1", [1])
        cache.set("hash2", [2])
        
        cache.invalidate("hash1")
        
        assert cache.get("hash1") is None
        assert cache.get("hash2") is not None
    
    def test_stats(self):
        """Test cache statistics."""
        cache = QueryCache(max_size=100, ttl=300)
        
        cache.set("hash1", [1])
        cache.set("hash2", [2])
        cache.get("hash1")  # Hit
        cache.get("nonexistent")  # Miss
        
        stats = cache.stats()
        
        assert stats['size'] == 2
        assert stats['max_size'] == 100
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert 'hit_rate' in stats
        assert stats['ttl'] == 300
    
    def test_hash_query(self):
        """Test query state hashing."""
        state1 = QueryState(
            collection_name="Articles",
            search_type=SearchType.HYBRID,
            search_params={'query': 'test'},
            limit=10
        )
        
        state2 = QueryState(
            collection_name="Articles",
            search_type=SearchType.HYBRID,
            search_params={'query': 'test'},
            limit=10
        )
        
        state3 = QueryState(
            collection_name="Articles",
            search_type=SearchType.HYBRID,
            search_params={'query': 'different'},
            limit=10
        )
        
        hash1 = QueryCache.hash_query(state1)
        hash2 = QueryCache.hash_query(state2)
        hash3 = QueryCache.hash_query(state3)
        
        # Same states should have same hash
        assert hash1 == hash2
        
        # Different states should have different hash
        assert hash1 != hash3
    
    def test_hash_consistency(self):
        """Test that hashing is consistent."""
        state = QueryState(
            collection_name="Articles",
            search_type=SearchType.BM25,
            search_params={'query': 'test'},
            limit=10
        )
        
        hash1 = QueryCache.hash_query(state)
        hash2 = QueryCache.hash_query(state)
        
        assert hash1 == hash2


class TestGlobalCache:
    """Test global cache functions."""
    
    def test_get_cache_creates_instance(self):
        """Test that get_cache creates a cache instance."""
        # Clear any existing cache
        set_cache(None)
        
        cache = get_cache()
        
        assert cache is not None
        assert isinstance(cache, QueryCache)
    
    def test_get_cache_returns_same_instance(self):
        """Test that get_cache returns the same instance."""
        set_cache(None)
        
        cache1 = get_cache()
        cache2 = get_cache()
        
        assert cache1 is cache2
    
    def test_get_cache_with_custom_params(self):
        """Test get_cache with custom parameters."""
        set_cache(None)
        
        cache = get_cache(max_size=500, ttl=120)
        
        assert cache.max_size == 500
        assert cache.ttl == 120
    
    def test_set_cache(self):
        """Test setting a custom cache."""
        custom_cache = QueryCache(max_size=999)
        set_cache(custom_cache)
        
        retrieved = get_cache()
        
        assert retrieved is custom_cache
        assert retrieved.max_size == 999
    
    def test_clear_cache(self):
        """Test global cache clearing."""
        cache = get_cache()
        cache.set("hash1", [1])
        
        clear_cache()
        
        # Cache should be empty
        assert cache.get("hash1") is None


class TestPerformanceIntegration:
    """Integration tests for performance components."""
    
    def test_optimize_and_cache_workflow(self):
        """Test typical workflow with optimization and caching."""
        # Create a query state
        state = QueryState(
            collection_name="Articles",
            search_type=SearchType.HYBRID,
            search_params={'query': 'test'},
            filters=Q(category="tech"),
            limit=50
        )
        
        # Optimize
        optimized = QueryOptimizer.optimize(state)
        
        # Generate hash for caching
        query_hash = QueryCache.hash_query(optimized)
        
        # Use cache
        cache = QueryCache()
        results = [{'id': '1', 'title': 'Test'}]
        cache.set(query_hash, results)
        
        # Retrieve from cache
        cached_results = cache.get(query_hash)
        
        assert cached_results == results
        assert cache._hits == 1
    
    def test_cache_performance_benefit(self):
        """Test that caching provides performance benefit."""
        cache = QueryCache()
        
        # Simulate expensive operation
        def expensive_operation():
            time.sleep(0.01)  # 10ms
            return [{'id': str(i)} for i in range(100)]
        
        query_hash = "test_hash"
        
        # First call - cache miss
        start = time.time()
        results = expensive_operation()
        cache.set(query_hash, results)
        first_duration = time.time() - start
        
        # Second call - cache hit
        start = time.time()
        cached_results = cache.get(query_hash)
        second_duration = time.time() - start
        
        # Cache hit should be much faster
        assert second_duration < first_duration
        assert cached_results == results

