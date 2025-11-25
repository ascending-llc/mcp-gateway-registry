import weaviate
import logging
from weaviate.auth import AuthApiKey
from weaviate.client import WeaviateClient as OriginalWeaviateClient
from weaviate.config import AdditionalConfig, Config, ConnectionConfig, Timeout

from config import settings

logger = logging.getLogger(__name__)


class WeaviateClient:
    """Base Weaviate client class, responsible for client initialization and connection management"""

    def __init__(self, client=None):
        """
        Initialize WeaviateClient

        Args:
            client: Optional Weaviate client instance, will be created automatically if not provided
        """
        self.client = client if client is not None else self._create_client()

    def _create_client(self) -> OriginalWeaviateClient:
        """
        create Weaviate client instance

        Returns:
            weaviate.Client: Weaviate instance
        """
        conn_config = ConnectionConfig(
            session_pool_connections=settings.weaviate_session_pool_connections,  # Maximum connections
            session_pool_maxsize=settings.weaviate_session_pool_maxsize
        )

        client = weaviate.connect_to_local(
            host=settings.weaviate_host,
            port=settings.weaviate_port,
            auth_credentials=AuthApiKey(
                api_key=settings.weaviate_api_key) if settings.weaviate_api_key else None,
            headers={},
            additional_config=AdditionalConfig(
                timeout=Timeout(init=settings.weaviate_init_time,
                                query=settings.weaviate_query_time,
                                insert=settings.weaviate_insert_time),
                connection=conn_config
            )
        )
        logger.debug("Weaviate client created successfully")
        return client

    @classmethod
    def create(cls):
        """
        Factory method to create WeaviateClient instance

        Returns:
            WeaviateClient: Newly created client instance
        """
        return cls()

    async def ensure_connected(self):
        """Ensure client is connected to Weaviate server"""
        try:
            if not self.client.is_connected():
                self.client.connect()
        except Exception as e:
            logger.error(f"Error connecting to Weaviate: {str(e)}")
            raise

    def ensure_connection(self):
        """
        Ensure connection is established, establish connection if not connected

        Returns:
            bool: Connection state before this call (True means was already connected, False means newly established)
        """
        was_connected = False
        try:
            if self.client is not None:
                was_connected = self.client.is_connected()
                if not was_connected:
                    logger.info("🔌 Weaviate client not connected, establishing connection...")
                    self.client.connect()
                    logger.info("✅ Weaviate client connected successfully")
                else:
                    logger.debug("✅ Weaviate client already connected")
            return was_connected
        except Exception as e:
            logger.error(f"❌ Failed to ensure Weaviate connection: {e}")
            raise

    def managed_connection(self):
        """
        Return a context manager for automatically managing connection lifecycle

        Returns:
            ManagedConnection: Connection manager context
        """
        return ManagedConnection(self)

    def close(self):
        """Close Weaviate client connection"""
        if self.client is not None:
            try:
                if self.client.is_connected():
                    self.client.close()
                    logger.info("🔒 Weaviate client connection closed")
                else:
                    logger.debug("Weaviate client already disconnected")
            except Exception as e:
                logger.error(f"⚠️ Error closing Weaviate client: {e}")


class ManagedConnection:
    """
    Weaviate connection manager context class

    Automatically manages Weaviate connection lifecycle:
    - On enter: Ensure connection is established
    - On exit: Close connection and release resources

    """

    def __init__(self, weaviate_client: 'WeaviateClient'):
        """
        Initialize connection manager

        Args:
            weaviate_client: WeaviateClient instance
        """
        self.weaviate_client = weaviate_client
        self.was_connected = False

    def __enter__(self):
        """
        Ensure connection is established when entering context

        Returns:
            WeaviateClient: Weaviate client instance
        """
        self.was_connected = self.weaviate_client.ensure_connection()
        return self.weaviate_client

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Close connection when exiting context

        """
        try:
            self.weaviate_client.close()
        except Exception as e:
            logger.error(f"⚠️ Error closing connection in managed context: {e}")
        return False  # Do not suppress exceptions
