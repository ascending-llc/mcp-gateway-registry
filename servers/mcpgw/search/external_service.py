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
    init_weaviate,
    SearchType
)
from packages.shared.models import McpTool
from .base import VectorSearchService
from config import settings

logger = logging.getLogger(__name__)


class ExternalVectorSearchService(VectorSearchService):
    """
    External vector search using Weaviate with multiple search types.
    """

    def __init__(self):
        """
        Initialize vector search service using new config system.
        """
        try:
            # Use new configuration system
            connection = ConnectionConfig(
                host=settings.WEAVIATE_HOST,
                port=settings.WEAVIATE_PORT,
                api_key=settings.WEAVIATE_API_KEY
            )
            self._client = init_weaviate(connection=connection)
            self._initialized = False
            logger.info(
                f"Vector search service initialized with connection to "
                f"{connection.host}:{connection.port}"
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
                
                try:
                    # Get collection info
                    info = McpTool.objects.get_collection_info()
                    if info:
                        # Get object count using QueryBuilder
                        object_count = McpTool.objects.all().count()
                        logger.info(
                            f"   Collection has {object_count} tools, "
                            f"{info.get('property_count', 0)} properties"
                        )
                except Exception as e:
                    logger.debug(f"Could not get collection stats: {e}")

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
        Search for tools with flexible search type selection.
        
        Uses the unified search_by_type() method from QueryBuilder for
        clean, type-safe search execution across all search types.
        
        Args:
            query: Search query text
            tags: List of tags to filter by (uses contains_any logic)
            user_scopes: User scopes for access control (currently not used)
            top_k_services: Max services to consider (not used in direct DB search)
            top_n_tools: Maximum number of tools to return
            search_type: Type of search to execute (default: SearchType.HYBRID)
                Available types:
                - SearchType.BM25: Fast keyword/exact match search
                - SearchType.NEAR_TEXT: Semantic similarity search  
                - SearchType.HYBRID: Combined semantic + keyword (recommended)
                - SearchType.FUZZY: Typo-tolerant search
                - SearchType.FETCH_OBJECTS: Simple filtered fetch (no search)
        
        Returns:
            List of tool dictionaries in mcpgw format with fields:
            - tool_name: Name of the tool
            - tool_parsed_description: Parsed description object
            - tool_schema: JSON schema for the tool
            - service_path: Path to the service
            - service_name: Display name of the service
            - supported_transports: List of supported transports
            - overall_similarity_score: Search relevance score (if available)
            
        Example:
            from packages.db import SearchType
            
            # Hybrid search (default, best for most cases)
            results = await service.search_tools(
                query="get weather data",
                tags=["weather", "api"],
                top_n_tools=5,
                search_type=SearchType.HYBRID
            )
            
            # BM25 for exact keyword matching
            results = await service.search_tools(
                query="get_weather",
                search_type=SearchType.BM25
            )
            
            # Semantic for natural language
            results = await service.search_tools(
                query="I need to check the weather forecast",
                search_type=SearchType.NEAR_TEXT
            )
            
            # Fuzzy for typo tolerance
            results = await service.search_tools(
                query="wether forcast",  # typos
                search_type=SearchType.FUZZY
            )
        
        Note:
            This method leverages the unified search_by_type() from QueryBuilder,
            eliminating code duplication across model-based and collection-based searches.
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
            
            # Execute search using unified search_by_type method
            results = query_builder.search_by_type(
                search_type,
                query=query,
                alpha=0.7  # For hybrid search
            ).limit(top_n_tools).all()
            
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
