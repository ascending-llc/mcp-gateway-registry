"""
Permission Management API Routes V1

RESTful API endpoints for managing MCP servers using MongoDB.
This is a complete rewrite independent of the legacy server_routes.py.
"""

import asyncio
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
from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument

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
    server_id: str,
    data: UpdateServerPermissionsRequest,
    user_context: dict = Depends(get_user_context),
) -> dict:
    # Check if user has SHARE permissions or if they're an ADMIN
    acl_permission_map = user_context.get("acl_permission_map", {})
    user_perms_for_server = acl_permission_map.get(ResourceType.MCPSERVER.value, {}).get(str(server_id), {})
    if not (user_perms_for_server.get("SHARE", False) or user_context.get("role") == "ADMIN"):
        raise HTTPException(
        status_code=http_status.HTTP_403_FORBIDDEN,
        detail={
            "error": "forbidden",
            "message": "You do not have share permissions for this server."
        })
    
    try:
        updated_count = 0
        deleted_count = 0
        if data.public:
            # find the author of the server
            mcp_server = await MCPServerDocument.find_one({"_id": PydanticObjectId(server_id)})

            # delete all permissions except the author
            deleted_count = await acl_service.delete_acl_entries_for_resource(
                resource_type=ResourceType.MCPSERVER.value,
                resource_id=PydanticObjectId(server_id),
                author_id=mcp_server.author
            )

            # create a public acl entry
            public_acl = await acl_service.grant_permission(
                principal_type=PrincipalType.PUBLIC.value,
                principal_id=None,
                resource_type=ResourceType.MCPSERVER,
                resource_id=PydanticObjectId(server_id),
                perm_bits=PermissionBits.VIEW
            )
        else:
            # Grant permissions for principals in data.updated
            for principal in data.updated:
                result =  await asyncio.gather(
                    acl_service.grant_permission(
                        principal_type=principal.principal_type,
                        principal_id={"userId": PydanticObjectId(principal.principal_id)},
                        resource_type=ResourceType.MCPSERVER,
                        resource_id=PydanticObjectId(server_id),
                        perm_bits=principal.perm_bits,
                    )
                )

            # Delete all ACL entries for pricnipals in data.removed
            if data.removed:
                for principal in data.removed: 
                    await asyncio.gather(
                        acl_service.delete_permission(
                            resource_type=ResourceType.MCPSERVER,
                            resource_id=PydanticObjectId(server_id),
                            principal_type=principal.principal_type,
                            principal_id=PydanticObjectId(principal.principal_id)
                        )
                    )

        return UpdateServerPermissionsResponse(
            message=f"Updated {updated_count} and deleted {deleted_count} permissions",
            results={f"server_id": server_id}
        )
    
    except Exception as e: 
        logger.error(f"Error updating permissions for server {server_id}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_server_error",
                "message": "An error occurred while updating permissions."
            }
        )

