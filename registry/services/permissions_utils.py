"""
Permission utility functions for ACL checks.
"""

from fastapi import HTTPException, status as http_status
from beanie import PydanticObjectId

def check_required_permission(acl_permission_map: dict, resource_type: str, resource_id: str, required_permission: str) -> None:
    """
    Checks if a user has the required permission for a given resource using the provided ACL permission map.

    Args:
    acl_permission_map (dict): The user's ACL permission map (resource_type → resource_id → permissions dict).
    resource_type (str): The type of resource to check (e.g., 'mcpServer').
    resource_id (str): The ID of the resource to check.
    required_permission (str): The permission to check for (e.g., 'SHARE', 'EDIT', 'VIEW').

    Raises:
    HTTPException: If the user lacks the required permission for the specified resource.
    """
    perms_for_resource = acl_permission_map.get(resource_type, {}).get(str(resource_id), {})
    if not (perms_for_resource.get(required_permission, False)):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": f"You do not have {required_permission} permissions for this server."
            }
        )


def make_user_principal_id_dict(principal_id: str) -> dict: 
    """
    Helper to construct the PrincipalId dict expected by IAclEntry.
    Args:
        principal_id (str): The user ID to wrap in a dict.
    Returns:
        dict: Dictionary in the format {"userId": principal_id} for user principals.
    """
    if principal_id:
        return {"userId": PydanticObjectId(principal_id)}
    
    return {}
    