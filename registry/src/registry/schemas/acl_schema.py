"""
Pydantic Schemas for ACL Management API v1

These schemas define the request and response models for the
ACL Management endpoints based on the API documentation.
"""

from pydantic import BaseModel, Field

from registry.core.acl_constants import PrincipalType


class ResourcePermissions(BaseModel):
    VIEW: bool = False
    EDIT: bool = False
    DELETE: bool = False
    SHARE: bool = False


class PermissionPrincipalIn(BaseModel):
    principal_id: str
    principal_type: PrincipalType
    perm_bits: int | None = 0
    accessRoleId: str | None = None


class UpdateResourcePermissionsRequest(BaseModel):
    updated: list[PermissionPrincipalIn] = Field(default_factory=list)
    removed: list[PermissionPrincipalIn] = Field(default_factory=list)
    public: bool = False


class PermissionPrincipalOut(BaseModel):
    principal_type: PrincipalType
    principal_id: str
    name: str | None = None
    email: str | None = None
    accessRoleId: str


class UpdateResourcePermissionsResponse(BaseModel):
    message: str
    results: dict
