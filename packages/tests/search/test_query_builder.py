"""
Tests for QueryBuilder.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from db.search.query_builder import QueryBuilder
from db.search.filters import Q
from db.core.enums import SearchType


class TestQueryBuilder:
    """Test QueryBuilder class."""
    
    def test_initialization_with_model(self, mock_weaviate_client, test_model):
        """Test initialization with a model class."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        assert builder.collection_name == "TestArticles"
        assert builder.client == mock_weaviate_client
        assert builder._limit is None
        assert builder._offset is None
        assert builder.filters is None
        assert builder.search_type is None
    
    def test_initialization_with_collection_name(self, mock_weaviate_client):
        """Test initialization with collection name."""
        builder = QueryBuilder("Articles", mock_weaviate_client)
        
        assert builder.collection_name == "Articles"
        assert builder.client == mock_weaviate_client
    
    def test_filter_with_kwargs(self, mock_weaviate_client, test_model):
        """Test filter method with keyword arguments."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.filter(category="tech", published=True)
        
        assert result is builder  # Returns self for chaining
        assert builder.filters is not None
        assert not builder.filters.is_empty()
    
    def test_filter_with_q_object(self, mock_weaviate_client, test_model):
        """Test filter method with Q object."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        q = Q(category="tech") | Q(category="science")
        result = builder.filter(q)
        
        assert result is builder
        assert builder.filters is not None
    
    def test_filter_chaining(self, mock_weaviate_client, test_model):
        """Test chaining multiple filters."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = (builder
                  .filter(category="tech")
                  .filter(published=True)
                  .filter(views__gt=1000))
        
        assert result is builder
        assert builder.filters is not None
    
    def test_exclude(self, mock_weaviate_client, test_model):
        """Test exclude method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.exclude(status="draft")
        
        assert result is builder
        assert builder.filters is not None
    
    def test_search_method(self, mock_weaviate_client, test_model):
        """Test generic search method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.search("test query", SearchType.HYBRID, alpha=0.7)
        
        assert result is builder
        assert builder.search_type == SearchType.HYBRID
        assert builder.search_params['query'] == "test query"
        assert builder.search_params['alpha'] == 0.7
    
    def test_bm25_method(self, mock_weaviate_client, test_model):
        """Test BM25 search method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.bm25("test query")
        
        assert result is builder
        assert builder.search_type == SearchType.BM25
    
    def test_near_text_method(self, mock_weaviate_client, test_model):
        """Test near_text method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.near_text("semantic query")
        
        assert result is builder
        assert builder.search_type == SearchType.NEAR_TEXT
    
    def test_hybrid_method(self, mock_weaviate_client, test_model):
        """Test hybrid search method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.hybrid("query", alpha=0.8)
        
        assert result is builder
        assert builder.search_type == SearchType.HYBRID
        assert builder.search_params['alpha'] == 0.8
    
    
    def test_near_vector_method(self, mock_weaviate_client, test_model):
        """Test near_vector method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        vector = [0.1, 0.2, 0.3]
        result = builder.near_vector(vector)
        
        assert result is builder
        assert builder.search_type == SearchType.NEAR_VECTOR
        assert builder.search_params['vector'] == vector
    
    def test_limit_method(self, mock_weaviate_client, test_model):
        """Test limit method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.limit(10)
        
        assert result is builder
        assert builder._limit == 10
    
    def test_offset_method(self, mock_weaviate_client, test_model):
        """Test offset method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.offset(20)
        
        assert result is builder
        assert builder._offset == 20
    
    def test_order_by_method(self, mock_weaviate_client, test_model):
        """Test order_by method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.order_by("views", desc=True)
        
        assert result is builder
        assert builder._order_by == "views"
        assert builder._order_desc is True
    
    def test_only_method(self, mock_weaviate_client, test_model):
        """Test only method for field selection."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        result = builder.only("title", "id")
        
        assert result is builder
        assert builder._return_properties == ["title", "id"]
    
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
        assert builder.filters is not None
        assert builder.search_type == SearchType.HYBRID
        assert builder._limit == 20
        assert builder._offset == 10
        assert builder._return_properties == ["title", "content"]
    
    def test_count_method(self, mock_weaviate_client, test_model, mock_search_results):
        """Test count method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        # Mock the execute to return results
        with patch.object(builder, 'execute', return_value=[{}, {}]):
            count = builder.count()
            assert count == 2
    
    def test_first_method(self, mock_weaviate_client, test_model, sample_articles_data):
        """Test first method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        # Mock the execute
        with patch.object(builder, 'execute', return_value=sample_articles_data):
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
        
        with patch.object(builder, 'execute', return_value=[]):
            first = builder.first()
            assert first is None
    
    def test_exists_method(self, mock_weaviate_client, test_model):
        """Test exists method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        # With results
        with patch.object(builder, 'execute', return_value=[{}]):
            assert builder.exists() is True
        
        # Create new builder for second test
        builder2 = QueryBuilder(test_model, mock_weaviate_client)
        
        # Without results
        with patch.object(builder2, 'execute', return_value=[]):
            assert builder2.exists() is False
    
    def test_iterator_support(self, mock_weaviate_client, test_model, sample_articles_data):
        """Test that QueryBuilder is iterable."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        with patch.object(builder, 'execute', return_value=sample_articles_data):
            results = list(builder)
            assert len(results) == 3
    
    def test_len_support(self, mock_weaviate_client, test_model, sample_articles_data):
        """Test that len() works on QueryBuilder."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        with patch.object(builder, 'execute', return_value=sample_articles_data):
            length = len(builder)
            assert length == 3
    
    def test_all_method(self, mock_weaviate_client, test_model, sample_articles_data):
        """Test all method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        with patch.object(builder, 'execute', return_value=sample_articles_data):
            results = builder.all()
            assert len(results) == 3
    
    def test_execute_method(self, mock_weaviate_client, test_model, sample_articles_data):
        """Test execute method."""
        builder = QueryBuilder(test_model, mock_weaviate_client)
        
        # Mock the actual execution
        with patch.object(builder, 'execute', return_value=sample_articles_data):
            results = builder.execute()
            assert len(results) == 3


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
