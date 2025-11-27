"""
External vector search service for MCPGW.

This implementation uses direct database search via McpTool.objects.search_by_type()
instead of HTTP API calls for better performance and simplicity.
"""

import logging
import json
from typing import List, Dict, Any, Optional
from packages.db import WeaviateClientRegistry, init_weaviate, get_weaviate_client, SearchType
from weaviate.classes.query import Filter

from packages.shared.models import McpTool
from .base import VectorSearchService
from config import settings

logger = logging.getLogger(__name__)


class ExternalVectorSearchService(VectorSearchService):
    """External vector search using registry's semantic search API."""

    def __init__(self):
        """
        Initialize the external vector search service.
        
        """
        if not WeaviateClientRegistry.instance:
            init_weaviate(
                host=settings.WEAVIATE_HOST,
                port=settings.WEAVIATE_PORT,
                api_key=settings.WEAVIATE_API_KEY,
                embeddings_provider=settings.WEAVIATE_EMBEDDINGS_PROVIDER,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                aws_region=settings.AWS_REGION,
            )
        self._client = get_weaviate_client()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the external vector search service."""
        # Check connectivity to registry
        try:
            await self._client.ensure_connected()
            if not McpTool.collection_exists():
                logger.info("Creating MCPTool collection...")
                if not McpTool.create_collection():
                    raise RuntimeError("Failed to create MCPTool collection")
                logger.info("MCPTool collection created")
            else:
                logger.info("MCPTool collection exists")

            self._initialized = True
            logger.info("Vector search initialized successfully")
        except Exception as e:
            logger.error(f"Failed to connect to registry at {e}")
            self._initialized = False
            raise Exception(f"Cannot connect to registry: {e}")

    async def search_tools(
            self,
            query: Optional[str] = None,
            tags: Optional[List[str]] = None,
            user_scopes: Optional[List[str]] = None,
            top_k_services: int = 3,
            top_n_tools: int = 1,
            search_type: Optional[str] = "bm25"
    ) -> List[Dict[str, Any]]:
        """
        Search for tools using direct database search via McpTool.objects.search_by_type().
        
        Args:
            query: Search query text
            tags: List of tags to filter by
            user_scopes: List of user scopes for access control
            top_k_services: Maximum number of services (not used in direct search)
            top_n_tools: Maximum number of tools to return
            search_type: Type of search to perform (default: "bm25")
                Options: "bm25", "near_text", "hybrid", "fuzzy"
        
        Returns:
            List of tool dictionaries in mcpgw format
        """
        if not self._initialized:
            raise Exception("External vector search service not initialized")

        # Input validation
        if not query and not tags:
            raise Exception("At least one of 'query' or 'tags' must be provided")
        
        try:
            # Build Weaviate Filter object for tags and enabled status
            filter_parts = [Filter.by_property("is_enabled").equal(True)]

            # Add tag filter if provided
            if tags:
                # Filter tools that have any of the specified tags
                filter_parts.append(Filter.by_property("tags").contains_any(tags))
            
            filters = None
            if len(filter_parts) == 1:
                filters = filter_parts[0]
            elif len(filter_parts) > 1:
                filters = filter_parts[0]
                for f in filter_parts[1:]:
                    filters = filters & f
            
            # Perform search using McpTool.objects.search_by_type()
            logger.info(f"Searching tools with search_type={search_type}, query={query}, tags={tags}, limit={top_n_tools}")
            
            if query:
                # Search with query text
                results = McpTool.objects.search_by_type(
                    search_type,
                    text=query,
                    filters=filters,
                    limit=top_n_tools * 3  # Get more results for filtering
                )
            else:
                # No query, just filter by tags and enabled status
                results = McpTool.objects.search_by_type(
                    SearchType.FETCH_OBJECTS,
                    filters=filters,
                    limit=top_n_tools * 3
                )
            
            logger.info(f"Database search returned {len(results)} tools")
            
            # Convert to mcpgw format
            formatted_tools = []
            for tool in results[:top_n_tools]:  # Limit to top_n_tools
                # Parse schema JSON if it's a string
                schema = tool.schema_json
                if isinstance(schema, str):
                    try:
                        schema = json.loads(schema)
                    except Exception as e:
                        logger.error(f"Failed to load schema from {schema}")
                        schema = {}
                
                # Build parsed description
                parsed_description = {
                    "main": tool.description_main or "",
                    "args": tool.description_args or "",
                    "returns": tool.description_returns or "",
                    "raises": tool.description_raises or ""
                }
                
                formatted_tool = {
                    "tool_name": tool.tool_name,
                    "tool_parsed_description": parsed_description,
                    "tool_schema": schema,
                    "service_path": tool.server_path,
                    "service_name": tool.server_name,
                    "supported_transports": ["streamable-http"],  # Default transport
                    "auth_provider": None,  # TODO: Add auth provider if available
                }
                
                # Add similarity score if available
                if hasattr(tool, '_score'):
                    formatted_tool["overall_similarity_score"] = tool._score
                elif hasattr(tool, '_distance'):
                    # Convert distance to score (lower distance = higher score)
                    formatted_tool["overall_similarity_score"] = 1.0 - tool._distance
                elif hasattr(tool, '_certainty'):
                    formatted_tool["overall_similarity_score"] = tool._certainty
                
                formatted_tools.append(formatted_tool)
            
            logger.info(f"Returning {len(formatted_tools)} formatted tools")
            return formatted_tools
        except Exception as e:
            logger.error(f"Direct database search failed: {e}", exc_info=True)
            raise
    
    async def check_availability(self) -> bool:
        """Check if the external vector search service is available."""
        if not self._initialized:
            return False
        return True
