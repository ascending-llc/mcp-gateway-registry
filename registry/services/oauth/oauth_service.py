from typing import Dict, Optional, Any, Tuple

from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument
from registry.auth.oauth import OAuthHttpClient, get_flow_state_manager, FlowStateManager, parse_scope
from registry.models.oauth_models import OAuthTokens
from registry.schemas.enums import OAuthFlowStatus
from registry.utils.utils import generate_code_verifier, generate_code_challenge
from registry.services.server_service import server_service_v1 as server_service
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
            server: MCPServerDocument
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Initialize OAuth flow
        
        Notes: MCPOAuthHandler.initiateOAuthFlow()
        """
        try:
            server_id = str(server.id)
            logger.info(f"Starting OAuth flow for user={user_id}, server={server_id}")

            # Get OAuth config from authentication
            oauth_config = server.config.get("oauth")
            if not oauth_config:
                return None, None, f"Server '{server.serverName}' authentication configuration not found"

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
                server_name=server.serverName,
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

    async def get_valid_access_token(
            self,
            user_id: str,
            server: MCPServerDocument
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Get valid access token with automatic refresh and re-authentication flow
        
        This method implements the complete token lifecycle:
        1. Try to use existing access token (if not expired)
        2. If expired, try to refresh using refresh token
        3. If refresh fails, return OAuth required error to initiate new flow
        
        Args:
            user_id: User ID
            server: MCPServer document
            
        Returns:
            Tuple of (access_token, auth_url, error_message)
            - (token, None, None) if token is valid or refreshed successfully
            - (None, auth_url, None) if re-authentication is needed
            - (None, None, error) if an error occurred
        """
        try:
            server_name = server.serverName

            # 1. Check if access token exists and is not expired
            is_expired = await token_service.is_access_token_expired(user_id, server_name)

            if not is_expired:
                tokens = await token_service.get_oauth_tokens(user_id, server_name)
                if tokens and tokens.access_token:
                    logger.debug(f"Using existing valid access token for {user_id}/{server_name}")
                    return tokens.access_token, None, None

            logger.info(f"Access token expired or missing for {user_id}/{server_name}, attempting refresh")

            # 2. Try refresh token if access token is expired/missing
            has_refresh = await token_service.has_refresh_token(user_id, server_name)

            if has_refresh:
                success, error = await self.validate_and_refresh_tokens(user_id, server)

                if success:
                    tokens = await token_service.get_oauth_tokens(user_id, server_name)
                    if tokens and tokens.access_token:
                        logger.info(f"Successfully refreshed access token for {user_id}/{server_name}")
                        return tokens.access_token, None, None

                logger.warning(f"Token refresh failed for {user_id}/{server_name}: {error}")
            else:
                logger.info(f"No refresh token available for {user_id}/{server_name}")

            # 3. Both access and refresh failed - initiate new OAuth flow
            logger.info(f"Initiating new OAuth flow for {user_id}/{server_name}")
            flow_id, auth_url, flow_error = await self.initiate_oauth_flow(user_id, server)

            if flow_error:
                return None, None, f"Failed to initiate OAuth flow: {flow_error}"

            return None, auth_url, None

        except Exception as e:
            logger.error(f"Error getting valid access token: {e}", exc_info=True)
            return None, None, str(e)

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

    async def refresh_token(
            self,
            user_id: str,
            server_id: str,
            server_name: str,
            refresh_token_value: str,
            oauth_config: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Refresh OAuth token using provided refresh_token value
        
        Core refresh logic: exchanges refresh_token for new access_token and saves to database.
        
        Args:
            user_id: User ID
            server_id: Server ID
            server_name: Server name
            refresh_token_value: Refresh token value
            oauth_config: Decrypted OAuth configuration
            
        Returns:
            Tuple[bool, Optional[str]]: (success, error_message)
        """
        try:
            logger.info(f"[OAuth] Refreshing token for user={user_id}, server={server_id}")

            # 1. Refresh tokens via OAuth provider
            new_tokens = await self.http_client.refresh_tokens(
                oauth_config=oauth_config,
                refresh_token=refresh_token_value
            )

            if not new_tokens:
                return False, "Token refresh failed"

            # 2. Log refresh_token rotation
            has_new_refresh = new_tokens.refresh_token is not None
            logger.info(f"[OAuth] Token refresh successful for {server_id}, "
                        f"refresh_token_rotated={has_new_refresh}")

            if not has_new_refresh:
                logger.debug(f"[OAuth] OAuth server did not rotate refresh_token for {server_id} "
                             f"(normal for non-rotating providers)")

            # 3. Store new tokens (handles rotation automatically)
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
            return True, None

        except Exception as e:
            logger.error(f"Failed to refresh token: {e}", exc_info=True)
            return False, str(e)

    async def validate_and_refresh_tokens(
            self,
            user_id: str,
            mcp_server: MCPServerDocument
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate and refresh OAuth tokens (with token retrieval and validation)
        
        This method is used by external APIs that need full validation.
        For internal use with pre-validated tokens, use refresh_token() instead.
        """
        try:
            logger.info(f"[OAuth] Validating and refreshing tokens for user={user_id}, server={mcp_server}")
            server_name = mcp_server.serverName
            server_id = str(mcp_server.id)

            # 2. Get current tokens
            current_tokens = await token_service.get_oauth_tokens(user_id, server_name)
            if not current_tokens or not current_tokens.refresh_token:
                return False, "No refresh token available"

            # 3. Get OAuth config
            oauth_config = mcp_server.config.get("oauth")
            if not oauth_config:
                return False, f"Server '{server_id}' OAuth configuration not found"

            # Decrypt OAuth config
            oauth_config = decrypt_auth_fields(oauth_config)

            # 4. Call core refresh logic
            return await self.refresh_token(
                user_id=user_id,
                server_id=server_id,
                server_name=server_name,
                refresh_token_value=current_tokens.refresh_token,
                oauth_config=oauth_config
            )

        except Exception as e:
            logger.error(f"Failed to validate and refresh tokens: {e}", exc_info=True)
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

    async def handle_reinitialize_auth(
            self,
            user_id: str,
            server: MCPServerDocument
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Handle OAuth authentication for server reinitialization
        
        Decision tree:
        1. Check if access_token exists
           ├─ Exists
           │  ├─ Valid → CONNECTED, return success (Step 2.1)
           │  └─ Expired
           │     ├─ refresh_token exists and valid → Refresh → CONNECTED (Step 2.2.1.2)
           │     └─ refresh_token invalid/missing → CONNECTING, return OAuth URL (Step 2.2.1.1)
           └─ Not exists
              ├─ refresh_token exists and valid → Refresh → CONNECTED (Step 3.1.2)
              └─ refresh_token invalid/missing → CONNECTING, return OAuth URL (Step 3.1.1/3.2)
        
        Args:
            user_id: User ID
            server: Server document containing all server configuration
            
        Returns:
            Tuple[bool, Dict]: (needs_connection, response_data)
                - needs_connection: True if connection should be marked as CONNECTED
                - response_data: Response content dict
        """
        server_id = str(server.id)
        server_name = server.serverName

        # Check token status
        access_token_doc, access_valid = await token_service.get_access_token_status(
            user_id, server_name
        )
        refresh_token_doc, refresh_valid = await token_service.get_refresh_token_status(
            user_id, server_name
        )

        logger.debug(f"[Reinitialize] Token status for {server_name}({server_id}): "
                     f"access_exists={access_token_doc is not None}, "
                     f"access_valid={access_valid}, "
                     f"refresh_exists={refresh_token_doc is not None}, "
                     f"refresh_valid={refresh_valid}")

        # Branch 1: Access token exists
        if access_token_doc is not None:
            # Step 2.1: Access token is valid
            if access_valid:
                logger.info(f"[Reinitialize] Valid access token for {server_name}({server_id})")
                return True, self._build_success_response(server)

            # Step 2.2: Access token is expired
            # Step 2.2.1.2: Refresh token exists and valid
            if refresh_valid:
                logger.info(f"[Reinitialize] Access token expired for {server_name}, "
                            f"refresh token valid, attempting refresh")
                return await self._refresh_and_connect(user_id, server)

            # Step 2.2.1.1: Refresh token invalid or missing
            logger.info(f"[Reinitialize] Access token expired for {server_name}, "
                        f"no valid refresh token, initiating OAuth")
            return await self._build_oauth_required_response(user_id, server)

        # Branch 2: Access token does not exist
        # Step 3.1.2: Refresh token exists and valid
        if refresh_valid:
            logger.info(f"[Reinitialize] No access token for {server_name}, "
                        f"but refresh token valid, attempting refresh")
            return await self._refresh_and_connect(user_id, server)

        # Step 3.1.1 / 3.2 / Step 1: No valid tokens
        logger.info(f"[Reinitialize] No valid tokens for {server_name}, initiating OAuth")
        return await self._build_oauth_required_response(user_id, server)

    async def _refresh_and_connect(
            self,
            user_id: str,
            server: MCPServerDocument
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Helper method: Refresh tokens and return success response
        
        Args:
            user_id: User ID
            server: Server document containing all configuration
            
        Returns:
            Tuple[bool, Dict]: (needs_connection, response_data)
        """
        server_id = str(server.id)
        server_name = server.serverName

        try:
            # Get refresh token value (already validated by caller)
            refresh_token_doc, _ = await token_service.get_refresh_token_status(user_id, server_name)
            if not refresh_token_doc:
                logger.error(f"[Reinitialize] Refresh token disappeared for {server_name}({server_id})")
                return await self._build_oauth_required_response(user_id, server)

            # Get and decrypt OAuth config
            oauth_config = server.config.get("oauth")
            if not oauth_config:
                logger.error(f"[Reinitialize] OAuth config not found for {server_name}")
                return False, {
                    "success": False,
                    "message": f"OAuth configuration not found for server '{server_name}'",
                    "serverId": server_id,
                    "server_name": server_name
                }

            oauth_config = decrypt_auth_fields(oauth_config)

            # Call core refresh logic
            success, error = await self.refresh_token(
                user_id=user_id,
                server_id=server_id,
                server_name=server_name,
                refresh_token_value=refresh_token_doc.token,
                oauth_config=oauth_config
            )

            if success:
                logger.info(f"[Reinitialize] Token refreshed successfully for {server_name}({server_id})")
                return True, self._build_success_response(server)
            else:
                # Refresh failed - need re-authorization
                logger.warning(f"[Reinitialize] Token refresh failed for {server_name}: {error}")
                return await self._build_oauth_required_response(user_id, server)

        except Exception as e:
            logger.error(f"[Reinitialize] Error in _refresh_and_connect: {e}", exc_info=True)
            return await self._build_oauth_required_response(user_id, server)

    async def _build_oauth_required_response(
            self,
            user_id: str,
            server: MCPServerDocument
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Helper method: Build response indicating OAuth is required
        
        Does NOT initiate OAuth flow - frontend should call /{server_id}/oauth/initiate
        This ensures connection status remains DISCONNECTED until frontend starts OAuth
        
        Args:
            user_id: User ID
            server: Server document containing all configuration
            
        Returns:
            Tuple[bool, Dict]: (needs_connection=False, response_data indicating OAuth required)
        """
        return False, {
            "success": True,
            "message": "OAuth authorization required",
            "serverId": str(server.id),
            "server_name": server.serverName,
            "requires_oauth": server.config.get("requiresOAuth", False),
        }

    def _build_success_response(self, server: MCPServerDocument) -> Dict[str, Any]:
        """
        Build success response for reinitialization
        
        Args:
            server: Server document
            
        Returns:
            Response data dict
        """
        return {
            "success": True,
            "message": f"Server '{server.serverName}' reinitialized successfully",
            "server_id": str(server.id),
            "server_name": server.serverName,
            "requires_oauth": server.config.get("requiresOAuth", False)
        }


_oauth_service_instance: Optional[MCPOAuthService] = None


async def get_oauth_service() -> MCPOAuthService:
    global _oauth_service_instance
    if _oauth_service_instance is None:
        _oauth_service_instance = MCPOAuthService()
    return _oauth_service_instance
