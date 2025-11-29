"""
Tests for search strategies.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from db.search.strategies import (
    SearchStrategy,
    BM25Strategy,
    NearTextStrategy,
    HybridStrategy,
    FuzzyStrategy,
    FetchObjectsStrategy,
    SearchStrategyFactory
)
from db.search.query_state import QueryState
from db.core.enums import SearchType


class TestSearchStrategyFactory:
    """Test SearchStrategyFactory."""
    
    def test_get_bm25_strategy(self):
        """Test getting BM25 strategy."""
        strategy = SearchStrategyFactory.get(SearchType.BM25)
        assert isinstance(strategy, BM25Strategy)
    
    def test_get_near_text_strategy(self):
        """Test getting near_text strategy."""
        strategy = SearchStrategyFactory.get(SearchType.NEAR_TEXT)
        assert isinstance(strategy, NearTextStrategy)
    
    def test_get_hybrid_strategy(self):
        """Test getting hybrid strategy."""
        strategy = SearchStrategyFactory.get(SearchType.HYBRID)
        assert isinstance(strategy, HybridStrategy)
    
    def test_get_fuzzy_strategy(self):
        """Test getting fuzzy strategy."""
        strategy = SearchStrategyFactory.get(SearchType.FUZZY)
        assert isinstance(strategy, FuzzyStrategy)
    
    def test_get_fetch_strategy(self):
        """Test getting fetch_objects strategy."""
        strategy = SearchStrategyFactory.get(SearchType.FETCH_OBJECTS)
        assert isinstance(strategy, FetchObjectsStrategy)
    
    def test_get_none_defaults_to_fetch(self):
        """Test that None search type defaults to fetch."""
        strategy = SearchStrategyFactory.get(None)
        assert isinstance(strategy, FetchObjectsStrategy)
    
    def test_list_strategies(self):
        """Test listing all strategies."""
        strategies = SearchStrategyFactory.list_strategies()
        
        assert SearchType.BM25 in strategies
        assert SearchType.NEAR_TEXT in strategies
        assert SearchType.HYBRID in strategies
        assert SearchType.FETCH_OBJECTS in strategies
    
    def test_register_custom_strategy(self):
        """Test registering a custom strategy."""
        class CustomStrategy(SearchStrategy):
            def execute(self, state, client):
                return []
        
        custom_type = SearchType.NEAR_TEXT  # Just for testing
        original_strategy = SearchStrategyFactory.get(custom_type)
        
        # Register custom
        custom_strategy = CustomStrategy()
        SearchStrategyFactory.register(custom_type, custom_strategy)
        
        # Should get custom strategy
        retrieved = SearchStrategyFactory.get(custom_type)
        assert retrieved is custom_strategy
        
        # Restore original
        SearchStrategyFactory.register(custom_type, original_strategy)


class TestBM25Strategy:
    """Test BM25Strategy."""
    
    def test_execute_success(self, mock_weaviate_client, mock_search_results):
        """Test successful BM25 search execution."""
        strategy = BM25Strategy()
        state = QueryState(
            collection_name="Articles",
            search_params={'query': 'test query'},
            limit=10
        )
        
        # Mock collection
        mock_collection = MagicMock()
        mock_collection.query.bm25 = MagicMock(return_value=mock_search_results)
        
        # Setup client mock
        mock_conn = MagicMock()
        mock_conn.client.collections.get = MagicMock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = MagicMock(return_value=None)
        
        # Execute
        results = strategy.execute(state, mock_weaviate_client)
        
        # Verify
        assert isinstance(results, list)
        assert len(results) == 2
        assert 'id' in results[0]
        assert 'title' in results[0]
    
    def test_execute_handles_text_param(self, mock_weaviate_client):
        """Test that 'text' param is converted to 'query'."""
        strategy = BM25Strategy()
        state = QueryState(
            collection_name="Articles",
            search_params={'text': 'test query'},  # Using 'text' instead of 'query'
            limit=10
        )
        
        mock_collection = MagicMock()
        mock_response = MagicMock()
        mock_response.objects = []
        mock_collection.query.bm25 = MagicMock(return_value=mock_response)
        
        mock_conn = MagicMock()
        mock_conn.client.collections.get = MagicMock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = MagicMock(return_value=None)
        
        results = strategy.execute(state, mock_weaviate_client)
        
        # Verify bm25 was called with 'query' parameter
        call_args = mock_collection.query.bm25.call_args
        assert 'query' in call_args[1]
    
    def test_execute_error_handling(self, mock_weaviate_client):
        """Test error handling in BM25 strategy."""
        strategy = BM25Strategy()
        state = QueryState(
            collection_name="Articles",
            search_params={'query': 'test'}
        )
        
        # Mock to raise error
        mock_weaviate_client.managed_connection.side_effect = Exception("Test error")
        
        results = strategy.execute(state, mock_weaviate_client)
        
        # Should return empty list on error
        assert results == []


class TestNearTextStrategy:
    """Test NearTextStrategy."""
    
    def test_execute_success(self, mock_weaviate_client, mock_search_results):
        """Test successful semantic search execution."""
        strategy = NearTextStrategy()
        state = QueryState(
            collection_name="Articles",
            search_params={'query': 'semantic query'},
            limit=5
        )
        
        mock_collection = MagicMock()
        mock_collection.query.near_text = MagicMock(return_value=mock_search_results)
        
        mock_conn = MagicMock()
        mock_conn.client.collections.get = MagicMock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = MagicMock(return_value=None)
        
        results = strategy.execute(state, mock_weaviate_client)
        
        assert isinstance(results, list)
        assert len(results) == 2


class TestHybridStrategy:
    """Test HybridStrategy."""
    
    def test_execute_with_default_alpha(self, mock_weaviate_client, mock_search_results):
        """Test hybrid search with default alpha."""
        strategy = HybridStrategy()
        state = QueryState(
            collection_name="Articles",
            search_params={'query': 'test'},
            limit=10
        )
        
        mock_collection = MagicMock()
        mock_collection.query.hybrid = MagicMock(return_value=mock_search_results)
        
        mock_conn = MagicMock()
        mock_conn.client.collections.get = MagicMock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = MagicMock(return_value=None)
        
        results = strategy.execute(state, mock_weaviate_client)
        
        # Verify hybrid was called with default alpha=0.7
        call_args = mock_collection.query.hybrid.call_args
        assert call_args[1]['alpha'] == 0.7
    
    def test_execute_with_custom_alpha(self, mock_weaviate_client, mock_search_results):
        """Test hybrid search with custom alpha."""
        strategy = HybridStrategy()
        state = QueryState(
            collection_name="Articles",
            search_params={'query': 'test', 'alpha': 0.5},
            limit=10
        )
        
        mock_collection = MagicMock()
        mock_collection.query.hybrid = MagicMock(return_value=mock_search_results)
        
        mock_conn = MagicMock()
        mock_conn.client.collections.get = MagicMock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = MagicMock(return_value=None)
        
        results = strategy.execute(state, mock_weaviate_client)
        
        # Should use provided alpha
        call_args = mock_collection.query.hybrid.call_args
        assert call_args[1]['alpha'] == 0.5


class TestFuzzyStrategy:
    """Test FuzzyStrategy."""
    
    def test_execute_uses_lower_alpha(self, mock_weaviate_client):
        """Test that fuzzy search uses lower alpha for better keyword matching."""
        strategy = FuzzyStrategy()
        state = QueryState(
            collection_name="Articles",
            search_params={'query': 'test'},
            limit=10
        )
        
        mock_collection = MagicMock()
        mock_response = MagicMock()
        mock_response.objects = []
        mock_collection.query.hybrid = MagicMock(return_value=mock_response)
        
        mock_conn = MagicMock()
        mock_conn.client.collections.get = MagicMock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = MagicMock(return_value=None)
        
        strategy.execute(state, mock_weaviate_client)
        
        # Should use alpha=0.3 for fuzzy search
        call_args = mock_collection.query.hybrid.call_args
        assert call_args[1]['alpha'] == 0.3


class TestFetchObjectsStrategy:
    """Test FetchObjectsStrategy."""
    
    def test_execute_success(self, mock_weaviate_client, mock_search_results):
        """Test successful object fetching."""
        strategy = FetchObjectsStrategy()
        state = QueryState(
            collection_name="Articles",
            limit=10
        )
        
        mock_collection = MagicMock()
        mock_collection.query.fetch_objects = MagicMock(return_value=mock_search_results)
        
        mock_conn = MagicMock()
        mock_conn.client.collections.get = MagicMock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = MagicMock(return_value=None)
        
        results = strategy.execute(state, mock_weaviate_client)
        
        assert isinstance(results, list)
        assert len(results) == 2


class TestSearchStrategyBase:
    """Test base SearchStrategy functionality."""
    
    def test_build_query_params(self, mock_weaviate_client):
        """Test _build_query_params helper."""
        strategy = BM25Strategy()
        
        from db.search.filters import Q
        state = QueryState(
            collection_name="Articles",
            search_params={'query': 'test'},
            filters=Q(category="tech"),
            limit=10,
            offset=5,
            return_properties=["title", "content"]
        )
        
        params = strategy._build_query_params(state)
        
        assert 'limit' in params
        assert params['limit'] == 10
        assert 'offset' in params
        assert params['offset'] == 5
        assert 'filters' in params
        assert 'return_properties' in params
        assert params['return_properties'] == ["title", "content"]
    
    def test_parse_response_with_metadata(self, mock_search_results):
        """Test _parse_response includes metadata."""
        strategy = BM25Strategy()
        
        results = strategy._parse_response(mock_search_results)
        
        assert len(results) == 2
        assert results[0]['id'] == "uuid-1"
        assert results[0]['title'] == 'Article 1'
        assert '_distance' in results[0]
        assert results[0]['_distance'] == 0.1
        assert '_score' in results[0]
        assert results[0]['_score'] == 0.95
    
    def test_parse_response_without_metadata(self):
        """Test _parse_response when no metadata available."""
        strategy = BM25Strategy()
        
        # Create mock without metadata
        mock_obj = MagicMock()
        mock_obj.uuid = "uuid-1"
        mock_obj.properties = {'title': 'Test'}
        delattr(mock_obj, 'metadata')
        
        mock_response = MagicMock()
        mock_response.objects = [mock_obj]
        
        results = strategy._parse_response(mock_response)
        
        assert len(results) == 1
        assert results[0]['id'] == "uuid-1"
        assert '_distance' not in results[0] or results[0].get('_distance') is None

