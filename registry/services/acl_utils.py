"""
Permission utility functions for ACL checks.
"""

from fastapi import HTTPException, status as http_status
from registry.core.acl_constants import ResourceType


def validate_resource_type(resource_type: str) -> None:
    if resource_type not in [rt.value for rt in ResourceType]:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_resource_type",
                "message": f"Resource type '{resource_type}' is not valid."
            }
        )
            