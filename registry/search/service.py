"""
Vector search service factory.

This module provides the main entry point for vector search operations.
Depending on the configuration (discovery_mode), it will either use:
- Embedded FAISS with sentence-transformers (default, requires heavy dependencies)
- External MCP vector search service (lightweight, no heavy dependencies)
"""

import logging
from typing import TYPE_CHECKING

from ..core.config import settings
from .base import VectorSearchService

if TYPE_CHECKING:
    from .embedded_service import EmbeddedFaissService
    from .external_service import ExternalVectorSearchService

logger = logging.getLogger(__name__)


def create_vector_search_service() -> VectorSearchService:
    """
    Factory function to create the appropriate vector search service based on configuration.
    
    Returns:
        VectorSearchService: Either EmbeddedFaissService or ExternalVectorSearchService
    """
    if settings.use_external_discovery:
        logger.info(f"Initializing EXTERNAL vector search service at {settings.external_vector_search_url}")
        from .external_service import ExternalVectorSearchService
        return ExternalVectorSearchService(settings.external_vector_search_url)
    else:
        logger.info("Initializing EMBEDDED FAISS vector search service")
        from .embedded_service import EmbeddedFaissService
        return EmbeddedFaissService(settings)


# Global service instance - created based on configuration
# This maintains backward compatibility with existing code that imports vector_service
faiss_service = create_vector_search_service()
vector_service = faiss_service

# Backward compatibility: expose the service with its original name
__all__ = ['faiss_service', 'create_vector_search_service'] 