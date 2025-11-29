"""
Tests for QueryBuilder and QueryExecutor.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from db.search.query_builder import QueryBuilder, QueryExecutor
from db.search.query_state import QueryState
from db.search.filters import Q
from db.core.enums import SearchType


class TestQueryState:
    """Test QueryState class."""
    
    def test_initialization(self):
        """Test QueryState initialization."""
        state = QueryState()
        
        assert state.collection_name is None
        assert state.search_type is None
        assert state.filters is None
        assert state.limit is None
        assert state.offset is None
    
    def test_clone(self):
        """Test cloning a query state."""
        state = QueryState(
            collection_name="Articles",
            search_type=SearchType.HYBRID,
            limit=10
        )
        
        cloned = state.clone()
        
        assert cloned.collection_name == state.collection_name
        assert cloned.search_type == state.search_type
        assert cloned.limit == state.limit
        assert cloned is not state  # Different instance
    
    def test_is_cross_collection(self):
        """Test is_cross_collection method."""
        state = QueryState()
        assert not state.is_cross_collection()
        
        state.collection_names = ["Articles"]
        assert not state.is_cross_collection()
        
        state.collection_names = ["Articles", "Documents"]
        assert state.is_cross_collection()
    
    def test_has_filters(self):
        """Test has_filters method."""
        state = QueryState()
        assert not state.has_filters()
        
        state.filters = Q(category="tech")
        assert state.has_filters()
        
        state.filters = Q()  # Empty Q
        assert not state.has_filters()


class TestQueryBuilder:
    """Test QueryBuilder class."""
    
    def test_initialization_with_model(self, mock_weaviate_client, test_model):
        """Test initialization with a model class."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        assert builder.state.collection_name == "TestArticles"
        assert builder.client == mock_weaviate_client
    
    def test_initialization_with_collection_name(self, mock_weaviate_client):
        """Test initialization with collection name."""
        builder = QueryBuilder("Articles", mock_weaviate_client)
        
        assert builder.state.collection_name == "Articles"
        assert builder.client == mock_weaviate_client
    
    def test_filter_with_kwargs(self, mock_weaviate_client, test_model):
        """Test filter method with keyword arguments."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.filter(category="tech", published=True)
        
        assert result is builder  # Returns self for chaining
        assert builder.state.filters is not None
        assert not builder.state.filters.is_empty()
    
    def test_filter_with_q_object(self, mock_weaviate_client, test_model):
        """Test filter method with Q object."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        q = Q(category="tech") | Q(category="science")
        result = builder.filter(q)
        
        assert result is builder
        assert builder.state.filters is not None
    
    def test_filter_chaining(self, mock_weaviate_client, test_model):
        """Test chaining multiple filters."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = (builder
                  .filter(category="tech")
                  .filter(published=True)
                  .filter(views__gt=1000))
        
        assert result is builder
        assert builder.state.filters is not None
    
    def test_exclude(self, mock_weaviate_client, test_model):
        """Test exclude method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.exclude(status="draft")
        
        assert result is builder
        assert builder.state.filters is not None
    
    def test_search_method(self, mock_weaviate_client, test_model):
        """Test generic search method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.search("test query", SearchType.HYBRID, alpha=0.7)
        
        assert result is builder
        assert builder.state.search_type == SearchType.HYBRID
        assert builder.state.search_params['query'] == "test query"
        assert builder.state.search_params['alpha'] == 0.7
    
    def test_bm25_method(self, mock_weaviate_client, test_model):
        """Test BM25 search method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.bm25("test query")
        
        assert result is builder
        assert builder.state.search_type == SearchType.BM25
    
    def test_near_text_method(self, mock_weaviate_client, test_model):
        """Test near_text method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.near_text("semantic query")
        
        assert result is builder
        assert builder.state.search_type == SearchType.NEAR_TEXT
    
    def test_hybrid_method(self, mock_weaviate_client, test_model):
        """Test hybrid search method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.hybrid("query", alpha=0.8)
        
        assert result is builder
        assert builder.state.search_type == SearchType.HYBRID
        assert builder.state.search_params['alpha'] == 0.8
    
    def test_fuzzy_method(self, mock_weaviate_client, test_model):
        """Test fuzzy search method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.fuzzy("test query")
        
        assert result is builder
        assert builder.state.search_type == SearchType.FUZZY
    
    def test_near_vector_method(self, mock_weaviate_client, test_model):
        """Test near_vector method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        vector = [0.1, 0.2, 0.3]
        result = builder.near_vector(vector)
        
        assert result is builder
        assert builder.state.search_type == SearchType.NEAR_VECTOR
        assert builder.state.search_params['vector'] == vector
    
    def test_limit_method(self, mock_weaviate_client, test_model):
        """Test limit method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.limit(10)
        
        assert result is builder
        assert builder.state.limit == 10
    
    def test_offset_method(self, mock_weaviate_client, test_model):
        """Test offset method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.offset(20)
        
        assert result is builder
        assert builder.state.offset == 20
    
    def test_order_by_method(self, mock_weaviate_client, test_model):
        """Test order_by method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.order_by("views", desc=True)
        
        assert result is builder
        assert builder.state.order_by == "views"
        assert builder.state.order_desc is True
    
    def test_across_collections_method(self, mock_weaviate_client, test_model):
        """Test across_collections method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        collections = ["Articles", "Documents", "Notes"]
        result = builder.across_collections(collections)
        
        assert result is builder
        assert builder.state.collection_names == collections
    
    def test_only_method(self, mock_weaviate_client, test_model):
        """Test only method for field selection."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.only("title", "id")
        
        assert result is builder
        assert builder.state.return_properties == ["title", "id"]
    
    def test_complex_query_chain(self, mock_weaviate_client, test_model):
        """Test complex query chain."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = (builder
                  .filter(category="tech")
                  .filter(Q(published=True) & Q(views__gt=1000))
                  .hybrid("machine learning", alpha=0.7)
                  .limit(20)
                  .offset(10)
                  .only("title", "content"))
        
        assert result is builder
        assert builder.state.filters is not None
        assert builder.state.search_type == SearchType.HYBRID
        assert builder.state.limit == 20
        assert builder.state.offset == 10
        assert builder.state.return_properties == ["title", "content"]
    
    def test_execute_after_modification_raises_error(self, mock_weaviate_client, test_model):
        """Test that modifying after execution raises error."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        # Mock execute to set _executed flag
        with patch.object(QueryExecutor, 'execute', return_value=[]):
            builder.execute()
        
        # Should raise error when trying to modify
        with pytest.raises(RuntimeError, match="Cannot modify query after execution"):
            builder.filter(category="tech")
    
    def test_count_method(self, mock_weaviate_client, test_model, mock_search_results):
        """Test count method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        # Mock the executor to return results
        with patch.object(QueryExecutor, 'execute', return_value=[{}, {}]):
            count = builder.count()
            assert count == 2
    
    def test_first_method(self, mock_weaviate_client, test_model, sample_articles_data):
        """Test first method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        # Mock the executor
        with patch.object(QueryExecutor, 'execute', return_value=sample_articles_data):
            first = builder.first()
            assert first is not None
            # first could be either a dict or a model instance
            if isinstance(first, dict):
                assert first['title'] == 'Machine Learning Basics'
            else:
                assert first.title == 'Machine Learning Basics'
    
    def test_first_method_no_results(self, mock_weaviate_client, test_model):
        """Test first method with no results."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        with patch.object(QueryExecutor, 'execute', return_value=[]):
            first = builder.first()
            assert first is None
    
    def test_exists_method(self, mock_weaviate_client, test_model):
        """Test exists method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        # With results
        with patch.object(QueryExecutor, 'execute', return_value=[{}]):
            assert builder.exists() is True
        
        # Create new builder for second test
        builder2 = QueryBuilder(test_model, mock_weaviate_client)
        
        # Without results
        with patch.object(QueryExecutor, 'execute', return_value=[]):
            assert builder2.exists() is False
    
    def test_iterator_support(self, mock_weaviate_client, test_model, sample_articles_data):
        """Test that QueryBuilder is iterable."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        with patch.object(QueryExecutor, 'execute', return_value=sample_articles_data):
            results = list(builder)
            assert len(results) == 3
    
    def test_len_support(self, mock_weaviate_client, test_model, sample_articles_data):
        """Test that len() works on QueryBuilder."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        with patch.object(QueryExecutor, 'execute', return_value=sample_articles_data):
            length = len(builder)
            assert length == 3


class TestQueryExecutor:
    """Test QueryExecutor class."""
    
    def test_initialization(self, mock_weaviate_client):
        """Test QueryExecutor initialization."""
        state = QueryState(collection_name="Articles")
        executor = QueryExecutor(state, mock_weaviate_client)
        
        assert executor.state == state
        assert executor.client == mock_weaviate_client
    
    def test_execute_calls_strategy(self, mock_weaviate_client, mock_search_results):
        """Test that execute calls the appropriate strategy."""
        state = QueryState(
            collection_name="Articles",
            search_type=SearchType.BM25,
            search_params={'query': 'test'}
        )
        executor = QueryExecutor(state, mock_weaviate_client)
        
        # Mock the strategy
        with patch('db.search.query_builder.SearchStrategyFactory') as mock_factory:
            mock_strategy = Mock()
            mock_strategy.execute = Mock(return_value=[])
            mock_factory.get = Mock(return_value=mock_strategy)
            
            results = executor.execute()
            
            # Strategy should be called
            mock_factory.get.assert_called_once_with(SearchType.BM25)
            mock_strategy.execute.assert_called_once()
    
    def test_cross_collection_execution(self, mock_weaviate_client):
        """Test cross-collection search execution."""
        state = QueryState(
            collection_names=["Articles", "Documents"],
            search_type=SearchType.HYBRID,
            search_params={'query': 'test'},
            limit=10
        )
        state.collection_name = None  # Important: must be None for cross-collection
        executor = QueryExecutor(state, mock_weaviate_client)
        
        # Mock the parallel execution
        with patch.object(executor, '_execute_cross_collection', return_value=[]):
            results = executor.execute()
            assert isinstance(results, list)
    
    def test_error_handling(self, mock_weaviate_client):
        """Test error handling in executor."""
        state = QueryState(
            collection_name="Articles",
            search_type=SearchType.BM25
        )
        executor = QueryExecutor(state, mock_weaviate_client)
        
        # Mock strategy to raise error
        with patch('db.search.query_builder.SearchStrategyFactory') as mock_factory:
            mock_strategy = Mock()
            mock_strategy.execute = Mock(side_effect=Exception("Test error"))
            mock_factory.get = Mock(return_value=mock_strategy)
            
            results = executor.execute()
            # Should return empty list on error
            assert results == []


class TestQueryBuilderIntegration:
    """Integration tests for QueryBuilder."""
    
    def test_full_search_workflow(self, mock_weaviate_client, test_model, sample_articles_data):
        """Test complete search workflow."""
        # Mock the Weaviate response
        mock_response = Mock()
        mock_response.objects = []
        for data in sample_articles_data:
            mock_obj = Mock()
            mock_obj.uuid = data['id']
            mock_obj.properties = {k: v for k, v in data.items() if k != 'id'}
            mock_obj.metadata = Mock()
            mock_obj.metadata.distance = 0.1
            mock_obj.metadata.score = 0.9
            mock_response.objects.append(mock_obj)
        
        # Mock collection.query.hybrid
        mock_collection = Mock()
        mock_collection.query.hybrid = Mock(return_value=mock_response)
        
        # Setup client mock
        mock_conn = Mock()
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection = Mock()
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Build and execute query
        builder = QueryBuilder(test_model, mock_weaviate_client)
        results = (builder
                   .filter(category="tech", published=True)
                   .hybrid("machine learning", alpha=0.7)
                   .limit(10)
                   .all())
        
        # Verify results
        assert len(results) == 3
        # Results can be dicts or model instances
        assert all(isinstance(r, (dict, test_model)) or hasattr(r, 'title') for r in results)

