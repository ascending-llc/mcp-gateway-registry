"""OAuth client using Authlib for OAuth 2.0 operations with PKCE support."""

import logging
import secrets
from typing import Any

from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oauth2.rfc7636 import create_s256_code_challenge

from registry.models.oauth_models import MCPOAuthFlowMetadata, OAuthTokens

logger = logging.getLogger(__name__)


class OAuthClient:
    """OAuth client using Authlib for RFC-compliant OAuth 2.0 operations."""

    def __init__(self):
        """Initialize OAuth client."""
        self._clients: dict[str, AsyncOAuth2Client] = {}

    def generate_code_verifier(self) -> str:
        """Generate PKCE code_verifier using secure random generator."""
        return secrets.token_urlsafe(32)

    def generate_code_challenge(self, code_verifier: str) -> str:
        """Generate PKCE code_challenge from code_verifier using S256 method."""
        return create_s256_code_challenge(code_verifier)

    def _get_client(self, flow_metadata: MCPOAuthFlowMetadata, code_verifier: str | None = None) -> AsyncOAuth2Client:
        """
        Create Authlib OAuth2 client for the flow.

        Args:
            flow_metadata: OAuth flow metadata
            code_verifier: PKCE code verifier (required for token exchange)

        Returns:
            AsyncOAuth2Client configured for the flow
        """
        client_info = flow_metadata.client_info
        metadata = flow_metadata.metadata

        # Determine client authentication method
        auth_method = "client_secret_post"
        if metadata.token_endpoint_auth_methods_supported:
            if "client_secret_basic" in metadata.token_endpoint_auth_methods_supported:
                auth_method = "client_secret_basic"

        # Create Authlib client
        client = AsyncOAuth2Client(
            client_id=client_info.client_id,
            client_secret=client_info.client_secret,
            redirect_uri=client_info.redirect_uris[0] if client_info.redirect_uris else None,
            scope=client_info.scope,
            token_endpoint=metadata.token_endpoint,
            token_endpoint_auth_method=auth_method,
            code_challenge_method="S256",
            timeout=30.0,
        )

        # Store code_verifier for token exchange
        if code_verifier:
            client.code_verifier = code_verifier

        return client

    async def build_authorization_url(
        self, flow_metadata: MCPOAuthFlowMetadata, code_challenge: str, flow_id: str
    ) -> str:
        """
        Build OAuth authorization URL with PKCE.

        Args:
            flow_metadata: OAuth flow metadata
            code_challenge: PKCE code challenge
            flow_id: Flow identifier (for logging)

        Returns:
            Authorization URL with all required parameters
        """
        client_info = flow_metadata.client_info
        metadata = flow_metadata.metadata
        state = flow_metadata.state

        if not state.startswith(flow_id):
            logger.warning(f"State format issue: state does not start with flow_id. state={state}, flow_id={flow_id}")

        # Create temporary client for URL generation
        client = self._get_client(flow_metadata)

        # Prepare authorization URL parameters
        params = {
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        # Add additional parameters from config
        if client_info.additional_params:
            params.update(client_info.additional_params)

        # Build authorization URL using Authlib
        authorization_url, _ = client.create_authorization_url(
            metadata.authorization_endpoint,
            **params,
        )

        logger.debug(f"Built authorization URL: {authorization_url}")
        return authorization_url

    async def exchange_code_for_tokens(
        self, flow_metadata: MCPOAuthFlowMetadata, authorization_code: str
    ) -> OAuthTokens | None:
        """
        Exchange authorization code for access tokens using PKCE.

        Args:
            flow_metadata: OAuth flow metadata with code_verifier
            authorization_code: Authorization code from OAuth provider

        Returns:
            OAuthTokens if successful, None otherwise
        """
        try:
            if not flow_metadata.metadata or not flow_metadata.client_info:
                logger.error("Missing metadata or client info for token exchange")
                return None

            token_url = flow_metadata.metadata.token_endpoint
            if not token_url:
                logger.error("No token endpoint in metadata")
                return None

            logger.debug(f"Exchanging code for tokens at {token_url}")

            # Create client with code_verifier for PKCE
            client = self._get_client(flow_metadata, flow_metadata.code_verifier)

            # Additional parameters from config
            extra_params = {}
            if flow_metadata.client_info.additional_params:
                extra_params.update(flow_metadata.client_info.additional_params)

            # Exchange code for tokens using Authlib
            # Authlib automatically handles PKCE, client authentication, and token response parsing
            token_response = await client.fetch_token(
                token_url,
                code=authorization_code,
                code_verifier=flow_metadata.code_verifier,
                **extra_params,
            )

            logger.info("Token exchange successful")

            return OAuthTokens(
                access_token=token_response.get("access_token"),
                token_type=token_response.get("token_type", "Bearer"),
                expires_in=token_response.get("expires_in"),
                refresh_token=token_response.get("refresh_token"),
                scope=token_response.get("scope"),
                expires_at=token_response.get("expires_at"),  # Authlib calculates this automatically
            )

        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {e}", exc_info=True)
            return None
        finally:
            # Close the client connection
            if "client" in locals():
                await client.aclose()

    async def refresh_tokens(self, oauth_config: dict[str, Any], refresh_token: str) -> OAuthTokens | None:
        """
        Refresh OAuth tokens using refresh token.

        Args:
            oauth_config: OAuth configuration from MongoDB
            refresh_token: Current refresh token

        Returns:
            New OAuthTokens if successful, None otherwise
        """
        try:
            token_url = oauth_config.get("token_url")
            if not token_url:
                logger.error("No token URL for refresh")
                return None

            # Determine client authentication method
            auth_methods = oauth_config.get(
                "token_endpoint_auth_methods_supported", ["client_secret_basic", "client_secret_post"]
            )
            auth_method = "client_secret_basic" if "client_secret_basic" in auth_methods else "client_secret_post"

            # Handle scope format (list or string)
            scopes = oauth_config.get("scope")
            if isinstance(scopes, list):
                scope_str = " ".join(scopes)
            else:
                scope_str = scopes

            # Create temporary client for token refresh
            client = AsyncOAuth2Client(
                client_id=oauth_config.get("client_id", ""),
                client_secret=oauth_config.get("client_secret"),
                token_endpoint=token_url,
                token_endpoint_auth_method=auth_method,
                scope=scope_str,
                timeout=30.0,
            )

            logger.debug(f"Refreshing tokens at {token_url}")

            # Refresh tokens using Authlib
            # Authlib automatically handles client authentication and token response parsing
            token_response = await client.refresh_token(token_url, refresh_token=refresh_token)

            logger.info("Token refresh successful")

            return OAuthTokens(
                access_token=token_response.get("access_token"),
                token_type=token_response.get("token_type", "Bearer"),
                expires_in=token_response.get("expires_in"),
                refresh_token=token_response.get("refresh_token", refresh_token),  # Keep old if not rotated
                scope=token_response.get("scope"),
                expires_at=token_response.get("expires_at"),  # Authlib calculates this automatically
            )

        except Exception as e:
            logger.error(f"Failed to refresh tokens: {e}", exc_info=True)
            return None
        finally:
            # Close the client connection
            if "client" in locals():
                await client.aclose()

    async def close(self):
        """Close all HTTP clients."""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
