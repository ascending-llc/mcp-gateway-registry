import logging
from typing import Annotated, List, Literal, Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request

from registry.services.search.service import faiss_service
from ..services.agent_service import agent_service
from ..schemas.errors import ErrorCode, create_error_detail

logger = logging.getLogger(__name__)

router = APIRouter()

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
    "/semantic",
    response_model=SemanticSearchResponse,
    summary="Unified semantic search for MCP servers and tools",
)
async def semantic_search(
        request: Request,
        search_request: SemanticSearchRequest,
) -> SemanticSearchResponse:
    """
    Run a semantic search against MCP servers (and their tools) using FAISS embeddings.
    """
    if not request.state.is_authenticated:
        raise HTTPException(
            status_code=401,
            detail=create_error_detail(
                ErrorCode.AUTHENTICATION_REQUIRED,
                "Not authenticated"
            )
        )
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_error_detail(
                ErrorCode.INVALID_REQUEST,
                str(exc)
            )
        ) from exc
    except RuntimeError as exc:
        logger.error("FAISS search service unavailable: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=create_error_detail(
                ErrorCode.SERVICE_UNAVAILABLE,
                "Semantic search is temporarily unavailable. Please try again later."
            )
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
