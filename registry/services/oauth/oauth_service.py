from typing import Dict, Optional, Any, Tuple
from registry.auth.oauth import OAuthHttpClient, get_flow_state_manager, FlowStateManager, parse_scope
from registry.models.oauth_models import OAuthTokens
from registry.schemas.enums import OAuthFlowStatus
from registry.utils.utils import generate_code_verifier, generate_code_challenge
from registry.services.server_service_v1 import server_service_v1 as server_service
from registry.services.oauth.token_service import token_service

from registry.utils.log import logger
from registry.utils.crypto_utils import decrypt_auth_fields


class MCPOAuthService:
    """
    MCP OAuth service, referencing TypeScript MCPOAuthHandler
    
    Notes: MCPOAuthHandler class
    
    """

    def __init__(self, flow_manager: Optional[FlowStateManager] = None):
        self.flow_manager = flow_manager or get_flow_state_manager()
        self.http_client = OAuthHttpClient()

    async def initiate_oauth_flow(
            self,
            user_id: str,
            server_id: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Initialize OAuth flow
        
        Notes: MCPOAuthHandler.initiateOAuthFlow()
        """
        try:
            logger.info(f"Starting OAuth flow for user={user_id}, server={server_id}")

            mcp_server = await server_service.get_server_by_id(server_id)
            if not mcp_server:
                return None, None, "Server not found"

            # Check if server requires OAuth
            if not mcp_server.config.get("requiresOAuth"):
                return None, None, f"Server '{server_id}' does not require OAuth"

            # Get OAuth config from authentication
            oauth_config = mcp_server.config.get("oauth")
            if not oauth_config:
                return None, None, f"Server '{server_id}' authentication configuration not found"
            
            # OAuth configuration is directly under authentication
            oauth_config = decrypt_auth_fields(oauth_config)

            # Debug logs: verify OAuth configuration
            logger.debug(f"OAuth config keys: {list(oauth_config.keys())}")
            logger.debug(f"authorization_url: {oauth_config.get('authorization_url')}")
            logger.debug(f"token_url: {oauth_config.get('token_url')}")
            logger.debug(f"client_id: {oauth_config.get('client_id')}")
            logger.debug(f"scope: {oauth_config.get('scope')}")

            # Generate PKCE parameters
            code_verifier = generate_code_verifier()
            code_challenge = generate_code_challenge(code_verifier)
            flow_id = self.flow_manager.generate_flow_id(user_id, server_id)

            # Create OAuth flow metadata (using flow_id as state)
            authorization_url = oauth_config.get("authorization_url")
            flow_metadata = self.flow_manager.create_flow_metadata(
                server_id=server_id,
                server_name=mcp_server.serverName,
                user_id=user_id,
                authorization_url=authorization_url,
                code_verifier=code_verifier,
                oauth_config=oauth_config,
                flow_id=flow_id
            )

            # Create OAuth flow
            flow = self.flow_manager.create_flow(
                flow_id=flow_id,
                server_id=server_id,
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

            logger.info(f"Initiated OAuth flow: {flow_id} for {user_id}/{server_id}")
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

            # Persist tokens to database with OAuth metadata
            metadata = {}
            if flow.metadata and flow.metadata.metadata:
                metadata = {
                    "authorization_endpoint": flow.metadata.metadata.authorization_endpoint,
                    "token_endpoint": flow.metadata.metadata.token_endpoint,
                    "issuer": flow.metadata.metadata.issuer,
                    "scopes_supported": flow.metadata.metadata.scopes_supported or [],
                    "grant_types_supported": ["authorization_code", "refresh_token"],
                    "response_types_supported": ["code"],
                }

            await token_service.store_oauth_tokens(
                user_id=flow.user_id,
                service_name=flow.server_name,
                tokens=tokens,
                metadata=metadata
            )
            logger.info(f"Persisted OAuth tokens to database for {flow.user_id}/{flow.server_id}")

            logger.info(f"Completed OAuth flow: {flow_id}")
            return True, None

        except Exception as e:
            logger.error(f"Failed to complete OAuth flow: {e}", exc_info=True)
            return False, str(e)

    async def get_tokens(self, user_id: str, server_name: str) -> Optional[OAuthTokens]:
        """
        Get user's OAuth tokens from database
        
        Args:
            user_id: 用户ID
            server_name: 服务名称
            
        Returns:
            OAuthTokens对象或None
        """
        tokens = await token_service.get_oauth_tokens(user_id, server_name)
        if tokens:
            logger.debug(f"Retrieved tokens from database for {user_id}/{server_name}")
        else:
            logger.debug(f"No tokens found in database for {user_id}/{server_name}")
        return tokens

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
            "server_id": flow.server_id,
            "user_id": flow.user_id,
            "created_at": flow.created_at,
            "completed_at": flow.completed_at
        }

    async def cancel_oauth_flow(self, user_id: str, server_id: str) -> Tuple[bool, Optional[str]]:
        """Cancel OAuth flow"""
        try:
            success = self.flow_manager.cancel_user_flow(user_id, server_id)
            if not success:
                return True, "No active OAuth flow to cancel"

            logger.info(f"Cancelled OAuth flow for {user_id}/{server_id}")
            return True, None

        except Exception as e:
            logger.error(f"Failed to cancel OAuth flow: {e}", exc_info=True)
            return False, str(e)

    async def refresh_tokens(
            self,
            user_id: str,
            server_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Refresh OAuth tokens
        """
        try:
            logger.info(f"[OAuth] Refreshing tokens for user={user_id}, server={server_id}")

            # 1. Get server OAuth config
            mcp_server = await server_service.get_server_by_id(server_id)
            if not mcp_server:
                return False, f"Server '{server_id}' not found"

            server_name = mcp_server.serverName
            # 2. Get current tokens
            current_tokens = await token_service.get_oauth_tokens(user_id, server_name)
            if not current_tokens or not current_tokens.refresh_token:
                return False, "No refresh token available"

            oauth_config = mcp_server.config.get("oauth")
            if not oauth_config:
                return False, f"Server '{server_id}' OAuth configuration not found"

            # Decrypt OAuth config
            oauth_config = decrypt_auth_fields(oauth_config)

            # 3. Refresh tokens
            new_tokens = await self.http_client.refresh_tokens(
                oauth_config=oauth_config,
                refresh_token=current_tokens.refresh_token
            )

            if not new_tokens:
                return False, "Token refresh failed"

            # Log refresh_token rotation
            has_new_refresh = new_tokens.refresh_token is not None
            logger.info(f"[OAuth] Token refresh successful for {server_id}, "
                f"refresh_token_rotated={has_new_refresh}")

            if not has_new_refresh:
                logger.debug(
                    f"[OAuth] OAuth server did not rotate refresh_token for {server_id} "
                    f"(normal for non-rotating providers)"
                )

            # 4. Store new tokens (handles rotation automatically)
            auth_url = oauth_config.get("authorization_url")
            scopes = parse_scope(oauth_config.get("scope"), default=[])
            
            metadata = {
                "authorization_endpoint": auth_url,
                "token_endpoint": oauth_config.get("token_url"),
                "issuer": oauth_config.get("issuer"),
                "scopes_supported": scopes,
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "response_types_supported": ["code"],
            }
            await token_service.store_oauth_tokens(
                user_id=user_id,
                service_name=server_name,
                tokens=new_tokens,
                metadata=metadata
            )
            logger.info(f"Persisted refreshed tokens to database for {user_id}/{server_name}")
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
            if flow.status == OAuthFlowStatus.FAILED:
                return True
        return False


_oauth_service_instance: Optional[MCPOAuthService] = None


async def get_oauth_service() -> MCPOAuthService:
    global _oauth_service_instance
    if _oauth_service_instance is None:
        _oauth_service_instance = MCPOAuthService()
    return _oauth_service_instance
