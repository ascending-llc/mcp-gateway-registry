"""
Tests for CollectionManager enhancements.
"""

import pytest
from unittest.mock import Mock, MagicMock
from weaviate.classes.config import DataType
from db.managers.collection import CollectionManager
from db.core.exceptions import CollectionNotFound


class TestCollectionEnhancements:
    """Test enhanced CollectionManager features."""
    
    def test_add_property_success(self, mock_weaviate_client, test_model):
        """Test adding property to collection."""
        manager = CollectionManager(mock_weaviate_client)
        
        # Mock collection
        mock_collection = Mock()
        mock_collection.config.add_property = Mock()
        
        mock_conn = Mock()
        mock_conn.client.collections.exists = Mock(return_value=True)
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Add property
        result = manager.add_property(
            test_model,
            "featured",
            DataType.BOOL,
            description="Is featured"
        )
        
        assert result is True
        mock_collection.config.add_property.assert_called_once()
    
    def test_add_property_collection_not_found(self, mock_weaviate_client, test_model):
        """Test add_property raises error if collection doesn't exist."""
        manager = CollectionManager(mock_weaviate_client)
        
        # Mock collection doesn't exist
        mock_conn = Mock()
        mock_conn.client.collections.exists = Mock(return_value=False)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Should raise
        with pytest.raises(CollectionNotFound):
            manager.add_property(
                test_model,
                "new_prop",
                DataType.TEXT
            )
    
    def test_list_all_collections(self, mock_weaviate_client):
        """Test listing all collections."""
        manager = CollectionManager(mock_weaviate_client)
        
        # Mock collections
        mock_col1 = Mock()
        mock_col1.name = "Articles"
        mock_col2 = Mock()
        mock_col2.name = "Products"
        
        mock_conn = Mock()
        mock_conn.client.collections.list_all = Mock(return_value=[mock_col1, mock_col2])
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # List collections
        collections = manager.list_all_collections()
        
        assert len(collections) == 2
        assert "Articles" in collections
        assert "Products" in collections
    
    def test_get_collection_stats(self, mock_weaviate_client, test_model):
        """Test get_collection_stats."""
        manager = CollectionManager(mock_weaviate_client)
        
        # Mock aggregation result
        mock_agg_result = Mock()
        mock_agg_result.total_count = 1000
        
        mock_collection = Mock()
        mock_collection.aggregate.over_all = Mock(return_value=mock_agg_result)
        mock_collection.config.get = Mock(return_value=Mock(
            properties=[Mock(name="title"), Mock(name="content")],
            vector_config={}
        ))
        
        mock_conn = Mock()
        mock_conn.client.collections.exists = Mock(return_value=True)
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        stats = manager.get_collection_stats(test_model)
        
        assert stats is not None
        assert stats['object_count'] == 1000

