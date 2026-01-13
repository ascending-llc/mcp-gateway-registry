from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from registry.auth.dependencies import CurrentUser
from registry.services.oauth.mcp_service import MCPService, get_mcp_service
from registry.schemas.enums import ConnectionState
from registry.utils.log import logger
from registry.services.server_service_v1 import server_service_v1
from registry.services.oauth.connection_status_service import (
    get_servers_connection_status,
    get_single_server_connection_status
)

router = APIRouter(prefix="/v1/mcp", tags=["connection"])


@router.post("/{server_name}/reinitialize")
async def reinitialize_server(
        server_name: str,
        current_user: CurrentUser,
        mcp_service: MCPService = Depends(get_mcp_service)
) -> JSONResponse:
    """
    Reinitialize MCP server connection
    
    Process:
    1. Clear cached data (tools, resources, prompts)
    2. Disconnect existing connection
    3. Reconnect with fresh configuration
    
    Notes: POST /:serverName/reinitialize (TypeScript reference)
    """
    try:
        user_id = current_user.get('user_id')
        logger.info(f"User {user_id} reinitializing server: {server_name}")

        # 1. Disconnect existing connection
        disconnected = await mcp_service.connection_service.disconnect_user_connection(user_id, server_name)
        if disconnected:
            logger.info(f"Disconnected {server_name} for user {user_id}")

        server_docs = await get_service_config(server_name)

        # 2. Check if OAuth tokens exist for reconnection
        tokens = await mcp_service.oauth_service.get_tokens(user_id, server_name)

        if tokens:
            # Has tokens, create new connection
            await mcp_service.connection_service.create_user_connection(
                user_id=user_id,
                server_name=server_name,
                initial_state=ConnectionState.CONNECTED,
                details={"reinitialized": True, "has_oauth": True}
            )

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "message": f"Server '{server_name}' reinitialized successfully",
                    "server_name": server_name,
                    "requires_oauth": server_docs.config.get("requires_oauth", False)
                }
            )
        else:
            # No tokens - need OAuth flow
            flow_id, auth_url, error = await mcp_service.oauth_service.initiate_oauth_flow(
                user_id, server_name
            )

            if error:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "success": False,
                        "message": f"Failed to initiate OAuth: {error}",
                        "server_name": server_name,
                        "requires_oauth": server_docs.config.get("requires_oauth", False)
                    }
                )

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "message": "OAuth authorization required",
                    "server_name": server_name,
                    "requires_oauth": server_docs.config.get("requires_oauth", False),
                    "oauth_url": auth_url
                }
            )

    except Exception as e:
        logger.error(f"Unexpected error for {server_name}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Internal server error: {str(e)}")


@DeprecationWarning
@router.get("/connection/status")
async def get_all_connection_status(
        current_user: CurrentUser,
        mcp_service: MCPService = Depends(get_mcp_service)
) -> Dict[str, Any]:
    """
    Get connection status for all MCP servers
    
    Returns comprehensive connection status for all configured servers.
    
    Notes: GET /connection/status (TypeScript reference)
    """
    try:
        user_id = current_user.get('user_id')
        logger.debug(f"Fetching connection status for all servers (user: {user_id})")

        # Get all active servers
        all_services, _ = await server_service_v1.list_servers(per_page=1000, status="active")
        logger.info(f"Found {len(all_services)} servers")

        connection_status = await get_servers_connection_status(
            user_id=user_id,
            servers=all_services,
            mcp_service=mcp_service
        )
        return {
            "success": True,
            "connectionStatus": connection_status
        }

    except Exception as e:
        logger.error(f"Failed to get connection status: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to get connection status")


@DeprecationWarning
@router.get("/connection/status/{server_name}")
async def get_server_connection_status(
        server_name: str,
        current_user: CurrentUser,
        mcp_service: MCPService = Depends(get_mcp_service)
) -> Dict[str, Any]:
    """
    Get connection status for a specific MCP server
    
    Returns detailed connection status including state, OAuth requirement, and details.
    Uses the same logic as /connection/status to ensure consistency.
    
    Notes: GET /connection/status/:serverName (TypeScript reference)
    """
    try:
        user_id = current_user.get('user_id')
        logger.debug(f"Fetching status for {server_name} (user: {user_id})")

        server_status = await get_single_server_connection_status(
            user_id=user_id,
            server_name=server_name,
            mcp_service=mcp_service
        )
        return {
            "success": True,
            "server_name": server_name,
            "connection_state": server_status["connection_state"],
            "requires_oauth": server_status["requires_oauth"]
        }
    except ValueError as e:
        # Server not found
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get status for {server_name}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to get connection status for {server_name}")


@router.get("/{server_name}/auth-values")
async def check_auth_values(
        server_name: str,
        current_user: CurrentUser,
        mcp_service: MCPService = Depends(get_mcp_service)
) -> Dict[str, Any]:
    """
    Check which authentication values are set for an MCP server
    
    Returns boolean flags indicating which auth variables have values set,
    without exposing the actual credential values.
    
    Notes: GET /:serverName/auth-values (TypeScript reference)
    
    Security: Only returns boolean flags, never actual credential values
    """
    try:
        user_id = current_user.get('user_id')
        logger.debug(f"Checking auth values for {server_name} (user: {user_id})")

        # Check if OAuth tokens exist
        tokens = await mcp_service.oauth_service.get_tokens(user_id, server_name)

        auth_value_flags = {
            "oauth_tokens": tokens is not None
        }

        # TODO: Check custom user vars from config if needed
        # For now, just return OAuth token status
        return {
            "success": True,
            "server_name": server_name,
            "auth_value_flags": auth_value_flags
        }

    except Exception as e:
        logger.error(f"Failed to check auth values for {server_name}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to check auth values for {server_name}")


async def get_service_config(server_name):
    """
    Get service config for a specific MCP server
    """
    server_docs = await server_service_v1.get_server_by_name(server_name)
    if not server_docs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Server'{server_name}'config  not found")
    if not server_docs.config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Server'{server_name}' not found")
    return server_docs
