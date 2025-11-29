import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ConnectionConfig:
    """
    Weaviate connection configuration.
    
    Encapsulates all connection-related parameters.
    """
    host: str = "127.0.0.1"
    port: int = 8099
    api_key: Optional[str] = None
    pool_connections: int = 10
    pool_maxsize: int = 10
    
    @classmethod
    def from_env(cls) -> 'ConnectionConfig':
        """
        Create configuration from environment variables.
        
        Environment variables:
            WEAVIATE_HOST: Weaviate host
            WEAVIATE_PORT: Weaviate port
            WEAVIATE_API_KEY: API key
        
        Returns:
            ConnectionConfig instance
        """
        return cls(
            host=os.getenv("WEAVIATE_HOST", "127.0.0.1"),
            port=int(os.getenv("WEAVIATE_PORT", "8099")),
            api_key=os.getenv("WEAVIATE_API_KEY"),
            pool_connections=int(os.getenv("WEAVIATE_POOL_CONNECTIONS", "10")),
            pool_maxsize=int(os.getenv("WEAVIATE_POOL_MAXSIZE", "10"))
        )
    
    @classmethod
    def from_dict(cls, config: dict) -> 'ConnectionConfig':
        """Create configuration from dictionary."""
        return cls(**config)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'host': self.host,
            'port': self.port,
            'api_key': self.api_key,
            'pool_connections': self.pool_connections,
            'pool_maxsize': self.pool_maxsize
        }


@dataclass
class TimeoutConfig:
    """
    Timeout configuration for Weaviate operations.
    
    All timeouts are in seconds.
    """
    init: int = 10
    query: int = 60
    insert: int = 60
    
    @classmethod
    def from_env(cls) -> 'TimeoutConfig':
        """
        Create configuration from environment variables.
        
        Environment variables:
            WEAVIATE_INIT_TIMEOUT: Initialization timeout
            WEAVIATE_QUERY_TIMEOUT: Query timeout
            WEAVIATE_INSERT_TIMEOUT: Insert timeout
        
        Returns:
            TimeoutConfig instance
        """
        return cls(
            init=int(os.getenv("WEAVIATE_INIT_TIMEOUT", "10")),
            query=int(os.getenv("WEAVIATE_QUERY_TIMEOUT", "60")),
            insert=int(os.getenv("WEAVIATE_INSERT_TIMEOUT", "60"))
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'init': self.init,
            'query': self.query,
            'insert': self.insert
        }

