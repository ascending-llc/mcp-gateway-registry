from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class M2MAccountRequest(BaseModel):
    """Payload for creating a Keycloak service account client."""

    name: str = Field(..., min_length=1)
    groups: List[str] = Field(..., min_length=1)
    description: Optional[str] = None


class HumanUserRequest(BaseModel):
    """Payload for creating a Keycloak human user."""

    username: str = Field(..., min_length=1)
    email: EmailStr
    first_name: str = Field(..., min_length=1, alias="firstname")
    last_name: str = Field(..., min_length=1, alias="lastname")
    groups: List[str] = Field(..., min_length=1)
    password: Optional[str] = Field(
        None, description="Initial password (optional, generated elsewhere)"
    )

    model_config = {"populate_by_name": True}


class UserDeleteResponse(BaseModel):
    """Standard response returned when a Keycloak user is deleted."""

    username: str
    deleted: bool = True


class KeycloakUserSummary(BaseModel):
    """Subset of Keycloak user information exposed through the API."""

    id: str
    username: str
    email: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    enabled: bool = True
    groups: List[str] = Field(default_factory=list)


class UserListResponse(BaseModel):
    """Wrapper for list users endpoint."""

    users: List[KeycloakUserSummary] = Field(default_factory=list)
    total: int


class GroupCreateRequest(BaseModel):
    """Payload for creating a Keycloak group."""

    name: str = Field(..., min_length=1)
    description: Optional[str] = None


class KeycloakGroupSummary(BaseModel):
    """Keycloak group information."""

    id: str
    name: str
    path: str
    attributes: Optional[dict] = None


class GroupListResponse(BaseModel):
    """Response for listing Keycloak groups."""

    groups: List[KeycloakGroupSummary] = Field(default_factory=list)
    total: int


class GroupDeleteResponse(BaseModel):
    """Response when a Keycloak group is deleted."""

    name: str
    deleted: bool = True
