"""
Vector search service factory.

This module provides the main entry point for vector search operations.
Depending on the configuration (discovery_mode), it will either use:
- Embedded FAISS with sentence-transformers (default, requires heavy dependencies)
- Weaviate-based vector search service (uses WeaviateClient for tool indexing)
"""

import logging
from typing import TYPE_CHECKING

from registry.core.config import settings

from .base import VectorSearchService

if TYPE_CHECKING:
    pass
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


def create_vector_search_service() -> VectorSearchService:
    """
    Factory function to create the appropriate vector search service based on configuration.
    
    Returns:
        VectorSearchService: Either EmbeddedFaissService or ExternalVectorSearchService (Weaviate-based)
    """
    if settings.use_external_discovery:
        logger.info("Initializing Weaviate-based vector search service for MCP tools")
        from .external_service import ExternalVectorSearchService
        return ExternalVectorSearchService()
    logger.info("Initializing EMBEDDED FAISS vector search service")
    from .embedded_service import EmbeddedFaissService
    return EmbeddedFaissService(settings)


# Global service instance - created based on configuration
# This maintains backward compatibility with existing code that imports vector_service
faiss_service = create_vector_search_service()
vector_service = faiss_service

# Backward compatibility: expose the service with its original name
__all__ = ["create_vector_search_service", "faiss_service"]
