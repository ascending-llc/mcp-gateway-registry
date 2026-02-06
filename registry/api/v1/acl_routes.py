"""
ACL Management API Routes V1

RESTful API endpoints for managing ACL permissions using MongoDB.
"""

import asyncio
import logging
from typing import Any

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status

from registry.auth.dependencies import CurrentUser
from registry.core.acl_constants import PermissionBits, PrincipalType
from registry.schemas.acl_schema import (
    PermissionPrincipalOut,
    UpdateResourcePermissionsRequest,
    UpdateResourcePermissionsResponse,
)
from registry.services.access_control_service import acl_service
from registry.utils.utils import validate_resource_type

logger = logging.getLogger(__name__)
router = APIRouter()


def get_user_context(user_context: CurrentUser):
    """Extract user context from authentication dependency"""
    return user_context


@router.get(
    "/permissions/search-principals",
    summary="Search for principals",
    description="Search for principals by query string. Used for ACL sharing UI.",
)
async def search_principals(
    query: str,
    limit: int | None = None,
    principal_types: list[str] | None = Query(None),
) -> list[PermissionPrincipalOut]:
    """
    Search for principals (users, groups, public) matching the query string.
    Returns a paginated response with metadata.
    """
    try:
        response = await acl_service.search_principals(query=query, limit=limit, principal_types=principal_types)
        return response
    except Exception as e:
        logger.error(f"Error searching principals: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_server_error", "message": "An error occurred while searching principals."},
        )


@router.put(
    "/permissions/{resource_type}/{resource_id}",
    summary="Update ACL permissions for a specific resource",
    description="Update ACL permissions for a specific resource",
    response_model=UpdateResourcePermissionsResponse,
)
async def update_resource_permissions(
    resource_id: str,
    resource_type: str,
    data: UpdateResourcePermissionsRequest,
    user_context: dict = Depends(get_user_context),
) -> UpdateResourcePermissionsResponse:
    validate_resource_type(resource_type)

    user_id = user_context.get("user_id")
    await acl_service.check_user_permission(
        user_id=PydanticObjectId(user_id),
        resource_type=resource_type,
        resource_id=PydanticObjectId(resource_id),
        required_permission="SHARE",
    )

    try:
        deleted_count = 0
        updated_count = 0
        if data.public:
            # Delete all the ACL entries granting VIEW access
            deleted_count = await acl_service.delete_acl_entries_for_resource(
                resource_type=resource_type,
                resource_id=PydanticObjectId(resource_id),
                perm_bits_to_delete=PermissionBits.VIEW,
            )
            logger.info(f"Deleted {deleted_count} VIEW ACL entries for resource {resource_id}")

            # Create 1 public acl entry
            acl_entry = await acl_service.grant_permission(
                principal_type=PrincipalType.PUBLIC.value,
                principal_id=None,
                resource_type=resource_type,
                resource_id=PydanticObjectId(resource_id),
                perm_bits=PermissionBits.VIEW,
            )
            logger.info(f"Created public ACL entry: {acl_entry.id} for resource {resource_id}")
            updated_count = 1 if acl_entry else 0
        else:
            # Delete the public ACL entry
            deleted_public_entry = await acl_service.delete_permission(
                resource_type=resource_type,
                resource_id=PydanticObjectId(resource_id),
                principal_type=PrincipalType.PUBLIC.value,
                principal_id=None,
            )
            deleted_count += deleted_public_entry
            logger.info(f"Deleted public ACL entry for resource {resource_id}")

        if data.removed:
            delete_results = await asyncio.gather(
                *[
                    acl_service.delete_permission(
                        resource_type=resource_type,
                        resource_id=PydanticObjectId(resource_id),
                        principal_type=principal.principal_type,
                        principal_id=PydanticObjectId(principal.principal_id),
                    )
                    for principal in data.removed
                ]
            )
            deleted_count += sum(delete_results)

        if data.updated:
            update_results = await asyncio.gather(
                *[
                    acl_service.grant_permission(
                        principal_type=principal.principal_type,
                        principal_id=PydanticObjectId(principal.principal_id),
                        resource_type=resource_type,
                        resource_id=PydanticObjectId(resource_id),
                        perm_bits=principal.perm_bits,
                    )
                    for principal in data.updated
                ]
            )
            updated_count += len(update_results)

        logger.info(f"Updated permissions for resource {resource_id}: {updated_count} updated, {deleted_count} deleted")
        return UpdateResourcePermissionsResponse(
            message=f"Updated {updated_count} and deleted {deleted_count} permissions",
            results={"resource_id": resource_id},
        )

    except Exception as e:
        logger.error(f"Error updating permissions for resource {resource_id}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_server_error", "message": "An error occurred while updating permissions."},
        )


@router.get(
    "/permissions/{resource_type}/{resource_id}",
    summary="Get all permissions for a specific resource",
    description="Get ACL permissions for a specific resource.",
)
async def get_resource_permissions(
    resource_type: str,
    resource_id: str,
    user_context: dict = Depends(get_user_context),
) -> dict[str, Any]:
    """
    Get ACL permissions for a specific resource.
    """
    validate_resource_type(resource_type)

    user_id = user_context.get("user_id")
    await acl_service.check_user_permission(
        user_id=PydanticObjectId(user_id),
        resource_type=resource_type,
        resource_id=PydanticObjectId(resource_id),
        required_permission="VIEW",
    )

    try:
        result = await acl_service.get_resource_permissions(
            resource_type=resource_type,
            resource_id=PydanticObjectId(resource_id),
        )
        return result
    except Exception as e:
        logger.error(f"Error fetching resource permissions for {resource_type} {resource_id}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_server_error",
                "message": "An error occurred while fetching resource permissions.",
            },
        )
