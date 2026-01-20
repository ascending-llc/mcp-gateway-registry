"""
Permission Management API Routes V1

RESTful API endpoints for managing MCP servers using MongoDB.
This is a complete rewrite independent of the legacy server_routes.py.
"""

import logging
import math
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status as http_status, Depends
from pydantic import ValidationError
from beanie import PydanticObjectId

from registry.auth.dependencies import CurrentUser
from registry.services.access_control_service import acl_service
from registry.services.constants import PrincipalType, ResourceType, PermissionBits
from registry.schemas.permissions_schema import (
    UpdateServerPermissionsRequest,
    UpdateServerPermissionsResponse,
    PermissionPrincipalOut,
)


API_VERSION = "v1"
logger = logging.getLogger(__name__)
router = APIRouter()


def get_user_context(user_context: CurrentUser):
    """Extract user context from authentication dependency"""
    return user_context

@router.put(
    f"/{API_VERSION}/permissions/servers/{{server_id}}",
    summary="Update ACL permissions for a specific server",
    description="Update ACL permissions for a specific server",
    response_model=UpdateServerPermissionsResponse,
)
async def update_server_permissions(
    server_id: PydanticObjectId,
    data: UpdateServerPermissionsRequest,
    user_context: dict = Depends(get_user_context),
) -> dict:
    # Check if user has SHARE permissions or is an ADMIN
    acl_permission_map = user_context.get("acl_permission_map", {})
    user_perms_for_server = acl_permission_map.get(ResourceType.MCPSERVER.value, {}).get(str(server_id), {})
    if not (user_perms_for_server.get("SHARE", False) or user_context.get("role") == "ADMIN"):
        raise HTTPException(
        status_code=http_status.HTTP_403_FORBIDDEN,
        detail={
            "error": "forbidden",
            "message": "You do not have edit permissions for this server."
        })
    if data.public:
        # Only one ACL entry for public resources
        await acl_service.grant_permission(
            principal_type=PrincipalType.PUBLIC.value,
            principal_id=None,
            resource_type=ResourceType.MCPSERVER,
            resource_id=server_id,
            perm_bits=PermissionBits.VIEW
        )

        # TODO: Public resources are globally viewable & privately editable.
        # Find all ACL entries for this resource dont that belong to Admin & Owner
        # Delete those entries.
    else:
        for principal in data.updated:
            principal_type = principal.get("principal_type")
            principal_id = principal.get("principal_id")
            await acl_service.grant_permission(
                principal_type=principal_type,
                principal_id={"userId": principal_id} if principal_type == PrincipalType.USER.value else principal_id,
                resource_type=ResourceType.MCPSERVER,
                resource_id=server_id,
                perm_bits=principal.get("permBits"),
            )

        # TODO: Delete all ACL entries in data.removed

    return UpdateServerPermissionsResponse(
        message="Permissions updated successfully.",
        results={}
    )

