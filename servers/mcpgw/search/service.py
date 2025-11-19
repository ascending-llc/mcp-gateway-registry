"""
Vector search service factory for MCPGW.

This module provides the main entry point for vector search operations.
Depending on the configuration (TOOL_DISCOVERY_MODE), it will either use:
- Embedded FAISS with sentence-transformers (default, requires heavy dependencies)
- External registry semantic search service (lightweight, no heavy dependencies)
"""

import os
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .base import VectorSearchService

if TYPE_CHECKING:
    from .embedded_service import EmbeddedFaissService
    from .external_service import ExternalVectorSearchService

logger = logging.getLogger(__name__)


def create_vector_search_service() -> VectorSearchService:
    """
    Factory function to create the appropriate vector search service based on configuration.
    
    Environment Variables:
        TOOL_DISCOVERY_MODE: 'embedded' or 'external' (default: 'embedded')
        REGISTRY_BASE_URL: Base URL for external registry (required for external mode)
        REGISTRY_USERNAME: Username for registry authentication (optional)
        REGISTRY_PASSWORD: Password for registry authentication (optional)
        EMBEDDINGS_MODEL_NAME: Name of sentence-transformers model (for embedded mode)
        EMBEDDINGS_MODEL_DIMENSION: Expected embedding dimension (default: 384)
    
    Returns:
        VectorSearchService: Either EmbeddedFaissService or ExternalVectorSearchService
    """
    mode = os.environ.get('TOOL_DISCOVERY_MODE', 'embedded').lower()
    
    if mode == 'external':
        logger.info("Initializing EXTERNAL vector search service")
        
        registry_base_url = os.environ.get('REGISTRY_BASE_URL', 'http://localhost:7860')
        registry_username = os.environ.get('REGISTRY_USERNAME')
        registry_password = os.environ.get('REGISTRY_PASSWORD')
        
        from .external_service import ExternalVectorSearchService
        return ExternalVectorSearchService(
            registry_base_url=registry_base_url,
            registry_username=registry_username,
            registry_password=registry_password,
            timeout=30.0
        )
    
    elif mode == 'embedded':
        logger.info("Initializing EMBEDDED FAISS vector search service")
        
        # Determine paths
        # When running in Docker, server.py is at /app/server.py and registry files are at /app/registry/servers/
        from pathlib import Path
        current_file = Path(__file__).resolve()
        # Go up from search/ to mcpgw/ to servers/ and then to registry/servers/
        registry_server_data_path = current_file.parent.parent.parent / "registry" / "servers"
        
        # Get configuration from environment
        embeddings_model_name = os.environ.get('EMBEDDINGS_MODEL_NAME', 'all-MiniLM-L6-v2')
        embedding_dimension = int(os.environ.get('EMBEDDINGS_MODEL_DIMENSION', '384'))
        check_interval = float(os.environ.get('FAISS_CHECK_INTERVAL', '5.0'))
        
        from .embedded_service import EmbeddedFaissService
        return EmbeddedFaissService(
            registry_server_data_path=registry_server_data_path,
            embeddings_model_name=embeddings_model_name,
            embedding_dimension=embedding_dimension,
            check_interval=check_interval
        )
    
    else:
        raise ValueError(
            f"Invalid TOOL_DISCOVERY_MODE: {mode}. "
            f"Must be 'embedded' or 'external'"
        )


# Global service instance - created based on configuration
# This maintains backward compatibility and provides a singleton
vector_search_service: VectorSearchService = create_vector_search_service()

__all__ = ['vector_search_service', 'create_vector_search_service']
