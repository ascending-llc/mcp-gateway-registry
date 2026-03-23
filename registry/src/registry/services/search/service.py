"""
Vector search service factory.

This module provides the main entry point for vector search operations.
Depending on the configuration (discovery_mode), it will either use:
- Embedded FAISS with sentence-transformers (default, requires heavy dependencies)
- Weaviate-based vector search service (uses WeaviateClient for tool indexing)
As of 2026-02-12, we decide not to use the embedded FAISS service moving forward.
"""

import logging

from registry_pkgs.vector.repositories.mcp_server_repository import MCPServerRepository

from ...core.config import settings
from .base import VectorSearchService

# Get logger - logging is configured centrally in main.py via settings.configure_logging()
logger = logging.getLogger(__name__)


def create_vector_search_service(mcp_server_repo: MCPServerRepository) -> VectorSearchService:
    """
    Factory function to create the appropriate vector search service based on configuration.

    Returns:
        VectorSearchService: Either EmbeddedFaissService or ExternalVectorSearchService (Weaviate-based)
    """
    if settings.use_external_discovery:
        logger.info("Initializing Weaviate-based vector search service for MCP tools")
        from .external_service import ExternalVectorSearchService

        return ExternalVectorSearchService(mcp_server_repo=mcp_server_repo)
    else:
        logger.info("Initializing EMBEDDED FAISS vector search service")
        from .embedded_service import EmbeddedFaissService

        return EmbeddedFaissService(settings)


__all__ = ["create_vector_search_service"]
