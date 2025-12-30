import asyncio
import time
import secrets
import os
from typing import Dict, Optional, Any
from registry.models.models import OAuthFlow, MCPOAuthFlowMetadata, OAuthTokens, OAuthClientInformation, OAuthMetadata
from registry.schemas.enums import OAuthFlowStatus
from registry.utils.log import logger



class FlowStateManager:
    """OAuth flow manager"""
    
    STATE_SEPARATOR = "##"  # state separator

    def __init__(self):
        self.flows: Dict[str, OAuthFlow] = {} # TODO:  添加redis
        self._lock = asyncio.Lock()
        self._flow_ttl = 600  # Flow time-to-live (seconds)
        logger.info("FlowStateManager instance created")

    def generate_flow_id(self, user_id: str, server_name: str) -> str:
        """Generate OAuth flow ID"""
        timestamp = int(time.time() * 1000)
        random_hex = secrets.token_hex(4)
        return f"{user_id}-{server_name}-{timestamp}-{random_hex}"
    
    def encode_state(self, flow_id: str, security_token: Optional[str] = None) -> str:
        """Encode state parameter"""
        if security_token is None:
            security_token = secrets.token_urlsafe(32)
        
        state = f"{flow_id}{self.STATE_SEPARATOR}{security_token}"
        logger.debug(f"Encoded state: flow_id={flow_id}, token_length={len(security_token)}")
        return state
    
    def decode_state(self, state: str) -> tuple[str, str]:
        """Decode state parameter"""
        if self.STATE_SEPARATOR not in state:
            error_msg = f"Invalid state format: missing separator '{self.STATE_SEPARATOR}'"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        parts = state.split(self.STATE_SEPARATOR, 1)
        if len(parts) != 2:
            error_msg = f"Invalid state format: expected 2 parts, got {len(parts)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        flow_id, security_token = parts
        logger.debug(f"Decoded state: flow_id={flow_id}, token_length={len(security_token)}")
        return flow_id, security_token

    def create_flow_metadata(
            self,
            server_name: str,
            user_id: str,
            server_url: str,
            code_verifier: str,
            oauth_config: Dict[str, Any],
            flow_id: str
    ) -> MCPOAuthFlowMetadata:
        """Create OAuth flow metadata"""
        # Generate secure state parameter (flow_id##random_token)
        security_token = secrets.token_urlsafe(32)
        state = self.encode_state(flow_id, security_token)
        
        return MCPOAuthFlowMetadata(
            server_name=server_name,
            user_id=user_id,
            server_url=server_url,
            state=state,
            code_verifier=code_verifier,
            client_info=self._create_client_info(oauth_config, server_name),
            metadata=self._create_oauth_metadata(oauth_config)
        )

    def create_flow(
            self,
            flow_id: str,
            server_name: str,
            user_id: str,
            code_verifier: str,
            metadata: MCPOAuthFlowMetadata
    ) -> OAuthFlow:
        """Create OAuth flow"""
        flow = OAuthFlow(
            flow_id=flow_id,
            server_name=server_name,
            user_id=user_id,
            code_verifier=code_verifier,
            state=metadata.state,
            metadata=metadata
        )
        self.flows[flow_id] = flow
        logger.info(f"Created OAuth flow: flow_id={flow_id}, state={flow.state}, user={user_id}, server={server_name}")
        return flow

    def get_flow(self, flow_id: str) -> Optional[OAuthFlow]:
        """Get flow"""
        flow = self.flows.get(flow_id)
        if flow:
            logger.info(f"Flow found: {flow_id}, status: {flow.status}")
        else:
            logger.warning(f"Flow not found: {flow_id}, available flows: {list(self.flows.keys())}")
        return flow

    def is_flow_expired(self, flow: OAuthFlow) -> bool:
        """Check if flow is expired"""
        return time.time() - flow.created_at > self._flow_ttl

    def delete_flow(self, flow_id: str) -> None:
        """Delete flow"""
        if flow_id in self.flows:
            del self.flows[flow_id]

    def complete_flow(self, flow_id: str, tokens: OAuthTokens) -> None:
        """Complete flow"""
        flow = self.flows.get(flow_id)
        if flow:
            flow.status = OAuthFlowStatus.COMPLETED
            flow.completed_at = time.time()
            flow.tokens = tokens
            self.delete_flow(flow_id) #
            logger.info(f"Completed flow: {flow_id}, status: {flow.status}")

    def fail_flow(self, flow_id: str, error: str) -> None:
        """Mark flow as failed"""
        flow = self.flows.get(flow_id)
        if flow:
            flow.status = OAuthFlowStatus.FAILED
            flow.error = error

    def cancel_user_flow(self, user_id: str, server_name: str) -> bool:
        """Cancel user's OAuth flow"""
        flow_to_cancel = None
        for flow_id, flow in self.flows.items():
            if flow.user_id == user_id and flow.server_name == server_name and flow.status == "pending":
                flow_to_cancel = flow
                break

        if not flow_to_cancel:
            return False

        # Set fail status
        flow_to_cancel.status = OAuthFlowStatus.FAILED
        flow_to_cancel.error = "User cancelled OAuth flow"
        return True

    def get_user_flows(self, user_id: str, server_name: str) -> list:
        """Get all flows for user and server"""
        user_flows = []
        for flow_id, flow in self.flows.items():
            if flow.user_id == user_id and flow.server_name == server_name:
                user_flows.append(flow)
        return user_flows

    def _create_client_info(self, oauth_config: Dict[str, Any], server_name: str) -> OAuthClientInformation:
        """Create client information"""
        redirect_uri = oauth_config.get("redirect_uri")
        if not redirect_uri:
            base_url = os.environ.get("REGISTRY_URL", "http://127.0.0.1:3080")
            redirect_uri = f"{base_url}/api/mcp/{server_name}/oauth/callback"

        redirect_uris = [redirect_uri] if redirect_uri else []

        # TODO: Fixed for testing environment, needs adjustment
        redirect_uris = ['http://localhost:3080/api/mcp/github-copilot/oauth/callback']
        return OAuthClientInformation(
            client_id=oauth_config.get("client_id", ""),
            client_secret=oauth_config.get("client_secret"),
            redirect_uris=redirect_uris,
            scope=" ".join(oauth_config.get("scopes", [])),
            additional_params=oauth_config.get("additional_params")
        )

    def _create_oauth_metadata(self, oauth_config: Dict[str, Any]) -> OAuthMetadata:
        """Create OAuth metadata"""
        return OAuthMetadata(
            authorization_endpoint=oauth_config.get("auth_url", ""),
            token_endpoint=oauth_config.get("token_url", ""),
            issuer=oauth_config.get("issuer", ""),
            scopes_supported=oauth_config.get("scopes", []),
            grant_types_supported=oauth_config.get("grant_types_supported", ["authorization_code", "refresh_token"]),
            token_endpoint_auth_methods_supported=oauth_config.get("token_endpoint_auth_methods_supported",
                                                                   ["client_secret_basic", "client_secret_post"]),
            response_types_supported=oauth_config.get("response_types_supported", ["code"]),
            code_challenge_methods_supported=oauth_config.get("code_challenge_methods_supported", ["S256", "plain"])
        )


_flow_state_manager_instance: Optional[FlowStateManager] = None

def get_flow_state_manager() -> FlowStateManager:
    """Get flow state manager"""
    global _flow_state_manager_instance
    if _flow_state_manager_instance is None:
        _flow_state_manager_instance = FlowStateManager()
        logger.info("Initialized global FlowStateManager singleton")
    return _flow_state_manager_instance
