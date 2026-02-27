"""User context model for MCP Gateway Registry authentication."""

from typing import Any, TypedDict


class UserContextDict(TypedDict, total=False):
    """Type hint for user context dictionaries.

    Authenticated user context populated by auth middlewares and stored
    on request.state.user (as a plain dict) for downstream handlers.

    All fields except 'username', 'auth_method', 'provider', and 'auth_source'
    are optional to support various auth scenarios (e.g., basic auth without user_id).
    """

    user_id: str | None
    username: str
    groups: list[str]
    scopes: list[str]
    auth_method: str
    provider: str
    accessible_servers: list[str]
    accessible_services: list[str]
    accessible_agents: list[str]
    ui_permissions: dict[str, Any]
    can_modify_servers: bool
    is_admin: bool
    auth_source: str
