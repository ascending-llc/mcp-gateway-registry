import base64
import time
import urllib.parse
import httpx
from typing import Dict, Optional, Any
from registry.models.oauth_models import MCPOAuthFlowMetadata, OAuthTokens, TokenTransformConfig
from registry.utils.log import logger


class OAuthHttpClient:
    """OAuth HTTP client"""

    def __init__(self):
        self._http_client = httpx.AsyncClient(timeout=30.0)

    def build_authorization_url(
            self,
            flow_metadata: MCPOAuthFlowMetadata,
            code_challenge: str,
            flow_id: str
    ) -> str:
        """Build authorization URL"""
        client_info = flow_metadata.client_info
        metadata = flow_metadata.metadata

        state = flow_metadata.state

        if not state.startswith(flow_id):
            logger.warning(f"State format issue: state does not start with flow_id. state={state}, flow_id={flow_id}")

        redirect_uri = client_info.redirect_uris[0] if client_info.redirect_uris else ""
        logger.debug(f"redirect_uri={redirect_uri}")
        params = {
            "response_type": "code",
            "client_id": client_info.client_id,
            "redirect_uri": redirect_uri,
            "scope": client_info.scope or "",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }

        # Add additional parameters
        if client_info.additional_params:
            params.update(client_info.additional_params)

        # Build URL
        auth_url = metadata.authorization_endpoint
        query_string = urllib.parse.urlencode(params)

        full_url = f"{auth_url}?{query_string}"
        logger.debug(f"Built authorization URL: {full_url}")

        return full_url

    async def exchange_code_for_tokens(
            self,
            flow_metadata: MCPOAuthFlowMetadata,
            authorization_code: str
    ) -> Optional[OAuthTokens]:
        """Exchange authorization code for tokens"""
        try:
            if not flow_metadata.metadata or not flow_metadata.client_info:
                logger.error("Missing metadata or client info for token exchange")
                return None

            # Prepare request parameters
            token_url = flow_metadata.metadata.token_endpoint
            if not token_url:
                logger.error("No token endpoint in metadata")
                return None

            # Build request body
            data = {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "code_verifier": flow_metadata.code_verifier,
                "redirect_uri": flow_metadata.client_info.redirect_uris[
                    0] if flow_metadata.client_info.redirect_uris else "",
                "client_id": flow_metadata.client_info.client_id
            }

            # Add client_secret if exists
            if flow_metadata.client_info.client_secret:
                data["client_secret"] = flow_metadata.client_info.client_secret

            # Add scope if exists
            if flow_metadata.client_info.scope:
                data["scope"] = flow_metadata.client_info.scope

            # Add additional parameters
            if flow_metadata.client_info.additional_params:
                for key, value in flow_metadata.client_info.additional_params.items():
                    data[key] = value

            # Prepare request headers
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            }

            # Handle client authentication
            auth_method = flow_metadata.metadata.token_endpoint_auth_methods_supported
            if auth_method and "client_secret_basic" in auth_method and flow_metadata.client_info.client_secret:
                # Basic authentication
                credentials = f"{flow_metadata.client_info.client_id}:{flow_metadata.client_info.client_secret}"
                encoded_credentials = base64.b64encode(credentials.encode()).decode()
                headers["Authorization"] = f"Basic {encoded_credentials}"
                # Remove client_id and client_secret from data
                data.pop("client_id", None)
                data.pop("client_secret", None)

            logger.debug(f"Exchanging code for tokens at {token_url}")

            # Send request
            response = await self._http_client.post(
                token_url,
                data=data,
                headers=headers
            )

            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return None

            # Parse response
            token_data = response.json()

            # Calculate expiration time (convert to integer timestamp)
            expires_at = None
            if "expires_in" in token_data:
                expires_at = int(time.time()) + int(token_data["expires_in"])

            return OAuthTokens(
                access_token=token_data.get("access_token"),
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in"),
                refresh_token=token_data.get("refresh_token"),
                scope=token_data.get("scope"),
                expires_at=expires_at
            )

        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {e}", exc_info=True)
            return None

    async def refresh_tokens(
            self,
            oauth_config: Dict[str, Any],
            refresh_token: str
    ) -> Optional[OAuthTokens]:
        """Refresh tokens using OAuth config from MongoDB"""
        try:
            token_url = oauth_config.get("token_url")
            if not token_url:
                logger.error("No token URL for refresh")
                return None

            # Build request body
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": oauth_config.get("client_id", ""),
            }

            # Add client_secret if exists
            if "client_secret" in oauth_config:
                data["client_secret"] = oauth_config["client_secret"]

            # Add scope if exists (handle both list and string formats)
            scopes = oauth_config.get("scopes")
            if scopes:
                if isinstance(scopes, list):
                    data["scope"] = " ".join(scopes)
                else:
                    data["scope"] = scopes

            # Prepare request headers
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            }

            # Handle client authentication
            auth_method = oauth_config.get("token_endpoint_auth_methods_supported",
                                           ["client_secret_basic", "client_secret_post"])
            if "client_secret_basic" in auth_method and "client_secret" in oauth_config:
                # Basic authentication
                credentials = f"{oauth_config['client_id']}:{oauth_config['client_secret']}"
                encoded_credentials = base64.b64encode(credentials.encode()).decode()
                headers["Authorization"] = f"Basic {encoded_credentials}"
                # Remove client_id and client_secret from data
                data.pop("client_id", None)
                data.pop("client_secret", None)

            logger.debug(f"Refreshing tokens at {token_url}")

            # Send request
            response = await self._http_client.post(
                token_url,
                data=data,
                headers=headers
            )

            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                return None

            # Parse response
            token_data = response.json()

            # Calculate expiration time (convert to integer timestamp)
            expires_at = None
            if "expires_in" in token_data:
                expires_at = int(time.time()) + int(token_data["expires_in"])

            return OAuthTokens(
                access_token=token_data.get("access_token"),
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in"),
                refresh_token=token_data.get("refresh_token"),
                scope=token_data.get("scope"),
                expires_at=expires_at
            )

        except Exception as e:
            logger.error(f"Failed to refresh tokens: {e}", exc_info=True)
            return None

    def _transform_tokens(
            self,
            token_data: Dict[str, Any],
            token_transform: Optional[TokenTransformConfig]
    ) -> Dict[str, Any]:
        """Transform token format"""
        if not token_transform:
            return token_data

        transformed = token_data.copy()

        # Apply field mappings
        if token_transform.field_mappings:
            for target_field, source_field in token_transform.field_mappings.items():
                if source_field in token_data:
                    transformed[target_field] = token_data[source_field]

        # Apply value transformations
        if token_transform.value_transforms:
            for field, transform_func in token_transform.value_transforms.items():
                if field in transformed:
                    # TODO: Actually execute transformation function
                    pass

        return transformed

    async def close(self):
        """Close HTTP client"""
        await self._http_client.aclose()
