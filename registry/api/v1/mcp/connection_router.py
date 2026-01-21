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
from services.oauth.token_service import token_service

router = APIRouter(prefix="/v1/mcp", tags=["connection"])


@router.post("/{server_id}/reinitialize")
async def reinitialize_server(
        server_id: str,
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
        logger.info(f"[Reinitialize] User {user_id} reinitializing server: {server_id}")

        # 1. Disconnect existing connection
        disconnected = await mcp_service.connection_service.disconnect_user_connection(
            user_id, server_id
        )
        if disconnected:
            logger.info(f"[Reinitialize] Disconnected {server_id} for user {user_id}")

        server = await get_service_config(server_id)

        # 2. Check if access_token is expired
        is_expired = await token_service.is_access_token_expired(user_id,server.serverName )
        has_refresh = await token_service.has_refresh_token(user_id, server.serverName)

        # 3. If expired but has refresh_token, try auto-refresh
        if is_expired and has_refresh:
            logger.info(f"[Reinitialize] Access token expired for {server_id}, attempting refresh")
            success, error = await mcp_service.oauth_service.refresh_tokens(user_id, server_id)

            if success:
                logger.info(f"[Reinitialize] Token refreshed successfully for {server_id}")
                is_expired = False  # Token is now valid
            else:
                logger.warn(f"[Reinitialize] Token refresh failed for {server_id}: {error}")
                # Continue, will check if we need OAuth below

        # 4. Try to get valid tokens
        tokens = await mcp_service.oauth_service.get_tokens(user_id, server_id)

        if tokens and not is_expired:
            # Has valid tokens, create connection
            logger.info(f"[Reinitialize] Valid tokens available for {server_id}, creating connection")
            await mcp_service.connection_service.create_user_connection(
                user_id=user_id,
                server_id=server_id,
                initial_state=ConnectionState.CONNECTED,
                details={"reinitialized": True, "has_oauth": True}
            )

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "message": f"Server '{server_id}' reinitialized successfully",
                    "server_id": server_id,
                    "requires_oauth": server.config.get('requiresOAuth', False)
                }
            )
        else:
            # 5. No valid tokens - need OAuth flow
            logger.info(f"[Reinitialize] No valid tokens for {server_id}, initiating OAuth")
            flow_id, auth_url, error = await mcp_service.oauth_service.initiate_oauth_flow(
                user_id, server_id
            )

            if error:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "success": False,
                        "message": f"Failed to initiate OAuth: {error}",
                        "server_id": server_id,
                        "requires_oauth": server.config.get("requiresOAuth", False)
                    }
                )

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": True,
                    "message": "OAuth authorization required",
                    "server_id": server_id,
                    "requires_oauth": server.config.get("requiresOAuth", False),
                    "oauth_url": auth_url
                }
            )

    except Exception as e:
        logger.error(f"[Reinitialize] Unexpected error for {server_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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



@router.get("/connection/status/{server_id}")
async def get_server_connection_status(
        server_id: str,
        current_user: CurrentUser,
        mcp_service: MCPService = Depends(get_mcp_service)
) -> Dict[str, Any]:
    """
    Get connection status for a specific MCP server by server ID

    Returns detailed connection status including state, OAuth requirement, and details.
    Uses the same logic as /connection/status to ensure consistency.
    """
    try:
        user_id = current_user.get('user_id')
        logger.debug(f"Fetching status for {server_id} (user: {user_id})")

        server = await server_service_v1.get_server_by_id(server_id)
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Server '{server_id}' not found"
            )

        server_status = await get_single_server_connection_status(
            user_id=user_id,
            server_id=server.id,
            mcp_service=mcp_service
        )
        return {
            "success": True,
            "serverName": server.serverName,
            "connectionState": server_status["connection_state"],
            "requiresOAuth": server_status["requires_oauth"]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get status for {server_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to get connection status for {server_id}")

@DeprecationWarning
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


async def get_service_config(server_id):
    """
    Get service config for a specific MCP server
    """
    server_docs = await server_service_v1.get_server_by_id(server_id)
    if not server_docs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Server'{server_id}'config  not found")
    if not server_docs.config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Server'{server_id}' not found")
    return server_docs
