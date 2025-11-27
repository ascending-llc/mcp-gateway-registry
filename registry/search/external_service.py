import logging
from typing import Dict, Any, Optional, List

from packages.shared.models import McpTool
from .base import VectorSearchService
from packages.db import WeaviateClientRegistry, init_weaviate, get_weaviate_client
from ..constants import REGISTRY_CONSTANTS

logger = logging.getLogger(__name__)


class ExternalVectorSearchService(VectorSearchService):
    """
    Vector search service using packages.db ORM with AWS Bedrock.

    """

    def __init__(self):
        """
        Initialize vector search service from environment variables.
        
        """
        if not WeaviateClientRegistry.instance:
            init_weaviate(
                host=REGISTRY_CONSTANTS.WEAVIATE_HOST,
                port=REGISTRY_CONSTANTS.WEAVIATE_PORT,
                api_key=REGISTRY_CONSTANTS.WEAVIATE_API_KEY,
                embeddings_provider=REGISTRY_CONSTANTS.WEAVIATE_EMBEDDINGS_PROVIDER,
                aws_access_key_id=REGISTRY_CONSTANTS.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=REGISTRY_CONSTANTS.AWS_SECRET_ACCESS_KEY,
                aws_region=REGISTRY_CONSTANTS.AWS_REGION,
            )
        self._client = get_weaviate_client()
        self._initialized = False

    async def initialize(self):
        """
        Initialize Weaviate and ensure MCPTool collection exists.
        """
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
            logger.error(f"Initialization failed: {e}", exc_info=True)
            logger.warning("Vector search DISABLED - service will continue without it")
            self._initialized = False

    async def add_or_update_service(
            self,
            service_path: str,
            server_info: Dict[str, Any],
            is_enabled: bool = False
    ) -> Optional[Dict[str, int]]:
        """
        Add or update tools for a service with AWS Bedrock embeddings.
        
        Automatically removes existing tools and batch creates new ones.
        
        Args:
            service_path: Service path (e.g., /weather)
            server_info: Server info with tool_list
            is_enabled: Whether service is enabled
            
        Returns:
            {"indexed_tools": count} or None if service unavailable
        """
        if not self._initialized:
            logger.warning(f"Vector search not initialized, skipping '{service_path}'")
            return None

        tool_count = len(server_info.get("tool_list", []))
        logger.info(f"Indexing '{service_path}': {tool_count} tools, enabled={is_enabled}")

        try:
            # Remove existing tools
            remove_result = await self.remove_service(service_path)
            if remove_result:
                logger.info(f"Removed {remove_result['deleted_tools']} old tools")

            # Bulk create new tools
            tools = McpTool.bulk_create_from_server_info(
                service_path=service_path,
                server_info=server_info,
                is_enabled=is_enabled
            )
            logger.info(f"Indexed {len(tools)} tools for '{service_path}'")
            return {"indexed_tools": len(tools)}
        except Exception as e:
            logger.error(f"Indexing failed for '{service_path}': {e}", exc_info=True)
            return None

    async def remove_service(self, service_path: str) -> Optional[Dict[str, int]]:
        """
        Remove all tools for a service.
        
        Args:
            service_path: Service path identifier
            
        Returns:
            {"deleted_tools": count} or None if service unavailable
        """
        if not self._initialized:
            return None

        try:
            tools = McpTool.objects.filter(server_path=service_path).limit(1000).all()
            deleted_count = sum(1 for tool in tools if tool.delete())
            logger.info(f"Removed {deleted_count} tools for '{service_path}'")
            return {"deleted_tools": deleted_count}
        except Exception as e:
            logger.error(f"Removal failed for '{service_path}': {e}")
            return None

    async def search(
            self,
            query: Optional[str] = None,
            tags: Optional[List[str]] = None,
            top_k: int = 10,
            filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search tools with AWS Bedrock semantic search.
        
        Automatically uses:
        - Hybrid search (70% semantic + 30% keyword) if query provided
        - Filtered fetch if no query
        
        Args:
            query: Search text for semantic search
            tags: Tag filters (uses contains_any)
            top_k: Maximum results
            filters: Field filters, e.g., {"is_enabled": True}
            
        Returns:
            List of tool dictionaries with metadata
            
        """
        if not self._initialized:
            logger.warning("Vector search unavailable, returning empty results")
            return []

        logger.info(f"Search: query='{query}', tags={tags}, limit={top_k}")

        try:
            tools = McpTool.objects.smart_search(
                query=query,
                limit=top_k,
                field_filters=filters,
                list_filters={"tags": tags} if tags else None,
                alpha=0.7
            )
            return self._tools_to_results(tools)

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _tools_to_results(self, tools: List[McpTool]) -> List[Dict[str, Any]]:
        """
        Convert MCPTool model instances to result dictionaries.
        
        Extracts tool data and search metadata (distance, certainty, score).
        """
        return [
            {
                "tool_name": t.tool_name,
                "server_path": t.server_path,
                "server_name": t.server_name,
                "description": t.description_main,
                "description_args": t.description_args,
                "description_returns": t.description_returns,
                "tags": t.tags or [],
                "is_enabled": t.is_enabled,
                **{
                    meta.lstrip('_'): getattr(t, meta)
                    for meta in ['_distance', '_certainty', '_score']
                    if hasattr(t, meta)
                }
            }
            for t in tools
        ]

    async def cleanup(self):
        """
        Cleanup resources and close Weaviate client connection.
        
        Note: Managed connections auto-close per operation.
        This performs final lifecycle cleanup.
        """
        logger.info("Cleaning up vector search service")

        if self._client and self._client.client:
            try:
                if self._client.client.is_connected():
                    self._client.close()
                    logger.info("Weaviate connection closed")
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

        self._initialized = False
        logger.info("Vector search cleanup complete")
