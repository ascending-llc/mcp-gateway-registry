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
            session_pool_connections=settings.WEAVIATE_SESSION_POOL_CONNECTIONS,  # 最大连接数
            session_pool_maxsize=settings.WEAVIATE_SESSION_POOL_MAXSIZE
        )

        client = weaviate.connect_to_local(
            host=settings.WEAVIATE_HOST,
            port=settings.WEAVIATE_PORT,
            auth_credentials=AuthApiKey(
                api_key=settings.WEAVIATE_API_KEY) if settings.WEAVIATE_API_KEY else None,
            headers={},
            additional_config=AdditionalConfig(
                timeout=Timeout(init=settings.WEAVIATE_INIT_TIME,
                                query=settings.WEAVIATE_QUERY_TIME,
                                insert=settings.WEAVIATE_INSERT_TIME),
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
        确保连接已建立，如果未连接则建立连接

        Returns:
            bool: 连接前的状态（True 表示之前已连接，False 表示新建立连接）
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
        返回一个上下文管理器，用于自动管理连接的生命周期

        Returns:
            ManagedConnection: 连接管理器上下文
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
    Weaviate 连接管理器上下文类

    自动管理 Weaviate 连接的生命周期：
    - 进入时：确保连接已建立
    - 退出时：关闭连接释放资源

    """

    def __init__(self, weaviate_client: 'WeaviateClient'):
        """
        初始化连接管理器

        Args:
            weaviate_client: WeaviateClient 实例
        """
        self.weaviate_client = weaviate_client
        self.was_connected = False

    def __enter__(self):
        """
        进入上下文时确保连接已建立

        Returns:
            WeaviateClient: Weaviate 客户端实例
        """
        self.was_connected = self.weaviate_client.ensure_connection()
        return self.weaviate_client

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        退出上下文时关闭连接

        """
        try:
            self.weaviate_client.close()
        except Exception as e:
            logger.error(f"⚠️ Error closing connection in managed context: {e}")
        return False  # 不抑制异常
