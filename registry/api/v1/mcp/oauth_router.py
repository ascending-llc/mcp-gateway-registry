import time
from typing import Dict, Any, Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from registry.auth.dependencies import CurrentUser
from registry.services.oauth.mcp_service import get_mcp_service, MCPService
from registry.schemas.enums import ConnectionState, OAuthFlowStatus
from registry.utils.log import logger
from registry.utils.utils import load_template
from registry.auth.oauth.reconnection import get_reconnection_manager
from registry.constants import REGISTRY_CONSTANTS

router = APIRouter(prefix="/v1", tags=["oauth"])


@router.get("/{server_name}/oauth/initiate")
async def initiate_oauth_flow(
        server_name: str,
        user_context: CurrentUser,
        mcp_service: MCPService = Depends(get_mcp_service)
) -> JSONResponse:
    """
    Initialize OAuth flow
    
    Notes: GET /:serverName/oauth/initiate
    TypeScript implementation: Directly call MCPOAuthHandler.initiateOAuthFlow()
    """
    try:
        user_id = user_context.get('user_id')
        logger.info(f"Oauth initiate for user id : {user_id}")
        flow_id, auth_url, error = await mcp_service.oauth_service.initiate_oauth_flow(
            user_id=user_id,
            server_name=server_name
        )
        if error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

        if not flow_id or not auth_url:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Failed to initiate OAuth flow")

        return JSONResponse(status_code=status.HTTP_200_OK,
                            content={"flow_id": flow_id,
                                     "authorization_url": auth_url,
                                     "server_name": server_name,
                                     "user_id": user_id})
    except HTTPException:
        # Re-raise HTTP exceptions with their original status code
        raise
    except Exception as e:
        logger.error(f"Failed to initialize OAuth flow: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to initialize OAuth flow: {str(e)}")


@router.get("/{server_name}/oauth/callback")
async def oauth_callback(
        server_name: str,
        request: Request,
        code: Optional[str] = Query(None, description="OAuth authorization code"),
        state: Optional[str] = Query(None, description="State parameter (format: flow_id##security_token)"),
        error: Optional[str] = Query(None, description="OAuth error message"),
        mcp_service: MCPService = Depends(get_mcp_service)
) -> RedirectResponse:
    """
    OAuth callback handler
    
    Notes: /:serverName/oauth/callback
    
    Process:
    1. Check for errors returned by OAuth provider
    2. Validate required parameters (code, state)
    3. Decode state to get flow_id and security_token
    4. Complete OAuth flow (validation + token exchange)
    5. Redirect to success/failure page
    """
    try:
        # 1. Check for errors returned by OAuth provider
        if error:
            logger.error(f"[MCP OAuth] OAuth error received from provider: {error}")
            return _redirect_to_page(server_name, error_msg=error)

        # 2. Validate required parameters
        if not code or not isinstance(code, str):
            logger.error("[MCP OAuth] Missing or invalid authorization code")
            return _redirect_to_page(server_name, error_msg="missing_code")

        if not state or not isinstance(state, str):
            logger.error("[MCP OAuth] Missing or invalid state parameter")
            return _redirect_to_page(server_name, error_msg="missing_state")

        # 3. Decode flow_id from state (state format: flow_id##security_token)
        try:
            flow_id, security_token = mcp_service.oauth_service.flow_manager.decode_state(state)
            logger.info(f"[MCP OAuth] Callback received: server={server_name}, "
                        f"flow_id={flow_id}, code={'present' if code else 'missing'}, "
                        f"security_token_length={len(security_token)}")
        except ValueError as e:
            logger.error(f"[MCP OAuth] Failed to decode state: {e}")
            return _redirect_to_page(server_name, error_msg="invalid_state_format")

        # Check if flow is already completed
        flow = mcp_service.oauth_service.flow_manager.get_flow(flow_id)
        if flow and flow.status == OAuthFlowStatus.COMPLETED:
            logger.warning(f"[MCP OAuth] Flow already completed, preventing duplicate token exchange: {flow_id}")
            return _redirect_to_page(server_name, flag="success")

        # 4. Complete OAuth flow (validate state + exchange tokens)
        logger.debug(f"[MCP OAuth] Completing OAuth flow for {server_name}")
        success, error_msg = await mcp_service.oauth_service.complete_oauth_flow(
            flow_id=flow_id,
            authorization_code=code,
            state=state
        )

        if not success:
            logger.error(f"[MCP OAuth] Failed to complete OAuth flow: {error_msg}")
            return _redirect_to_page(server_name, error_msg=error_msg or "unknown_error")

        logger.info(f"[MCP OAuth] OAuth flow completed successfully for {server_name}")

        # 5. Create user connection and setup server
        try:
            # Get user_id from flow
            flow = mcp_service.oauth_service.flow_manager.get_flow(flow_id)
            if flow and flow.user_id:
                user_id = flow.user_id
                logger.debug(f"[MCP OAuth] Attempting to reconnect {server_name} with new OAuth tokens")

                # Create user connection with CONNECTED state
                await mcp_service.connection_service.create_user_connection(
                    user_id=user_id,
                    server_name=server_name,
                    initial_state=ConnectionState.CONNECTED,
                    details={
                        "oauth_completed": True,
                        "flow_id": flow_id,
                        "created_at": time.time()
                    }
                )
                logger.info(f"[MCP OAuth] Successfully reconnected {server_name} for user {user_id}")

                # Clear any reconnection attempts
                try:
                    reconnection_manager = get_reconnection_manager(
                        mcp_service=mcp_service,
                        oauth_service=mcp_service.oauth_service
                    )
                    reconnection_manager.clear_reconnection(user_id, server_name)
                    logger.debug(f"[MCP OAuth] Cleared reconnection attempts for {server_name}")
                except Exception as e:
                    logger.error(f"[MCP OAuth] Could not clear reconnection (manager not initialized): {e}")

                # TODO: Fetch tools, resources, and prompts in parallel
                # This should be done asynchronously in the background
                logger.debug(f"[MCP OAuth] User connection created for {server_name}")

        except Exception as error:
            logger.error(f"[MCP OAuth] Failed to reconnect {server_name} after OAuth, "
                         f"but tokens are saved: {error}")

        # 6. Redirect to success page
        return _redirect_to_page(server_name, flag="success")

    except Exception as e:
        logger.error(f"[MCP OAuth] OAuth callback error: {str(e)}", exc_info=True)
        return _redirect_to_page(server_name, error_msg="callback_failed")


@router.get("/oauth/tokens/{flow_id}")
async def get_oauth_tokens(
        flow_id: str,
        current_user: CurrentUser,
        mcp_service: MCPService = Depends(get_mcp_service)
) -> Dict[str, Any]:
    """
    Get OAuth tokens
    
    Notes: GET /oauth/tokens/:flowId
    TypeScript implementation: Get tokens via flowManager.getFlowState()
    
    Parameters:
    - flow_id: Flow ID
    - current_user: Current user information
    
    Returns:
    - OAuth tokens
    """
    try:
        user_id = current_user.get("user_id")

        # 1. Verify flow_id belongs to current user
        if not flow_id.startswith(f"{user_id}") and not flow_id.startswith("system:"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="No permission to access this flow")

        # 2. Get tokens by flow ID
        tokens = await mcp_service.oauth_service.get_tokens_by_flow_id(flow_id)
        if not tokens:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Tokens not found or flow not completed")

        # 3. Return tokens
        return {
            "tokens": tokens.dict() if hasattr(tokens, 'dict') else tokens
        }
    except HTTPException:
        # Re-raise HTTP exceptions with their original status code
        raise
    except Exception as e:
        logger.error(f"Failed to get OAuth tokens: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to get tokens: {str(e)}")


@router.get("/oauth/status/{flow_id}")
async def get_oauth_status(
        flow_id: str,
        mcp_service: MCPService = Depends(get_mcp_service)
) -> Dict[str, Any]:
    """
    Check OAuth flow status
    
    Notes: GET /oauth/status/:flowId
    TypeScript implementation: Get status via flowManager.getFlowState()
    
    """
    try:
        # Get flow status
        flow_status = await mcp_service.oauth_service.get_flow_status(flow_id)

        return flow_status

    except Exception as e:
        logger.error(f"Failed to check OAuth flow status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check flow status: {str(e)}"
        )


@router.post("/oauth/cancel/{server_name}")
async def cancel_oauth_flow(
        server_name: str,
        current_user: CurrentUser,
        mcp_service: MCPService = Depends(get_mcp_service)
) -> Dict[str, Any]:
    """
    Cancel OAuth flow
    
    Notes: POST /oauth/cancel/:serverName
    TypeScript implementation: Directly call flowManager.failFlow()
    
    Process:
    1. Cancel the OAuth flow
    2. Update user connection state to DISCONNECTED
    """
    try:
        user_id = current_user.get("user_id")
        logger.info(f"[OAuth Cancel] Cancelling OAuth flow for {server_name} by user {user_id}")

        # 1. Cancel the OAuth flow
        success, error_msg = await mcp_service.oauth_service.cancel_oauth_flow(user_id, server_name)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg or "Failed to cancel OAuth flow")

        # 2. Update user connection state to DISCONNECTED
        try:
            await mcp_service.connection_service.update_connection_state(
                user_id=user_id,
                server_name=server_name,
                state=ConnectionState.DISCONNECTED,
                details={
                    "oauth_cancelled": True,
                    "cancelled_at": time.time(),
                    "reason": "User cancelled OAuth flow"
                }
            )
            logger.info(f"[OAuth Cancel] Updated connection state to DISCONNECTED for {server_name}")
        except Exception as e:
            logger.warning(f"[OAuth Cancel] Failed to update connection state: {e}")

        return {
            "success": True,
            "message": f"OAuth flow for {server_name} cancelled successfully",
            "server_name": server_name,
            "user_id": user_id
        }
    except HTTPException:
        # Re-raise HTTP exceptions with their original status code
        raise
    except Exception as e:
        logger.error(f"Failed to cancel OAuth flow: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel flow: {str(e)}"
        )


@router.post("/oauth/refresh/{server_name}")
async def refresh_oauth_tokens(
        server_name: str,
        current_user: CurrentUser,
        mcp_service: MCPService = Depends(get_mcp_service)
) -> Dict[str, Any]:
    """
    Refresh OAuth tokens
    
    Notes: POST /oauth/refresh/:serverName
    TypeScript implementation: Call MCPOAuthHandler.refreshOAuthTokens()
    
    Process:
    1. Refresh OAuth tokens
    2. Update user connection state to CONNECTED
    3. Clear any reconnection attempts
    """
    try:
        user_id = current_user.get("user_id")
        logger.info(f"[OAuth Refresh] Refreshing OAuth tokens for {server_name} by user {user_id}")

        # 1. Refresh OAuth tokens
        success, error_msg = await mcp_service.oauth_service.refresh_tokens(user_id, server_name)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg or "Failed to refresh tokens")

        logger.info(f"[OAuth Refresh] Successfully refreshed tokens for {server_name}")

        # 2. Update user connection state to CONNECTED
        try:
            # Check if user connection exists, if not create it
            connection = await mcp_service.connection_service.get_connection(user_id, server_name)
            if connection:
                # Update existing connection
                await mcp_service.connection_service.update_connection_state(
                    user_id=user_id,
                    server_name=server_name,
                    state=ConnectionState.CONNECTED,
                    details={
                        "oauth_refreshed": True,
                        "refreshed_at": time.time()
                    }
                )
                logger.info(f"[OAuth Refresh] Updated connection state to CONNECTED for {server_name}")
            else:
                # Create new connection if it doesn't exist
                await mcp_service.connection_service.create_user_connection(
                    user_id=user_id,
                    server_name=server_name,
                    initial_state=ConnectionState.CONNECTED,
                    details={
                        "oauth_refreshed": True,
                        "created_at": time.time(),
                        "refreshed_at": time.time()
                    }
                )
                logger.info(f"[OAuth Refresh] Created new connection with CONNECTED state for {server_name}")
        except Exception as e:
            logger.warning(f"[OAuth Refresh] Failed to update connection state: {e}")

        # 3. Clear any reconnection attempts
        try:
            reconnection_manager = get_reconnection_manager(
                mcp_service=mcp_service,
                oauth_service=mcp_service.oauth_service
            )
            reconnection_manager.clear_reconnection(user_id, server_name)
            logger.debug(f"[OAuth Refresh] Cleared reconnection attempts for {server_name}")
        except Exception as e:
            logger.warning(f"[OAuth Refresh] Could not clear reconnection (manager not initialized): {e}")

        return {
            "success": True,
            "message": f"Tokens refreshed successfully for {server_name}",
            "server_name": server_name,
            "user_id": user_id
        }
    except HTTPException:
        # Re-raise HTTP exceptions with their original status code
        raise
    except Exception as e:
        logger.error(f"Failed to refresh OAuth tokens: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to refresh tokens: {str(e)}")


# ==================== Helper Functions ====================

def _redirect_to_page(server_name: str,
                      flag: str = "error",
                      error_msg: str = None) -> RedirectResponse:
    """
    Generate a response that redirects to frontend OAuth callback page.
        /oauth/callback?type=success&serverName=value
        /oauth/callback?type=error&serverName=value&error=value
    """
    base_path = REGISTRY_CONSTANTS.NGINX_BASE_PATH.rstrip("/")
    encoded_server = quote(str(server_name))

    redirect_url = f"/{base_path}/oauth/callback?type={flag}&serverName={encoded_server}"

    if error_msg and flag == "error":
        encoded_error = quote(str(error_msg))
        redirect_url += f"&error={encoded_error}"

    logger.debug(f"[OAuth Redirect] Redirecting to {flag} page: {redirect_url}")
    return RedirectResponse(url=redirect_url)
