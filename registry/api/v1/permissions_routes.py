"""
Permission Management API Routes V1

RESTful API endpoints for managing MCP servers using MongoDB.
This is a complete rewrite independent of the legacy server_routes.py.
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, status as http_status, Depends
from beanie import PydanticObjectId

from registry.auth.dependencies import CurrentUser
from registry.services.access_control_service import acl_service
from registry.services.constants import PrincipalType, ResourceType, PermissionBits
from registry.schemas.permissions_schema import (
    UpdateServerPermissionsRequest,
    UpdateServerPermissionsResponse,
)
from registry.services.permissions_utils import (
    check_required_permission,
    make_user_principal_id_dict
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
    server_id: str,
    data: UpdateServerPermissionsRequest,
    user_context: dict = Depends(get_user_context),
) -> dict:
    # Check if user is an Admin or has SHARE permissions
    is_admin = user_context.get("is_admin")
    if not is_admin: 
        acl_permission_map = user_context.get("acl_permission_map", {})
        check_required_permission(acl_permission_map,ResourceType.MCPSERVER.value, server_id, "SHARE")
    
    try:
        deleted_count = 0
        updated_count = 0
        if data.public:
            # Delete all the ACL entries granting VIEW access
            deleted_count = await acl_service.delete_acl_entries_for_resource(
                resource_type=ResourceType.MCPSERVER.value,
                resource_id=PydanticObjectId(server_id),
                perm_bits_to_delete=PermissionBits.VIEW
            )

            # Create 1 public acl entry
            acl_entry = await acl_service.grant_permission(
                principal_type=PrincipalType.PUBLIC.value,
                principal_id=None,
                resource_type=ResourceType.MCPSERVER,
                resource_id=PydanticObjectId(server_id),
                perm_bits=PermissionBits.VIEW
            )
            updated_count = 1 if acl_entry else 0
        else:
            # Delete the public ACL entry
            deleted_public_entry = await acl_service.delete_permission(
                resource_type=ResourceType.MCPSERVER,
                resource_id=PydanticObjectId(server_id),
                principal_type=PrincipalType.PUBLIC,
                principal_id=None
            )
            deleted_count += deleted_public_entry

        if data.removed:
            delete_results = await asyncio.gather(*[
                acl_service.delete_permission(
                    resource_type=ResourceType.MCPSERVER,
                    resource_id=PydanticObjectId(server_id),
                    principal_type=principal.principal_type,
                    principal_id=principal.principal_id
                ) for principal in data.removed
            ])
            deleted_count += sum(delete_results)

        if data.updated:
            update_results = await asyncio.gather(*[
                acl_service.grant_permission(
                    principal_type=principal.principal_type,
                    principal_id=make_user_principal_id_dict(principal.principal_id),
                    resource_type=ResourceType.MCPSERVER,
                    resource_id=PydanticObjectId(server_id),
                    perm_bits=principal.perm_bits,
                ) for principal in data.updated
            ])
            updated_count += len(update_results)

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

