"""
Tests for ObjectManager batch operations.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from db.managers.object import ObjectManager
from db.managers.batch import BatchResult
from db.core.exceptions import DoesNotExist, MultipleObjectsReturned


class TestSingleObjectOperations:
    """Test single object CRUD operations."""
    
    def test_create(self, mock_weaviate_client, test_model):
        """Test creating a single object."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        # Mock the save operation
        with patch.object(manager, 'save') as mock_save:
            mock_instance = test_model(title="Test")
            mock_save.return_value = mock_instance
            
            result = manager.create(title="Test", content="Content")
            
            mock_save.assert_called_once()
    
    def test_get_by_id_found(self, mock_weaviate_client, test_model):
        """Test get_by_id when object exists."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        # Mock the response
        mock_obj = Mock()
        mock_obj.uuid = "uuid-123"
        mock_obj.properties = {'title': 'Test Article', 'content': 'Content'}
        
        mock_collection = Mock()
        mock_collection.query.fetch_object_by_id = Mock(return_value=mock_obj)
        
        mock_conn = Mock()
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Get by ID
        result = manager.get_by_id("uuid-123")
        
        assert result is not None
        assert result.id == "uuid-123"
        mock_collection.query.fetch_object_by_id.assert_called_once_with("uuid-123")
    
    def test_get_by_id_not_found(self, mock_weaviate_client, test_model):
        """Test get_by_id raises DoesNotExist when not found."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        # Mock empty response
        mock_collection = Mock()
        mock_collection.query.fetch_object_by_id = Mock(return_value=None)
        
        mock_conn = Mock()
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Should raise DoesNotExist
        with pytest.raises(DoesNotExist) as exc_info:
            manager.get_by_id("nonexistent")
        
        assert exc_info.value.model_name == "TestArticle"
        assert exc_info.value.filters == {"id": "nonexistent"}
    
    def test_get_optimizes_to_get_by_id(self, mock_weaviate_client, test_model):
        """Test that get() uses get_by_id when only id provided."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        with patch.object(manager, 'get_by_id') as mock_get_by_id:
            mock_get_by_id.return_value = test_model()
            
            # Should use get_by_id
            manager.get(id="uuid-123")
            
            mock_get_by_id.assert_called_once_with("uuid-123")
    
    def test_get_uses_filter_for_other_fields(self, mock_weaviate_client, test_model):
        """Test that get() uses filter for non-id fields."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        with patch.object(manager, 'filter') as mock_filter:
            mock_builder = Mock()
            mock_builder.limit.return_value = mock_builder
            mock_builder.all.return_value = [test_model()]
            mock_filter.return_value = mock_builder
            
            # Should use filter
            manager.get(title="Test")
            
            mock_filter.assert_called_once_with(title="Test")
            mock_builder.limit.assert_called_once_with(2)


class TestBatchOperations:
    """Test batch operations."""
    
    def test_bulk_create_all_success(self, mock_weaviate_client, test_model):
        """Test bulk_create when all objects succeed."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        instances = [
            test_model(title=f"Article {i}") 
            for i in range(3)
        ]
        
        # Mock batch context
        mock_batch = Mock()
        mock_batch.failed_objects = []
        mock_batch.add_object = Mock()
        mock_batch.__enter__ = Mock(return_value=mock_batch)
        mock_batch.__exit__ = Mock(return_value=None)
        
        mock_collection = Mock()
        mock_collection.batch.fixed_size = Mock(return_value=mock_batch)
        
        mock_conn = Mock()
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Bulk create
        result = manager.bulk_create(instances)
        
        assert isinstance(result, BatchResult)
        assert result.total == 3
        assert result.successful == 3
        assert result.failed == 0
        assert result.is_complete_success
    
    def test_bulk_create_partial_failure(self, mock_weaviate_client, test_model):
        """Test bulk_create with some failures."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        instances = [test_model(title=f"Article {i}") for i in range(5)]
        
        # Mock partial failure
        failed_obj = Mock()
        failed_obj.uuid = "failed-uuid"
        failed_obj.message = "Validation error"
        
        mock_batch = Mock()
        mock_batch.failed_objects = [failed_obj]
        mock_batch.add_object = Mock()
        mock_batch.__enter__ = Mock(return_value=mock_batch)
        mock_batch.__exit__ = Mock(return_value=None)
        
        mock_collection = Mock()
        mock_collection.batch.fixed_size = Mock(return_value=mock_batch)
        
        mock_conn = Mock()
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        result = manager.bulk_create(instances)
        
        assert result.total == 5
        assert result.successful == 4
        assert result.failed == 1
        assert len(result.errors) == 1
        assert not result.is_complete_success
    
    def test_bulk_create_with_error_callback(self, mock_weaviate_client, test_model):
        """Test bulk_create calls error callback."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        instances = [test_model(title="Article")]
        
        # Mock failure
        failed_obj = Mock()
        failed_obj.uuid = "failed-uuid"
        failed_obj.message = "Error"
        
        mock_batch = Mock()
        mock_batch.failed_objects = [failed_obj]
        mock_batch.add_object = Mock()
        mock_batch.__enter__ = Mock(return_value=mock_batch)
        mock_batch.__exit__ = Mock(return_value=None)
        
        mock_collection = Mock()
        mock_collection.batch.fixed_size = Mock(return_value=mock_batch)
        
        mock_conn = Mock()
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Error callback
        error_callback = Mock()
        
        result = manager.bulk_create(instances, on_error=error_callback)
        
        # Callback should be called
        error_callback.assert_called_once()
        call_args = error_callback.call_args[0][0]
        assert 'uuid' in call_args
        assert 'message' in call_args
    
    def test_delete_where_success(self, mock_weaviate_client, test_model):
        """Test delete_where deletes matching objects."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        # Mock delete_many result
        mock_result = Mock()
        mock_result.deleted = 10
        
        mock_collection = Mock()
        mock_collection.data.delete_many = Mock(return_value=mock_result)
        
        mock_conn = Mock()
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Delete where
        count = manager.delete_where(status="draft")
        
        assert count == 10
        mock_collection.data.delete_many.assert_called_once()
    
    def test_delete_where_no_filters(self, mock_weaviate_client, test_model):
        """Test delete_where without filters returns 0."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        # Should return 0 without calling delete_many
        count = manager.delete_where()
        
        assert count == 0


class TestBulkImport:
    """Test bulk_import with progress tracking."""
    
    def test_bulk_import_with_progress(self, mock_weaviate_client, test_model):
        """Test bulk_import calls progress callback."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        data_list = [{'title': f'Article {i}'} for i in range(250)]
        
        # Mock batch
        mock_batch = Mock()
        mock_batch.failed_objects = []
        mock_batch.add_object = Mock()
        mock_batch.__enter__ = Mock(return_value=mock_batch)
        mock_batch.__exit__ = Mock(return_value=None)
        
        mock_collection = Mock()
        mock_collection.batch.fixed_size = Mock(return_value=mock_batch)
        
        mock_conn = Mock()
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Progress callback
        progress_callback = Mock()
        
        result = manager.bulk_import(data_list, on_progress=progress_callback)
        
        # Progress callback should be called multiple times
        assert progress_callback.call_count > 0
        
        # Final call should be (250, 250)
        final_call = progress_callback.call_args_list[-1]
        assert final_call == call(250, 250)
    
    def test_bulk_import_dynamic_mode(self, mock_weaviate_client, test_model):
        """Test bulk_import with dynamic batching."""
        manager = ObjectManager(test_model, mock_weaviate_client)
        
        data_list = [{'title': 'Article'}]
        
        # Mock dynamic batch
        mock_batch = Mock()
        mock_batch.failed_objects = []
        mock_batch.add_object = Mock()
        mock_batch.__enter__ = Mock(return_value=mock_batch)
        mock_batch.__exit__ = Mock(return_value=None)
        
        mock_collection = Mock()
        mock_collection.batch.dynamic = Mock(return_value=mock_batch)
        
        mock_conn = Mock()
        mock_conn.client.collections.get = Mock(return_value=mock_collection)
        mock_weaviate_client.managed_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_weaviate_client.managed_connection.return_value.__exit__ = Mock(return_value=None)
        
        # Use dynamic
        result = manager.bulk_import(data_list, use_dynamic=True)
        
        # Should call dynamic()
        mock_collection.batch.dynamic.assert_called_once()
        assert result.successful == 1

