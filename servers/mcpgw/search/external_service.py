import logging
import json
from typing import List, Dict, Any, Optional
from packages.db import initialize_database
from packages.shared.models import McpTool
from .base import VectorSearchService

logger = logging.getLogger(__name__)


class ExternalVectorSearchService(VectorSearchService):
    """
    External vector search using three-layer architecture.
    
    Supports both Weaviate and Chroma with native filter formats.
    """

    def __init__(self):
        """Initialize vector search service using DatabaseClient."""
        try:
            self._client = initialize_database()
            self._mcp_tools = self._client.for_model(McpTool)
            self._adapter_type = self._client.get_info().get('adapter_type', 'Unknown')
            self._initialized = True
            logger.info(f"Vector search service initialized with {self._adapter_type}")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector search: {e}")
            self._client = None
            self._mcp_tools = None
            self._adapter_type = None
            self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize and verify database connection.
        
        Checks adapter status and collection availability.
        """
        if not self._client:
            logger.error("Client not initialized")
            self._initialized = False
            raise Exception("DatabaseClient not initialized")
        
        try:
            if not self._client.is_initialized():
                raise Exception("DatabaseClient not initialized")
            
            # Get adapter info
            adapter = self._client.adapter
            collection_name = McpTool.COLLECTION_NAME
            
            # Check if collection exists
            if hasattr(adapter, 'collection_exists'):
                exists = adapter.collection_exists(collection_name)
                if exists:
                    logger.info(f"Collection '{collection_name}' exists")
                else:
                    logger.warning(f"Collection '{collection_name}' may not exist yet")
            
            # Try a simple filter query to verify
            try:
                test_results = self._mcp_tools.filter(
                    filters={"is_enabled": True},  # Dict auto-converted
                    limit=1
                )
                logger.info(f"Collection check: found {len(test_results)} tools")
            except Exception as e:
                logger.debug(f"Collection verification query failed: {e}")
            
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
        top_n_tools: int = 10,
        search_type: str = "semantic"
    ) -> List[Dict[str, Any]]:
        """
        Search for tools using Repository API.
        
        Uses native filters for optimal performance.
        
        Args:
            query: Search query text
            tags: List of tags to filter by
            user_scopes: User scopes for access control (not implemented)
            top_k_services: Max services (not used in new architecture)
            top_n_tools: Maximum number of tools to return
            search_type: Type of search ("semantic", "hybrid", "keyword")
        
        Returns:
            List of tool dictionaries in mcpgw format
            
        Example:
            # Semantic search with filters
            results = await service.search_tools(
                query="get weather data",
                tags=["weather"],
                top_n_tools=5
            )
        """
        if not self._initialized:
            raise Exception("Vector search service not initialized")

        if not query and not tags:
            raise Exception("At least one of 'query' or 'tags' must be provided")
        
        logger.info(
            f"Searching tools: query='{query}', tags={tags}, limit={top_n_tools}"
        )
        try:
            filter_conditions = {"is_enabled": True}
            if query:
                tools = self._mcp_tools.search(
                    query=query,
                    k=top_n_tools * 2,  # Get more for tag filtering
                    filters=filter_conditions  # Dict auto-converted
                )
            else:
                tools = self._mcp_tools.filter(
                    filters=filter_conditions,  # Dict auto-converted
                    limit=top_n_tools * 2
                )
            
            # Apply tag filtering in-memory if needed
            if tags:
                filtered_tools = []
                for tool in tools:
                    tool_tags = tool.tags or []
                    if any(tag in tool_tags for tag in tags):
                        filtered_tools.append(tool)
                tools = filtered_tools[:top_n_tools]
            else:
                tools = tools[:top_n_tools]
            
            logger.info(f"Search returned {len(tools)} tools")
            
            # Convert to mcpgw format
            formatted_tools = self._format_tools_for_mcpgw(tools)
            
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
        return self._initialized and self._client is not None and self._client.is_initialized()
    
    async def cleanup(self):
        """Cleanup resources and close database connection."""
        logger.info("Cleaning up vector search service")
        
        if self._initialized and self._client:
            try:
                self._client.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")
        
        self._client = None
        self._mcp_tools = None
        self._initialized = False
        logger.info("Vector search cleanup complete")
