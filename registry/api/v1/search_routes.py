import logging
from typing import List, Literal, Optional
from registry.auth.dependencies import CurrentUser
from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request

from registry.services.search.service import faiss_service
from registry.core.telemetry_decorators import (
    track_registry_operation,
    track_tool_discovery,
)
from packages.vector.enum.enums import SearchType
from registry.schemas.server_api_schemas import convert_to_detail
from registry.services.server_service import server_service_v1
from packages.vector.repositories.mcp_server_repository import get_mcp_server_repo
from ...services.agent_service import agent_service

logger = logging.getLogger(__name__)

router = APIRouter()

mcp_server_repo = get_mcp_server_repo()

EntityType = Literal["mcp_server", "tool", "a2a_agent"]


class MatchingToolResult(BaseModel):
    tool_name: str
    description: Optional[str] = None
    relevance_score: float = Field(0.0, ge=0.0, le=1.0)
    match_context: Optional[str] = None


class ServerSearchResult(BaseModel):
    path: str
    server_name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    num_tools: int = 0
    is_enabled: bool = False
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    match_context: Optional[str] = None
    matching_tools: List[MatchingToolResult] = Field(default_factory=list)


class ToolSearchResult(BaseModel):
    server_path: str
    server_name: str
    tool_name: str
    description: Optional[str] = None
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    match_context: Optional[str] = None


class AgentSearchResult(BaseModel):
    path: str
    agent_name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    trust_level: Optional[str] = None
    visibility: Optional[str] = None
    is_enabled: bool = False
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    match_context: Optional[str] = None


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512, description="Natural language query")
    entity_types: Optional[List[EntityType]] = Field(
        default=None, description="Optional entity filters"
    )
    max_results: int = Field(
        default=10, ge=1, le=50, description="Maximum results per entity collection"
    )


class SemanticSearchResponse(BaseModel):
    query: str
    servers: List[ServerSearchResult] = Field(default_factory=list)
    tools: List[ToolSearchResult] = Field(default_factory=list)
    agents: List[AgentSearchResult] = Field(default_factory=list)
    total_servers: int = 0
    total_tools: int = 0
    total_agents: int = 0


def _user_can_access_agent(agent_path: str, user_context: dict) -> bool:
    """Validate user access for a given agent."""
    if user_context.get("is_admin"):
        return True

    accessible_agents = user_context.get("accessible_agents") or []
    if "all" not in accessible_agents and agent_path not in accessible_agents:
        return False

    agent_card = agent_service.get_agent_info(agent_path)
    if not agent_card:
        return False

    if agent_card.visibility == "public":
        return True

    if agent_card.visibility == "private":
        return agent_card.registered_by == user_context.get("username")

    if agent_card.visibility == "group-restricted":
        allowed_groups = set(agent_card.allowed_groups)
        user_groups = set(user_context.get("groups", []))
        return bool(allowed_groups & user_groups)

    return False


@router.post(
    "/search/semantic",
    response_model=SemanticSearchResponse,
    summary="Unified semantic search for MCP servers and tools",
)
@track_registry_operation("search", resource_type="semantic")
async def semantic_search(
        request: Request,
        search_request: SemanticSearchRequest,
) -> SemanticSearchResponse:
    """
    Run a semantic search against MCP servers (and their tools) using FAISS embeddings.
    """
    if not request.state.is_authenticated:
        raise HTTPException(detail="Not authenticated", status_code=401)
    user_context = request.state.user
    logger.info(
        "Semantic search requested by %s (entities=%s, max=%s)",
        user_context.get("username"),
        search_request.entity_types or ["mcp_server", "tool"],
        search_request.max_results,
    )

    try:
        raw_results = await faiss_service.search_mixed(
            query=search_request.query,
            entity_types=search_request.entity_types,
            max_results=search_request.max_results,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        logger.error("FAISS search service unavailable: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Semantic search is temporarily unavailable. Please try again later.",
        ) from exc

    filtered_servers: List[ServerSearchResult] = []
    for server in raw_results.get("servers", []):
        matching_tools = [
            MatchingToolResult(
                tool_name=tool.get("tool_name", ""),
                description=tool.get("description"),
                relevance_score=tool.get("relevance_score", 0.0),
                match_context=tool.get("match_context"),
            )
            for tool in server.get("matching_tools", [])
        ]

        filtered_servers.append(
            ServerSearchResult(
                path=server.get("path", ""),
                server_name=server.get("server_name", ""),
                description=server.get("description"),
                tags=server.get("tags", []),
                num_tools=server.get("num_tools", 0),
                is_enabled=server.get("is_enabled", False),
                relevance_score=server.get("relevance_score", 0.0),
                match_context=server.get("match_context"),
                matching_tools=matching_tools,
            )
        )

    filtered_tools: List[ToolSearchResult] = []
    for tool in raw_results.get("tools", []):
        server_path = tool.get("server_path", "")
        server_name = tool.get("server_name", "")
        filtered_tools.append(
            ToolSearchResult(
                server_path=server_path,
                server_name=server_name,
                tool_name=tool.get("tool_name", ""),
                description=tool.get("description"),
                relevance_score=tool.get("relevance_score", 0.0),
                match_context=tool.get("match_context"),
            )
        )

    filtered_agents: List[AgentSearchResult] = []
    for agent in raw_results.get("agents", []):
        agent_path = agent.get("path", "")
        if not agent_path:
            continue

        if not _user_can_access_agent(agent_path, user_context):
            continue

        agent_card_obj = agent_service.get_agent_info(agent_path)
        agent_card_dict = (
            agent_card_obj.model_dump()
            if agent_card_obj
            else agent.get("agent_card", {})
        )

        tags = agent_card_dict.get("tags", []) or agent.get("tags", [])
        raw_skills = agent_card_dict.get("skills", []) or agent.get("skills", [])
        skills = [
            skill.get("name")
            if isinstance(skill, dict)
            else skill
            for skill in raw_skills
        ]

        filtered_agents.append(
            AgentSearchResult(
                path=agent_path,
                agent_name=agent_card_dict.get(
                    "name", agent.get("agent_name", agent_path.strip("/"))
                ),
                description=agent_card_dict.get(
                    "description", agent.get("description")
                ),
                tags=tags or [],
                skills=[s for s in skills if s],
                trust_level=agent_card_dict.get("trust_level"),
                visibility=agent_card_dict.get("visibility"),
                is_enabled=agent_card_dict.get("is_enabled", False),
                relevance_score=agent.get("relevance_score", 0.0),
                match_context=agent.get("match_context")
                              or agent_card_dict.get("description"),
            )
        )

    return SemanticSearchResponse(
        query=search_request.query.strip(),
        servers=filtered_servers,
        tools=filtered_tools,
        agents=filtered_agents,
        total_servers=len(filtered_servers),
        total_tools=len(filtered_tools),
        total_agents=len(filtered_agents),
    )


class ToolDiscoveryMatch(BaseModel):
    """A discovered tool with metadata for execution"""
    tool_name: str
    server_id: str
    server_path: str
    description: Optional[str] = None
    input_schema: Optional[dict] = None
    discovery_score: float = Field(..., ge=0.0, le=1.0)
    transport_type: str = "streamable-http"


class ToolDiscoveryResponse(BaseModel):
    """Response from tool discovery"""
    query: str
    total_matches: int
    matches: List[ToolDiscoveryMatch]


@router.post("/search/tools")
@track_tool_discovery(extract_query=lambda body, **kw: body.get("query", "unknown"))
async def discover_tools(
        request: Request,
        body: dict,
        user_context: CurrentUser
) -> ToolDiscoveryResponse:
    """    
    Request body:
    {
        "query": "search GitHub pull requests",
        "top_n": 5
    }
    
    Returns:
    {
        "query": "search GitHub pull requests",
        "total_matches": 2,
        "matches": [
            {
                "tool_name": "search_pull_requests",
                "server_name": "github-copilot",
                "server_path": "/github",
                "description": "Search for pull requests...",
                "input_schema": {...},
                "discovery_score": 0.9902,
                "transport_type": "streamable-http"
            }
        ]
    }
    """
    query = body.get("query", "")
    top_n = body.get("top_n", 5)

    if not query:
        raise HTTPException(
            status_code=400,
            detail="query parameter is required"
        )

    logger.info(f"🔍 Tool discovery from user '{user_context.get('username', 'unknown')}': '{query}'")

    # PROTOTYPE: Hard-code Tavily Search server discovery
    # In production, this would query your intelligent_tool_finder service

    tavily_server_path = "/tavilysearch"
    tavily_tools = [
        {
            "tool_name": "tavily_search",
            "description": "Search the web using Tavily's AI-powered search engine",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "max_results": {"type": "integer", "description": "Maximum number of results to return",
                                    "default": 5},
                    "search_depth": {"type": "string", "enum": ["basic", "advanced"], "description": "Search depth",
                                     "default": "basic"},
                    "include_domains": {"type": "array", "items": {"type": "string"},
                                        "description": "Domains to include in search"},
                    "exclude_domains": {"type": "array", "items": {"type": "string"},
                                        "description": "Domains to exclude from search"}
                },
                "required": ["query"]
            },
            "discovery_score": 0.9952
        },
        {
            "tool_name": "tavily_extract",
            "description": "Extract content from specific URLs using Tavily",
            "input_schema": {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of URLs to extract content from"
                    }
                },
                "required": ["urls"]
            },
            "discovery_score": 0.9958
        },
        {
            "tool_name": "tavily_map",
            "description": "Map and analyze a website's structure using Tavily",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to map"}
                },
                "required": ["url"]
            },
            "discovery_score": 0.9963
        },
        {
            "tool_name": "tavily_crawl",
            "description": "Crawl a website to gather comprehensive information",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to crawl"},
                    "max_depth": {"type": "integer", "description": "Maximum crawl depth", "default": 2}
                },
                "required": ["url"]
            },
            "discovery_score": 0.9955
        }
    ]

    # Filter based on query keywords (simple prototype logic)
    query_lower = query.lower()
    matches = []

    for tool in tavily_tools[:top_n]:
        # Simple keyword matching for prototype
        tool_desc_lower = tool["description"].lower()
        tool_name_lower = tool["tool_name"].lower()

        # Boost score if query matches tool name or description
        score = tool["discovery_score"]
        if any(word in tool_name_lower or word in tool_desc_lower
               for word in query_lower.split()):
            score = min(1.0, score + 0.1)

        matches.append(
            ToolDiscoveryMatch(
                tool_name=tool["tool_name"],
                server_id="6972e222755441652c23090f",
                server_path=tavily_server_path,
                description=tool["description"],
                input_schema=tool["input_schema"],
                discovery_score=score,
                transport_type="streamable-http"
            )
        )

    # Sort by score
    matches.sort(key=lambda x: x.discovery_score, reverse=True)

    logger.info(f"✅ Found {len(matches)} tools for query: '{query}'")

    return ToolDiscoveryResponse(
        query=query,
        total_matches=len(matches),
        matches=matches
    )


@router.post("/search/servers")
@track_registry_operation("search", resource_type="server")
async def search_servers(
        request: Request,
        body: dict,
        user_context: CurrentUser
):
    """
    Search for MCP servers with their tools, resources, and prompts.
    POC endpoint returning raw JSON with dual-format tool definitions.
    
    Request body:
    {
        "query": "search",
        "top_n": 5,
        "search_type": "hybrid",  # Optional: "near_text", "bm25", or "hybrid" (default: "hybrid")
        "include_disabled": false  # Optional: include disabled servers (default: false)
    }
    
    Returns raw JSON that can be converted to ExtendedMCPServer format.
    """
    query = body.get("query", "")
    top_n = body.get("top_n", 10)

    # Get search_type from body or use default (hybrid)
    search_type_str = body.get("search_type", "hybrid").lower()
    search_type_mapping = {
        "near_text": SearchType.NEAR_TEXT,
        "bm25": SearchType.BM25,
        "hybrid": SearchType.HYBRID,
        "similarity_store": SearchType.SIMILARITY_STORE
    }
    search_type = search_type_mapping.get(search_type_str, SearchType.HYBRID)

    if search_type_str not in search_type_mapping:
        logger.warning(f"Invalid search_type '{search_type_str}', using HYBRID")

    logger.info(f"🔍 Server search from user '{user_context.get('username', 'unknown')}': "
                f"query='{query}', top_n={top_n}, search_type={search_type}")

    # Search with reranking using specialized repository
    search_results = await mcp_server_repo.asearch_with_rerank(
        query=query,
        k=top_n,
        candidate_k=min(top_n * 5, 100),  # Fetch 5x candidates for reranking (max 100)
        search_type=search_type,
    )

    logger.info(
        "Search completed: %d results for query=%r",
        len(search_results),
        query,
    )

    # Convert search results to server details
    servers = []
    for search_result in search_results:
        server_id = search_result.get("server_id")
        if server_id:
            server = await server_service_v1.get_server_by_id(server_id=server_id)
            if server:
                servers.append(convert_to_detail(server))

    logger.info(f"✅ Found {len(servers)} servers")

    return {
        "query": query,
        "total": len(servers),
        "servers": servers
    }
