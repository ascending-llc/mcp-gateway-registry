"""
Tests for configuration classes.
"""

import os
import pytest
from db.core.config import ConnectionConfig, TimeoutConfig


class TestConnectionConfig:
    """Test ConnectionConfig class."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = ConnectionConfig()
        
        assert config.host == "127.0.0.1"
        assert config.port == 8099
        assert config.api_key is None
        assert config.pool_connections == 10
        assert config.pool_maxsize == 10
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = ConnectionConfig(
            host="prod-server",
            port=80,
            api_key="secret-key",
            pool_connections=20,
            pool_maxsize=30
        )
        
        assert config.host == "prod-server"
        assert config.port == 80
        assert config.api_key == "secret-key"
        assert config.pool_connections == 20
        assert config.pool_maxsize == 30
    
    def test_from_env(self, monkeypatch):
        """Test creating config from environment variables."""
        monkeypatch.setenv("WEAVIATE_HOST", "test-host")
        monkeypatch.setenv("WEAVIATE_PORT", "9999")
        monkeypatch.setenv("WEAVIATE_API_KEY", "test-key")
        monkeypatch.setenv("WEAVIATE_POOL_CONNECTIONS", "15")
        
        config = ConnectionConfig.from_env()
        
        assert config.host == "test-host"
        assert config.port == 9999
        assert config.api_key == "test-key"
        assert config.pool_connections == 15
    
    def test_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            'host': 'dict-host',
            'port': 7777,
            'api_key': 'dict-key'
        }
        
        config = ConnectionConfig.from_dict(config_dict)
        
        assert config.host == "dict-host"
        assert config.port == 7777
        assert config.api_key == "dict-key"
    
    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = ConnectionConfig(host="test", port=8080)
        config_dict = config.to_dict()
        
        assert isinstance(config_dict, dict)
        assert config_dict['host'] == "test"
        assert config_dict['port'] == 8080


class TestTimeoutConfig:
    """Test TimeoutConfig class."""
    
    def test_default_values(self):
        """Test default timeout values."""
        config = TimeoutConfig()
        
        assert config.init == 10
        assert config.query == 60
        assert config.insert == 60
    
    def test_custom_values(self):
        """Test custom timeout values."""
        config = TimeoutConfig(init=20, query=120, insert=90)
        
        assert config.init == 20
        assert config.query == 120
        assert config.insert == 90
    
    def test_from_env(self, monkeypatch):
        """Test creating config from environment variables."""
        monkeypatch.setenv("WEAVIATE_INIT_TIMEOUT", "15")
        monkeypatch.setenv("WEAVIATE_QUERY_TIMEOUT", "100")
        monkeypatch.setenv("WEAVIATE_INSERT_TIMEOUT", "80")
        
        config = TimeoutConfig.from_env()
        
        assert config.init == 15
        assert config.query == 100
        assert config.insert == 80
    
    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = TimeoutConfig(init=5, query=30, insert=45)
        config_dict = config.to_dict()
        
        assert isinstance(config_dict, dict)
        assert config_dict['init'] == 5
        assert config_dict['query'] == 30
        assert config_dict['insert'] == 45

