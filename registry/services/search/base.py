"""
Base interface for vector search services.

This module defines the abstract interface that all vector search implementations
must follow, enabling pluggable backends (embedded FAISS, external MCP, etc.)
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class VectorSearchService(ABC):
    """Abstract base class for vector search services."""

    @abstractmethod
    async def initialize(self):
        """Initialize the search service (load models, connect to external service, etc.)."""

    @abstractmethod
    async def add_or_update_service(self, service_path: str, server_info: dict[str, Any], is_enabled: bool = False):
        """
        Add or update a service in the search index.
        
        Args:
            service_path: Unique identifier for the service (e.g., "/weather")
            server_info: Dictionary containing service metadata (name, description, tags, etc.)
            is_enabled: Whether the service is currently enabled
        """

    @abstractmethod
    async def remove_service(self, service_path: str):
        """
        Remove a service from the search index.
        
        Args:
            service_path: Unique identifier for the service to remove
        """

    @abstractmethod
    async def search(
        self,
        query: str | None = None,
        tags: list[str] | None = None,
        top_k: int = 10,
        filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Search for services matching the query and/or filters.
        
        Args:
            query: Natural language query for semantic search
            tags: List of tags to filter by
            top_k: Maximum number of results to return
            filters: Additional filters (e.g., {"is_enabled": True})
            
        Returns:
            List of matching services with metadata and relevance scores
        """

    async def cleanup(self):
        """Optional cleanup method for resources."""
