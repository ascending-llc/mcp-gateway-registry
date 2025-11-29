"""
Tests for plugin system.
"""

import pytest
from unittest.mock import Mock
from db.search.plugins import (
    SearchPlugin,
    LoggingPlugin,
    MetricsPlugin,
    ResultTransformPlugin,
    CachePlugin,
    PluginManager,
    get_plugin_manager,
    set_plugin_manager
)
from db.search.query_state import QueryState
from db.core.enums import SearchType


class TestSearchPluginInterface:
    """Test SearchPlugin base class."""
    
    def test_plugin_must_implement_methods(self):
        """Test that plugins must implement abstract methods."""
        # Cannot instantiate abstract class directly
        with pytest.raises(TypeError):
            SearchPlugin()


class TestLoggingPlugin:
    """Test LoggingPlugin."""
    
    def test_initialization(self):
        """Test plugin initialization."""
        plugin = LoggingPlugin()
        assert plugin is not None
    
    def test_on_before_search(self):
        """Test before search hook."""
        plugin = LoggingPlugin()
        state = QueryState(
            collection_name="Articles",
            search_type=SearchType.HYBRID
        )
        
        result = plugin.on_before_search(state)
        
        # Should return None (no modification)
        assert result is None
    
    def test_on_after_search(self):
        """Test after search hook."""
        plugin = LoggingPlugin()
        state = QueryState(collection_name="Articles")
        results = [{'id': '1'}, {'id': '2'}]
        
        modified = plugin.on_after_search(state, results, duration=0.5)
        
        # Should return None (no modification)
        assert modified is None
    
    def test_on_error(self):
        """Test error hook."""
        plugin = LoggingPlugin()
        state = QueryState(collection_name="Articles")
        error = Exception("Test error")
        
        # Should not raise
        plugin.on_error(state, error)


class TestMetricsPlugin:
    """Test MetricsPlugin."""
    
    def test_initialization(self):
        """Test metrics plugin initialization."""
        plugin = MetricsPlugin()
        
        assert plugin.metrics['total_searches'] == 0
        assert plugin.metrics['total_results'] == 0
    
    def test_on_before_search_increments_counter(self):
        """Test that before_search increments search counter."""
        plugin = MetricsPlugin()
        state = QueryState(
            collection_name="Articles",
            search_type=SearchType.HYBRID
        )
        
        plugin.on_before_search(state)
        
        assert plugin.metrics['total_searches'] == 1
        assert plugin.metrics['searches_by_type']['hybrid'] == 1
    
    def test_on_after_search_records_metrics(self):
        """Test that after_search records metrics."""
        plugin = MetricsPlugin()
        state = QueryState(collection_name="Articles")
        results = [{'id': '1'}, {'id': '2'}]
        
        plugin.on_after_search(state, results, duration=0.5)
        
        assert plugin.metrics['total_results'] == 2
        assert plugin.metrics['total_duration'] == 0.5
    
    def test_on_error_increments_error_counter(self):
        """Test that error increments error counter."""
        plugin = MetricsPlugin()
        state = QueryState(collection_name="Articles")
        
        plugin.on_error(state, Exception("Test"))
        
        assert plugin.metrics['errors'] == 1
    
    def test_get_metrics(self):
        """Test getting metrics summary."""
        plugin = MetricsPlugin()
        
        # Simulate some activity
        state = QueryState(
            collection_name="Articles",
            search_type=SearchType.HYBRID
        )
        plugin.on_before_search(state)
        plugin.on_after_search(state, [{'id': '1'}], duration=0.5)
        
        metrics = plugin.get_metrics()
        
        assert metrics['total_searches'] == 1
        assert 'average_duration' in metrics
        assert 'average_results' in metrics
        assert 'error_rate' in metrics
    
    def test_reset(self):
        """Test resetting metrics."""
        plugin = MetricsPlugin()
        
        # Add some metrics
        state = QueryState(collection_name="Articles")
        plugin.on_before_search(state)
        
        # Reset
        plugin.reset()
        
        assert plugin.metrics['total_searches'] == 0
        assert plugin.metrics['errors'] == 0
    
    def test_multiple_search_types_tracking(self):
        """Test tracking multiple search types."""
        plugin = MetricsPlugin()
        
        # Perform different search types
        plugin.on_before_search(QueryState(search_type=SearchType.HYBRID))
        plugin.on_before_search(QueryState(search_type=SearchType.BM25))
        plugin.on_before_search(QueryState(search_type=SearchType.HYBRID))
        
        metrics = plugin.get_metrics()
        
        assert metrics['searches_by_type']['hybrid'] == 2
        assert metrics['searches_by_type']['bm25'] == 1


class TestResultTransformPlugin:
    """Test ResultTransformPlugin."""
    
    def test_initialization(self):
        """Test plugin initialization with transform function."""
        def transform(result):
            result['transformed'] = True
            return result
        
        plugin = ResultTransformPlugin(transform)
        assert plugin.transform_fn == transform
    
    def test_transform_results(self):
        """Test that results are transformed."""
        def transform(result):
            result['computed'] = result.get('views', 0) * 2
            return result
        
        plugin = ResultTransformPlugin(transform)
        state = QueryState(collection_name="Articles")
        results = [
            {'id': '1', 'views': 100},
            {'id': '2', 'views': 200}
        ]
        
        transformed = plugin.on_after_search(state, results, duration=0.1)
        
        assert transformed is not None
        assert transformed[0]['computed'] == 200
        assert transformed[1]['computed'] == 400
    
    def test_transform_handles_non_dict_results(self):
        """Test that non-dict results are passed through."""
        def transform(result):
            result['transformed'] = True
            return result
        
        plugin = ResultTransformPlugin(transform)
        state = QueryState(collection_name="Articles")
        
        # Non-dict result
        results = ["string_result"]
        
        transformed = plugin.on_after_search(state, results, duration=0.1)
        
        # Should pass through unchanged
        assert transformed == results
    
    def test_transform_error_handling(self):
        """Test that transform errors are handled."""
        def bad_transform(result):
            raise ValueError("Transform error")
        
        plugin = ResultTransformPlugin(bad_transform)
        state = QueryState(collection_name="Articles")
        results = [{'id': '1'}]
        
        # Should return None on error
        transformed = plugin.on_after_search(state, results, duration=0.1)
        assert transformed is None


class TestPluginManager:
    """Test PluginManager."""
    
    def test_initialization(self):
        """Test manager initialization."""
        manager = PluginManager()
        assert len(manager.plugins) == 0
    
    def test_register_plugin(self):
        """Test registering a plugin."""
        manager = PluginManager()
        plugin = LoggingPlugin()
        
        manager.register(plugin)
        
        assert len(manager.plugins) == 1
        assert plugin in manager.plugins
    
    def test_unregister_plugin(self):
        """Test unregistering a plugin."""
        manager = PluginManager()
        plugin = LoggingPlugin()
        
        manager.register(plugin)
        manager.unregister(plugin)
        
        assert len(manager.plugins) == 0
        assert plugin not in manager.plugins
    
    def test_clear_plugins(self):
        """Test clearing all plugins."""
        manager = PluginManager()
        manager.register(LoggingPlugin())
        manager.register(MetricsPlugin())
        
        manager.clear()
        
        assert len(manager.plugins) == 0
    
    def test_trigger_before_search(self):
        """Test triggering before_search hooks."""
        manager = PluginManager()
        plugin1 = Mock(spec=SearchPlugin)
        plugin1.on_before_search = Mock(return_value=None)
        plugin2 = Mock(spec=SearchPlugin)
        plugin2.on_before_search = Mock(return_value=None)
        
        manager.register(plugin1)
        manager.register(plugin2)
        
        state = QueryState(collection_name="Articles")
        manager.trigger_before_search(state)
        
        # Both plugins should be called
        plugin1.on_before_search.assert_called_once()
        plugin2.on_before_search.assert_called_once()
    
    def test_trigger_after_search(self):
        """Test triggering after_search hooks."""
        manager = PluginManager()
        plugin = Mock(spec=SearchPlugin)
        plugin.on_after_search = Mock(return_value=None)
        
        manager.register(plugin)
        
        state = QueryState(collection_name="Articles")
        results = [{'id': '1'}]
        manager.trigger_after_search(state, results, duration=0.5)
        
        plugin.on_after_search.assert_called_once_with(state, results, 0.5)
    
    def test_trigger_error(self):
        """Test triggering error hooks."""
        manager = PluginManager()
        plugin = Mock(spec=SearchPlugin)
        plugin.on_error = Mock()
        
        manager.register(plugin)
        
        state = QueryState(collection_name="Articles")
        error = Exception("Test error")
        manager.trigger_error(state, error)
        
        plugin.on_error.assert_called_once_with(state, error)
    
    def test_plugin_error_doesnt_break_chain(self):
        """Test that plugin errors don't break the chain."""
        manager = PluginManager()
        
        # Plugin that raises error
        bad_plugin = Mock(spec=SearchPlugin)
        bad_plugin.on_before_search = Mock(side_effect=Exception("Plugin error"))
        
        # Good plugin
        good_plugin = Mock(spec=SearchPlugin)
        good_plugin.on_before_search = Mock(return_value=None)
        
        manager.register(bad_plugin)
        manager.register(good_plugin)
        
        state = QueryState(collection_name="Articles")
        
        # Should not raise, and good plugin should still be called
        result = manager.trigger_before_search(state)
        
        assert result is not None
        good_plugin.on_before_search.assert_called_once()
    
    def test_state_modification_through_plugins(self):
        """Test that plugins can modify state."""
        manager = PluginManager()
        
        # Plugin that modifies state
        class ModifyingPlugin(SearchPlugin):
            def on_before_search(self, state):
                modified = state.clone()
                modified.limit = 999
                return modified
            
            def on_after_search(self, state, results, duration):
                return None
            
            def on_error(self, state, error):
                pass
        
        manager.register(ModifyingPlugin())
        
        state = QueryState(collection_name="Articles", limit=10)
        modified_state = manager.trigger_before_search(state)
        
        assert modified_state.limit == 999
    
    def test_result_transformation_through_plugins(self):
        """Test that plugins can transform results."""
        manager = PluginManager()
        
        def add_field(result):
            result['added'] = True
            return result
        
        manager.register(ResultTransformPlugin(add_field))
        
        state = QueryState(collection_name="Articles")
        results = [{'id': '1'}]
        
        transformed = manager.trigger_after_search(state, results, duration=0.1)
        
        assert transformed[0]['added'] is True


class TestGlobalPluginManager:
    """Test global plugin manager functions."""
    
    def test_get_plugin_manager_creates_instance(self):
        """Test that get_plugin_manager creates an instance."""
        # Reset global
        set_plugin_manager(None)
        
        manager = get_plugin_manager()
        
        assert manager is not None
        assert isinstance(manager, PluginManager)
    
    def test_get_plugin_manager_returns_same_instance(self):
        """Test that get_plugin_manager returns same instance."""
        set_plugin_manager(None)
        
        manager1 = get_plugin_manager()
        manager2 = get_plugin_manager()
        
        assert manager1 is manager2
    
    def test_set_plugin_manager(self):
        """Test setting custom plugin manager."""
        custom_manager = PluginManager()
        custom_manager.register(LoggingPlugin())
        
        set_plugin_manager(custom_manager)
        
        retrieved = get_plugin_manager()
        
        assert retrieved is custom_manager
        assert len(retrieved.plugins) == 1


class TestPluginIntegration:
    """Integration tests for plugin system."""
    
    def test_multiple_plugins_workflow(self):
        """Test workflow with multiple plugins."""
        manager = PluginManager()
        
        # Add logging and metrics
        logging_plugin = LoggingPlugin()
        metrics_plugin = MetricsPlugin()
        
        manager.register(logging_plugin)
        manager.register(metrics_plugin)
        
        # Simulate search workflow
        state = QueryState(
            collection_name="Articles",
            search_type=SearchType.HYBRID
        )
        
        # Before search
        manager.trigger_before_search(state)
        
        # After search
        results = [{'id': '1'}, {'id': '2'}]
        manager.trigger_after_search(state, results, duration=0.5)
        
        # Check metrics were recorded
        metrics = metrics_plugin.get_metrics()
        assert metrics['total_searches'] == 1
        # Check that average_results exists (format may vary)
        assert 'average_results' in metrics
    
    def test_plugin_pipeline(self):
        """Test plugin pipeline with transformations."""
        manager = PluginManager()
        
        # Add transformation plugins
        def add_score(result):
            result['score'] = 1.0
            return result
        
        def add_rank(result):
            result['rank'] = 1
            return result
        
        manager.register(ResultTransformPlugin(add_score))
        manager.register(ResultTransformPlugin(add_rank))
        
        # Trigger pipeline
        state = QueryState(collection_name="Articles")
        results = [{'id': '1'}]
        
        transformed = manager.trigger_after_search(state, results, duration=0.1)
        
        # Both transformations should be applied
        assert transformed[0]['score'] == 1.0
        assert transformed[0]['rank'] == 1

