import logging
from typing import Dict, Any, Optional, List
from packages.db.managers import CollectionManager
from packages.shared.models import McpTool
from packages.db import (
    ConnectionConfig,
    ProviderFactory,
    init_weaviate,
    get_weaviate_client,
    BatchResult,
)
from packages.db.search.filters import Q
from .base import VectorSearchService
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
        try:
            # Use new configuration system
            connection = ConnectionConfig(
                host=REGISTRY_CONSTANTS.WEAVIATE_HOST,
                port=REGISTRY_CONSTANTS.WEAVIATE_PORT,
                api_key=REGISTRY_CONSTANTS.WEAVIATE_API_KEY
            )

            # Get provider from environment (supports IAM Role)
            provider = ProviderFactory.from_env()

            # Initialize client with config objects
            init_weaviate(
                connection=connection,
                provider=provider
            )

            self._client = get_weaviate_client()
            self._initialized = True

            logger.info(
                f"Vector search service initialized with "
                f"{provider.__class__.__name__} "
                f"({provider.get_vectorizer_name()})"
            )

        except Exception as e:
            logger.error(f"Failed to initialize vector search service: {e}")
            self._client = None
            self._initialized = False

    async def initialize(self):
        """
        Initialize Weaviate and ensure MCPTool collection exists.
        """
        if not self._client:
            logger.error("Client not initialized, skipping vector search setup")
            self._initialized = False
            return

        try:
            # Check connection
            if not self._client.is_ready():
                logger.warning("Client not ready, attempting to connect...")
                self._client.ensure_connection()

            # Verify with ping
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

                # Get collection stats
                manager = CollectionManager(self._client)
                stats = manager.get_collection_stats(McpTool)
                if stats:
                    logger.info(
                        f"   Collection has {stats['object_count']} tools, "
                        f"{stats['property_count']} properties"
                    )
            self._initialized = True
            logger.info("Vector search service initialized successfully")

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
            {"indexed_tools": count, "failed": count} or None if unavailable
        """
        if not self._initialized:
            logger.warning(f"Vector search not initialized, skipping '{service_path}'")
            return None

        tool_count = len(server_info.get("tool_list", []))
        logger.info(f"Indexing '{service_path}': {tool_count} tools, enabled={is_enabled}")

        try:
            # Remove existing tools using optimized delete_where
            deleted_count = await self.remove_service(service_path)
            if deleted_count and deleted_count.get('deleted_tools', 0) > 0:
                logger.info(f"Removed {deleted_count['deleted_tools']} old tools")

            # Bulk create new tools
            tools = McpTool.bulk_create_from_server_info(
                service_path=service_path,
                server_info=server_info,
                is_enabled=is_enabled
            )

            # Handle BatchResult (new return type)
            if isinstance(tools, BatchResult):
                result = tools
                logger.info(
                    f"Indexed {result.successful}/{result.total} tools for '{service_path}' "
                    f"(success rate: {result.success_rate:.1f}%)"
                )

                if result.has_errors:
                    logger.warning(f"{result.failed} tools failed to index:")
                    for error in result.errors[:3]:  # Log first 3 errors
                        logger.warning(f"   - {error.get('uuid', 'unknown')}: {error.get('message', 'unknown')}")

                return {
                    "indexed_tools": result.successful,
                    "failed_tools": result.failed
                }
            else:
                # Fallback for old return type (list)
                count = len(tools) if isinstance(tools, list) else 0
                logger.info(f"Indexed {count} tools for '{service_path}'")
                return {"indexed_tools": count, "failed_tools": 0}

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
            deleted_count = McpTool.objects.delete_where(server_path=service_path)
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
        Search tools with semantic/hybrid search.
        
        Uses new search framework:
        - Hybrid search (if query provided)
        - Filtered fetch (if no query)
        - Q objects for complex filtering
        
        Args:
            query: Search text for semantic search
            tags: Tag filters (uses contains_any)
            top_k: Maximum results
            filters: Field filters, e.g., {"is_enabled": True}
            
        Returns:
            List of tool dictionaries with search metadata
            
        Example:
            results = await service.search(
                query="weather forecast",
                tags=["weather", "api"],
                top_k=5,
                filters={"is_enabled": True}
            )
        """
        if not self._initialized:
            logger.warning("Vector search unavailable, returning empty results")
            return []

        logger.info(f"Search: query='{query}', tags={tags}, top_k={top_k}, filters={filters}")

        try:
            # Build query using new QueryBuilder
            query_builder = McpTool.objects

            # Apply field filters using Q objects
            if filters:
                query_builder = query_builder.filter(**filters)

            # Apply tag filters using Q objects
            if tags:
                query_builder = query_builder.filter(tags__contains_any=tags)

            # Execute search
            if query:
                # Hybrid search (70% semantic + 30% keyword)
                tools = query_builder.hybrid(query, alpha=0.7).limit(top_k).all()
            else:
                # Just filtered fetch
                tools = query_builder.limit(top_k).all()

            # Convert to result dicts
            results = self._tools_to_results(tools)

            logger.info(f"Found {len(results)} tools")
            return results

        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return []

    def _tools_to_results(self, tools: List[McpTool]) -> List[Dict[str, Any]]:
        """
        Convert MCPTool model instances to result dictionaries.
        
        Extracts tool data and search metadata (distance, certainty, score).
        
        Args:
            tools: List of MCPTool instances
        
        Returns:
            List of dictionaries with tool data and metadata
        """
        results = []

        for t in tools:
            result = {
                "tool_name": t.tool_name,
                "server_path": t.server_path,
                "server_name": t.server_name,
                "description": t.description_main,
                "description_args": t.description_args,
                "description_returns": t.description_returns,
                "tags": t.tags or [],
                "is_enabled": t.is_enabled,
                "entity_type": t.entity_type or ["all"],
            }

            # Add search metadata if available
            for meta in ['_distance', '_certainty', '_score']:
                if hasattr(t, meta):
                    value = getattr(t, meta)
                    if value is not None:
                        result[meta.lstrip('_')] = value

            results.append(result)

        return results

    def _agent_to_server_info(
        self,
        agent_card_dict: Dict[str, Any],
        entity_path: str
    ) -> Dict[str, Any]:
        """
        Convert AgentCard dictionary to server_info format for McpTool.
        
        Args:
            agent_card_dict: AgentCard data as dictionary
            entity_path: Agent path
            
        Returns:
            server_info dictionary compatible with add_or_update_service
        """
        skills = agent_card_dict.get("skills", [])
        skills_text = ", ".join([
            skill.get("name", "") if isinstance(skill, dict) else str(skill)
            for skill in skills
        ])
        
        return {
            "server_name": agent_card_dict.get("name", entity_path.strip("/")),
            "description": agent_card_dict.get("description", ""),
            "path": entity_path,
            "tags": agent_card_dict.get("tags", []),
            "entity_type": "a2a_agent",
            "skills": skills,
            "tool_list": [],  # Empty list, will create virtual tool in bulk_create_from_server_info
            "is_enabled": agent_card_dict.get("is_enabled", False),
        }

    async def add_or_update_entity(
        self,
        entity_path: str,
        entity_info: Dict[str, Any],
        entity_type: str,
        is_enabled: bool = False,
    ) -> Optional[Dict[str, int]]:
        """
        Add or update an entity (agent or server) in the search index.
        
        Unified interface compatible with EmbeddedFaissService.
        Routes entities to appropriate methods based on entity_type.
        
        Args:
            entity_path: Entity path identifier
            entity_info: Entity data dictionary
            entity_type: Entity type ("a2a_agent" or "mcp_server")
            is_enabled: Whether the entity is enabled
            
        Returns:
            Result dictionary or None if unavailable
        """
        if entity_type == "a2a_agent":
            # Convert AgentCard to server_info format
            server_info = self._agent_to_server_info(entity_info, entity_path)
            # Override is_enabled from parameter
            server_info["is_enabled"] = is_enabled
            return await self.add_or_update_service(entity_path, server_info, is_enabled)
        elif entity_type == "mcp_server":
            # Ensure entity_type is set in server_info
            if "entity_type" not in entity_info:
                entity_info["entity_type"] = "mcp_server"
            return await self.add_or_update_service(entity_path, entity_info, is_enabled)
        else:
            logger.warning(f"Unknown entity_type '{entity_type}', skipping indexing")
            return None

    async def remove_entity(
        self,
        entity_path: str,
    ) -> Optional[Dict[str, int]]:
        """
        Remove an entity (agent or server) from the search index.
        
        Unified interface compatible with EmbeddedFaissService.
        Uses remove_service which works for both agents and servers.
        
        Args:
            entity_path: Entity path identifier
            
        Returns:
            Result dictionary or None if unavailable
        """
        return await self.remove_service(entity_path)

    async def cleanup(self):
        """
        Cleanup resources and close Weaviate client connection.
        
        Uses new client health check and close methods.
        """
        logger.info("Cleaning up vector search service")

        if self._client:
            try:
                if self._client.is_ready():
                    self._client.close()
                    logger.info("Weaviate connection closed")
                else:
                    logger.debug("Client already disconnected")
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

        self._initialized = False
        logger.info("Vector search cleanup complete")

    async def search_mixed(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        max_results: int = 20,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search across multiple entity types: servers, tools, and agents.
        
        Uses Weaviate's search capabilities to query McpTool collection
        based on entity_type field. All data is stored in McpTool with
        entity_type field indicating which types the tool belongs to.
        
        Args:
            query: Natural language query text
            entity_types: List of entity types to search
                Options: ["mcp_server", "tool", "a2a_agent"]
                Default: all types
            max_results: Maximum results per entity type (default: 20)
        
        Returns:
            Dictionary with entity type keys and result lists:
            {
                "servers": [...],  # MCP server results
                "tools": [...],    # Tool results  
                "agents": [...]    # A2A agent results
            }
        """
        if not self._initialized:
            logger.warning("Vector search not initialized")
            return {"servers": [], "tools": [], "agents": []}
        
        if not query or not query.strip():
            raise ValueError("Query text is required for search_mixed")
        
        # Validate and normalize entity types
        max_results = max(1, min(max_results, 50))
        requested_types = set(entity_types or ["mcp_server", "tool", "a2a_agent"])
        allowed_types = {"mcp_server", "tool", "a2a_agent"}
        entity_filter = list(requested_types & allowed_types)
        
        if not entity_filter:
            entity_filter = list(allowed_types)
        
        logger.info(
            f"search_mixed: query='{query}', types={entity_filter}, "
            f"max={max_results}"
        )
        results = {
            "servers": [],
            "tools": [],
            "agents": []
        }
        try:
            # Query already filters by entity_type, so returned tools match the requested types
            entity_type_filter = (Q(entity_type__contains_any=entity_filter)
                                  | Q(entity_type__contains_any=["all"]))
            tools = McpTool.objects.filter(
                is_enabled=True
            ).filter(entity_type_filter).hybrid(query, alpha=0.7).limit(max_results).all()
            
            # Query already filtered by entity_filter, so all returned tools match
            # Just categorize results based on what was requested in entity_filter
            for tool in tools:
                # Calculate relevance score
                relevance = 0.8  # Default
                if hasattr(tool, '_score'):
                    relevance = tool._score
                elif hasattr(tool, '_distance'):
                    relevance = 1.0 - min(1.0, tool._distance)
                elif hasattr(tool, '_certainty'):
                    relevance = tool._certainty
                
                match_context = (
                    tool.combined_text[:200] 
                    if hasattr(tool, 'combined_text') and tool.combined_text 
                    else tool.description_main[:200]
                )
                
                # Build result dict using tool's fields, including entity_type
                result = {
                    "server_path": tool.server_path,
                    "server_name": tool.server_name,
                    "tool_name": tool.tool_name,
                    "description": tool.description_main,
                    "match_context": match_context,
                    "relevance_score": relevance,
                    "entity_type": tool.entity_type or ["all"],
                }
                
                # Add search metadata if available
                for meta in ['_distance', '_certainty', '_score']:
                    if hasattr(tool, meta):
                        value = getattr(tool, meta)
                        if value is not None:
                            result[meta.lstrip('_')] = value
                
                # Add to results based on what was requested
                if "tool" in entity_filter:
                    results["tools"].append(result)
                
                if "mcp_server" in entity_filter:
                    server_result = result.copy()
                    server_result["path"] = tool.server_path
                    server_result["description"] = tool.description_main[:100] if tool.description_main else ""
                    server_result["tags"] = tool.tags or []
                    server_result["is_enabled"] = tool.is_enabled
                    results["servers"].append(server_result)
                
                if "a2a_agent" in entity_filter:
                    agent_result = result.copy()
                    agent_result["path"] = tool.server_path
                    agent_result["agent_name"] = tool.server_name
                    agent_result["tags"] = tool.tags or []
                    agent_result["is_enabled"] = tool.is_enabled
                    results["agents"].append(agent_result)
            
            # Sort results by relevance and limit
            results["tools"].sort(key=lambda x: x["relevance_score"], reverse=True)
            results["tools"] = results["tools"][:max_results]
            results["servers"].sort(key=lambda x: x["relevance_score"], reverse=True)
            results["servers"] = results["servers"][:max_results]
            results["agents"].sort(key=lambda x: x["relevance_score"], reverse=True)
            results["agents"] = results["agents"][:max_results]
            
            logger.info(
                f"Found {len(results['tools'])} tools, "
                f"{len(results['servers'])} servers, "
                f"{len(results['agents'])} agents"
            )
            return results
            
        except Exception as e:
            logger.error(f"search_mixed failed: {e}", exc_info=True)
            return {"servers": [], "tools": [], "agents": []}
