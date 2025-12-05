"""
Tests for UnifiedSearchInterface.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from db.search.unified import (
    UnifiedSearchInterface,
    get_search_interface,
    set_search_interface,
    search_model,
    search_collection
)
from db.search.query_builder import QueryBuilder


class TestUnifiedSearchInterface:
    """Test UnifiedSearchInterface."""
    
    def test_initialization_with_client(self, mock_weaviate_client):
        """Test initialization with provided client."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        assert search.client == mock_weaviate_client
    
    def test_initialization_without_client(self):
        """Test initialization without client uses registry."""
        with patch('db.core.registry.get_weaviate_client') as mock_get:
            mock_client = Mock()
            mock_get.return_value = mock_client
            
            search = UnifiedSearchInterface()
            
            assert search.client == mock_client
            mock_get.assert_called_once()
    
    def test_model_method(self, mock_weaviate_client, test_model):
        """Test model() method returns QueryBuilder."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        builder = search.model(test_model)
        
        assert isinstance(builder, QueryBuilder)
        assert builder.state.collection_name == "TestArticles"
    
    def test_collection_method(self, mock_weaviate_client):
        """Test collection() method returns QueryBuilder."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        builder = search.collection("Articles")
        
        assert isinstance(builder, QueryBuilder)
        assert builder.state.collection_name == "Articles"
    
    def test_across_method(self, mock_weaviate_client):
        """Test across() method for cross-collection search."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        builder = search.across(["Articles", "Documents", "Notes"])
        
        assert isinstance(builder, QueryBuilder)
        assert builder.state.collection_names == ["Articles", "Documents", "Notes"]
    
    def test_bm25_convenience_method(self, mock_weaviate_client, test_model):
        """Test BM25 convenience method."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        with patch.object(QueryBuilder, 'all', return_value=[]):
            results = search.bm25(test_model, "test query", limit=5)
            
            assert isinstance(results, list)
    
    def test_near_text_convenience_method(self, mock_weaviate_client):
        """Test near_text convenience method."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        with patch.object(QueryBuilder, 'all', return_value=[]):
            results = search.near_text("Articles", "semantic query", limit=10)
            
            assert isinstance(results, list)
    
    def test_hybrid_convenience_method(self, mock_weaviate_client, test_model):
        """Test hybrid convenience method."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        with patch.object(QueryBuilder, 'all', return_value=[]):
            results = search.hybrid(test_model, "query", alpha=0.7, limit=10)
            
            assert isinstance(results, list)
    
    def test_fuzzy_convenience_method(self, mock_weaviate_client):
        """Test fuzzy convenience method."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        with patch.object(QueryBuilder, 'all', return_value=[]):
            results = search.fuzzy("Articles", "typo query", limit=5)
            
            assert isinstance(results, list)
    
    def test_collection_exists(self, mock_weaviate_client):
        """Test collection_exists method."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        # Mock exists check
        mock_conn = MagicMock()
        mock_conn.client.collections.exists = MagicMock(return_value=True)
        mock_weaviate_client.managed_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = MagicMock(return_value=None)
        
        exists = search.collection_exists("Articles")
        
        assert exists is True
    
    def test_collection_info(self, mock_weaviate_client):
        """Test collection_info method."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        # Mock collection info
        mock_property = MagicMock()
        mock_property.name = "title"
        
        mock_config = MagicMock()
        mock_config.properties = [mock_property]
        
        mock_collection = MagicMock()
        mock_collection.config.get = MagicMock(return_value=mock_config)
        
        mock_conn = MagicMock()
        mock_conn.client.collections.exists = MagicMock(return_value=True)
        mock_conn.client.collections.get = MagicMock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = MagicMock(return_value=None)
        
        info = search.collection_info("Articles")
        
        assert info is not None
        assert info['name'] == "Articles"
        assert 'properties' in info
    
    def test_list_collections(self, mock_weaviate_client):
        """Test list_collections method."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        # Mock collection list
        mock_col1 = MagicMock()
        mock_col1.name = "Articles"
        mock_col2 = MagicMock()
        mock_col2.name = "Documents"
        
        mock_conn = MagicMock()
        mock_conn.client.collections.list_all = MagicMock(return_value=[mock_col1, mock_col2])
        mock_weaviate_client.managed_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = MagicMock(return_value=None)
        
        collections = search.list_collections()
        
        assert len(collections) == 2
        assert "Articles" in collections
        assert "Documents" in collections


class TestGlobalSearchInterface:
    """Test global search interface functions."""
    
    def test_get_search_interface_creates_instance(self, mock_weaviate_client):
        """Test that get_search_interface creates an instance."""
        set_search_interface(None)
        
        with patch('db.core.registry.get_weaviate_client', return_value=mock_weaviate_client):
            search = get_search_interface()
            
            assert search is not None
            assert isinstance(search, UnifiedSearchInterface)
    
    def test_get_search_interface_returns_same_instance(self, mock_weaviate_client):
        """Test that get_search_interface returns same instance."""
        set_search_interface(None)
        
        with patch('db.core.registry.get_weaviate_client', return_value=mock_weaviate_client):
            search1 = get_search_interface()
            search2 = get_search_interface()
            
            assert search1 is search2
    
    def test_set_search_interface(self, mock_weaviate_client):
        """Test setting custom search interface."""
        custom_search = UnifiedSearchInterface(mock_weaviate_client)
        set_search_interface(custom_search)
        
        retrieved = get_search_interface()
        
        assert retrieved is custom_search
    
    def test_search_model_convenience(self, mock_weaviate_client, test_model):
        """Test search_model convenience function."""
        set_search_interface(None)
        
        with patch('db.core.registry.get_weaviate_client', return_value=mock_weaviate_client):
            builder = search_model(test_model)
            
            assert isinstance(builder, QueryBuilder)
            assert builder.state.collection_name == "TestArticles"
    
    def test_search_collection_convenience(self, mock_weaviate_client):
        """Test search_collection convenience function."""
        set_search_interface(None)
        
        with patch('db.core.registry.get_weaviate_client', return_value=mock_weaviate_client):
            builder = search_collection("Articles")
            
            assert isinstance(builder, QueryBuilder)
            assert builder.state.collection_name == "Articles"


class TestUnifiedSearchIntegration:
    """Integration tests for UnifiedSearchInterface."""
    
    def test_end_to_end_model_search(self, mock_weaviate_client, test_model, sample_articles_data):
        """Test end-to-end model-based search."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        # Mock the response
        mock_response = Mock()
        mock_response.objects = []
        for data in sample_articles_data:
            mock_obj = Mock()
            mock_obj.uuid = data['id']
            mock_obj.properties = {k: v for k, v in data.items() if k != 'id'}
            mock_obj.metadata = Mock()
            mock_obj.metadata.distance = 0.1
            mock_response.objects.append(mock_obj)
        
        mock_collection = Mock()
        mock_collection.query.hybrid = Mock(return_value=mock_response)
        
        mock_conn = Mock()
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Execute search
        results = search.hybrid(test_model, "machine learning", alpha=0.7, limit=10)
        
        assert len(results) == 3
    
    def test_end_to_end_collection_search(self, mock_weaviate_client):
        """Test end-to-end collection-based search."""
        search = UnifiedSearchInterface(mock_weaviate_client)
        
        # Mock response
        mock_response = Mock()
        mock_response.objects = []
        
        mock_collection = Mock()
        mock_collection.query.bm25 = Mock(return_value=mock_response)
        
        mock_conn = Mock()
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Execute search
        results = search.bm25("Articles", "python", limit=5)
        
        assert isinstance(results, list)

