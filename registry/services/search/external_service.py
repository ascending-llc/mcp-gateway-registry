from typing import Dict, Any, Optional, List
from packages.vector import initialize_database
from packages.vector.enum.enums import SearchType, RerankerProvider
from packages.models.mcp_tool import McpTool
from vector import get_search_index_manager
from .base import VectorSearchService
from registry.utils.log import logger

search_mgr = get_search_index_manager()


class ExternalVectorSearchService(VectorSearchService):
    """
    Vector search service with rerank support.
    """

    def __init__(
            self,
            enable_rerank: bool = True,
            search_type: SearchType = SearchType.HYBRID,
            reranker_model: str = "ms-marco-TinyBERT-L-2-v2"
    ):
        """
        Initialize vector search service with rerank support.
        
        Args:
            enable_rerank: Enable reranking (default: True)
            search_type: Default search type (NEAR_TEXT, BM25, HYBRID)
            reranker_model: FlashRank model name
        """
        self.enable_rerank = enable_rerank
        self.search_type = search_type
        self.reranker_model = reranker_model

        try:
            self._client = initialize_database()
            self._mcp_tools = self._client.for_model(McpTool)
            self._initialized = True

            logger.info(f"Vector search service initialized: "
                        f"rerank={enable_rerank}, search_type={search_type.value}")
        except Exception as e:
            self._client = None
            self._mcp_tools = None
            self._initialized = False
            logger.error(f"Failed to initialize vector search service: {e}")

    async def initialize(self):
        """
        Initialize vector database and ensure MCPTool collection exists.
        """
        if not self._initialized:
            logger.error("Model operations not initialized, skipping vector search setup")
            return
        logger.info("Vector search service initialized successfully")

    def get_retriever(
            self,
            search_type: Optional[SearchType] = None,
            enable_rerank: Optional[bool] = None,
            top_k: int = 10
    ):
        """
        Get a LangChain retriever (with optional rerank) for RAG applications.
        
        Similar to BedrockRerank usage:
        - Creates base retriever
        - Optionally wraps with ContextualCompressionRetriever for reranking
        
        Args:
            search_type: Search type (uses default if None)
            enable_rerank: Enable rerank (uses instance setting if None)
            top_k: Number of results to return
            
        Returns:
            BaseRetriever or ContextualCompressionRetriever

        """
        if not self._initialized:
            raise Exception("Vector search service not initialized")

        use_rerank = enable_rerank if enable_rerank is not None else self.enable_rerank
        use_search_type = search_type or self.search_type

        if use_rerank:
            # Return compression retriever with rerank
            return self._mcp_tools.get_compression_retriever(
                reranker_type=RerankerProvider.FLASHRANK,
                search_type=use_search_type,
                search_kwargs={"k": top_k * 3},  # 3x candidates
                reranker_kwargs={
                    "top_k": top_k,
                    "model": self.reranker_model
                }
            )
        else:
            # Return base retriever without rerank
            return self._mcp_tools.get_retriever(
                search_type=use_search_type,
                k=top_k
            )

    async def add_or_update_service(
            self,
            service_path: str,
            server_info: Dict[str, Any],
            is_enabled: bool = False
    ) -> Optional[Dict[str, int]]:
        """
        Add or update tools for a service with vector database.

        Args:
            service_path: Service path (e.g., /weather)
            server_info: Server info with tool_list
            is_enabled: Whether service is enabled

        Returns:
            {"indexed_tools": count, "failed_tools": count} or None if unavailable
        """
        return await search_mgr.add_or_update_entity(
            entity_path=service_path,
            entity_info=server_info,
            entity_type="mcp_server",
            is_enabled=is_enabled
        )

    async def remove_service(self, service_path: str) -> Optional[Dict[str, int]]:
        """
        Remove all tools for a service.
        
        **Delegates to SearchIndexManager for efficient index management.**

        Args:
            service_path: Service path identifier

        Returns:
            {"deleted_tools": count} or None if service unavailable
        """
        return await search_mgr.remove_entity(service_path)

    async def search(
            self,
            query: Optional[str] = None,
            tags: Optional[List[str]] = None,
            top_k: int = 10,
            filters: Optional[Dict[str, Any]] = None,
            search_type: Optional[SearchType] = None
    ) -> List[Dict[str, Any]]:
        """
        Search tools with optional reranking.

        Args:
            query: Search text for semantic search
            tags: Tag filters (applied in-memory)
            top_k: Maximum results
            filters: Field filters (dict format, converted to native)
            search_type: Override default search type (NEAR_TEXT, BM25, HYBRID)

        Returns:
            List of tool dictionaries with search metadata
        """
        if not self._initialized:
            logger.warning("Vector search unavailable, returning empty results")
            return []

        use_search_type = search_type or self.search_type
        logger.info(f"Search: query='{query}', tags={tags}, top_k={top_k}, "
                    f"filters={filters}, search_type={use_search_type}")

        try:
            if not query:
                # Metadata-only filter
                if not filters:
                    logger.warning("No query and no filters provided")
                    return []
                tools = self._mcp_tools.filter(
                    filters=filters,
                    limit=top_k * 2 if tags else top_k
                )
            elif self.enable_rerank:
                # Use rerank - Repository layer handles candidate_k automatically
                candidate_k = min(top_k * 3, 100)
                if tags:
                    candidate_k = min(candidate_k * 2, 150)

                logger.info(f"Using rerank: type={use_search_type.value}, "
                            f"candidate_k={candidate_k}, k={top_k * 2 if tags else top_k}")
                tools = self._mcp_tools.search_with_rerank(
                    query=query,
                    search_type=use_search_type,
                    k=top_k * 2 if tags else top_k,
                    candidate_k=candidate_k,
                    filters=filters,
                    reranker_type=RerankerProvider.FLASHRANK,
                    reranker_kwargs={"model": self.reranker_model}
                )
            else:
                # Regular search without rerank
                tools = self._mcp_tools.search(
                    query=query,
                    search_type=use_search_type,
                    k=top_k * 2 if tags else top_k,
                    filters=filters
                )

            # Apply tag filtering if needed (in-memory)
            if tags:
                filtered_tools = []
                for tool in tools:
                    tool_tags = tool.tags or []
                    if any(tag in tool_tags for tag in tags):
                        filtered_tools.append(tool)
                tools = filtered_tools[:top_k]
            else:
                tools = tools[:top_k]

            # Convert to result dicts
            results = self._tools_to_results(tools)
            logger.info(f"Found {len(results)} tools (rerank={'ON' if self.enable_rerank else 'OFF'})")
            return results

        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return []

    def _tools_to_results(self, tools: List[McpTool]) -> List[Dict[str, Any]]:
        """
        Convert MCPTool model instances to result dictionaries.

        Extracts tool data and search metadata.

        Args:
            tools: List of MCPTool instances

        Returns:
            List of dictionaries with tool data and metadata
        """
        results = []

        for tool in tools:
            logger.info(f"Processing tool: {tool}")
            relevance_score = round(tool.relevance_score, 4)
            result = {
                "tool_name": tool.tool_name,
                "server_path": tool.server_path,
                "server_name": tool.server_name,
                "description": tool.description_main,
                "description_args": tool.description_args,
                "description_returns": tool.description_returns,
                "tags": tool.tags or [],
                "is_enabled": tool.is_enabled,
                "entity_type": tool.entity_type or ["all"],
                "relevance_score": relevance_score,  # Always set relevance_score
            }

            # Add score field if available
            if hasattr(tool, 'score') and tool.score is not None:
                result['score'] = tool.score
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
            server_info["is_enabled"] = is_enabled
            return await search_mgr.add_or_update_entity(
                entity_path=entity_path,
                entity_info=server_info,
                entity_type="a2a_agent",
                is_enabled=is_enabled
            )
        elif entity_type == "mcp_server":
            # Ensure entity_type is set
            if "entity_type" not in entity_info:
                entity_info["entity_type"] = "mcp_server"
            return await search_mgr.add_or_update_entity(
                entity_path=entity_path,
                entity_info=entity_info,
                entity_type="mcp_server",
                is_enabled=is_enabled
            )
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
        
        Args:
            entity_path: Entity path identifier
            
        Returns:
            Result dictionary or None if unavailable
        """
        return await search_mgr.remove_entity(entity_path)

    async def cleanup(self):
        """
        Cleanup resources and close database client connection.
        """
        logger.info("Cleaning up vector search service")

        if self._initialized:
            try:
                # Close the database client
                self._client.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

        self._client = None
        self._mcp_tools = None
        self._initialized = False
        logger.info("Vector search cleanup complete")

    async def search_mixed(
            self,
            query: str,
            entity_types: Optional[List[str]] = None,
            max_results: int = 20,
            search_type: Optional[SearchType] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search across multiple entity types with rerank support.

        Searches servers, tools, and agents with improved relevance.

        Args:
            query: Natural language query text
            entity_types: List of entity types to search
                Options: ["mcp_server", "tool", "a2a_agent"]
                Default: all types
            max_results: Maximum results per entity type (default: 20)
            search_type: Override default search type (NEAR_TEXT, BM25, HYBRID)

        Returns:
            Dictionary with entity type keys and result lists
        """
        if not self._mcp_tools:
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

        logger.info(f"search_mixed: query='{query}', types={entity_filter}, "
                    f"max={max_results}, search_type={search_type or self.search_type}")

        use_search_type = search_type or self.search_type
        results = {
            "servers": [],
            "tools": [],
            "agents": []
        }

        try:
            # Calculate search parameters
            search_k = max_results * 2  # Get 2x for entity filtering
            candidate_k = min(search_k * 3, 100) if self.enable_rerank else search_k

            # Use rerank if enabled
            if self.enable_rerank:
                logger.info(
                    f"Mixed search with rerank: type={use_search_type.value}, "
                    f"candidate_k={candidate_k}, k={search_k}"
                )
                tools = self._mcp_tools.search_with_rerank(
                    query=query,
                    search_type=use_search_type,
                    k=search_k,
                    candidate_k=candidate_k,
                    reranker_type=RerankerProvider.FLASHRANK,
                    reranker_kwargs={"model": self.reranker_model}
                )
            else:
                # Regular search without rerank
                tools = self._mcp_tools.search(
                    query=query,
                    search_type=use_search_type,
                    k=search_k
                )

            # Filter and categorize results
            for tool in tools:
                tool_entity_types = set(tool.entity_type or ["all"])

                # Check if this tool matches any of the requested entity types
                if not (tool_entity_types & set(entity_filter) or "all" in tool_entity_types):
                    continue

                match_context = (
                    tool.content[:200]
                    if tool.content
                    else tool.description_main[:200]
                )
                relevance_score = round(tool.relevance_score, 4)
                # Build result dict
                result = {
                    "server_path": tool.server_path,
                    "server_name": tool.server_name,
                    "tool_name": tool.tool_name,
                    "description": tool.description_main,
                    "match_context": match_context,
                    "relevance_score": relevance_score,
                    "entity_type": tool.entity_type or ["all"]
                }
                # Add to results based on entity types
                if "tool" in entity_filter and ("tool" in tool_entity_types or "all" in tool_entity_types):
                    results["tools"].append(result)

                if "mcp_server" in entity_filter and ("mcp_server" in tool_entity_types or "all" in tool_entity_types):
                    server_result = result.copy()
                    server_result["path"] = tool.server_path
                    server_result["description"] = tool.description_main[:100] if tool.description_main else ""
                    server_result["tags"] = tool.tags or []
                    server_result["is_enabled"] = tool.is_enabled
                    results["servers"].append(server_result)

                if "a2a_agent" in entity_filter and ("a2a_agent" in tool_entity_types or "all" in tool_entity_types):
                    agent_result = result.copy()
                    agent_result["path"] = tool.server_path
                    agent_result["agent_name"] = tool.server_name
                    agent_result["tags"] = tool.tags or []
                    agent_result["is_enabled"] = tool.is_enabled
                    results["agents"].append(agent_result)

            # Sort and limit results
            for key in ["tools", "servers", "agents"]:
                # Sort by relevance_score (with fallback to 0.0 for safety)
                results[key].sort(
                    key=lambda x: x.get("relevance_score", 0.0),
                    reverse=True
                )
                results[key] = results[key][:max_results]

            logger.info(f"Found {len(results['tools'])} tools, "
                        f"{len(results['servers'])} servers, "
                        f"{len(results['agents'])} agents "
                        f"(rerank={'ON' if self.enable_rerank else 'OFF'})")
            return results

        except Exception as e:
            logger.error(f"search_mixed failed: {e}", exc_info=True)
            return {"servers": [], "tools": [], "agents": []}
