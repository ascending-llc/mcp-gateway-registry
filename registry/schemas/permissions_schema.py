"""
Pydantic Schemas for Permission Management API v1

These schemas define the request and response models for the
Permisison Management endpoints based on the API documentation.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from registry.services.constants import PrincipalType

class PermissionPrincipalIn(BaseModel):
    principal_id: str
    type: PrincipalType
    permBits: Optional[int]
    accessRoleId: Optional[str]

class UpdateServerPermissionsRequest(BaseModel):
    updated: List[PermissionPrincipalIn] = Field(default_factory=list)
    removed: List[PermissionPrincipalIn] = Field(default_factory=list)
    public: bool = False


class PermissionPrincipalOut(BaseModel):
    type: PrincipalType
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    idOnTheSource: Optional[str] = None
    accessRoleId: str


class UpdateServerPermissionsResponse(BaseModel):
    message: str
    results: dict