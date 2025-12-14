from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth.dependencies import nginx_proxied_auth
from ..schemas.management import (
    GroupCreateRequest,
    GroupDeleteResponse,
    GroupListResponse,
    HumanUserRequest,
    KeycloakGroupSummary,
    KeycloakUserSummary,
    M2MAccountRequest,
    UserDeleteResponse,
    UserListResponse,
)
from ..utils.keycloak_manager import (
    KeycloakAdminError,
    create_human_user_account,
    create_keycloak_group,
    create_service_account_client,
    delete_keycloak_group,
    delete_keycloak_user,
    list_keycloak_groups,
    list_keycloak_users,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/management", tags=["Management API"])


def _translate_keycloak_error(exc: KeycloakAdminError) -> HTTPException:
    """Map Keycloak admin errors to HTTP responses."""
    detail = str(exc)
    lowered = detail.lower()
    status_code = status.HTTP_502_BAD_GATEWAY
    if any(keyword in lowered for keyword in ("already exists", "not found", "provided")):
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=detail)


def _require_admin(user_context: dict) -> None:
    if not user_context.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator permissions are required for this operation",
        )


@router.get("/iam/users", response_model=UserListResponse)
async def management_list_users(
    search: str | None = None,
    limit: int = 500,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
):
    """List Keycloak users for administrators."""
    _require_admin(user_context)
    try:
        raw_users = await list_keycloak_users(search=search, max_results=limit)
    except KeycloakAdminError as exc:
        raise _translate_keycloak_error(exc) from exc

    summaries = [
        KeycloakUserSummary(
            id=user.get("id", ""),
            username=user.get("username", ""),
            email=user.get("email"),
            firstName=user.get("firstName"),
            lastName=user.get("lastName"),
            enabled=user.get("enabled", True),
            groups=user.get("groups", []),
        )
        for user in raw_users
    ]
    return UserListResponse(users=summaries, total=len(summaries))


@router.post("/iam/users/m2m")
async def management_create_m2m_user(
    payload: M2MAccountRequest,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
):
    """Create a service account client and return its credentials."""
    _require_admin(user_context)
    try:
        result = await create_service_account_client(
            client_id=payload.name,
            group_names=payload.groups,
            description=payload.description,
        )
    except KeycloakAdminError as exc:
        raise _translate_keycloak_error(exc) from exc
    return result


@router.post("/iam/users/human")
async def management_create_human_user(
    payload: HumanUserRequest,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
):
    """Create a Keycloak human user and assign groups."""
    _require_admin(user_context)
    try:
        user_doc = await create_human_user_account(
            username=payload.username,
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            groups=payload.groups,
            password=payload.password,
        )
    except KeycloakAdminError as exc:
        raise _translate_keycloak_error(exc) from exc

    return KeycloakUserSummary(
        id=user_doc.get("id", ""),
        username=user_doc.get("username", payload.username),
        email=user_doc.get("email"),
        firstName=user_doc.get("firstName"),
        lastName=user_doc.get("lastName"),
        enabled=user_doc.get("enabled", True),
        groups=user_doc.get("groups", payload.groups),
    )


@router.delete("/iam/users/{username}", response_model=UserDeleteResponse)
async def management_delete_user(
    username: str,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
):
    """Delete a Keycloak user by username."""
    _require_admin(user_context)
    try:
        await delete_keycloak_user(username)
    except KeycloakAdminError as exc:
        raise _translate_keycloak_error(exc) from exc
    return UserDeleteResponse(username=username)


@router.get("/iam/groups", response_model=GroupListResponse)
async def management_list_keycloak_groups(
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
):
    """List Keycloak IAM groups (admin only)."""
    _require_admin(user_context)
    try:
        raw_groups = await list_keycloak_groups()
        summaries = [
            KeycloakGroupSummary(
                id=group.get("id", ""),
                name=group.get("name", ""),
                path=group.get("path", ""),
                attributes=group.get("attributes"),
            )
            for group in raw_groups
        ]
        return GroupListResponse(groups=summaries, total=len(summaries))
    except Exception as exc:  # noqa: BLE001 - surface upstream failure
        logger.error("Failed to list Keycloak groups: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to list Keycloak groups",
        ) from exc


@router.post("/iam/groups", response_model=KeycloakGroupSummary)
async def management_create_group(
    payload: GroupCreateRequest,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
):
    """Create a new Keycloak group (admin only)."""
    _require_admin(user_context)
    try:
        result = await create_keycloak_group(
            group_name=payload.name,
            description=payload.description or ""
        )
        return KeycloakGroupSummary(
            id=result.get("id", ""),
            name=result.get("name", ""),
            path=result.get("path", ""),
            attributes=result.get("attributes"),
        )
    except KeycloakAdminError as exc:
        raise _translate_keycloak_error(exc) from exc
    except Exception as exc:
        logger.error("Failed to create Keycloak group: %s", exc)
        # Check if it's an "already exists" error
        if "already exists" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create group: {exc}",
        ) from exc


@router.delete("/iam/groups/{group_name}", response_model=GroupDeleteResponse)
async def management_delete_group(
    group_name: str,
    user_context: Annotated[dict, Depends(nginx_proxied_auth)] = None,
):
    """Delete a Keycloak group by name (admin only)."""
    _require_admin(user_context)
    try:
        await delete_keycloak_group(group_name)
        return GroupDeleteResponse(name=group_name)
    except KeycloakAdminError as exc:
        raise _translate_keycloak_error(exc) from exc
    except Exception as exc:
        logger.error("Failed to delete Keycloak group: %s", exc)
        # Check if it's a "not found" error
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group '{group_name}' not found",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to delete group: {exc}",
        ) from exc
