"""
Unit tests for FAISS search service.
"""
import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path
import numpy as np

from registry.search.service import FaissService, faiss_service


@pytest.mark.unit
@pytest.mark.search
class TestFaissService:
    """Test suite for FAISS search service."""

    @pytest.fixture
    def faiss_service_instance(self):
        """Create a fresh FAISS service for testing."""
        return FaissService()

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        with patch('registry.search.service.settings') as mock_settings:
            # Use actual Path objects for proper path operations
            mock_settings.servers_dir = Path("/tmp/test_servers")
            mock_settings.container_registry_dir = Path("/tmp/test_registry")
            mock_settings.embeddings_model_dir = Path("/tmp/test_model")
            mock_settings.embeddings_model_name = "all-MiniLM-L6-v2"
            mock_settings.embeddings_model_dimensions = 384
            mock_settings.faiss_index_path = Path("/tmp/test_index.faiss")
            mock_settings.faiss_metadata_path = Path("/tmp/test_metadata.json")
            
            # Mock the mkdir calls to avoid actual directory creation
            with patch.object(Path, 'mkdir'):
                yield mock_settings

    def test_get_text_for_embedding(self, faiss_service_instance):
        """Test text preparation for embedding."""
        server_info = {
            "server_name": "Test Server",
            "description": "A test server for demonstration",
            "tags": ["test", "demo", "example"]
        }
        
        result = faiss_service_instance._get_text_for_embedding(server_info)
        
        expected = "Name: Test Server\nDescription: A test server for demonstration\nTags: test, demo, example"
        assert result == expected

    def test_get_text_for_embedding_empty_data(self, faiss_service_instance):
        """Test text preparation with empty/missing data."""
        server_info = {}
        
        result = faiss_service_instance._get_text_for_embedding(server_info)
        
        expected = "Name: \nDescription: \nTags: "
        assert result == expected

    def test_initialize_new_index(self, faiss_service_instance, mock_settings):
        """Test initialization of a new FAISS index."""
        faiss_service_instance._initialize_new_index()
        
        assert faiss_service_instance.faiss_index is not None
        assert faiss_service_instance.metadata_store == {}
        assert faiss_service_instance.next_id_counter == 0

    @pytest.mark.asyncio
    async def test_initialize_success(self, faiss_service_instance, mock_settings):
        """Test successful service initialization."""
        with patch.object(faiss_service_instance, '_load_embedding_model') as mock_load_model, \
             patch.object(faiss_service_instance, '_load_faiss_data') as mock_load_data:
            
            mock_load_model.return_value = None
            mock_load_data.return_value = None
            
            await faiss_service_instance.initialize()
            
            mock_load_model.assert_called_once()
            mock_load_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_embedding_model_local_exists(self, faiss_service_instance, mock_settings):
        """Test loading embedding model from local path when it exists."""
        with patch('registry.search.service.SentenceTransformer') as mock_transformer, \
             patch('os.environ') as mock_env, \
             patch.object(Path, 'exists') as mock_exists, \
             patch.object(Path, 'iterdir') as mock_iterdir:
            
            # Mock local model exists
            mock_exists.return_value = True
            mock_iterdir.return_value = [Path("model.bin")]
            
            mock_transformer_instance = Mock()
            mock_transformer.return_value = mock_transformer_instance
            
            await faiss_service_instance._load_embedding_model()
            
            mock_transformer.assert_called_once_with(str(mock_settings.embeddings_model_dir))
            assert faiss_service_instance.embedding_model == mock_transformer_instance

    @pytest.mark.asyncio
    async def test_load_embedding_model_download_from_hf(self, faiss_service_instance, mock_settings):
        """Test downloading embedding model from Hugging Face."""
        with patch('registry.search.service.SentenceTransformer') as mock_transformer, \
             patch('os.environ') as mock_env, \
             patch.object(Path, 'exists') as mock_exists:
            
            # Mock local model doesn't exist
            mock_exists.return_value = False
            
            mock_transformer_instance = Mock()
            mock_transformer.return_value = mock_transformer_instance
            
            await faiss_service_instance._load_embedding_model()
            
            mock_transformer.assert_called_once_with(str(mock_settings.embeddings_model_name))
            assert faiss_service_instance.embedding_model == mock_transformer_instance

    @pytest.mark.asyncio
    async def test_load_embedding_model_exception(self, faiss_service_instance, mock_settings):
        """Test handling exception during model loading."""
        with patch('registry.search.service.SentenceTransformer') as mock_transformer:
            mock_transformer.side_effect = Exception("Model load failed")
            
            await faiss_service_instance._load_embedding_model()
            
            assert faiss_service_instance.embedding_model is None

    @pytest.mark.asyncio
    async def test_load_faiss_data_existing_files(self, faiss_service_instance, mock_settings):
        """Test loading existing FAISS index and metadata."""
        with patch('registry.search.service.faiss') as mock_faiss, \
             patch('builtins.open', create=True) as mock_open, \
             patch.object(Path, 'exists') as mock_exists:
            
            # Mock files exist
            mock_exists.return_value = True
            
            # Mock FAISS index
            mock_index = Mock()
            mock_index.d = 384  # Matching dimension
            mock_faiss.read_index.return_value = mock_index
            
            # Mock metadata file
            mock_metadata = {
                "metadata": {"service1": {"id": 1, "text": "test"}},
                "next_id": 2
            }
            mock_file = Mock()
            mock_file.read.return_value = json.dumps(mock_metadata)
            mock_open.return_value.__enter__.return_value = mock_file
            
            with patch('json.load') as mock_json_load:
                mock_json_load.return_value = mock_metadata
                
                await faiss_service_instance._load_faiss_data()
            
            assert faiss_service_instance.faiss_index == mock_index
            assert faiss_service_instance.metadata_store == mock_metadata["metadata"]
            assert faiss_service_instance.next_id_counter == 2

    @pytest.mark.asyncio
    async def test_load_faiss_data_dimension_mismatch(self, faiss_service_instance, mock_settings):
        """Test handling dimension mismatch in loaded index."""
        with patch('registry.search.service.faiss') as mock_faiss, \
             patch('builtins.open', create=True) as mock_open, \
             patch.object(faiss_service_instance, '_initialize_new_index') as mock_init, \
             patch.object(Path, 'exists') as mock_exists:
            
            # Mock files exist
            mock_exists.return_value = True
            
            # Mock FAISS index with wrong dimension
            mock_index = Mock()
            mock_index.d = 256  # Wrong dimension
            mock_faiss.read_index.return_value = mock_index
            
            # Mock metadata file
            mock_metadata = {"metadata": {}, "next_id": 0}
            with patch('json.load') as mock_json_load:
                mock_json_load.return_value = mock_metadata
                
                await faiss_service_instance._load_faiss_data()
            
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_faiss_data_no_files(self, faiss_service_instance, mock_settings):
        """Test initialization when no existing files found."""
        with patch.object(faiss_service_instance, '_initialize_new_index') as mock_init, \
             patch.object(Path, 'exists') as mock_exists:
            # Mock files don't exist
            mock_exists.return_value = False
            
            await faiss_service_instance._load_faiss_data()
            
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_data_success(self, faiss_service_instance, mock_settings):
        """Test successful data saving."""
        with patch('registry.search.service.faiss') as mock_faiss, \
             patch('builtins.open', create=True) as mock_open:
            
            # Setup service state
            mock_index = Mock()
            mock_index.ntotal = 5
            faiss_service_instance.faiss_index = mock_index
            faiss_service_instance.metadata_store = {"test": "data"}
            faiss_service_instance.next_id_counter = 10
            
            mock_file = Mock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            await faiss_service_instance.save_data()
            
            mock_faiss.write_index.assert_called_once()
            mock_file.write.assert_called()

    @pytest.mark.asyncio
    async def test_save_data_no_index(self, faiss_service_instance, mock_settings):
        """Test save_data when no index is initialized."""
        faiss_service_instance.faiss_index = None
        
        # Should return early without error
        await faiss_service_instance.save_data()

    @pytest.mark.asyncio
    async def test_save_data_exception(self, faiss_service_instance, mock_settings):
        """Test handling exception during save."""
        with patch('registry.search.service.faiss') as mock_faiss:
            mock_faiss.write_index.side_effect = Exception("Save failed")
            
            mock_index = Mock()
            faiss_service_instance.faiss_index = mock_index
            
            # Should not raise exception
            await faiss_service_instance.save_data()

    @pytest.mark.asyncio
    async def test_add_or_update_service_not_initialized(self, faiss_service_instance):
        """Test add_or_update_service when service not initialized."""
        faiss_service_instance.embedding_model = None
        faiss_service_instance.faiss_index = None
        
        server_info = {"server_name": "test", "description": "test"}
        
        # Should return early without error
        await faiss_service_instance.add_or_update_service("test_path", server_info)

    @pytest.mark.asyncio
    async def test_add_or_update_service_new_service(self, faiss_service_instance):
        """Test adding a completely new service."""
        with patch('asyncio.to_thread') as mock_to_thread:
            # Setup mocks
            mock_model = Mock()
            mock_embedding = np.array([[0.1, 0.2, 0.3]])
            mock_model.encode.return_value = mock_embedding
            mock_to_thread.return_value = mock_embedding
            
            mock_index = Mock()
            mock_index.add_with_ids = Mock()
            
            faiss_service_instance.embedding_model = mock_model
            faiss_service_instance.faiss_index = mock_index
            faiss_service_instance.metadata_store = {}
            faiss_service_instance.next_id_counter = 0
            
            server_info = {
                "server_name": "New Server",
                "description": "A new test server",
                "tags": ["new", "test"]
            }
            
            # Mock asyncio.to_thread to handle both encode and save_data calls
            mock_to_thread.side_effect = lambda func, *args: mock_embedding if args else AsyncMock()
            
            await faiss_service_instance.add_or_update_service("new_service", server_info, True)
            
            # Verify service was added
            assert "new_service" in faiss_service_instance.metadata_store
            assert faiss_service_instance.metadata_store["new_service"]["id"] == 0
            assert faiss_service_instance.next_id_counter == 1
            mock_index.add_with_ids.assert_called_once()
            # Verify asyncio.to_thread was called (for both encode and save_data)
            assert mock_to_thread.call_count >= 2

    @pytest.mark.asyncio
    async def test_add_or_update_service_existing_no_change(self, faiss_service_instance):
        """Test updating existing service with no embedding change."""
        # Setup existing service
        existing_text = "Name: Test Server\nDescription: Test description\nTags: test"
        faiss_service_instance.metadata_store = {
            "existing_service": {
                "id": 1,
                "text_for_embedding": existing_text,
                "full_server_info": {"server_name": "Test Server", "is_enabled": False}
            }
        }
        
        mock_model = Mock()
        mock_index = Mock()
        faiss_service_instance.embedding_model = mock_model
        faiss_service_instance.faiss_index = mock_index
        
        server_info = {
            "server_name": "Test Server",
            "description": "Test description",
            "tags": ["test"]
        }
        
        with patch.object(faiss_service_instance, 'save_data') as mock_save:
            await faiss_service_instance.add_or_update_service("existing_service", server_info, True)
        
        # Should update metadata but not re-embed
        mock_save.assert_called_once()
        assert faiss_service_instance.metadata_store["existing_service"]["full_server_info"]["is_enabled"] is True

    @pytest.mark.asyncio
    async def test_add_or_update_service_encoding_error(self, faiss_service_instance):
        """Test handling encoding error."""
        with patch('asyncio.to_thread') as mock_to_thread:
            mock_to_thread.side_effect = Exception("Encoding failed")
            
            mock_model = Mock()
            mock_index = Mock()
            
            faiss_service_instance.embedding_model = mock_model
            faiss_service_instance.faiss_index = mock_index
            faiss_service_instance.metadata_store = {}
            faiss_service_instance.next_id_counter = 0
            
            server_info = {"server_name": "test", "description": "test"}
            
            # Should not raise exception
            await faiss_service_instance.add_or_update_service("test_service", server_info)

    def test_global_service_instance(self):
        """Test that the global service instance is accessible."""
        from registry.search.service import faiss_service
        assert faiss_service is not None
        assert isinstance(faiss_service, FaissService) 