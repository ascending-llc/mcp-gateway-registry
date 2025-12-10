import os
import time
import weaviate
import logging
from typing import Optional

from weaviate.auth import AuthApiKey
from weaviate.client import WeaviateClient as OriginalWeaviateClient
from weaviate.config import AdditionalConfig, ConnectionConfig as WeaviateConnectionConfig, Timeout

from .config import ConnectionConfig, TimeoutConfig
from .providers import EmbeddingsProvider, create_provider_from_env
from .exceptions import ConnectionException

logger = logging.getLogger(__name__)


class WeaviateClient:
    """
    Weaviate client with simplified configuration.
    
    Reduced from 17 parameters to 3 clean configuration objects:
    - ConnectionConfig: host, port, API key, connection pool
    - EmbeddingsProvider: authentication and vectorizer (strategy pattern)
    - TimeoutConfig: operation timeouts
    
    Example:
        # Simple initialization (from environment)
        client = WeaviateClient()
        
        # Custom configuration
        client = WeaviateClient(
            connection=ConnectionConfig(host="prod-server", port=80),
            provider=BedrockProvider.from_env()
        )
    """

    def __init__(
            self,
        connection: Optional[ConnectionConfig] = None,
        provider: Optional[EmbeddingsProvider] = None,
        timeouts: Optional[TimeoutConfig] = None
    ):
        """
        Initialize Weaviate client with configuration objects.

        Args:
            connection: Connection configuration (default: from environment)
            provider: Embeddings provider (default: from environment)
            timeouts: Timeout configuration (default: standard timeouts)
        """
        self.connection = connection or ConnectionConfig.from_env()
        self.provider = provider or create_provider_from_env()
        self.timeouts = timeouts or TimeoutConfig()
        
        self.client = self._create_client()
        
        logger.info(
            f"WeaviateClient initialized: {self.connection.host}:{self.connection.port}, "
            f"provider={self.provider.__class__.__name__}"
        )
    
    def _create_client(self) -> OriginalWeaviateClient:
        """
        Create underlying Weaviate client instance.

        Returns:
            Configured Weaviate client
            
        Raises:
            ConnectionFailed: If client creation fails
        """
        try:
            # Build Weaviate connection config
            conn_config = WeaviateConnectionConfig(
                session_pool_connections=self.connection.pool_connections,
                session_pool_maxsize=self.connection.pool_maxsize
            )
            
            # Create client
            client = weaviate.connect_to_local(
                host=self.connection.host,
                port=self.connection.port,
                auth_credentials=AuthApiKey(api_key=self.connection.api_key) if self.connection.api_key else None,
                headers=self.provider.get_headers(),
                additional_config=AdditionalConfig(
                    timeout=Timeout(
                        init=self.timeouts.init,
                        query=self.timeouts.query,
                        insert=self.timeouts.insert
                    ),
                    connection=conn_config
                )
            )
            
            logger.info("Weaviate client created successfully")
            return client
            
        except Exception as e:
            logger.error(f"Failed to create Weaviate client: {e}")
            raise ConnectionException(
                self.connection.host,
                self.connection.port,
                str(e)
            )
    
    def ensure_connection(self, max_retries: int = 10, retry_delay: float = 2.0) -> bool:
        """
        Ensure connection is established with retry logic.
        
        Args:
            max_retries: Maximum number of connection attempts
            retry_delay: Delay in seconds between retries

        Returns:
            bool: True if connection established, False otherwise
            
        Raises:
            ConnectionException: If connection fails after all retries
        """
        if self.client is None:
            raise RuntimeError("Weaviate client not initialized")
        
        last_exception = None
        was_connected = False
        
        for attempt in range(1, max_retries + 1):
            try:
                was_connected = self.client.is_connected()
                
                if not was_connected:
                    logger.info(f"Establishing connection (attempt {attempt}/{max_retries})...")
                    self.client.connect()
                    logger.info("✅ Connection established")
                else:
                    logger.debug("Already connected")
                
                return was_connected
                
            except Exception as e:
                last_exception = e
                
                if attempt < max_retries:
                    logger.warning(
                        f"Connection attempt {attempt}/{max_retries} failed: {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Connection failed after {max_retries} attempts")
        
        raise ConnectionException(
            self.connection.host,
            self.connection.port,
            f"Failed after {max_retries} attempts. Last error: {last_exception}"
        )

    def managed_connection(self, keep_alive: bool = False):
        """
        Context manager for automatic connection lifecycle management.
        
        Args:
            keep_alive: If True, connection persists after context exit

        Returns:
            ManagedConnection context manager
            
        Example:
            with client.managed_connection() as conn:
                result = conn.client.collections.get("Articles")
        """
        return ManagedConnection(self, keep_alive=keep_alive)

    def is_ready(self) -> bool:
        """
        Simple health check - verify client is connected and ready.
        
        Returns:
            True if client is ready, False otherwise
        """
        try:
            return self.client.is_connected() if self.client else False
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    def ping(self) -> bool:
        """
        Ping Weaviate server to verify connectivity.
        
        Performs a simple query to ensure server is responding.
        
        Returns:
            True if server responds, False otherwise
        """
        try:
            with self.managed_connection() as conn:
                # Simple operation to verify server is responding
                conn.client.collections.list_all()
                return True
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return False
    
    def close(self):
        """Close Weaviate client connection."""
        if self.client is not None:
            try:
                if self.client.is_connected():
                    self.client.close()
                    logger.info("Weaviate client connection closed")
                else:
                    logger.debug("Client already disconnected")
            except Exception as e:
                logger.error(f"Error closing client: {e}")


class ManagedConnection:
    """
    Context manager for Weaviate connection lifecycle.
    
    Automatically manages connection state:
    - On enter: Ensure connection is established
    - On exit: Close connection (unless keep_alive=True or already connected)
    
    Supports both synchronous and asynchronous contexts.
    """

    def __init__(self, weaviate_client: WeaviateClient, keep_alive: bool = False):
        """
        Initialize connection manager.

        Args:
            weaviate_client: WeaviateClient instance
            keep_alive: If True, don't close connection on exit
        """
        self.weaviate_client = weaviate_client
        self.was_connected = False
        self.keep_alive = keep_alive

    def __enter__(self):
        """Enter context (synchronous)."""
        self.was_connected = self.weaviate_client.ensure_connection()
        return self.weaviate_client

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context (synchronous)."""
        # Only close if we opened it and keep_alive is False
        if not self.keep_alive and not self.was_connected:
            try:
                self.weaviate_client.close()
                logger.debug("Managed connection closed")
            except Exception as e:
                logger.error(f"Error closing managed connection: {e}")
        
        return False  # Don't suppress exceptions

    async def __aenter__(self):
        """Enter context (asynchronous)."""
        self.was_connected = self.weaviate_client.ensure_connection()
        return self.weaviate_client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context (asynchronous)."""
        if not self.keep_alive and not self.was_connected:
            try:
                self.weaviate_client.close()
                logger.debug("Managed connection closed (async)")
            except Exception as e:
                logger.error(f"Error closing managed connection: {e}")
        
        return False
