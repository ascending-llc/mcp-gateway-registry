import os
import time
import weaviate
import logging
from typing import Optional
from weaviate.auth import AuthApiKey
from weaviate.client import WeaviateClient as OriginalWeaviateClient
from weaviate.config import AdditionalConfig, ConnectionConfig, Timeout
from .enums import LLMProvider

logger = logging.getLogger(__name__)


class WeaviateConfig:
    """Weaviate configuration class, manages default vectorizers and model configurations"""

    DEFAULT_CONFIGS = {
        LLMProvider.BEDROCK: {
            "vectorizer": "text2vec-aws",
            "model": "amazon.titan-embed-text-v2:0",
            "region": "us-east-1"
        },
        LLMProvider.OPENAI: {
            "vectorizer": "text2vec-openai",
            "model": "text-embedding-ada-002"
        }
    }

    @classmethod
    def get_default_vectorizer(cls) -> str:
        """Get default vectorizer"""
        provider = os.getenv("EMBEDDINGS_PROVIDER", LLMProvider.BEDROCK)
        return cls.DEFAULT_CONFIGS.get(provider, {}).get("vectorizer", "none")

    @classmethod
    def get_default_model(cls) -> str:
        """Get default model"""
        provider = os.getenv("EMBEDDINGS_PROVIDER", LLMProvider.BEDROCK)
        return os.getenv("EMBEDDINGS_MODEL",
                         cls.DEFAULT_CONFIGS.get(provider, {}).get("model", ""))

    @classmethod
    def get_aws_region(cls) -> str:
        """Get AWS region"""
        return os.getenv("AWS_REGION",
                         cls.DEFAULT_CONFIGS.get(LLMProvider.BEDROCK, {}).get("region", "us-east-1"))

    @classmethod
    def get_current_provider(cls) -> LLMProvider:
        """Get current LLMProvider"""
        provider_str = os.getenv("EMBEDDINGS_PROVIDER", LLMProvider.BEDROCK)
        try:
            return LLMProvider(provider_str)
        except ValueError:
            return LLMProvider.BEDROCK


class WeaviateClient:
    """Base Weaviate client class, responsible for client initialization and connection management"""

    def __init__(
            self,
            host: Optional[str] = None,
            port: Optional[int] = None,
            api_key: Optional[str] = None,
            embeddings_provider: Optional[str] = None,
            aws_access_key_id: Optional[str] = None,
            aws_secret_access_key: Optional[str] = None,
            aws_session_token: Optional[str] = None,
            aws_region: Optional[str] = None,
            openai_api_key: Optional[str] = None,
            session_pool_connections: int = 10,
            session_pool_maxsize: int = 10,
            init_timeout: int = 10,
            query_timeout: int = 60,
            insert_timeout: int = 60,
            client: Optional[OriginalWeaviateClient] = None
    ):
        """
        Initialize WeaviateClient with explicit parameters.

        Args:
            host: Weaviate host (default: from env or "127.0.0.1")
            port: Weaviate port (default: from env or 8099)
            api_key: Weaviate API key (default: from env or "test-secret-key")
            embeddings_provider: "bedrock" or "openai" (default: from env or "bedrock")
            aws_access_key_id: AWS access key for Bedrock
            aws_secret_access_key: AWS secret key for Bedrock
            aws_session_token: AWS session token (optional)
            aws_region: AWS region (default: "us-east-1")
            openai_api_key: OpenAI API key (if using OpenAI provider)
            session_pool_connections: Connection pool size
            session_pool_maxsize: Max pool size
            init_timeout: Init timeout in seconds
            query_timeout: Query timeout in seconds
            insert_timeout: Insert timeout in seconds
            client: Pre-configured Weaviate client instance (overrides all other params)
        """
        if client is not None:
            self.client = client
        else:
            self.client = self._create_client(
                host=host,
                port=port,
                api_key=api_key,
                embeddings_provider=embeddings_provider,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                aws_session_token=aws_session_token,
                aws_region=aws_region,
                openai_api_key=openai_api_key,
                session_pool_connections=session_pool_connections,
                session_pool_maxsize=session_pool_maxsize,
                init_timeout=init_timeout,
                query_timeout=query_timeout,
                insert_timeout=insert_timeout
            )

    def _create_client(
            self,
            host: Optional[str] = None,
            port: Optional[int] = None,
            api_key: Optional[str] = None,
            embeddings_provider: Optional[str] = None,
            aws_access_key_id: Optional[str] = None,
            aws_secret_access_key: Optional[str] = None,
            aws_session_token: Optional[str] = None,
            aws_region: Optional[str] = None,
            openai_api_key: Optional[str] = None,
            session_pool_connections: int = 10,
            session_pool_maxsize: int = 10,
            init_timeout: int = 100,
            query_timeout: int = 300,
            insert_timeout: int = 200
    ) -> OriginalWeaviateClient:
        """
        Create Weaviate client instance with explicit parameters.

        Args:
            host: Weaviate host (default: from env or "127.0.0.1")
            port: Weaviate port (default: from env or 8099)
            api_key: Weaviate API key (default: from env or "test-secret-key")
            embeddings_provider: "bedrock" or "openai"
            aws_access_key_id: AWS access key
            aws_secret_access_key: AWS secret key
            aws_session_token: AWS session token (optional)
            aws_region: AWS region
            openai_api_key: OpenAI API key
            session_pool_connections: Connection pool size
            session_pool_maxsize: Max pool size
            init_timeout: Init timeout in seconds
            query_timeout: Query timeout in seconds
            insert_timeout: Insert timeout in seconds

        Returns:
            OriginalWeaviateClient: Configured Weaviate client
        """
        # Use provided values or fallback to env vars
        host = host or os.getenv("WEAVIATE_HOST", "127.0.0.1")
        port = port or int(os.getenv("WEAVIATE_PORT", "8099"))
        api_key = api_key or os.getenv("WEAVIATE_API_KEY", "test-secret-key")
        embeddings_provider = embeddings_provider or os.getenv("EMBEDDINGS_PROVIDER", "bedrock")

        # Build headers based on provider
        headers = {}

        if embeddings_provider == "bedrock":
            # AWS Bedrock headers
            aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
            aws_secret_access_key = aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")
            aws_session_token = aws_session_token or os.getenv("AWS_SESSION_TOKEN")
            headers = self.get_fixed_aws_auth_headers(aws_access_key_id, aws_secret_access_key, aws_session_token)
            logger.info("AWS Bedrock headers  configured")
        elif embeddings_provider == "openai":
            # OpenAI headers
            openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
            if openai_api_key:
                headers["X-OpenAI-Api-Key"] = openai_api_key
                logger.info("OpenAI API key configured")

        logger.info(f"Creating Weaviate client: {host}:{port}, provider={embeddings_provider}")

        # Connection config
        conn_config = ConnectionConfig(
            session_pool_connections=session_pool_connections,
            session_pool_maxsize=session_pool_maxsize
        )

        client = weaviate.connect_to_local(
            host=host,
            port=port,
            auth_credentials=AuthApiKey(api_key=api_key) if api_key else None,
            headers=headers,
            additional_config=AdditionalConfig(
                timeout=Timeout(
                    init=init_timeout,
                    query=query_timeout,
                    insert=insert_timeout
                ),
                connection=conn_config
            )
        )

        logger.info("Weaviate client created successfully")
        return client

    def get_fixed_aws_auth_headers(self, aws_access_key_id, aws_secret_access_key, aws_session_token):
        """
        Return HTTP headers containing fixed AWS access key and secret.

        Returns:
            dict: HTTP headers containing fixed AWS authentication information.
        """
        headers = {}
        if aws_access_key_id and aws_secret_access_key:
            headers = {
                'X-AWS-Access-Key': aws_access_key_id,
                'X-AWS-Secret-Key': aws_secret_access_key
            }
            if aws_session_token:
                headers['X-AWS-Session-Token'] = aws_session_token
                logger.info("adding session token as X-AWS-Session-Token in headers")
            logger.info("AWS authentication headers configured for Bedrock")
        else:
            logger.warning("AWS credentials not found in environment variables")
        return headers

    @classmethod
    def create(cls):
        """
        Factory method to create WeaviateClient instance

        Returns:
            WeaviateClient: Newly created client instance
        """
        return cls()

    async def ensure_connected(self, max_retries: int = 10, retry_delay: float = 2.0):
        """
        Ensure client is connected to Weaviate server with retry logic.
        
        Args:
            max_retries: Maximum number of connection attempts (default: 10)
            retry_delay: Delay in seconds between retries (default: 2.0)
            
        Raises:
            Exception: If connection fails after all retries
        """
        last_exception = None
        
        for attempt in range(1, max_retries + 1):
            try:
                if not self.client.is_connected():
                    logger.info(f"Attempting to connect to Weaviate (attempt {attempt}/{max_retries})...")
                    self.client.connect()
                    logger.info("✅ Successfully connected to Weaviate")
                    return
                else:
                    logger.debug("Weaviate client already connected")
                    return
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    logger.warning(
                        f"Failed to connect to Weaviate (attempt {attempt}/{max_retries}): {str(e)}. "
                        f"Retrying in {retry_delay} seconds..."
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        f"Failed to connect to Weaviate after {max_retries} attempts: {str(e)}"
                    )
        
        # If we get here, all retries failed
        raise ConnectionError(
            f"Could not connect to Weaviate after {max_retries} attempts. "
            f"Last error: {str(last_exception)}"
        ) from last_exception

    def ensure_connection(self, max_retries: int = 10, retry_delay: float = 2.0):
        """
        Ensure connection is established with retry logic (synchronous version).

        Args:
            max_retries: Maximum number of connection attempts (default: 10)
            retry_delay: Delay in seconds between retries (default: 2.0)

        Returns:
            bool: Connection state before this call (True means was already connected, False means newly established)
            
        Raises:
            Exception: If connection fails after all retries
        """
        was_connected = False
        last_exception = None
        
        if self.client is None:
            raise RuntimeError("Weaviate client not initialized")
        
        for attempt in range(1, max_retries + 1):
            try:
                was_connected = self.client.is_connected()
                if not was_connected:
                    logger.info(f"🔌 Weaviate client not connected, establishing connection (attempt {attempt}/{max_retries})...")
                    self.client.connect()
                    logger.info("✅ Weaviate client connected successfully")
                else:
                    logger.debug("Weaviate client already connected")
                return was_connected
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    logger.warning(
                        f"Failed to ensure Weaviate connection (attempt {attempt}/{max_retries}): {e}. "
                        f"Retrying in {retry_delay} seconds..."
                    )
                    time.sleep(retry_delay)
                else:
                    logger.error(
                        f"Failed to ensure Weaviate connection after {max_retries} attempts: {e}"
                    )
        
        # If we get here, all retries failed
        raise ConnectionError(
            f"Could not connect to Weaviate after {max_retries} attempts. "
            f"Last error: {str(last_exception)}"
        ) from last_exception

    def managed_connection(self, keep_alive: bool = False):
        """
        Return a context manager for automatically managing connection lifecycle
        
        Args:
            keep_alive: If True, connection will not be closed on exit.
                       Useful for long-lived services that need persistent connections.

        Returns:
            ManagedConnection: Connection manager context (supports both sync and async)
            
        Example:
            # Short-lived operation (connection auto-closed)
            async with client.managed_connection() as conn:
                result = await some_operation(conn)
                
            # Long-lived service (connection kept alive)
            async with client.managed_connection(keep_alive=True) as conn:
                # Multiple operations...
        """
        return ManagedConnection(self, keep_alive=keep_alive)

    def close(self):
        """Close Weaviate client connection"""
        if self.client is not None:
            try:
                if self.client.is_connected():
                    self.client.close()
                    logger.info("Weaviate client connection closed")
                else:
                    logger.debug("Weaviate client already disconnected")
            except Exception as e:
                logger.error(f"Error closing Weaviate client: {e}")


class ManagedConnection:
    """
    Weaviate connection manager context class
    
    Supports both synchronous and asynchronous context management.
    Automatically manages Weaviate connection lifecycle:
    - On enter: Ensure connection is established
    - On exit: Close connection and release resources (only if we opened it)
    """

    def __init__(self, weaviate_client: 'WeaviateClient', keep_alive: bool = False):
        """
        Initialize connection manager

        Args:
            weaviate_client: WeaviateClient instance
            keep_alive: If True, don't close connection on exit (useful for persistent services)
        """
        self.weaviate_client = weaviate_client
        self.was_connected = False
        self.keep_alive = keep_alive

    def __enter__(self):
        """
        Ensure connection is established when entering context (sync)

        Returns:
            WeaviateClient: Weaviate client instance
        """
        self.was_connected = self.weaviate_client.ensure_connection()
        return self.weaviate_client

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Close connection when exiting context (sync)
        Only closes if we opened it and keep_alive is False
        """
        if not self.keep_alive and not self.was_connected:
            try:
                self.weaviate_client.close()
                logger.debug("Managed connection closed (sync)")
            except Exception as e:
                logger.error(f"Error closing connection in managed context: {e}")
        return False  # Do not suppress exceptions

    async def __aenter__(self):
        """
        Ensure connection is established when entering context (async)

        Returns:
            WeaviateClient: Weaviate client instance
        """
        await self.weaviate_client.ensure_connected()
        self.was_connected = self.weaviate_client.client.is_connected() if self.weaviate_client.client else False
        return self.weaviate_client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Close connection when exiting context (async)
        Only closes if we opened it and keep_alive is False
        """
        if not self.keep_alive and not self.was_connected:
            try:
                self.weaviate_client.close()
                logger.debug("Managed connection closed (async)")
            except Exception as e:
                logger.error(f"Error closing connection in managed context: {e}")
        return False  # Do not suppress exceptions
