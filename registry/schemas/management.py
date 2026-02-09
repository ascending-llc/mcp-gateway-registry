from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class M2MAccountRequest(BaseModel):
    """Payload for creating a Keycloak service account client."""

    name: str = Field(..., min_length=1)
    groups: list[str] = Field(..., min_length=1)
    description: str | None = None


class HumanUserRequest(BaseModel):
    """Payload for creating a Keycloak human user."""

    username: str = Field(..., min_length=1)
    email: EmailStr
    first_name: str = Field(..., min_length=1, alias="firstname")
    last_name: str = Field(..., min_length=1, alias="lastname")
    groups: list[str] = Field(..., min_length=1)
    password: str | None = Field(None, description="Initial password (optional, generated elsewhere)")

    model_config = {"populate_by_name": True}


class UserDeleteResponse(BaseModel):
    """Standard response returned when a Keycloak user is deleted."""

    username: str
    deleted: bool = True


class KeycloakUserSummary(BaseModel):
    """Subset of Keycloak user information exposed through the API."""

    id: str
    username: str
    email: str | None = None
    firstName: str | None = None
    lastName: str | None = None
    enabled: bool = True
    groups: list[str] = Field(default_factory=list)


class UserListResponse(BaseModel):
    """Wrapper for list users endpoint."""

    users: list[KeycloakUserSummary] = Field(default_factory=list)
    total: int


class GroupCreateRequest(BaseModel):
    """Payload for creating a Keycloak group."""

    name: str = Field(..., min_length=1)
    description: str | None = None


class KeycloakGroupSummary(BaseModel):
    """Keycloak group information."""

    id: str
    name: str
    path: str
    attributes: dict | None = None


class GroupListResponse(BaseModel):
    """Response for listing Keycloak groups."""

    groups: list[KeycloakGroupSummary] = Field(default_factory=list)
    total: int


class GroupDeleteResponse(BaseModel):
    """Response when a Keycloak group is deleted."""

    name: str
    deleted: bool = True
