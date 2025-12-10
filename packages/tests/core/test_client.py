"""
Tests for WeaviateClient.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from db.core.client import WeaviateClient, ManagedConnection
from db.core.config import ConnectionConfig, TimeoutConfig
from db.core.providers import BedrockProvider
from db.core.exceptions import ConnectionException


class TestWeaviateClient:
    """Test WeaviateClient class."""
    
    def test_initialization_with_defaults(self, monkeypatch):
        """Test client initialization with default configs."""
        # Mock environment
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-key")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
        monkeypatch.setenv("EMBEDDINGS_PROVIDER", "bedrock")
        
        # Mock weaviate.connect_to_local
        with patch('db.core.client.weaviate.connect_to_local') as mock_connect:
            mock_client = MagicMock()
            mock_connect.return_value = mock_client
            
            client = WeaviateClient()
            
            # Should use defaults from environment
            assert client.connection.host == "127.0.0.1"
            assert client.connection.port == 8099
            assert isinstance(client.provider, BedrockProvider)
    
    def test_initialization_with_custom_config(self):
        """Test client initialization with custom configs."""
        connection = ConnectionConfig(host="custom-host", port=7777)
        provider = BedrockProvider("key", "secret")
        timeouts = TimeoutConfig(query=120)
        
        with patch('db.core.client.weaviate.connect_to_local') as mock_connect:
            mock_connect.return_value = MagicMock()
            
            client = WeaviateClient(
                connection=connection,
                provider=provider,
                timeouts=timeouts
            )
            
            assert client.connection.host == "custom-host"
            assert client.connection.port == 7777
            assert client.provider == provider
            assert client.timeouts.query == 120
    
    def test_is_ready_when_connected(self):
        """Test is_ready returns True when connected."""
        with patch('db.core.client.weaviate.connect_to_local') as mock_connect:
            mock_client = MagicMock()
            mock_client.is_connected.return_value = True
            mock_connect.return_value = mock_client
            
            # Mock env vars
            with patch.dict('os.environ', {
                'AWS_ACCESS_KEY_ID': 'key',
                'AWS_SECRET_ACCESS_KEY': 'secret'
            }):
                client = WeaviateClient()
                
                assert client.is_ready() is True
    
    def test_is_ready_when_not_connected(self):
        """Test is_ready returns False when not connected."""
        with patch('db.core.client.weaviate.connect_to_local') as mock_connect:
            mock_client = MagicMock()
            mock_client.is_connected.return_value = False
            mock_connect.return_value = mock_client
            
            with patch.dict('os.environ', {
                'AWS_ACCESS_KEY_ID': 'key',
                'AWS_SECRET_ACCESS_KEY': 'secret'
            }):
                client = WeaviateClient()
                
                assert client.is_ready() is False
    
    def test_ping_success(self):
        """Test ping returns True when server responds."""
        with patch('db.core.client.weaviate.connect_to_local') as mock_connect:
            mock_client = MagicMock()
            mock_client.is_connected.return_value = True
            mock_client.collections.list_all.return_value = []
            mock_connect.return_value = mock_client
            
            with patch.dict('os.environ', {
                'AWS_ACCESS_KEY_ID': 'key',
                'AWS_SECRET_ACCESS_KEY': 'secret'
            }):
                client = WeaviateClient()
                
                # Mock managed_connection
                with patch.object(client, 'ensure_connection'):
                    # Ping should succeed
                    result = client.ping()
                    assert result is True
    
    def test_close(self):
        """Test closing client."""
        with patch('db.core.client.weaviate.connect_to_local') as mock_connect:
            mock_client = MagicMock()
            mock_client.is_connected.return_value = True
            mock_connect.return_value = mock_client
            
            with patch.dict('os.environ', {
                'AWS_ACCESS_KEY_ID': 'key',
                'AWS_SECRET_ACCESS_KEY': 'secret'
            }):
                client = WeaviateClient()
                client.close()
                
                # Should have called close
                mock_client.close.assert_called_once()


class TestManagedConnection:
    """Test ManagedConnection context manager."""
    
    def test_context_manager_sync(self):
        """Test synchronous context manager."""
        with patch('db.core.client.weaviate.connect_to_local') as mock_connect:
            mock_client = MagicMock()
            mock_client.is_connected.return_value = False
            mock_connect.return_value = mock_client
            
            with patch.dict('os.environ', {
                'AWS_ACCESS_KEY_ID': 'key',
                'AWS_SECRET_ACCESS_KEY': 'secret'
            }):
                client = WeaviateClient()
                
                # Use managed connection
                with client.managed_connection() as conn:
                    assert conn == client
                
                # Connection should be closed if we opened it
                # (tested indirectly through ensure_connection call)
