"""
Server Management API Routes V1

RESTful API endpoints for managing MCP servers using MongoDB.
This is a complete rewrite independent of the legacy server_routes.py.
"""

from functools import wraps
import logging
import math
from time import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status as http_status, Depends
from pydantic import ValidationError

from registry.auth.dependencies import CurrentUser
from registry.utils.log import metrics
from registry.services.server_service import server_service_v1
from registry.services.oauth.mcp_service import get_mcp_service
from registry.services.oauth.connection_status_service import (
    get_servers_connection_status,
    get_single_server_connection_status
)
from registry.schemas.enums import ConnectionState
from registry.schemas.server_api_schemas import (
    ServerListResponse,
    ServerDetailResponse,
    ServerCreateRequest,
    ServerCreateResponse,
    ServerUpdateRequest,
    ServerUpdateResponse,
    ServerToggleRequest,
    ServerToggleResponse,
    ServerToolsResponse,
    ServerHealthResponse,
    ServerStatsResponse,
    PaginationMetadata,
    convert_to_list_item,
    convert_to_detail,
    convert_to_create_response,
    convert_to_update_response,
    convert_to_toggle_response,
    convert_to_tools_response,
    convert_to_health_response,
)

logger = logging.getLogger(__name__)

router = APIRouter()

def track_operation(operation: str, resource_type: str):
    """
    Decorator to automatically track metrics for API operations.
    
    Args:
        operation: Type of operation (create, read, update, delete, list, etc.)
        resource_type: Type of resource (server, tool, etc.)
    
    Usage:
        @track_operation("read", "server")
        async def get_server(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time()
            success = False
            
            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except HTTPException:
                # HTTPException means client error (4xx) - still track as failed operation
                raise
            except Exception:
                # Unexpected error - track and re-raise
                raise
            finally:
                # Always record metrics, even if exception occurred
                duration = time() - start_time
                metrics.record_registry_operation(
                    operation=operation,
                    resource_type=resource_type,
                    success=success,
                    duration_seconds=duration
                )
        
        return wrapper
    return decorator


def get_user_context(user_context: CurrentUser):
    """Extract user context from authentication dependency"""
    return user_context


def check_admin_permission(user_context: dict) -> bool:
    """
    Check if user has admin permissions.
    
    This is a placeholder function for future permission system.
    Currently returns True for all users, but provides a hook for
    implementing role-based access control (RBAC) in the future.
    
    Future implementation should check:
    - user_context.get("role") == "ADMIN"
    - user_context.get("is_admin") == True
    
    Args:
        user_context: User context dictionary from authentication
        
    Returns:
        True if user is admin, False otherwise
    """
    # TODO: Implement actual permission check when RBAC is ready
    # For now, allow all authenticated users to access stats
    # Future: return user_context.get("role") == "ADMIN" or user_context.get("is_admin", False)
    return True


def apply_connection_status_to_server(
    server_item,
    status: Optional[Dict[str, Any]],
    fallback_requires_oauth: bool = False
) -> None:
    """
    Apply connection status to a server response object.
    """
    if status:
        server_item.connectionState = status.get("connection_state")
        server_item.requiresOAuth = status.get("requires_oauth", False)
        server_item.error = status.get("error")
    else:
        # Fallback if status not found
        server_item.connectionState = ConnectionState.ERROR.value
        server_item.requiresOAuth = fallback_requires_oauth
        server_item.error = "Connection status not available"


# ==================== Endpoints ====================

@router.get(
    f"/servers",
    response_model=ServerListResponse,
    summary="List Servers",
    description="List all servers with filtering, searching, and pagination. Includes connection status for each server.",
)
@track_operation("list", "server")
async def list_servers(
    query: Optional[str] = None,
    scope: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    user_context: dict = Depends(get_user_context),
):
    """
    List servers with optional filtering and pagination.
    Includes connection status (connection_state, requires_oauth, error) for each server.
    
    Query Parameters:
    - query: Free-text search across server_name, description, tags
    - scope: Filter by access level (shared_app, shared_user, private_user)
    - status: Filter by operational state (active, inactive, error)
    - page: Page number (default: 1, min: 1)
    - per_page: Items per page (default: 20, min: 1, max: 100)
    """
    try:
        # Validate scope if provided
        if scope and scope not in ["shared_app", "shared_user", "private_user"]:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Invalid scope. Must be one of: shared_app, shared_user, private_user"
            )
        
        # Validate status if provided
        if status and status not in ["active", "inactive", "error"]:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Invalid status. Must be one of: active, inactive, error"
            )
        
        # Get servers from service (no permission filtering)
        servers, total = await server_service_v1.list_servers(
            query=query,
            scope=scope,
            status=status,
            page=page,
            per_page=per_page,
            user_id=None,
        )
        
        # Convert to response models
        server_items = [convert_to_list_item(server) for server in servers]
        
        # Get connection status and enrich server items
        try:
            user_id = user_context.get('user_id')
            mcp_service = await get_mcp_service()
            
            connection_status = await get_servers_connection_status(
                user_id=user_id,
                servers=servers,
                mcp_service=mcp_service
            )
            # Enrich each server item with connection status
            for server_item in server_items:
                status = connection_status.get(str(server_item.id))
                apply_connection_status_to_server(server_item, status, fallback_requires_oauth=False)
        
        except Exception as e:
            logger.warning(f"Error getting connection status: {e}", exc_info=True)

        # Calculate pagination metadata
        total_pages = math.ceil(total / per_page) if total > 0 else 0
        
        return ServerListResponse(
            servers=server_items,
            pagination=PaginationMetadata(
                total=total,
                page=page,
                per_page=per_page,
                total_pages=total_pages,
            )
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing servers: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while listing servers"
        )


@router.get(
    f"/servers/stats",
    response_model=ServerStatsResponse,
    summary="Get System Statistics",
    description="Get system-wide statistics (Admin only). Includes server, token, and user metrics using MongoDB aggregation pipelines.",
)
@track_operation("read", "stats")
async def get_server_stats(
    user_context: dict = Depends(get_user_context),
):
    """
    Get system-wide statistics.
    
    **Admin Only Endpoint**
    
    Returns comprehensive statistics about:
    - Total servers and breakdown by scope, status, and transport
    - Total tokens and breakdown by type, expiry status
    - Active users count
    - Total tools across all servers
    
    Note: This endpoint uses MongoDB aggregation pipelines and is only 
    available when using MongoDB storage backend. File-based storage 
    will return a simplified version or 501 Not Implemented.
    """
    try:
        # Check admin permission (currently returns True for all, but reserved for future RBAC)
        if not check_admin_permission(user_context):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": "Admin access required to view system statistics",
                }
            )
        
        # Get statistics from service
        stats = await server_service_v1.get_stats()
        
        return ServerStatsResponse(**stats)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting server statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while getting statistics"
        )


@router.get(
    f"/servers/{{server_id}}",
    response_model=ServerDetailResponse,
    summary="Get Server Details",
    description="Get detailed information about a specific server, including connection status",
)
@track_operation("read", "server")
async def get_server(
    server_id: str,
    user_context: dict = Depends(get_user_context),
):
    """Get detailed information about a server by ID, including connection status"""
    try:
        server = await server_service_v1.get_server_by_id(
            server_id=server_id,
            user_id=None,
        )
        
        if not server:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        
        # Convert to response model
        server_detail = convert_to_detail(server)
        try:
            user_id = user_context.get('user_id')
            mcp_service = await get_mcp_service()
            server_status = await get_single_server_connection_status(
                user_id=user_id,
                server_id=server.id,
                mcp_service=mcp_service
            )
            apply_connection_status_to_server(server_detail, server_status)
        
        except Exception as e:
            logger.warning(f"Error getting connection status for {server.serverName}: {e}", exc_info=True)
            # Apply error state with custom error message
            fallback_requires_oauth = server.config.get("requires_oauth", False)
            apply_connection_status_to_server(server_detail, None, fallback_requires_oauth)
            server_detail.error = f"Failed to get connection status: {str(e)}"
        
        return server_detail
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting server {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while getting server"
        )


@router.post(
    f"/servers",
    response_model=ServerCreateResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Register Server",
    description="Register a new MCP server",
)
@track_operation("create", "server")
async def create_server(
    data: ServerCreateRequest,
    user_context: dict = Depends(get_user_context),
):
    """Create a new server"""
    try:
        user_id = user_context.get("username")
        
        server = await server_service_v1.create_server(
            data=data,
            user_id=user_id,
        )
        
        return convert_to_create_response(server)
        
    except ValueError as e:
        # Business logic errors (e.g., duplicate path, duplicate tags)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating server: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating server"
        )


@router.patch(
    f"/servers/{{server_id}}",
    response_model=ServerUpdateResponse,
    summary="Update Server",
    description="Update server configuration",
)
@track_operation("update", "server")
async def update_server(
    server_id: str,
    data: ServerUpdateRequest,
    user_context: dict = Depends(get_user_context),
):
    """Update a server with partial data"""
    try:
        user_id = user_context.get("username")
        
        server = await server_service_v1.update_server(
            server_id=server_id,
            data=data,
            user_id=user_id,
        )
        
        return convert_to_update_response(server)
        
    except ValueError as e:
        error_msg = str(e)
        
        # Check if server not found
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "not_found",
                    "message": error_msg,
                }
            )
        
        # Other validation errors
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating server {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while updating server"
        )


@router.delete(
    f"/servers/{{server_id}}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete Server",
    description="Delete a server",
)
@track_operation("delete", "server")
async def delete_server(
    server_id: str,
    user_context: dict = Depends(get_user_context),
):
    """Delete a server"""
    try:
        await server_service_v1.delete_server(
            server_id=server_id,
            user_id=None,
        )
        
        return None  # 204 No Content
        
    except ValueError as e:
        error_msg = str(e)
        
        # Not found
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "not_found",
                    "message": "Server not found",
                }
            )
        
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting server {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while deleting server"
        )


@router.post(
    f"/servers/{{server_id}}/toggle",
    response_model=ServerToggleResponse,
    summary="Toggle Server Status",
    description="Enable or disable a server",
)
@track_operation("update", "server")
async def toggle_server(
    server_id: str,
    data: ServerToggleRequest,
    user_context: dict = Depends(get_user_context),
):
    """Toggle server enabled/disabled status. When enabling, fetches tools from server."""
    try:
        # Get user_id from context for OAuth token retrieval
        user_id = user_context.get("username") or user_context.get("user_id")
        
        server = await server_service_v1.toggle_server_status(
            server_id=server_id,
            enabled=data.enabled,
            user_id=user_id,
        )
        
        return convert_to_toggle_response(server, data.enabled)
        
    except ValueError as e:
        error_msg = str(e)
        
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "not_found",
                    "message": "Server not found",
                }
            )
        
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling server {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while toggling server"
        )


@router.get(
    f"/servers/{{server_id}}/tools",
    response_model=ServerToolsResponse,
    summary="Get Server Tools",
    description="Get the list of tools provided by a server",
)
@track_operation("read", "tool")
async def get_server_tools(
    server_id: str,
    user_context: dict = Depends(get_user_context),
):
    """Get server tools"""
    try:
        server, tools = await server_service_v1.get_server_tools(
            server_id=server_id,
            user_id=None,
        )
        
        return convert_to_tools_response(server, tools)
        
    except ValueError as e:
        error_msg = str(e)
        
        if "access denied" in error_msg.lower():
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": error_msg,
                }
            )
        
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "not_found",
                    "message": "Server not found",
                }
            )
        
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tools for server {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while getting server tools"
        )


@router.post(
    f"/servers/{{server_id}}/refresh",
    response_model=ServerHealthResponse,
    summary="Refresh Server Health",
    description="Refresh server health status and check connectivity",
)
async def refresh_server_health(
    server_id: str,
    user_context: dict = Depends(get_user_context),
):
    """Refresh server health status. Updates tools if server becomes active."""
    try:
        # Get user_id from context for OAuth token retrieval
        user_id = user_context.get("user_id") or user_context.get("username")

        health_info = await server_service_v1.refresh_server_health(
            server_id=server_id,
            user_id=user_id,
        )
        
        # Check if health check failed
        if health_info["status"] == "unhealthy":
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "health_check_failed",
                    "message": health_info.get("status_message", "Failed to retrieve tools from server"),
                }
            )
        
        server = health_info["server"]
        
        return convert_to_health_response(server, health_info)
        
    except ValueError as e:
        error_msg = str(e)
        
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "not_found",
                    "message": "Server not found",
                }
            )
        
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing health for server {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while refreshing server health"
        )
