from typing import Any, TypedDict


class UserContextDict(TypedDict, total=False):
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
