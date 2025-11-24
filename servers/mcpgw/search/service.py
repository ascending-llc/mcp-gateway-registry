"""
Vector search service factory for MCPGW.

This module provides the main entry point for vector search operations.
Depending on the configuration (TOOL_DISCOVERY_MODE), it will either use:
- Embedded FAISS with sentence-transformers (requires heavy dependencies ~2-3GB)
- External registry semantic search service (lightweight, no heavy dependencies)

IMPORTANT: In external mode, FAISS and sentence-transformers are NOT imported,
making the service lightweight and suitable for deployment without ML dependencies.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .base import VectorSearchService

if TYPE_CHECKING:
    from .embedded_service import EmbeddedFaissService
    from .external_service import ExternalVectorSearchService

logger = logging.getLogger(__name__)

# Global service instance - lazily initialized
_vector_search_service: Optional[VectorSearchService] = None


def create_vector_search_service() -> VectorSearchService:
    """
    Factory function to create the appropriate vector search service based on configuration.
    
    This function uses lazy imports to ensure that heavy dependencies (FAISS, sentence-transformers)
    are only loaded when actually needed (embedded mode).
    
    Configuration is loaded from pydantic settings to ensure proper validation.
    
    Returns:
        VectorSearchService: Either EmbeddedFaissService or ExternalVectorSearchService
        
    Raises:
        ValueError: If TOOL_DISCOVERY_MODE is invalid
        ImportError: If embedded mode is requested but dependencies are not installed
    """
    # Import settings here to avoid circular imports
    from config import settings
    
    mode = settings.tool_discovery_mode.lower()
    
    if mode == 'external':
        logger.info("Initializing EXTERNAL vector search service (lightweight, no FAISS)")
        logger.info(f"  Registry URL: {settings.registry_base_url}")
        
        # Only import external service - no heavy dependencies
        from .external_service import ExternalVectorSearchService
        
        return ExternalVectorSearchService(
            registry_base_url=settings.registry_base_url,
            registry_username=settings.registry_username,
            registry_password=settings.registry_password,
            timeout=30.0
        )
    
    elif mode == 'embedded':
        logger.info("Initializing EMBEDDED FAISS vector search service")
        logger.warning("  ⚠️  This requires heavy dependencies (FAISS, sentence-transformers ~2-3GB)")
        
        # Lazy import - only load when embedded mode is active
        try:
            from .embedded_service import EmbeddedFaissService
        except ImportError as e:
            error_msg = (
                "\n" + "=" * 80 + "\n"
                "ERROR: Embedded vector search mode requires additional dependencies.\n"
                "\n"
                "These dependencies are heavy (~2-3GB) and include:\n"
                "  - faiss-cpu (~500MB)\n"
                "  - sentence-transformers (~2GB with models)\n"
                "  - scikit-learn (~50MB)\n"
                "\n"
                "Install them with:\n"
                "  pip install -e '.[embedded-search]'\n"
                "\n"
                "OR switch to external mode (recommended):\n"
                "  In .env file, set: TOOL_DISCOVERY_MODE=external\n"
                "=" * 80 + "\n"
                f"Original error: {e}"
            )
            logger.error(error_msg)
            raise ImportError(error_msg) from e
        
        # Determine paths
        current_file = Path(__file__).resolve()
        # Go up from search/ to mcpgw/ to servers/ and then to registry/servers/
        registry_server_data_path = current_file.parent.parent.parent / "registry" / "servers"
        
        logger.info(f"  Model: {settings.embeddings_model_name}")
        logger.info(f"  Dimension: {settings.embeddings_model_dimension}")
        logger.info(f"  Data path: {registry_server_data_path}")
        
        return EmbeddedFaissService(
            registry_server_data_path=registry_server_data_path,
            embeddings_model_name=settings.embeddings_model_name,
            embedding_dimension=settings.embeddings_model_dimension,
            check_interval=settings.faiss_check_interval
        )
    
    else:
        raise ValueError(
            f"Invalid TOOL_DISCOVERY_MODE: {mode}. "
            f"Must be 'embedded' or 'external'"
        )


def get_vector_search_service() -> VectorSearchService:
    """
    Get or create the global vector search service instance.
    
    This function ensures the service is only created once (singleton pattern).
    Lazy initialization means heavy dependencies are only loaded if/when needed.
    
    Returns:
        VectorSearchService: The global vector search service instance
    """
    global _vector_search_service
    
    if _vector_search_service is None:
        _vector_search_service = create_vector_search_service()
    
    return _vector_search_service


# For backward compatibility, expose the service through a property-like access
# This allows lazy initialization - the service is only created when first accessed
class VectorSearchServiceProxy:
    """
    Proxy to ensure lazy initialization of vector search service.
    
    This is critical for external mode - it ensures FAISS/sentence-transformers
    are never imported unless explicitly needed.
    """
    
    def __getattr__(self, name):
        """Delegate attribute access to the actual service instance."""
        service = get_vector_search_service()
        return getattr(service, name)
    
    async def initialize(self):
        """Initialize the vector search service."""
        service = get_vector_search_service()
        await service.initialize()
    
    async def search_tools(self, *args, **kwargs):
        """Search for tools using the vector search service."""
        service = get_vector_search_service()
        return await service.search_tools(*args, **kwargs)


# Export the proxy as the service
# This will be imported by other modules, but the actual service creation
# is delayed until first use
vector_search_service = VectorSearchServiceProxy()

__all__ = ['vector_search_service', 'create_vector_search_service', 'get_vector_search_service']
