"""
Plugin System for Search Framework

Provides hooks for extending search behavior without modifying core code.
Plugins can intercept before/after search execution, modify results, log metrics, etc.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from .query_state import QueryState

logger = logging.getLogger(__name__)


class SearchPlugin(ABC):
    """
    Base class for search plugins.
    
    Plugins can hook into the search lifecycle to add custom behavior:
    - Logging
    - Metrics collection
    - Result transformation
    - Caching
    - Access control
    """
    
    @abstractmethod
    def on_before_search(self, state: QueryState) -> Optional[QueryState]:
        """
        Called before search execution.
        
        Args:
            state: Query state about to be executed
            
        Returns:
            Modified state (or None to use original)
        """
        pass
    
    @abstractmethod
    def on_after_search(
        self, 
        state: QueryState, 
        results: List[Any],
        duration: float
    ) -> Optional[List[Any]]:
        """
        Called after search execution.
        
        Args:
            state: Query state that was executed
            results: Search results
            duration: Execution time in seconds
            
        Returns:
            Modified results (or None to use original)
        """
        pass
    
    @abstractmethod
    def on_error(self, state: QueryState, error: Exception):
        """
        Called when search fails.
        
        Args:
            state: Query state that failed
            error: Exception that occurred
        """
        pass


class LoggingPlugin(SearchPlugin):
    """
    Plugin that logs search operations.
    
    Useful for debugging and monitoring search behavior.
    """
    
    def __init__(self, log_level: int = logging.INFO):
        """
        Initialize logging plugin.
        
        Args:
            log_level: Logging level (e.g., logging.DEBUG, logging.INFO)
        """
        self.log_level = log_level
    
    def on_before_search(self, state: QueryState) -> Optional[QueryState]:
        """Log search initiation."""
        logger.log(
            self.log_level,
            f"Executing search: {state.search_type.value if state.search_type else 'fetch'} "
            f"on {state.collection_name}"
        )
        return None
    
    def on_after_search(
        self, 
        state: QueryState, 
        results: List[Any],
        duration: float
    ) -> Optional[List[Any]]:
        """Log search completion."""
        logger.log(
            self.log_level,
            f"Search completed: found {len(results)} results in {duration:.3f}s"
        )
        return None
    
    def on_error(self, state: QueryState, error: Exception):
        """Log search failure."""
        logger.error(f"Search failed: {error}", exc_info=True)


class MetricsPlugin(SearchPlugin):
    """
    Plugin that collects search metrics.
    
    Tracks:
    - Search counts by type
    - Average execution time
    - Result counts
    - Error rates
    """
    
    def __init__(self):
        """Initialize metrics plugin."""
        self.metrics = {
            'total_searches': 0,
            'searches_by_type': {},
            'total_duration': 0.0,
            'total_results': 0,
            'errors': 0
        }
    
    def on_before_search(self, state: QueryState) -> Optional[QueryState]:
        """Record search initiation."""
        self.metrics['total_searches'] += 1
        
        search_type = state.search_type.value if state.search_type else 'fetch'
        self.metrics['searches_by_type'][search_type] = \
            self.metrics['searches_by_type'].get(search_type, 0) + 1
        
        return None
    
    def on_after_search(
        self, 
        state: QueryState, 
        results: List[Any],
        duration: float
    ) -> Optional[List[Any]]:
        """Record search metrics."""
        self.metrics['total_duration'] += duration
        self.metrics['total_results'] += len(results)
        return None
    
    def on_error(self, state: QueryState, error: Exception):
        """Record error."""
        self.metrics['errors'] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get collected metrics.
        
        Returns:
            Dictionary with metrics
        """
        total = self.metrics['total_searches']
        avg_duration = (self.metrics['total_duration'] / total) if total > 0 else 0
        avg_results = (self.metrics['total_results'] / total) if total > 0 else 0
        
        return {
            'total_searches': total,
            'searches_by_type': self.metrics['searches_by_type'],
            'average_duration': f"{avg_duration:.3f}s",
            'average_results': f"{avg_results:.1f}",
            'errors': self.metrics['errors'],
            'error_rate': f"{(self.metrics['errors'] / total * 100):.2f}%" if total > 0 else "0%"
        }
    
    def reset(self):
        """Reset all metrics."""
        self.metrics = {
            'total_searches': 0,
            'searches_by_type': {},
            'total_duration': 0.0,
            'total_results': 0,
            'errors': 0
        }


class ResultTransformPlugin(SearchPlugin):
    """
    Plugin that transforms search results.
    
    Can be used to:
    - Add computed fields
    - Filter sensitive data
    - Format results
    """
    
    def __init__(self, transform_fn):
        """
        Initialize with a transformation function.
        
        Args:
            transform_fn: Function that takes (result_dict) and returns modified dict
        """
        self.transform_fn = transform_fn
    
    def on_before_search(self, state: QueryState) -> Optional[QueryState]:
        """No action before search."""
        return None
    
    def on_after_search(
        self, 
        state: QueryState, 
        results: List[Any],
        duration: float
    ) -> Optional[List[Any]]:
        """Transform each result."""
        if self.transform_fn and results:
            try:
                transformed = []
                for result in results:
                    if isinstance(result, dict):
                        transformed.append(self.transform_fn(result))
                    else:
                        transformed.append(result)
                return transformed
            except Exception as e:
                logger.error(f"Result transformation failed: {e}")
                return None
        return None
    
    def on_error(self, state: QueryState, error: Exception):
        """No action on error."""
        pass


class CachePlugin(SearchPlugin):
    """
    Plugin that provides caching.
    
    Note: This is an example. In practice, caching is handled
    by the QueryExecutor using the QueryCache class.
    """
    
    def __init__(self, cache):
        """
        Initialize with a cache instance.
        
        Args:
            cache: QueryCache instance
        """
        self.cache = cache
    
    def on_before_search(self, state: QueryState) -> Optional[QueryState]:
        """No modification before search."""
        return None
    
    def on_after_search(
        self, 
        state: QueryState, 
        results: List[Any],
        duration: float
    ) -> Optional[List[Any]]:
        """Cache results."""
        if state.use_cache and results:
            from .performance import QueryCache
            query_hash = QueryCache.hash_query(state)
            self.cache.set(query_hash, results)
        return None
    
    def on_error(self, state: QueryState, error: Exception):
        """No action on error."""
        pass


class PluginManager:
    """
    Manages search plugins and coordinates their execution.
    
    Provides methods to register plugins and trigger their hooks.
    """
    
    def __init__(self):
        """Initialize plugin manager."""
        self.plugins: List[SearchPlugin] = []
    
    def register(self, plugin: SearchPlugin):
        """
        Register a plugin.
        
        Args:
            plugin: Plugin instance to register
        """
        self.plugins.append(plugin)
        logger.info(f"Registered plugin: {plugin.__class__.__name__}")
    
    def unregister(self, plugin: SearchPlugin):
        """
        Unregister a plugin.
        
        Args:
            plugin: Plugin instance to remove
        """
        if plugin in self.plugins:
            self.plugins.remove(plugin)
            logger.info(f"Unregistered plugin: {plugin.__class__.__name__}")
    
    def clear(self):
        """Remove all plugins."""
        self.plugins.clear()
        logger.info("Cleared all plugins")
    
    def trigger_before_search(self, state: QueryState) -> QueryState:
        """
        Trigger all plugins' before_search hooks.
        
        Args:
            state: Query state
            
        Returns:
            Modified state (or original if no modifications)
        """
        current_state = state
        
        for plugin in self.plugins:
            try:
                modified = plugin.on_before_search(current_state)
                if modified:
                    current_state = modified
            except Exception as e:
                logger.error(f"Plugin {plugin.__class__.__name__} failed in before_search: {e}")
        
        return current_state
    
    def trigger_after_search(
        self, 
        state: QueryState, 
        results: List[Any],
        duration: float
    ) -> List[Any]:
        """
        Trigger all plugins' after_search hooks.
        
        Args:
            state: Query state
            results: Search results
            duration: Execution duration
            
        Returns:
            Modified results (or original if no modifications)
        """
        current_results = results
        
        for plugin in self.plugins:
            try:
                modified = plugin.on_after_search(state, current_results, duration)
                if modified is not None:
                    current_results = modified
            except Exception as e:
                logger.error(f"Plugin {plugin.__class__.__name__} failed in after_search: {e}")
        
        return current_results
    
    def trigger_error(self, state: QueryState, error: Exception):
        """
        Trigger all plugins' error hooks.
        
        Args:
            state: Query state
            error: Exception that occurred
        """
        for plugin in self.plugins:
            try:
                plugin.on_error(state, error)
            except Exception as e:
                logger.error(f"Plugin {plugin.__class__.__name__} failed in on_error: {e}")


# Global plugin manager
_global_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """
    Get or create the global plugin manager.
    
    Returns:
        PluginManager instance
    """
    global _global_plugin_manager
    
    if _global_plugin_manager is None:
        _global_plugin_manager = PluginManager()
    
    return _global_plugin_manager


def set_plugin_manager(manager: PluginManager):
    """
    Set the global plugin manager.
    
    Args:
        manager: PluginManager instance
    """
    global _global_plugin_manager
    _global_plugin_manager = manager

