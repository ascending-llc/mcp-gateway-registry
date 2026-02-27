"""Structured user context model for MCP Gateway Registry authentication."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """Authenticated user context populated by auth middlewares.

    Constructed by _build_user_context() in UnifiedAuthMiddleware and stored
    on request.state.user (as a plain dict via model_dump()) for downstream handlers.
    """

    # None when authenticated via _try_basic_auth (internal admin endpoints).
    # Basic auth uses environment credentials with no corresponding DB record,
    # so no user_id exists. User-facing routes that pass this to DB operations
    # must guard against None explicitly (see proxy_routes._build_authenticated_headers).
    user_id: Optional[str] = None
    username: str
    groups: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    auth_method: str
    provider: str
    accessible_servers: list[str] = Field(default_factory=list)
    accessible_services: list[str] = Field(default_factory=list)
    accessible_agents: list[str] = Field(default_factory=list)
    ui_permissions: dict[str, Any] = Field(default_factory=dict)
    can_modify_servers: bool = False
    is_admin: bool = False
    auth_source: str
