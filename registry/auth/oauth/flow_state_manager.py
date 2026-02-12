import asyncio
import logging
import os
import secrets
import time
from typing import Any

from packages.database.redis_client import get_redis_client
from registry.auth.oauth.oauth_utils import parse_scope, scope_to_string
from registry.auth.oauth.redis_flow_storage import RedisFlowStorage
from registry.models.oauth_models import (
    MCPOAuthFlowMetadata,
    OAuthClientInformation,
    OAuthFlow,
    OAuthMetadata,
    OAuthTokens,
)
from registry.schemas.enums import OAuthFlowStatus

logger = logging.getLogger(__name__)


class FlowStateManager:
    """
    OAuth Flow State Manager
    """

    STATE_SEPARATOR = "##"  # Separator for state parameter (flow_id##security_token)
    DEFAULT_FLOW_TTL = 600  # Flow time-to-live in seconds (10 minutes)

    def __init__(self, fallback_to_memory: bool = True):
        """
        Initialize FlowStateManager with Redis backend

        Args:
            fallback_to_memory: If True, use memory storage when Redis unavailable
        """
        self._lock = asyncio.Lock()
        self._flow_ttl = self.DEFAULT_FLOW_TTL
        self._use_redis = False
        self._memory_flows: dict[str, OAuthFlow] = {}
        self._redis_storage: RedisFlowStorage | None = None

        # Try to initialize Redis storage
        try:
            redis_conn = get_redis_client()
            if redis_conn:
                redis_conn.ping()

                self._redis_storage = RedisFlowStorage(redis_conn)
                self._use_redis = True

                logger.info("FlowStateManager initialized with Redis storage")
            else:
                raise RuntimeError("Redis client not initialized")

        except Exception as e:
            if fallback_to_memory:
                logger.warning(f"Redis unavailable, using memory storage: {e}")
                self._use_redis = False
                self._redis_storage = None
            else:
                logger.error(f"Failed to initialize FlowStateManager: {e}")
                raise

    def generate_flow_id(self, user_id: str, server_id: str) -> str:
        """
        Generate OAuth flow ID
        """
        return f"{user_id}:{server_id}"

    def encode_state(self, flow_id: str, security_token: str | None = None) -> str:
        """
        Encode state parameter with CSRF protection
        """
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
        server_path: str,
        server_id: str,
        user_id: str,
        authorization_url: str,
        code_verifier: str,
        oauth_config: dict[str, Any],
        flow_id: str,
    ) -> MCPOAuthFlowMetadata:
        """Create OAuth flow metadata"""
        # Generate secure state parameter (flow_id##random_token)
        security_token = secrets.token_urlsafe(32)
        state = self.encode_state(flow_id, security_token)

        server_path = server_path.strip()

        return MCPOAuthFlowMetadata(
            server_id=server_id.strip(),
            server_name=server_name.strip(),
            server_path=server_path,
            user_id=user_id.strip(),
            authorization_url=authorization_url,
            state=state,
            code_verifier=code_verifier,
            client_info=self._create_client_info(oauth_config, server_path),
            metadata=self._create_oauth_metadata(oauth_config),
        )

    def create_flow(
        self, flow_id: str, server_id: str, user_id: str, code_verifier: str, metadata: MCPOAuthFlowMetadata
    ) -> OAuthFlow:
        """
        Create OAuth flow and persist to storage
        """
        # Create dataclass flow object
        flow = OAuthFlow(
            flow_id=flow_id,
            server_id=server_id,
            server_name=metadata.server_name,
            user_id=user_id,
            code_verifier=code_verifier,
            state=metadata.state,
            status=OAuthFlowStatus.PENDING,
            created_at=time.time(),
            metadata=metadata,
        )

        if self._use_redis and self._redis_storage:
            try:
                # Save to Redis using native storage
                success = self._redis_storage.save_flow(flow, self._flow_ttl)
                if success:
                    logger.info(f"Created OAuth flow in Redis: flow_id={flow_id}")
                else:
                    logger.warning("Failed to save to Redis, using memory fallback")
                    self._memory_flows[flow_id] = flow
            except Exception as e:
                logger.error(f"Failed to save flow to Redis, using memory: {e}")
                self._memory_flows[flow_id] = flow
        else:
            # Use memory storage
            self._memory_flows[flow_id] = flow
            logger.debug(f"Created OAuth flow in memory: flow_id={flow_id}")

        return flow

    def get_flow(self, flow_id: str) -> OAuthFlow | None:
        """
        Retrieve OAuth flow by ID

        Args:
            flow_id: Flow identifier

        Returns:
            OAuthFlow if found, None otherwise
        """
        if self._use_redis and self._redis_storage:
            try:
                flow = self._redis_storage.get_flow(flow_id)
                if flow:
                    logger.info(f"Flow found in Redis: {flow_id}, status: {flow.status}")
                else:
                    logger.warning(f"Flow not found in Redis: {flow_id}")
                return flow

            except Exception as e:
                logger.error(f"Error getting flow from Redis: {e}")
                return None
        else:
            # Use memory storage
            flow = self._memory_flows.get(flow_id)
            if flow:
                logger.debug(f"Flow found in memory: {flow_id}, status: {flow.status}")
            else:
                logger.warning(f"Flow not found in memory: {flow_id}")
            return flow

    def is_flow_expired(self, flow: OAuthFlow) -> bool:
        """
        Check if OAuth flow has expired
        """
        if not flow.created_at:
            return True
        return time.time() - flow.created_at > self._flow_ttl

    def delete_flow(self, flow_id: str) -> None:
        """
        Delete OAuth flow from storage
        """
        if self._use_redis and self._redis_storage:
            try:
                success = self._redis_storage.delete_flow(flow_id)
                if success:
                    logger.info(f"Deleted flow from Redis: {flow_id}")
            except Exception as e:
                logger.warning(f"Error deleting flow from Redis: {e}")
        else:
            # Use memory storage
            if flow_id in self._memory_flows:
                del self._memory_flows[flow_id]
                logger.debug(f"Deleted flow from memory: {flow_id}")

    def complete_flow(self, flow_id: str, tokens: OAuthTokens) -> None:
        """
        Mark OAuth flow as completed and store tokens

        """
        if self._use_redis and self._redis_storage:
            try:
                flow = self._redis_storage.get_flow(flow_id)
                if flow:
                    flow.status = OAuthFlowStatus.COMPLETED
                    flow.completed_at = time.time()
                    flow.tokens = tokens
                    self._redis_storage.save_flow(flow, self._flow_ttl)
                    logger.info(f"Completed flow in Redis: {flow_id}")
            except Exception as e:
                logger.error(f"Error completing flow in Redis: {e}")
        else:
            # Use memory storage
            flow = self._memory_flows.get(flow_id)
            if flow:
                flow.status = OAuthFlowStatus.COMPLETED
                flow.completed_at = time.time()
                flow.tokens = tokens
                logger.debug(f"Completed flow in memory: {flow_id}")

    def fail_flow(self, flow_id: str, error: str) -> None:
        """
        Mark OAuth flow as failed with error message
        """
        if self._use_redis and self._redis_storage:
            try:
                flow = self._redis_storage.get_flow(flow_id)
                if flow:
                    flow.status = OAuthFlowStatus.FAILED
                    flow.error = error
                    self._redis_storage.save_flow(flow, self._flow_ttl)
                    logger.info(f"Marked flow as failed in Redis: {flow_id}")
            except Exception as e:
                logger.error(f"Error marking flow as failed in Redis: {e}")
        else:
            # Use memory storage
            flow = self._memory_flows.get(flow_id)
            if flow:
                flow.status = OAuthFlowStatus.FAILED
                flow.error = error
                logger.debug(f"Marked flow as failed in memory: {flow_id}")

    def cancel_user_flow(self, user_id: str, server_id: str) -> bool:
        """
        Cancel pending OAuth flow for user and server
        """
        if self._use_redis and self._redis_storage:
            try:
                # Find pending flows for user and server
                flows = self._redis_storage.find_flows(user_id, server_id)
                pending_flows = [f for f in flows if f.status == OAuthFlowStatus.PENDING]

                if not pending_flows:
                    return False

                # Cancel the first pending flow
                flow_to_cancel = pending_flows[0]
                flow_to_cancel.status = OAuthFlowStatus.FAILED
                flow_to_cancel.error = "User cancelled OAuth flow"
                self._redis_storage.save_flow(flow_to_cancel, self._flow_ttl)

                logger.info(f"Cancelled flow in Redis: {flow_to_cancel.flow_id}")
                return True

            except Exception as e:
                logger.error(f"Error cancelling flow in Redis: {e}")
                return False
        else:
            # Use memory storage
            flow_to_cancel = None
            for _flow_id, flow in self._memory_flows.items():
                if flow.user_id == user_id and flow.server_id == server_id and flow.status == OAuthFlowStatus.PENDING:
                    flow_to_cancel = flow
                    break

            if not flow_to_cancel:
                return False

            flow_to_cancel.status = OAuthFlowStatus.FAILED
            flow_to_cancel.error = "User cancelled OAuth flow"
            logger.debug(f"Cancelled flow in memory: {flow_to_cancel.flow_id}")
            return True

    def get_user_flows(self, user_id: str, server_id: str) -> list[OAuthFlow]:
        """
        Get all OAuth flows for specific user and server

        """
        if self._use_redis and self._redis_storage:
            try:
                user_flows = self._redis_storage.find_flows(user_id, server_id)
                logger.debug(f"Found {len(user_flows)} flows in Redis for {user_id}/{server_id}")
                return user_flows

            except Exception as e:
                logger.error(f"Error getting user flows from Redis: {e}")
                return []
        else:
            # Use memory storage
            user_flows = []
            for _flow_id, flow in self._memory_flows.items():
                if flow.user_id == user_id and flow.server_id == server_id:
                    user_flows.append(flow)

            logger.debug(f"Found {len(user_flows)} flows in memory for {user_id}/{server_id}")
            return user_flows

    def _create_client_info(self, oauth_config: dict[str, Any], server_path: str) -> OAuthClientInformation:
        """
        Build OAuth client information from server configuration
        """
        redirect_uri = oauth_config.get("redirect_uri")
        if not redirect_uri:
            base_url = os.environ.get("REGISTRY_URL", "http://127.0.0.1:3080")
            # Ensure server_path starts with / for proper URL construction
            normalized_path = server_path if server_path.startswith("/") else f"/{server_path}"
            redirect_uri = f"{base_url}/api/v1/mcp{normalized_path}/oauth/callback"

        redirect_uris = [redirect_uri] if redirect_uri else []

        scope_string = scope_to_string(oauth_config.get("scope"))
        logger.debug(f"Client info - redirect_uris: {redirect_uris}, scopes: {scope_string}")
        return OAuthClientInformation(
            client_id=str(oauth_config.get("client_id", "")).strip(),
            client_secret=str(oauth_config.get("client_secret")).strip(),
            redirect_uris=redirect_uris,
            scope=scope_string,
            additional_params=oauth_config.get("additional_params"),
        )

    def _create_oauth_metadata(self, oauth_config: dict[str, Any]) -> OAuthMetadata:
        """
        Build OAuth metadata from server configuration
        """
        auth_url = oauth_config.get("authorization_url", "")
        token_url = oauth_config.get("token_url", "")

        scopes = parse_scope(oauth_config.get("scope"), default=[])

        return OAuthMetadata(
            authorization_endpoint=auth_url,
            token_endpoint=token_url,
            issuer=oauth_config.get("issuer", ""),
            scopes_supported=scopes,
            grant_types_supported=oauth_config.get("grant_types_supported", ["authorization_code", "refresh_token"]),
            token_endpoint_auth_methods_supported=oauth_config.get(
                "token_endpoint_auth_methods_supported", ["client_secret_basic", "client_secret_post"]
            ),
            response_types_supported=oauth_config.get("response_types_supported", ["code"]),
            code_challenge_methods_supported=oauth_config.get("code_challenge_methods_supported", ["S256", "plain"]),
        )

    async def cleanup_expired_flows(self) -> int:
        """
        Clean up expired flows from Redis or memory
        """
        if self._use_redis and self._redis_storage:
            try:
                cleaned_count = self._redis_storage.cleanup_expired(self._flow_ttl)
                if cleaned_count > 0:
                    logger.info(f"Cleaned up {cleaned_count} expired flows from Redis")
                return cleaned_count

            except Exception as e:
                logger.error(f"Error cleaning up expired flows: {e}")
                return 0
        else:
            # Use memory storage
            cleaned_count = 0
            current_time = time.time()
            expired_ids = []

            for flow_id, flow in self._memory_flows.items():
                if current_time - flow.created_at > self._flow_ttl:
                    expired_ids.append(flow_id)

            for flow_id in expired_ids:
                del self._memory_flows[flow_id]
                cleaned_count += 1

            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired flows from memory")

            return cleaned_count


_flow_state_manager_instance: FlowStateManager | None = None


def get_flow_state_manager() -> FlowStateManager:
    """Get flow state manager"""
    global _flow_state_manager_instance
    if _flow_state_manager_instance is None:
        _flow_state_manager_instance = FlowStateManager()
        logger.info("Initialized global FlowStateManager singleton")
    return _flow_state_manager_instance
