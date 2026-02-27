"""User context model for MCP Gateway Registry authentication."""

from typing import Any

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """Authenticated user context populated by auth middlewares.

    Constructed by _build_user_context() in UnifiedAuthMiddleware and stored
    on request.state.user (as a plain dict via model_dump()) for downstream handlers.
    """

    user_id: str | None = (
        None  # internal admin endpoints (_try_basic_auth) use environment credentials and thus have no user_id
    )
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
