"""
A2A Agent API routes for MCP Gateway Registry.

This module provides REST API endpoints for agent registration, discovery,
and management following the A2A protocol specification.

Based on: docs/design/a2a-protocol-integration.md
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Dict, List, Optional, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
)
from fastapi.responses import JSONResponse
import httpx

from ..auth.dependencies import nginx_proxied_auth, SCOPES_CONFIG
from ..services.agent_service import agent_service
from ..schemas.agent_models import (
    AgentCard,
    AgentInfo,
    AgentProvider,
    AgentRegistrationRequest,
)
from pydantic import BaseModel
from ..core.config import settings


# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


router = APIRouter()


async def _perform_agent_security_scan_on_registration(
    path: str,
    agent_card: AgentCard,
    agent_card_dict: dict,
) -> bool:
    """Perform security scan on newly registered agent.

    Handles the complete security scan workflow including:
    - Running the security scan with configured analyzers
    - Adding security-pending tag if scan fails
    - Disabling agent if configured and scan fails
    - Updating FAISS with disabled state if agent disabled

    All scan failures are non-fatal and will be logged but not raised.

    Args:
        path: Agent path (e.g., /code-reviewer)
        agent_card: AgentCard Pydantic model instance
        agent_card_dict: Agent card as dictionary for scanning

    Returns:
        bool: True if agent should remain enabled, False if disabled due to scan
    """
    from ..services.agent_scanner import agent_scanner_service
    from ..search.service import faiss_service

    scan_config = agent_scanner_service.get_scan_config()
    if not (scan_config.enabled and scan_config.scan_on_registration):
        return True  # Agent remains enabled

    logger.info(f"Running A2A security scan for newly registered agent: {path}")

    try:
        # Run the security scan
        scan_result = await agent_scanner_service.scan_agent(
            agent_card=agent_card_dict,
            agent_path=path,
            analyzers=scan_config.analyzers,
            api_key=scan_config.llm_api_key,
            timeout=scan_config.scan_timeout_seconds,
        )

        # Handle unsafe agents
        if not scan_result.is_safe:
            logger.warning(
                f"Agent {path} failed security scan. "
                f"Critical: {scan_result.critical_issues}, High: {scan_result.high_severity}"
            )

            # Add security-pending tag if configured
            if scan_config.add_security_pending_tag:
                current_tags = agent_card.tags or []
                if "security-pending" not in current_tags:
                    current_tags.append("security-pending")
                    agent_card.tags = current_tags
                    # Update agent with new tags
                    agent_info = agent_service.get_agent_info(path)
                    if agent_info:
                        updated_card = agent_info.model_dump()
                        updated_card["tags"] = current_tags
                        from ..schemas.agent_models import AgentCard as AgentCardModel

                        agent_service.register_agent(AgentCardModel(**updated_card))
                    logger.info(f"Added 'security-pending' tag to agent {path}")

            # Disable agent if configured
            if scan_config.block_unsafe_agents:
                agent_service.toggle_agent(path, False)
                logger.warning(f"Disabled agent {path} due to failed security scan")

                # Update FAISS with disabled state
                await faiss_service.add_or_update_entity(
                    path, agent_card_dict, "a2a_agent", False
                )
                return False  # Agent disabled

        else:
            logger.info(f"Agent {path} passed security scan")

        return True  # Agent remains enabled

    except Exception as e:
        logger.error(f"Failed to run security scan for agent {path}: {e}")
        # Non-fatal error - agent is registered but not scanned
        return True  # Agent remains enabled on scan error


class RatingRequest(BaseModel):
    rating: int


def _normalize_path(
    path: Optional[str],
    agent_name: Optional[str] = None,
) -> str:
    """
    Normalize agent path format.

    If path is None, derives it from agent_name by converting to lowercase
    and replacing spaces with hyphens.

    Args:
        path: Agent path to normalize, or None to auto-generate
        agent_name: Agent name used for auto-generating path if needed

    Returns:
        Normalized path string

    Raises:
        ValueError: If path is None and agent_name is not provided
    """
    if path is None:
        if not agent_name:
            raise ValueError(
                "Path is required or agent_name must be provided for auto-generation"
            )
        path = agent_name.lower().replace(" ", "-")

    if not path.startswith("/"):
        path = "/" + path

    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")

    return path


def _check_agent_permission(
    permission: str,
    agent_name: str,
    user_context: Dict[str, Any],
) -> None:
    """
    Check if user has permission for agent operation.

    Args:
        permission: Permission to check
        agent_name: Name of the agent
        user_context: User context from auth

    Raises:
        HTTPException: If user lacks permission
    """
    from ..auth.dependencies import user_has_ui_permission_for_service

    if not user_has_ui_permission_for_service(
        permission,
        agent_name,
        user_context.get("ui_permissions", {}),
    ):
        logger.warning(
            f"User {user_context['username']} attempted to perform {permission} "
            f"on agent {agent_name} without permission"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to {permission} for {agent_name}",
        )


def _filter_agents_by_access(
    agents: List[AgentCard],
    user_context: Dict[str, Any],
) -> List[AgentCard]:
    """
    Filter agents based on user access permissions.

    Args:
        agents: List of agent cards
        user_context: User context from auth

    Returns:
        Filtered list of agents user can access
    """
    accessible = []
    user_groups = set(user_context.get("groups", []))
    username = user_context["username"]
    is_admin = user_context.get("is_admin", False)

    # Get accessible agents from user context (UI-Scopes)
    accessible_agent_list = user_context.get('accessible_agents', [])
    logger.debug(f"User {username} accessible agents from UI-Scopes: {accessible_agent_list}")

    for agent in agents:
        if is_admin:
            accessible.append(agent)
            continue

        # Check if user has agent-level restrictions from UI-Scopes
        if 'all' not in accessible_agent_list and agent.path not in accessible_agent_list:
            logger.debug(f"Agent {agent.path} filtered out: not in accessible agents {accessible_agent_list}")
            continue

        if agent.visibility == "public":
            accessible.append(agent)
            continue

        if agent.visibility == "private":
            if agent.registered_by == username:
                accessible.append(agent)
            continue

        if agent.visibility == "group-restricted":
            agent_groups = set(agent.allowed_groups)
            if agent_groups & user_groups:
                accessible.append(agent)
            continue

    return accessible


@router.post("/agents/register")
async def register_agent(
    request: AgentRegistrationRequest,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)],
):
    """
    Register a new A2A agent in the registry.

    Requires publish_agent scope/permission.

    Args:
        request: Agent registration request data
        user_context: Authenticated user context

    Returns:
        201 with agent card and registration metadata

    Raises:
        HTTPException: 409 if path exists, 422 if validation fails, 403 if unauthorized
    """
    ui_permissions = user_context.get("ui_permissions", {})
    publish_permissions = ui_permissions.get("publish_agent", [])

    if not publish_permissions:
        logger.warning(
            f"User {user_context['username']} attempted to register agent without permission"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to register agents",
        )

    logger.info(f"Agent registration request from user '{user_context['username']}'")
    logger.info(f"Name: {request.name}, Path: {request.path}, URL: {request.url}")

    path = _normalize_path(request.path, request.name)

    if agent_service.get_agent_info(path):
        logger.error(f"Agent registration failed: path '{path}' already exists")
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": f"Agent with path '{path}' already exists",
                "suggestion": "Use a different path or update the existing agent",
            },
        )

    tag_list = [tag.strip() for tag in request.tags.split(",") if tag.strip()]

    # Convert provider dict to AgentProvider object if provided
    provider_obj = None
    if request.provider:
        provider_obj = AgentProvider(
            organization=request.provider.get("organization", ""),
            url=request.provider.get("url", ""),
        )

    try:
        from ..utils.agent_validator import agent_validator

        agent_card = AgentCard(
            protocol_version=request.protocol_version,
            name=request.name,
            description=request.description,
            url=request.url,
            path=path,
            version=request.version,
            provider=provider_obj,
            security_schemes=request.security_schemes or {},
            skills=request.skills or [],
            streaming=request.streaming,
            tags=tag_list,
            license=request.license,
            visibility=request.visibility,
            registered_by=user_context["username"],
        )

        validation_result = await agent_validator.validate_agent_card(
            agent_card,
            verify_endpoint=True,
        )

        if not validation_result.is_valid:
            logger.error(f"Agent validation failed: {validation_result.errors}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Agent card validation failed",
                    "errors": validation_result.errors,
                    "warnings": validation_result.warnings,
                },
            )

    except ValueError as e:
        logger.error(f"Invalid agent card data: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid agent card: {str(e)}",
        )

    success = agent_service.register_agent(agent_card)

    if not success:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Failed to save agent data",
                "suggestion": "Check server logs for details",
            },
        )

    from ..search.service import faiss_service

    is_enabled = agent_service.is_agent_enabled(path)
    await faiss_service.add_or_update_entity(
        path,
        agent_card.model_dump(),
        "a2a_agent",
        is_enabled,
    )

    logger.info(
        f"New agent registered: '{request.name}' at path '{path}' "
        f"by user '{user_context['username']}'"
    )

    # Agent security scanning if enabled
    agent_card_dict = agent_card.model_dump()
    is_enabled = await _perform_agent_security_scan_on_registration(
        path, agent_card, agent_card_dict
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "message": "Agent registered successfully",
            "agent": {
                "name": agent_card.name,
                "path": agent_card.path,
                "url": str(agent_card.url),
                "num_skills": len(agent_card.skills),
                "registered_at": (
                    agent_card.registered_at.isoformat()
                    if agent_card.registered_at
                    else None
                ),
                "is_enabled": is_enabled,
            },
        },
    )


@router.get("/agents")
async def list_agents(
    query: Optional[str] = Query(None, description="Search query string"),
    enabled_only: bool = Query(False, description="Show only enabled agents"),
    visibility: Optional[str] = Query(None, description="Filter by visibility"),
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
):
    """
    List all agents filtered by user permissions.

    Args:
        query: Optional search query
        enabled_only: Only return enabled agents
        visibility: Filter by visibility level
        user_context: Authenticated user context

    Returns:
        List of agent info objects
    """
    # CRITICAL DIAGNOSTIC: Log user_context received by endpoint (for comparison with /servers)
    logger.debug(f"[GET_AGENTS_DEBUG] Received user_context: {user_context}")
    logger.debug(f"[GET_AGENTS_DEBUG] user_context type: {type(user_context)}")
    if user_context:
        logger.debug(f"[GET_AGENTS_DEBUG] Username: {user_context.get('username', 'NOT PRESENT')}")
        logger.debug(f"[GET_AGENTS_DEBUG] Scopes: {user_context.get('scopes', 'NOT PRESENT')}")
        logger.debug(f"[GET_AGENTS_DEBUG] Auth method: {user_context.get('auth_method', 'NOT PRESENT')}")

    all_agents = agent_service.get_all_agents()

    accessible_agents = _filter_agents_by_access(all_agents, user_context)

    filtered_agents = []
    search_query = query.lower() if query else ""

    for agent in accessible_agents:
        if enabled_only and not agent_service.is_agent_enabled(agent.path):
            continue

        if visibility and agent.visibility != visibility:
            continue

        searchable_text = (
            f"{agent.name.lower()} {agent.description.lower()} "
            f"{' '.join(agent.tags)} {' '.join([s.name for s in agent.skills])}"
        )

        if not search_query or search_query in searchable_text:
            # Extract streaming capability from agent capabilities dict
            streaming = agent.capabilities.get("streaming", False) if agent.capabilities else False

            # Extract provider organization name (provider is AgentProvider object)
            provider_name = agent.provider.organization if agent.provider else None

            agent_info = AgentInfo(
                name=agent.name,
                description=agent.description,
                path=agent.path,
                url=str(agent.url),
                tags=agent.tags,
                skills=[s.name for s in agent.skills],
                num_skills=len(agent.skills),
                num_stars=agent.num_stars,
                is_enabled=agent_service.is_agent_enabled(agent.path),
                provider=provider_name,
                streaming=streaming,
                trust_level=agent.trust_level,
            )
            filtered_agents.append(agent_info)

    logger.info(
        f"User {user_context['username']} listed {len(filtered_agents)} agents "
        f"(out of {len(all_agents)} total)"
    )

    return {
        "agents": [agent.model_dump() for agent in filtered_agents],
        "total_count": len(filtered_agents),
    }



# IMPORTANT: Specific routes with path suffixes (/health, /rate, /rating, /toggle)
# must come BEFORE catch-all {path:path} routes to prevent FastAPI from matching them incorrectly

@router.post("/agents/{path:path}/health")
async def check_agent_health(
    path: str,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)],
):
    """Perform a live /ping health check against an agent endpoint."""
    path = _normalize_path(path)

    agent_card = agent_service.get_agent_info(path)
    if not agent_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent not found at path '{path}'",
        )

    accessible = _filter_agents_by_access([agent_card], user_context)
    if not accessible:
        logger.warning(
            f"User {user_context['username']} attempted to health check agent {path} without permission"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this agent",
        )

    if not agent_service.is_agent_enabled(path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot perform health check on a disabled agent",
        )

    base_url = str(agent_card.url).rstrip("/")
    ping_url = f"{base_url}/ping"
    timeout_seconds = max(1, settings.health_check_timeout_seconds)

    status_label = "unknown"
    detail = None
    status_code = None
    response_time_ms = None
    start_time = datetime.now(timezone.utc)

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(ping_url)
        status_code = response.status_code
        response_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        if response.status_code == 200:
            status_label = "healthy"
        else:
            status_label = "unhealthy"
            detail = f"Agent responded with HTTP {response.status_code}"
    except httpx.TimeoutException:
        status_label = "unhealthy"
        detail = "Health check timed out"
    except httpx.HTTPError as exc:
        status_label = "unhealthy"
        detail = f"Health check failed: {exc}"
    except Exception as exc:
        status_label = "unhealthy"
        detail = f"Unexpected health check error: {exc}"

    last_checked_iso = datetime.now(timezone.utc).isoformat()

    logger.info(
        f"Agent health check for {path} ({ping_url}) completed with status {status_label}"
    )

    return {
        "agent_path": path,
        "ping_url": ping_url,
        "status": status_label,
        "status_code": status_code,
        "detail": detail,
        "response_time_ms": response_time_ms,
        "last_checked_iso": last_checked_iso,
    }


@router.post("/agents/{path:path}/rate")
async def rate_agent(
    path: str,
    request: RatingRequest,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)],
):
    """Save integer ratings to agent card."""
    path = _normalize_path(path)

    agent_card = agent_service.get_agent_info(path)
    if not agent_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent not found at path '{path}'",
        )

    accessible = _filter_agents_by_access([agent_card], user_context)
    if not accessible:
        logger.warning(
            f"User {user_context['username']} attempted to rate agent {path} without permission"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this agent",
        )

    try:
        avg_rating = agent_service.update_rating(path, user_context["username"], request.rating)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error updating rating: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save rating",
        )

    return {
        "message": "Rating added successfully",
        "average_rating": avg_rating,
    }


@router.get("/agents/{path:path}/rating")
async def get_agent_rating(
    path: str,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)],
):
    """Get agent rating information."""
    path = _normalize_path(path)

    agent_card = agent_service.get_agent_info(path)
    if not agent_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent not found at path '{path}'",
        )

    accessible = _filter_agents_by_access([agent_card], user_context)
    if not accessible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this agent",
        )
    
    return {
        "num_stars": agent_card.num_stars,
        "rating_details": agent_card.rating_details,
    }


@router.post("/agents/{path:path}/toggle")
async def toggle_agent(
    path: str,
    enabled: bool,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)],
):
    """
    Enable or disable an agent.

    Requires toggle_service permission for the agent.

    Args:
        path: Agent path
        enabled: New enabled state
        user_context: Authenticated user context

    Returns:
        Updated agent status

    Raises:
        HTTPException: 404 if not found, 403 if unauthorized
    """
    path = _normalize_path(path)

    agent_card = agent_service.get_agent_info(path)
    if not agent_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent not found at path '{path}'",
        )

    _check_agent_permission("toggle_service", agent_card.name, user_context)

    success = agent_service.toggle_agent(path, enabled)

    if not success:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Failed to toggle agent state"},
        )

    from ..search.service import faiss_service

    await faiss_service.add_or_update_entity(
        path,
        agent_card.model_dump(),
        "a2a_agent",
        enabled,
    )

    logger.info(
        f"Agent '{agent_card.name}' ({path}) toggled to {enabled} by user "
        f"'{user_context['username']}'"
    )

    return {
        "message": f"Agent {'enabled' if enabled else 'disabled'} successfully",
        "path": path,
        "is_enabled": enabled,
    }


@router.get("/agents/{path:path}")
async def get_agent(
    path: str,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)],
):
    """
    Get a single agent by path.

    Public agents are visible without special permissions.
    Private and group-restricted agents require authorization.

    Args:
        path: Agent path
        user_context: Authenticated user context

    Returns:
        Complete agent card

    Raises:
        HTTPException: 404 if not found, 403 if not authorized
    """
    path = _normalize_path(path)

    agent_card = agent_service.get_agent_info(path)
    if not agent_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent not found at path '{path}'",
        )

    accessible = _filter_agents_by_access([agent_card], user_context)

    if not accessible:
        logger.warning(
            f"User {user_context['username']} attempted to access agent {path} "
            f"without permission"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this agent",
        )

    return agent_card.model_dump()








@router.put("/agents/{path:path}")
async def update_agent(
    path: str,
    request: AgentRegistrationRequest,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)],
):
    """
    Update an existing agent card.

    Requires modify_service permission for the agent.
    User must be agent owner or admin.

    Args:
        path: Agent path
        request: Updated agent data
        user_context: Authenticated user context

    Returns:
        Updated agent card

    Raises:
        HTTPException: 404 if not found, 403 if unauthorized
    """
    path = _normalize_path(path)

    existing_agent = agent_service.get_agent_info(path)
    if not existing_agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent not found at path '{path}'",
        )

    _check_agent_permission("modify_service", existing_agent.name, user_context)

    if not user_context["is_admin"] and existing_agent.registered_by != user_context[
        "username"
    ]:
        logger.warning(
            f"User {user_context['username']} attempted to update agent {path} "
            f"owned by {existing_agent.registered_by}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update agents you registered",
        )

    tag_list = [tag.strip() for tag in request.tags.split(",") if tag.strip()]

    try:
        updated_agent = AgentCard(
            protocol_version=request.protocol_version,
            name=request.name,
            description=request.description,
            url=request.url,
            path=path,
            version=request.version,
            provider=request.provider,
            security_schemes=request.security_schemes or {},
            skills=request.skills or [],
            streaming=request.streaming,
            tags=tag_list,
            license=request.license,
            visibility=request.visibility,
            registered_by=existing_agent.registered_by,
            registered_at=existing_agent.registered_at,
            is_enabled=existing_agent.is_enabled,
            num_stars=existing_agent.num_stars,
        )

        from ..utils.agent_validator import agent_validator

        validation_result = await agent_validator.validate_agent_card(
            updated_agent,
            verify_endpoint=False,
        )

        if not validation_result.is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Agent card validation failed",
                    "errors": validation_result.errors,
                },
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid agent card: {str(e)}",
        )

    success = agent_service.update_agent(path, updated_agent)

    if not success:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Failed to save updated agent data"},
        )

    from ..search.service import faiss_service

    is_enabled = agent_service.is_agent_enabled(path)
    await faiss_service.add_or_update_entity(
        path,
        updated_agent.model_dump(),
        "a2a_agent",
        is_enabled,
    )

    logger.info(
        f"Agent '{updated_agent.name}' ({path}) updated by user "
        f"'{user_context['username']}'"
    )

    return updated_agent.model_dump()


@router.delete("/agents/{path:path}")
async def delete_agent(
    path: str,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)],
):
    """
    Delete an agent from the registry.

    Requires admin permission or agent ownership.

    Args:
        path: Agent path
        user_context: Authenticated user context

    Returns:
        204 No Content

    Raises:
        HTTPException: 404 if not found, 403 if unauthorized
    """
    path = _normalize_path(path)

    existing_agent = agent_service.get_agent_info(path)
    if not existing_agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent not found at path '{path}'",
        )

    if not user_context["is_admin"] and existing_agent.registered_by != user_context[
        "username"
    ]:
        logger.warning(
            f"User {user_context['username']} attempted to delete agent {path} "
            f"without permission"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins or agent owners can delete agents",
        )

    success = agent_service.remove_agent(path)

    if not success:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Failed to delete agent"},
        )

    from ..search.service import faiss_service

    await faiss_service.remove_entity(path)

    logger.info(
        f"Agent at path '{path}' deleted by user '{user_context['username']}'"
    )

    return JSONResponse(
        status_code=status.HTTP_204_NO_CONTENT,
        content=None,
    )




@router.post("/agents/discover")
async def discover_agents_by_skills(
    skills: List[str],
    tags: Optional[List[str]] = None,
    max_results: int = Query(10, ge=1, le=100),
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
):
    """
    Discover agents by required skills.

    Returns agents that have the specified skills, ranked by relevance.

    Args:
        skills: Required skill names or IDs
        tags: Optional tag filters
        max_results: Maximum number of results
        user_context: Authenticated user context

    Returns:
        List of matching agents with relevance scores

    Raises:
        HTTPException: 400 if no skills provided
    """
    if not skills:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one skill must be specified",
        )

    logger.info(
        f"User {user_context['username']} discovering agents with skills: {skills}"
    )

    all_agents = agent_service.get_all_agents()
    accessible_agents = _filter_agents_by_access(all_agents, user_context)

    matched_agents = []
    required_skills = set(s.lower() for s in skills)
    required_tags = set(t.lower() for t in tags) if tags else set()

    for agent in accessible_agents:
        if not agent_service.is_agent_enabled(agent.path):
            continue

        agent_skills = set(
            skill.id.lower() for skill in agent.skills
        ) | set(skill.name.lower() for skill in agent.skills)

        skill_matches = required_skills & agent_skills
        if not skill_matches:
            continue

        agent_tags = set(t.lower() for t in agent.tags)
        tag_matches = required_tags & agent_tags if required_tags else set()

        skill_match_score = len(skill_matches) / len(required_skills)
        tag_match_score = (
            len(tag_matches) / len(required_tags) if required_tags else 0.0
        )

        trust_boost = {
            "unverified": 0.0,
            "community": 0.2,
            "verified": 0.5,
            "trusted": 1.0,
        }.get(agent.trust_level, 0.0)

        relevance_score = 0.6 * skill_match_score + 0.2 * tag_match_score + 0.2 * trust_boost

        agent_info = AgentInfo(
            name=agent.name,
            description=agent.description,
            path=agent.path,
            url=str(agent.url),
            tags=agent.tags,
            skills=[s.name for s in agent.skills],
            num_skills=len(agent.skills),
            num_stars=agent.num_stars,
            is_enabled=True,
            provider=agent.provider,
            streaming=agent.streaming,
            trust_level=agent.trust_level,
        )

        matched_agents.append(
            {
                **agent_info.model_dump(),
                "relevance_score": round(relevance_score, 2),
                "matched_skills": list(skill_matches),
            }
        )

    matched_agents.sort(key=lambda x: x["relevance_score"], reverse=True)
    matched_agents = matched_agents[:max_results]

    logger.info(
        f"Found {len(matched_agents)} agents matching skills: {skills}"
    )

    return {
        "agents": matched_agents,
        "query": {
            "skills": skills,
            "tags": tags,
        },
    }


@router.post("/agents/discover/semantic")
async def discover_agents_semantic(
    query: str,
    max_results: int = Query(10, ge=1, le=100),
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
):
    """
    Discover agents using natural language semantic search.

    Uses FAISS vector search to find agents matching the query intent.

    Args:
        query: Natural language query describing needed capabilities
        max_results: Maximum number of results
        user_context: Authenticated user context

    Returns:
        List of matching agents with relevance scores

    Raises:
        HTTPException: 400 if query is empty
    """
    if not query or not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query cannot be empty",
        )

    logger.info(
        f"User {user_context['username']} semantic search for agents: {query}"
    )

    from ..search.service import faiss_service

    try:
        results = await faiss_service.search_entities(
            query=query,
            entity_types=["a2a_agent"],
            enabled_only=True,
            max_results=max_results,
        )

        all_agents = agent_service.get_all_agents()
        agent_map = {agent.path: agent for agent in all_agents}

        accessible_results = []
        for result in results:
            agent_card = agent_map.get(result.get("path"))
            if not agent_card:
                continue

            if not _filter_agents_by_access([agent_card], user_context):
                continue

            agent_info = AgentInfo(
                name=agent_card.name,
                description=agent_card.description,
                path=agent_card.path,
                url=str(agent_card.url),
                tags=agent_card.tags,
                skills=[s.name for s in agent_card.skills],
                num_skills=len(agent_card.skills),
                num_stars=agent_card.num_stars,
                is_enabled=True,
                provider=agent_card.provider,
                streaming=agent_card.streaming,
                trust_level=agent_card.trust_level,
            )

            accessible_results.append(
                {
                    **agent_info.model_dump(),
                    "score": result.get("relevance_score", 0.0),
                }
            )

        logger.info(
            f"Semantic search returned {len(accessible_results)} agents for query: {query}"
        )

        return {
            "agents": accessible_results,
            "query": query,
        }

    except Exception as e:
        logger.error(f"Error in semantic agent search: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Semantic search failed",
        )


@router.get("/agents/{path:path}/security-scan")
async def get_agent_security_scan(
    path: str,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)],
):
    """
    Get security scan results for an A2A agent.

    Returns the latest security scan results for the specified agent,
    including threat analysis, severity levels, and detailed findings
    from YARA, specification validation, and heuristic analyzers.

    **Authentication:** JWT Bearer token or session cookie
    **Authorization:** Requires admin privileges or access to the agent

    **Path Parameters:**
    - `path` (required): Agent path (e.g., /code-reviewer)

    **Response:**
    Returns security scan results with analysis_results and findings.

    **Example:**
    ```bash
    curl -X GET http://localhost/api/agents/code-reviewer/security-scan \\
      --cookie-jar .cookies --cookie .cookies
    ```
    """
    if not path.startswith("/"):
        path = "/" + path

    # Check if agent exists
    agent_info = agent_service.get_agent_info(path)
    if not agent_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent not found at path '{path}'",
        )

    # Check user permissions
    if not user_context["is_admin"]:
        # Check if user has access to this agent (similar to server access check)
        # For now, allow all authenticated users to view agent scan results
        # TODO: Implement agent-specific access control if needed
        pass

    # Get scan results
    from ..services.agent_scanner import agent_scanner_service

    scan_result = agent_scanner_service.get_scan_result(path)
    if not scan_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No security scan results found for agent '{path}'. "
            "The agent may not have been scanned yet.",
        )

    return scan_result


@router.post("/agents/{path:path}/rescan")
async def rescan_agent(
    path: str,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)],
):
    """
    Trigger a manual security scan for an A2A agent.

    Initiates a new security scan for the specified agent and returns
    the results. This endpoint is useful for re-scanning agents after
    updates or for on-demand security assessments.

    **Authentication:** JWT Bearer token or session cookie
    **Authorization:** Requires admin privileges

    **Path Parameters:**
    - `path` (required): Agent path (e.g., /code-reviewer)

    **Response:**
    Returns the newly generated security scan results.

    **Example:**
    ```bash
    curl -X POST http://localhost/api/agents/code-reviewer/rescan \\
      --cookie-jar .cookies --cookie .cookies
    ```
    """
    # Only admins can trigger manual scans
    if not user_context["is_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can trigger security scans",
        )

    if not path.startswith("/"):
        path = "/" + path

    # Check if agent exists
    agent_info = agent_service.get_agent_info(path)
    if not agent_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent not found at path '{path}'",
        )

    # Get agent card from agent info
    agent_card_dict = agent_info.model_dump()

    logger.info(
        f"Manual security scan requested by user '{user_context.get('username')}' "
        f"for agent '{path}'"
    )

    try:
        # Trigger security scan
        from ..services.agent_scanner import agent_scanner_service

        scan_result = await agent_scanner_service.scan_agent(
            agent_card=agent_card_dict,
            agent_path=path,
            analyzers=None,  # Use default analyzers from config
            api_key=None,  # Use default API key from config
            timeout=None,  # Use default timeout from config
        )

        # Return the scan result data
        return {
            "agent_path": scan_result.agent_path,
            "agent_url": scan_result.agent_url,
            "scan_timestamp": scan_result.scan_timestamp,
            "is_safe": scan_result.is_safe,
            "critical_issues": scan_result.critical_issues,
            "high_severity": scan_result.high_severity,
            "medium_severity": scan_result.medium_severity,
            "low_severity": scan_result.low_severity,
            "analyzers_used": scan_result.analyzers_used,
            "scan_failed": scan_result.scan_failed,
            "error_message": scan_result.error_message,
            "output_file": scan_result.output_file,
        }

    except Exception as e:
        logger.error(f"Manual security scan failed for agent '{path}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Security scan failed: {str(e)}",
        )
