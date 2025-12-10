import logging
from typing import Optional
from .client import WeaviateClient
from .config import ConnectionConfig
from .providers import create_provider_from_env

logger = logging.getLogger(__name__)


class WeaviateClientRegistry:
    """Client registry, manages global Weaviate client instance"""

    _instance: Optional[WeaviateClient] = None

    @classmethod
    def initialize(cls, **client_kwargs) -> WeaviateClient:
        """
        Initialize global client
        
            **client_kwargs: Client initialization parameters
        Returns:
            WeaviateClient: Global client instance
        """
        if cls._instance is None:
            cls._instance = WeaviateClient(**client_kwargs)
        return cls._instance

    @classmethod
    def get_client(cls) -> WeaviateClient:
        """
        Get global client instance
        
        Returns:
            WeaviateClient: Global client instance
            
        Raises:
            RuntimeError: Client not initialized
        """
        if cls._instance is None:
            raise RuntimeError(
                "Weaviate client not initialized. "
                "Please call ClientRegistry.initialize() first."
            )
        return cls._instance

    @classmethod
    def close(cls):
        """Close global client connection"""
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None
            logger.info("Global Weaviate client closed")

    @classmethod
    def reset(cls):
        """Reset registry (mainly for testing)"""
        cls.close()

    @property
    def instance(self):
        return self._instance


def init_weaviate(connection: Optional[ConnectionConfig] = None, **kwargs) -> WeaviateClient:
    """
    Initialize Weaviate client with simplified interface.
    
    If connection is provided, creates provider internally from environment.
    Maintains backward compatibility with direct kwargs.
    
    Args:
        connection: Connection configuration (optional)
        **kwargs: Additional client initialization parameters
        
    Returns:
        WeaviateClient: Global client instance
    """
    # If connection is provided, we'll handle provider internally
    if connection is not None:
        # Create provider from environment internally
        provider = create_provider_from_env()
        client_kwargs = {
            'connection': connection,
            'provider': provider
        }
        client_kwargs.update(kwargs)
        return WeaviateClientRegistry.initialize(**client_kwargs)
    else:
        # Backward compatibility: pass all kwargs directly
        return WeaviateClientRegistry.initialize(**kwargs)


def get_weaviate_client() -> WeaviateClient:
    """
    Get singleton Weaviate client.
    
    Automatically initializes if not already done.
    
    Returns:
        WeaviateClient: Singleton client instance
    """
    if WeaviateClientRegistry._instance is None:
        WeaviateClientRegistry.initialize()
    return WeaviateClientRegistry._instance


def close_weaviate():
    """Close Weaviate connection"""
    WeaviateClientRegistry.close()
