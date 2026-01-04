"""Unified database client interface."""

import logging
from typing import Optional, Dict, Any, Type, TypeVar

from .adapters.factory import VectorStoreFactory
from .config import BackendConfig
from .adapters.adapter import VectorStoreAdapter
from .repository import Repository

logger = logging.getLogger(__name__)

T = TypeVar('T')


class DatabaseClient:
    """
    Lightweight database manager.
    
    Core responsibilities:
    - Configuration management
    - Connection lifecycle (initialize/close)
    - Repository factory (for_model)
    - Direct adapter access for advanced users
    
    Recommended usage:
        db = initialize_database()
        tools_repo = db.for_model(McpTool)  # High-level Model API
        tools = tools_repo.search("query")
        
    Advanced usage:
        adapter = db.adapter  # Low-level Document API
        docs = adapter.similarity_search(collection_name="...", query="...")
    """

    def __init__(self, config: Optional[BackendConfig] = None):
        """Initialize database client with optional configuration."""
        self._config = config
        self._adapter: Optional[VectorStoreAdapter] = None
        self._initialized = False
        self._repositories = {}

    def initialize(self, config: Optional[BackendConfig] = None) -> None:
        """
        Initialize database client with configuration.
        
        Args:
            config: Database configuration (uses instance config if not provided)
            
        Raises:
            ValueError: If no configuration is provided
            RuntimeError: If initialization fails
        """
        if self._initialized:
            logger.warning("Database client already initialized")
            return

        try:
            config = config or self._config
            if not config:
                raise ValueError("Configuration required for initialization")

            logger.info("Initializing database client...")

            # Create adapter through factory
            self._adapter = VectorStoreFactory.create_adapter(config)
            self._config = config
            self._initialized = True

            logger.info(f"Database client initialized with {type(self._adapter).__name__}")

        except Exception as e:
            logger.error(f"Failed to initialize database client: {e}")
            raise

    def close(self) -> None:
        """Close database connection and clean up resources."""
        if not self._initialized:
            return
            
        try:
            logger.info("Closing database client...")

            if hasattr(self._adapter, 'close'):
                self._adapter.close()
            elif hasattr(self._adapter, '__exit__'):
                self._adapter.__exit__(None, None, None)

            self._adapter = None
            self._initialized = False
            self._repositories.clear()
            
            logger.info("Database client closed")

        except Exception as e:
            logger.error(f"Error closing database client: {e}")

    def is_initialized(self) -> bool:
        """Check if the client is initialized."""
        return self._initialized and self._adapter is not None

    @property
    def adapter(self) -> VectorStoreAdapter:
        """
        Get direct access to the underlying adapter.
        
        For advanced users who need low-level Document operations.
        
        """
        self._ensure_initialized()
        return self._adapter

    def for_model(self, model_class: Type[T]) -> Repository[T]:
        """
        Get repository for specific model class.
        
        This is the recommended way to interact with the database.
        Provides type-safe, ORM-style API for model operations.
        
        Args:
            model_class: Model class (must have to_document/from_document methods)
        """
        self._ensure_initialized()

        model_name = model_class.__name__

        if model_name not in self._repositories:
            self._repositories[model_name] = Repository(self, model_class)

        return self._repositories[model_name]

    def get_info(self) -> Dict[str, Any]:
        """
        Get client information and status.
        
        Returns:
            Dictionary with client status and configuration
        """
        if not self._initialized:
            return {"initialized": False}

        info = {
            "initialized": True,
            "adapter_type": type(self._adapter).__name__,
            "default_collection": getattr(self._adapter, '_default_collection', 'unknown'),
            "initialized_collections": getattr(self._adapter, 'list_collections', lambda: [])(),
        }

        return info

    def _ensure_initialized(self) -> None:
        """Ensure client is initialized."""
        if not self._initialized:
            raise RuntimeError("Database client not initialized. Call initialize() first.")


# Global client instance for convenience
_db_instance: Optional[DatabaseClient] = None


def get_db_client() -> DatabaseClient:
    """Get the global database client instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseClient()
    return _db_instance


def initialize_database(config: Optional[BackendConfig] = None) -> DatabaseClient:
    """
    Initialize the global database client.
    
    If config is None, automatically loads from environment variables.

    Args:
        config: Database configuration (optional, loads from env if not provided)

    Returns:
        Initialized database client
    """
    # Auto-load config from environment if not provided
    if config is None:
        config = BackendConfig.from_env()
    
    client = get_db_client()
    client.initialize(config)
    return client
