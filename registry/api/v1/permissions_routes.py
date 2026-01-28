"""
Permission Management API Routes V1

RESTful API endpoints for managing ACL permissions using MongoDB.
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, status as http_status, Depends
from beanie import PydanticObjectId

from registry.auth.dependencies import CurrentUserWithACLMap
from registry.services.access_control_service import acl_service
from registry.core.acl_constants import PrincipalType, ResourceType, PermissionBits
from registry.schemas.permissions_schema import (
    UpdateServerPermissionsRequest,
    UpdateServerPermissionsResponse,
)
from registry.services.permissions_utils import (
    check_required_permission,
)

from typing import Dict, Any

logger = logging.getLogger(__name__)
router = APIRouter()


def get_user_context(user_context: CurrentUserWithACLMap):
    """Extract user context from authentication dependency"""
    return user_context


@router.get(
    "/permissions/servers/{server_id}",
    summary="Get ACL permissions for a specific server (for UI controls)",
    description="Returns the current user's permissions for a specific server resource. Used by frontend to show/hide edit/delete buttons.",
)
async def get_server_permissions(
    server_id: str,
    user_context: dict = Depends(get_user_context),
) -> Dict[str, Any]:
    """
    Returns the current user's permissions for the given server resource.
    Example response:
    {
        "server_id": "...",
        "permissions": ["VIEW", "EDIT", "DELETE", ...]
    }
    """
    acl_permission_map = user_context.get("acl_permission_map", {})
    perms = acl_permission_map.get(ResourceType.MCPSERVER, {}).get(server_id, [])
    return {
        "server_id": server_id,
        "permissions": perms
    }

@router.put(
    f"/permissions/servers/{{server_id}}",
    summary="Update ACL permissions for a specific server",
    description="Update ACL permissions for a specific server",
    response_model=UpdateServerPermissionsResponse,
)
async def update_server_permissions(
    server_id: str,
    data: UpdateServerPermissionsRequest,
    user_context: dict = Depends(get_user_context),
) -> dict:
    # Check if user has SHARE permissions
    acl_permission_map = user_context.get("acl_permission_map", {})
    check_required_permission(acl_permission_map, ResourceType.MCPSERVER.value, server_id, "SHARE")
    
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
            logger.info(f"Deleted {deleted_count} VIEW ACL entries for server {server_id}")

            # Create 1 public acl entry
            acl_entry = await acl_service.grant_permission(
                principal_type=PrincipalType.PUBLIC.value,
                principal_id=None,
                resource_type=ResourceType.MCPSERVER.value,
                resource_id=PydanticObjectId(server_id),
                perm_bits=PermissionBits.VIEW
            )
            logger.info(f"Created public ACL entry: {acl_entry.id} for server {server_id}")
            updated_count = 1 if acl_entry else 0
        else:
            # Delete the public ACL entry
            deleted_public_entry = await acl_service.delete_permission(
                resource_type=ResourceType.MCPSERVER.value,
                resource_id=PydanticObjectId(server_id),
                principal_type=PrincipalType.PUBLIC.value,
                principal_id=None
            )
            deleted_count += deleted_public_entry
            logger.info(f"Deleted public ACL entry for server {server_id}")

        if data.removed:
            delete_results = await asyncio.gather(*[
                acl_service.delete_permission(
                    resource_type=ResourceType.MCPSERVER.value,
                    resource_id=PydanticObjectId(server_id),
                    principal_type=principal.principal_type,
                    principal_id=PydanticObjectId(principal.principal_id)
                ) for principal in data.removed
            ])
            deleted_count += sum(delete_results)

        if data.updated:
            update_results = await asyncio.gather(*[
                acl_service.grant_permission(
                    principal_type=principal.principal_type,
                    principal_id=PydanticObjectId(principal.principal_id),
                    resource_type=ResourceType.MCPSERVER.value,
                    resource_id=PydanticObjectId(server_id),
                    perm_bits=principal.perm_bits,
                ) for principal in data.updated
            ])
            updated_count += len(update_results)

        logger.info(f"Updated permissions for server {server_id}: {updated_count} updated, {deleted_count} deleted")
        return UpdateServerPermissionsResponse(
            message=f"Updated {updated_count} and deleted {deleted_count} permissions",
            results={"server_id": server_id}
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

