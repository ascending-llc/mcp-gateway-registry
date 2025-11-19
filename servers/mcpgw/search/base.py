"""
Base interface for vector search services in MCPGW.

This module defines the abstract interface that all vector search implementations
must follow, enabling flexible switching between embedded and external services.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class VectorSearchService(ABC):
    """Abstract base class for vector search services."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the vector search service.
        
        This should be called once during application startup to prepare
        the service for queries (e.g., load models, establish connections).
        """
        pass
    
    @abstractmethod
    async def search_tools(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_scopes: Optional[List[str]] = None,
        top_k_services: int = 3,
        top_n_tools: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Search for tools using natural language query and/or tags.
        
        Args:
            query: Natural language query describing the desired tool functionality
            tags: List of tags to filter by (AND logic - all must match)
            user_scopes: List of scopes the user has for access control filtering
            top_k_services: Number of top matching services to consider
            top_n_tools: Number of best matching tools to return
            
        Returns:
            List of tool dictionaries with metadata including:
            - tool_name: Name of the tool
            - tool_parsed_description: Parsed description object
            - tool_schema: JSON schema for the tool
            - service_path: Path to the service
            - service_name: Display name of the service
            - supported_transports: List of supported transports
            - auth_provider: Authentication provider (if any)
            - overall_similarity_score: Similarity score (if semantic search used)
        """
        pass
    
    @abstractmethod
    async def check_availability(self) -> bool:
        """
        Check if the vector search service is available and functional.
        
        Returns:
            True if service is ready, False otherwise
        """
        pass
