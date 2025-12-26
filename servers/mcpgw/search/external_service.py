import logging
import json
from typing import List, Dict, Any, Optional
from packages.db import initialize_database
from packages.db.enum.enums import SearchType, RerankerProvider
from packages.shared.models import McpTool
from .base import VectorSearchService

logger = logging.getLogger(__name__)


class ExternalVectorSearchService(VectorSearchService):
    """
    External vector search service with rerank support.
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
            logger.error(f"Failed to initialize vector search: {e}")
            self._client = None
            self._mcp_tools = None
            self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize and verify database connection.
        
        Checks adapter status and collection availability.
        """
        if not self._initialized:
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

    def get_retriever(
            self,
            search_type: Optional[SearchType] = None,
            enable_rerank: Optional[bool] = None,
            top_k: int = 10
    ):
        """
        Get a LangChain retriever (with optional rerank) for RAG applications.
        
        Similar to BedrockRerank usage pattern:
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

    async def search_tools(
            self,
            query: Optional[str] = None,
            tags: Optional[List[str]] = None,
            user_scopes: Optional[List[str]] = None,
            top_k_services: int = 3,
            top_n_tools: int = 10,
            search_type: Optional[SearchType] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for tools with optional reranking.
        
        Uses repository API with rerank support for improved relevance.

        Args:
            query: Search query text
            tags: List of tags to filter by
            user_scopes: User scopes for access control (not implemented)
            top_k_services: Max services (not used in new architecture)
            top_n_tools: Maximum number of tools to return
            search_type: Search type (NEAR_TEXT, BM25, HYBRID), uses default if None

        Returns:
            List of formatted tool dictionaries
        """
        if not self._initialized:
            raise Exception("Vector search service not initialized")

        if not query and not tags:
            raise Exception("At least one of 'query' or 'tags' must be provided")

        use_search_type = search_type or self.search_type
        logger.info(
            f"Searching tools: query='{query}', tags={tags}, limit={top_n_tools}, "
            f"search_type={use_search_type}"
        )

        try:
            filter_conditions = {"is_enabled": True}

            if not query:
                # Metadata-only filter
                tools = self._mcp_tools.filter(
                    filters=filter_conditions,
                    limit=top_n_tools * 2 if tags else top_n_tools
                )
            elif self.enable_rerank:
                # Use rerank - Repository layer handles logic automatically
                candidate_k = min(top_n_tools * 3, 100)
                if tags:
                    candidate_k = min(candidate_k * 2, 150)

                logger.info(f"Using rerank: type={use_search_type.value}, "
                            f"candidate_k={candidate_k}, k={top_n_tools * 2 if tags else top_n_tools}")
                tools = self._mcp_tools.search_with_rerank(
                    query=query,
                    search_type=use_search_type,
                    k=top_n_tools * 2 if tags else top_n_tools,
                    candidate_k=candidate_k,
                    filters=filter_conditions,
                    reranker_type=RerankerProvider.FLASHRANK,
                    reranker_kwargs={"model": self.reranker_model}
                )
            else:
                # Regular search without rerank
                tools = self._mcp_tools.search(
                    query=query,
                    search_type=use_search_type,
                    k=top_n_tools * 2 if tags else top_n_tools,
                    filters=filter_conditions
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

            logger.info(f"Search returned {len(tools)} tools (rerank={'ON' if self.enable_rerank else 'OFF'})")

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
        
        Handles both regular search and rerank scores.
        
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
            similarity_score = round(float(tool.relevance_score), 4)
            formatted_tool = {
                "tool_name": tool.tool_name,
                "tool_parsed_description": parsed_description,
                "tool_schema": schema,
                "service_path": tool.server_path,
                "service_name": tool.server_name,
                "supported_transports": ["streamable-http"],
                "auth_provider": None,
                "overall_similarity_score": similarity_score,
                "similarity_score": similarity_score,
            }
            logger.info(f"Formatted tool: {tool}")
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
