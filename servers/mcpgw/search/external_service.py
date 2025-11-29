"""
External Vector Search Service for MCPGW

This implementation uses direct database search via McpTool.objects.search_by_type()
instead of HTTP API calls for better performance and simplicity.
"""

import logging
import json
from typing import List, Dict, Any, Optional

from packages.db import (
    ConnectionConfig,
    ProviderFactory,
    init_weaviate,
    get_weaviate_client,
    Q,
    SearchType
)
from packages.db.managers import CollectionManager
from packages.shared.models import McpTool
from .base import VectorSearchService
from config import settings

logger = logging.getLogger(__name__)


class ExternalVectorSearchService(VectorSearchService):
    """
    External vector search using Weaviate with multiple search types.
    
    Refactored to use:
    - New configuration system (ConnectionConfig, Provider)
    - QueryBuilder with method selection
    - Q objects for filtering
    - Enhanced error handling
    """

    def __init__(self):
        """
        Initialize vector search service using new config system.
        
        Supports both explicit credentials and IAM Role authentication.
        """
        try:
            # Use new configuration system
            connection = ConnectionConfig(
                host=settings.WEAVIATE_HOST,
                port=settings.WEAVIATE_PORT,
                api_key=settings.WEAVIATE_API_KEY
            )
            
            # Get provider from environment (auto-detects IAM Role)
            provider = ProviderFactory.from_env()
            
            # Initialize with config objects
            init_weaviate(
                connection=connection,
                provider=provider
            )
            
            self._client = get_weaviate_client()
            self._initialized = False
            
            logger.info(
                f"MCPGW vector search initialized with {provider.__class__.__name__} "
                f"({provider.get_vectorizer_name()})"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize vector search: {e}")
            self._client = None
            self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize Weaviate and ensure MCPTool collection exists.
        
        Verifies connection and creates collection if needed.
        """
        if not self._client:
            logger.error("Client not initialized")
            self._initialized = False
            raise Exception("Weaviate client not initialized")
        
        try:
            # Check connection
            if not self._client.is_ready():
                logger.warning("Client not ready, connecting...")
                self._client.ensure_connection()
            
            # Verify server responds
            if not self._client.ping():
                raise ConnectionError("Weaviate server not responding")
            
            # Ensure collection exists
            if not McpTool.collection_exists():
                logger.info("Creating MCPTool collection...")
                if not McpTool.create_collection():
                    raise RuntimeError("Failed to create MCPTool collection")
                logger.info("MCPTool collection created")
            else:
                logger.info("MCPTool collection exists")
                
                # Get stats
                manager = CollectionManager(self._client)
                stats = manager.get_collection_stats(McpTool)
                if stats:
                    logger.info(
                        f"Collection: {stats['object_count']} tools, "
                        f"{stats['property_count']} properties"
                    )

            self._initialized = True
            logger.info("Vector search initialized successfully")
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}", exc_info=True)
            self._initialized = False
            raise Exception(f"Cannot initialize vector search: {e}")

    async def search_tools(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_scopes: Optional[List[str]] = None,
        top_k_services: int = 3,
        top_n_tools: int = 1,
        search_type: SearchType = SearchType.HYBRID
    ) -> List[Dict[str, Any]]:
        """
        Search for tools with support for multiple search types.
        
        Uses SearchType enum for type-safe search method selection.
        
        Args:
            query: Search query text
            tags: List of tags to filter by (contains_any logic)
            user_scopes: List of user scopes (not currently used in filtering)
            top_k_services: Maximum services (not used in direct search)
            top_n_tools: Maximum number of tools to return
            search_type: Type of search (default: SearchType.HYBRID)
                Options:
                - SearchType.BM25: Keyword search
                - SearchType.NEAR_TEXT: Semantic search
                - SearchType.HYBRID: Combined (70% semantic + 30% keyword)
                - SearchType.FUZZY: Typo-tolerant search
        
        Returns:
            List of tool dictionaries in mcpgw format
            
        Example:
            from packages.db import SearchType
            
            results = await service.search_tools(
                query="get weather data",
                tags=["weather", "api"],
                top_n_tools=5,
                search_type=SearchType.HYBRID
            )
        """
        if not self._initialized:
            raise Exception("Vector search service not initialized")

        # Input validation
        if not query and not tags:
            raise Exception("At least one of 'query' or 'tags' must be provided")
        
        logger.info(
            f"Searching tools: type={search_type.value}, query='{query}', "
            f"tags={tags}, limit={top_n_tools}"
        )
        
        try:
            # Build query with filters
            query_builder = McpTool.objects.filter(is_enabled=True)
            
            # Add tag filter if provided
            if tags:
                query_builder = query_builder.filter(tags__contains_any=tags)
            
            # Execute search based on type (using enum comparison)
            if query:
                if search_type == SearchType.BM25:
                    results = query_builder.bm25(query).limit(top_n_tools).all()
                elif search_type == SearchType.NEAR_TEXT:
                    results = query_builder.near_text(query).limit(top_n_tools).all()
                elif search_type == SearchType.HYBRID:
                    results = query_builder.hybrid(query, alpha=0.7).limit(top_n_tools).all()
                elif search_type == SearchType.FUZZY:
                    results = query_builder.fuzzy(query).limit(top_n_tools).all()
                else:
                    # Default to hybrid
                    logger.warning(f"Unknown search_type {search_type}, using hybrid")
                    results = query_builder.hybrid(query, alpha=0.7).limit(top_n_tools).all()
            else:
                # No query, just filtered fetch
                results = query_builder.limit(top_n_tools).all()
            
            logger.info(f"Search returned {len(results)} tools")
            
            # Convert to mcpgw format
            formatted_tools = self._format_tools_for_mcpgw(results)
            
            logger.info(f"Returning {len(formatted_tools)} formatted tools")
            return formatted_tools
            
        except Exception as e:
            logger.error(f"Tool search failed: {e}", exc_info=True)
            raise

    def _format_tools_for_mcpgw(self, tools: List[McpTool]) -> List[Dict[str, Any]]:
        """
        Convert MCPTool instances to mcpgw format.
        
        Args:
            tools: List of MCPTool model instances
        
        Returns:
            List of formatted tool dictionaries
        """
        formatted_tools = []
        
        for tool in tools:
            # Parse schema JSON if string
            schema = tool.schema_json
            if isinstance(schema, str):
                try:
                    schema = json.loads(schema)
                except Exception as e:
                    logger.error(f"Failed to parse schema JSON: {e}")
                    schema = {}
            
            # Build parsed description
            parsed_description = {
                "main": tool.description_main or "",
                "args": tool.description_args or "",
                "returns": tool.description_returns or "",
                "raises": tool.description_raises or ""
            }
            
            # Build result dict
            formatted_tool = {
                "tool_name": tool.tool_name,
                "tool_parsed_description": parsed_description,
                "tool_schema": schema,
                "service_path": tool.server_path,
                "service_name": tool.server_name,
                "supported_transports": ["streamable-http"],
                "auth_provider": None,
            }
            
            # Add search metadata if available
            if hasattr(tool, '_score') and tool._score is not None:
                formatted_tool["overall_similarity_score"] = tool._score
            elif hasattr(tool, '_distance') and tool._distance is not None:
                # Convert distance to score (lower distance = higher score)
                formatted_tool["overall_similarity_score"] = 1.0 - tool._distance
            elif hasattr(tool, '_certainty') and tool._certainty is not None:
                formatted_tool["overall_similarity_score"] = tool._certainty
            
            formatted_tools.append(formatted_tool)
        
        return formatted_tools
    
    async def check_availability(self) -> bool:
        """
        Check if vector search service is available.
        
        Returns:
            True if initialized and ready
        """
        return self._initialized and self._client is not None and self._client.is_ready()
