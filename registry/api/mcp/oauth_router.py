from typing import Dict, Any, Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer
from registry.auth.dependencies import CurrentUser
from services.oauth.mcp_service import get_mcp_service, MCPService
from registry.utils.log import logger
from registry.utils.utils import load_template

router = APIRouter()
security = HTTPBearer()


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
        user_id = user_context.get('username')
        logger.info(f"OAuth service config service id: {id(mcp_service.config_service)}")

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
    except Exception as e:
        logger.error(f"Failed to initialize OAuth flow: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to initialize OAuth flow: {str(e)}")


@router.get("/{server_name}/oauth/callback")
async def oauth_callback(
        server_name: str,
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
            # URL encode error message
            encoded_error = quote(str(error))
            return RedirectResponse(url=f"/api/mcp/oauth/error?error={encoded_error}")

        # 2. Validate required parameters
        if not code or not isinstance(code, str):
            logger.error("[MCP OAuth] Missing or invalid authorization code")
            return RedirectResponse(url="/api/mcp/oauth/error?error=missing_code")

        if not state or not isinstance(state, str):
            logger.error("[MCP OAuth] Missing or invalid state parameter")
            return RedirectResponse(url="/api/mcp/oauth/error?error=missing_state")

        # 3. Decode flow_id from state (state format: flow_id##security_token)
        try:
            flow_id, security_token = mcp_service.oauth_service.flow_manager.decode_state(state)
            logger.info(f"[MCP OAuth] Callback received: server={server_name}, "
                        f"flow_id={flow_id}, code={'present' if code else 'missing'}, "
                        f"security_token_length={len(security_token)}")
        except ValueError as e:
            logger.error(f"[MCP OAuth] Failed to decode state: {e}")
            return RedirectResponse(url="/api/mcp/oauth/error?error=invalid_state_format")

        # Check if flow is already completed
        flow = mcp_service.oauth_service.flow_manager.get_flow(flow_id)
        if flow and flow.status == "completed":
            logger.warning(f"[MCP OAuth] Flow already completed, preventing duplicate token exchange: {flow_id}")
            encoded_server_name = quote(server_name)
            return RedirectResponse(url=f"/api/mcp/oauth/success?serverName={encoded_server_name}")

        # 4. Complete OAuth flow (validate state + exchange tokens)
        logger.debug(f"[MCP OAuth] Completing OAuth flow for {server_name}")
        success, error_msg = await mcp_service.oauth_service.complete_oauth_flow(
            flow_id=flow_id,
            authorization_code=code,
            state=state
        )

        if not success:
            logger.error(f"[MCP OAuth] Failed to complete OAuth flow: {error_msg}")
            encoded_error = quote(str(error_msg) if error_msg else "unknown_error")
            return RedirectResponse(url=f"/api/mcp/oauth/error?error={encoded_error}")

        logger.info(f"[MCP OAuth] OAuth flow completed successfully for {server_name}")

        # 5. Redirect to success page
        encoded_server_name = quote(server_name)
        return RedirectResponse(url=f"/api/mcp/oauth/success?serverName={encoded_server_name}")

    except Exception as e:
        logger.error(f"[MCP OAuth] OAuth callback error: {str(e)}", exc_info=True)
        encoded_error = quote("callback_failed")
        return RedirectResponse(url=f"/api/mcp/oauth/error?error={encoded_error}")


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
        user_id = current_user.get("username")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid user ID")

        # 1. Verify flow_id belongs to current user
        if not flow_id.startswith(f"{user_id}-") and not flow_id.startswith("system:"):
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
    
    """
    try:
        user_id = current_user.get("id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Invalid user ID")
        success, error_msg = await mcp_service.oauth_service.cancel_oauth_flow(user_id, server_name)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg or "Failed to cancel OAuth flow")

        return {
            "success": True,
            "message": "OAuth flow cancelled",
            "server_name": server_name,
            "user_id": user_id
        }
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
    """
    try:
        user_id = current_user.get("id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user ID"
            )
        success, error_msg = await mcp_service.oauth_service.refresh_tokens(user_id, server_name)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg or "Failed to refresh tokens")
        return {
            "success": True,
            "message": "Tokens refreshed",
            "server_name": server_name,
            "user_id": user_id
        }
    except Exception as e:
        logger.error(f"Failed to refresh OAuth tokens: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to refresh tokens: {str(e)}")


# ==================== Helper Routes ====================

@router.get("/oauth/success")
async def oauth_success(
        serverName: Optional[str] = Query(None, description="Server name")
) -> HTMLResponse:
    """
    OAuth authorization success page
    
    Notes: Redirect to /oauth/success?serverName=xxx
    
    Provides a friendly HTML page showing success message and automatically closes window
    """
    server_display = serverName if serverName else "MCP Server"

    context = {
        "server_display": server_display,
        "server_name": serverName or ""
    }

    html_content = load_template("oauth_success.html", context)
    return HTMLResponse(content=html_content, status_code=200)


@router.get("/oauth/error")
async def oauth_error(
        error: Optional[str] = Query(None, description="Error message")
) -> HTMLResponse:
    """
    OAuth authorization failure page
    
    Notes: Redirect to /oauth/error?error=xxx
    
    Provides a friendly HTML page showing error message
    """
    error_message = error if error else "Unknown error"

    error_messages = {
        "missing_code": "Missing authorization code",
        "missing_state": "Missing state parameter",
        "invalid_state_format": "Invalid state parameter format",
        "invalid_state": "Invalid state parameter",
        "callback_failed": "Callback processing failed",
        "access_denied": "User denied authorization",
        "server_error": "Server error",
        "temporarily_unavailable": "Service temporarily unavailable",
    }

    display_error = error_messages.get(error_message, error_message)

    context = {
        "display_error": display_error,
        "error_message": error_message
    }

    html_content = load_template("oauth_error.html", context)
    return HTMLResponse(content=html_content, status_code=400)
