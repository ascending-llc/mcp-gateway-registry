from typing import Dict, Optional, Any, Tuple
from fastapi import Depends

from registry.models.models import OAuthTokens
from registry.services.oauth.service import MCPConfigService, get_config_service
from .flow_state_manager import FlowStateManager, get_flow_state_manager
from .token_manager import OAuthTokenManager
from .oauth_http_client import OAuthHttpClient
from registry.schemas.enums import OAuthFlowStatus
from registry.utils.utils import generate_code_verifier, generate_code_challenge

from registry.utils.log import logger

class MCPOAuthService:
    """
    MCP OAuth service, referencing TypeScript MCPOAuthHandler
    
    Notes: MCPOAuthHandler class
    
    """

    def __init__(self, config_service, flow_manager: Optional[FlowStateManager] = None):
        self.config_service = config_service
        self.flow_manager = flow_manager or get_flow_state_manager()
        self.token_manager = OAuthTokenManager()
        self.http_client = OAuthHttpClient()

    async def initiate_oauth_flow(
            self,
            user_id: str,
            server_name: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Initialize OAuth flow
        
        Notes: MCPOAuthHandler.initiateOAuthFlow()
        """
        try:
            logger.info(f"Starting OAuth flow for user={user_id}, server={server_name}")

            # Get server configuration
            config = self.config_service.get_server_config(server_name)
            if not config.requires_oauth:
                return None, None, f"Server '{server_name}' does not require OAuth"

            if not config.oauth_config:
                return None, None, f"Server '{server_name}' missing OAuth configuration"

            # Generate PKCE parameters
            code_verifier = generate_code_verifier()
            code_challenge = generate_code_challenge(code_verifier)
            flow_id = self.flow_manager.generate_flow_id(user_id, server_name)

            # Create OAuth flow metadata (using flow_id as state)
            flow_metadata = self.flow_manager.create_flow_metadata(
                server_name=server_name,
                user_id=user_id,
                server_url=config.url or "",
                code_verifier=code_verifier,
                oauth_config=config.oauth_config,
                flow_id=flow_id  # Pass flow_id as state
            )

            # Create OAuth flow
            flow = self.flow_manager.create_flow(
                flow_id=flow_id,
                server_name=server_name,
                user_id=user_id,
                code_verifier=code_verifier,
                metadata=flow_metadata
            )

            # Build authorization URL
            auth_url = self.http_client.build_authorization_url(
                flow_metadata=flow_metadata,
                code_challenge=code_challenge,
                flow_id=flow_id
            )

            logger.info(f"Initiated OAuth flow: {flow_id} for {user_id}/{server_name}")
            return flow_id, auth_url, None

        except Exception as e:
            logger.error(f"Failed to initiate OAuth flow: {e}", exc_info=True)
            return None, None, str(e)

    async def complete_oauth_flow(
            self,
            flow_id: str,
            authorization_code: str,
            state: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Complete OAuth flow
        
        Notes: MCPOAuthHandler.completeOAuthFlow()
        """
        try:
            # 1. Decode state parameter to get flow_id
            try:
                decoded_flow_id, security_token = self.flow_manager.decode_state(state)
            except ValueError as e:
                logger.error(f"Failed to decode state: {e}")
                return False, "Invalid state format"

            # 2. Verify flow_id consistency
            if decoded_flow_id != flow_id:
                logger.error(f"Flow ID mismatch: decoded={decoded_flow_id}, provided={flow_id}")
                return False, "Flow ID mismatch"

            # 3. Get flow
            flow = self.flow_manager.get_flow(flow_id)
            if not flow:
                return False, f"Flow '{flow_id}' not found"

            # 4. Verify state (should match exactly, including security token)
            if flow.state != state:
                logger.error(f"State mismatch: flow.state={flow.state}, received state={state}")
                return False, "Invalid state parameter"

            logger.info(f"State validation passed for flow {flow_id} (with security token)")

            # Check if flow has expired
            if self.flow_manager.is_flow_expired(flow):
                self.flow_manager.delete_flow(flow_id)
                return False, "Flow expired"

            # Get flow metadata
            if not flow.metadata:
                return False, "Flow metadata not found"

            # Exchange tokens
            tokens = await self.http_client.exchange_code_for_tokens(
                flow_metadata=flow.metadata,
                authorization_code=authorization_code
            )

            if not tokens:
                return False, "Failed to exchange code for tokens"

            # Update flow status
            self.flow_manager.complete_flow(flow_id, tokens)

            # Store tokens
            await self.token_manager.store_tokens(flow.user_id, flow.server_name, tokens)

            logger.info(f"Completed OAuth flow: {flow_id}")
            return True, None

        except Exception as e:
            logger.error(f"Failed to complete OAuth flow: {e}", exc_info=True)
            return False, str(e)

    async def get_tokens(self, user_id: str, server_name: str) -> Optional[OAuthTokens]:
        """Get user's OAuth tokens"""
        return await self.token_manager.get_tokens(user_id, server_name)

    async def get_tokens_by_flow_id(self, flow_id: str) -> Optional[OAuthTokens]:
        """Get OAuth tokens by flow ID"""
        flow = self.flow_manager.get_flow(flow_id)
        if not flow or flow.status != OAuthFlowStatus.COMPLETED:
            return None
        return flow.tokens

    async def get_flow_status(self, flow_id: str) -> Dict[str, Any]:
        """Get flow status"""
        flow = self.flow_manager.get_flow(flow_id)
        if not flow:
            return {
                "status": "not_found",
                "error": f"Flow '{flow_id}' not found"
            }

        return {
            "status": flow.status,
            "completed": flow.status == OAuthFlowStatus.COMPLETED,
            "failed": flow.status == OAuthFlowStatus.FAILED,
            "error": flow.error,
            "server_name": flow.server_name,
            "user_id": flow.user_id,
            "created_at": flow.created_at,
            "completed_at": flow.completed_at
        }

    async def cancel_oauth_flow(self, user_id: str, server_name: str) -> Tuple[bool, Optional[str]]:
        """Cancel OAuth flow"""
        try:
            success = self.flow_manager.cancel_user_flow(user_id, server_name)
            if not success:
                return True, "No active OAuth flow to cancel"

            logger.info(f"Cancelled OAuth flow for {user_id}/{server_name}")
            return True, None

        except Exception as e:
            logger.error(f"Failed to cancel OAuth flow: {e}", exc_info=True)
            return False, str(e)

    async def refresh_tokens(
            self,
            user_id: str,
            server_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Refresh OAuth tokens
        
        Notes: MCPOAuthHandler.refreshOAuthTokens()
        """
        try:
            # Get current tokens
            tokens = await self.get_tokens(user_id, server_name)
            if not tokens or not tokens.refresh_token:
                return False, "No refresh token available"

            # Get server configuration
            config = self.config_service.get_server_config(server_name)
            if not config or not config.oauth_config:
                return False, f"Server '{server_name}' configuration not found"

            # Refresh tokens
            new_tokens = await self.http_client.refresh_tokens(
                oauth_config=config.oauth_config,
                refresh_token=tokens.refresh_token
            )

            if not new_tokens:
                return False, "Failed to refresh tokens"

            # Store new tokens
            await self.token_manager.store_tokens(user_id, server_name, new_tokens)
            logger.info(f"Refreshed tokens for {user_id}/{server_name}")
            return True, None

        except Exception as e:
            logger.error(f"Failed to refresh tokens: {e}", exc_info=True)
            return False, str(e)

    async def has_active_flow(self, user_id: str, server_name: str) -> bool:
        """Check if there is an active OAuth flow"""
        user_flows = self.flow_manager.get_user_flows(user_id, server_name)
        return len(user_flows) > 0

    async def has_failed_flow(self, user_id: str, server_name: str) -> bool:
        """Check if there is a failed OAuth flow"""
        user_flows = self.flow_manager.get_user_flows(user_id, server_name)
        for flow in user_flows:
            if flow.status == "failed":
                return True
        return False


async def get_oauth_service(config_service: MCPConfigService = Depends(get_config_service)) -> MCPOAuthService:
    service = MCPOAuthService(config_service)
    logger.debug(f"Created MCPOAuthService with FlowStateManager id: {id(service.flow_manager)}")
    return service
