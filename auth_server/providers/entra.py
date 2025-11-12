"""Microsoft Entra ID (Azure AD) authentication provider implementation."""

import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import jwt
import requests

from .base import AuthProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


class EntraIdProvider(AuthProvider):
    """Microsoft Entra ID (Azure AD) authentication provider.

    This provider implements OAuth2/OIDC authentication using Microsoft Entra ID
    (formerly Azure Active Directory). It supports:
    - User authentication via OAuth2 authorization code flow
    - Machine-to-machine authentication via client credentials flow
    - JWT token validation using Azure AD JWKS
    - Group-based authorization with Azure AD security groups
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str
    ):
        """Initialize Entra ID provider.

        Args:
            tenant_id: Azure AD tenant ID (GUID)
            client_id: App registration client ID (GUID)
            client_secret: App registration client secret
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret

        # JWKS cache
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_time: float = 0
        self._jwks_cache_ttl: int = 3600  # 1 hour

        # Entra ID endpoints
        base_url = f"https://login.microsoftonline.com/{tenant_id}"
        self.auth_url = f"{base_url}/oauth2/v2.0/authorize"
        self.token_url = f"{base_url}/oauth2/v2.0/token"
        self.userinfo_url = "https://graph.microsoft.com/oidc/userinfo"
        self.jwks_url = f"{base_url}/discovery/v2.0/keys"
        self.logout_url = f"{base_url}/oauth2/v2.0/logout"

        # Entra ID supports two issuer formats:
        # v2.0 endpoint: https://login.microsoftonline.com/{tenant}/v2.0
        # v1.0/M2M endpoint: https://sts.windows.net/{tenant}/
        self.issuer_v2 = f"{base_url}/v2.0"
        self.issuer_v1 = f"https://sts.windows.net/{tenant_id}/"
        self.valid_issuers = [self.issuer_v2, self.issuer_v1]

        logger.debug(f"Initialized Entra ID provider for tenant '{tenant_id}'")

    def validate_token(
        self,
        token: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Validate Entra ID JWT token.

        Args:
            token: The JWT access token to validate
            **kwargs: Additional provider-specific arguments

        Returns:
            Dictionary containing:
                - valid: True if token is valid
                - username: User's preferred_username or sub claim
                - email: User's email address
                - groups: List of Azure AD group Object IDs
                - scopes: List of token scopes
                - client_id: Client ID that issued the token
                - method: 'entra'
                - data: Raw token claims

        Raises:
            ValueError: If token validation fails
        """
        try:
            logger.debug("Validating Entra ID JWT token")

            # Get JWKS for validation
            jwks = self.get_jwks()

            # Decode token header to get key ID
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get('kid')

            if not kid:
                raise ValueError("Token missing 'kid' in header")

            # Find matching key
            signing_key = None
            for key in jwks.get('keys', []):
                if key.get('kid') == kid:
                    from jwt import PyJWK
                    signing_key = PyJWK(key).key
                    break

            if not signing_key:
                raise ValueError(f"No matching key found for kid: {kid}")

            # First, decode without validation to check issuer
            unverified_claims = jwt.decode(token, options={"verify_signature": False})
            token_issuer = unverified_claims.get('iss')

            # Check if issuer is valid (v1.0 or v2.0)
            if token_issuer not in self.valid_issuers:
                raise ValueError(f"Invalid issuer: {token_issuer}. Expected one of: {self.valid_issuers}")

            # Validate and decode token with the correct issuer
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=['RS256'],
                issuer=token_issuer,
                audience=[self.client_id, f'api://{self.client_id}'],  # Accept both formats
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_aud": True
                }
            )

            logger.debug(f"Token validation successful for user: {claims.get('preferred_username', 'unknown')}")

            # Extract user info from claims
            # For M2M tokens, group memberships are in 'roles' claim instead of 'groups'
            # For user tokens, they're in 'groups' claim
            groups = claims.get('groups', [])
            if not groups and 'roles' in claims:
                # M2M token - use roles claim as groups
                groups = claims.get('roles', [])
                logger.debug(f"M2M token detected, using roles claim as groups: {groups}")

            return {
                'valid': True,
                'username': claims.get('preferred_username', claims.get('sub')),
                'email': claims.get('email'),
                'groups': groups,
                'scopes': claims.get('scope', '').split() if claims.get('scope') else [],
                'client_id': claims.get('azp', self.client_id),
                'method': 'entra',
                'data': claims
            }

        except jwt.ExpiredSignatureError:
            logger.warning("Token validation failed: Token has expired")
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token validation failed: Invalid token - {e}")
            raise ValueError(f"Invalid token: {e}")
        except Exception as e:
            logger.error(f"Entra ID token validation error: {e}")
            raise ValueError(f"Token validation failed: {e}")

    def get_jwks(self) -> Dict[str, Any]:
        """Get JSON Web Key Set from Entra ID with caching.

        Returns:
            Dictionary containing the JWKS data

        Raises:
            ValueError: If JWKS cannot be retrieved
        """
        current_time = time.time()

        # Check if cache is still valid
        if (self._jwks_cache and
            (current_time - self._jwks_cache_time) < self._jwks_cache_ttl):
            logger.debug("Using cached JWKS")
            return self._jwks_cache

        try:
            logger.debug(f"Fetching JWKS from {self.jwks_url}")
            response = requests.get(self.jwks_url, timeout=10)
            response.raise_for_status()

            self._jwks_cache = response.json()
            self._jwks_cache_time = current_time

            logger.debug("JWKS fetched and cached successfully")
            return self._jwks_cache

        except Exception as e:
            logger.error(f"Failed to retrieve JWKS from Entra ID: {e}")
            raise ValueError(f"Cannot retrieve JWKS: {e}")

    def exchange_code_for_token(
        self,
        code: str,
        redirect_uri: str
    ) -> Dict[str, Any]:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth2 flow
            redirect_uri: Redirect URI used in the authorization request

        Returns:
            Dictionary containing token response:
                - access_token: The access token
                - id_token: The ID token
                - refresh_token: The refresh token (if available)
                - token_type: "Bearer"
                - expires_in: Token expiration time in seconds

        Raises:
            ValueError: If code exchange fails
        """
        try:
            logger.debug("Exchanging authorization code for token")

            data = {
                'grant_type': 'authorization_code',
                'code': code,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': redirect_uri
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(self.token_url, data=data, headers=headers, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            logger.debug("Token exchange successful")

            return token_data

        except requests.RequestException as e:
            logger.error(f"Failed to exchange code for token: {e}")
            raise ValueError(f"Token exchange failed: {e}")

    def get_user_info(
        self,
        access_token: str
    ) -> Dict[str, Any]:
        """Get user information from Entra ID.

        Args:
            access_token: Valid access token

        Returns:
            Dictionary containing user information:
                - username: User's preferred_username
                - email: User's email
                - groups: User's group memberships (Object IDs)

        Raises:
            ValueError: If user info cannot be retrieved
        """
        try:
            logger.debug("Fetching user info from Entra ID")

            headers = {'Authorization': f'Bearer {access_token}'}
            response = requests.get(self.userinfo_url, headers=headers, timeout=10)
            response.raise_for_status()

            user_info = response.json()
            logger.debug(f"User info retrieved for: {user_info.get('preferred_username', 'unknown')}")

            return user_info

        except requests.RequestException as e:
            logger.error(f"Failed to get user info: {e}")
            raise ValueError(f"User info retrieval failed: {e}")

    def get_auth_url(
        self,
        redirect_uri: str,
        state: str,
        scope: Optional[str] = None
    ) -> str:
        """Get Entra ID authorization URL.

        Args:
            redirect_uri: URI to redirect to after authorization
            state: State parameter for CSRF protection
            scope: Optional scope parameter (defaults to openid email profile)

        Returns:
            Full authorization URL
        """
        logger.debug(f"Generating auth URL with redirect_uri: {redirect_uri}")

        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'scope': scope or 'openid email profile',
            'redirect_uri': redirect_uri,
            'state': state
        }

        auth_url = f"{self.auth_url}?{urlencode(params)}"
        logger.debug(f"Generated auth URL: {auth_url}")

        return auth_url

    def get_logout_url(
        self,
        redirect_uri: str
    ) -> str:
        """Get Entra ID logout URL.

        Args:
            redirect_uri: URI to redirect to after logout

        Returns:
            Full logout URL
        """
        logger.debug(f"Generating logout URL with redirect_uri: {redirect_uri}")

        params = {
            'client_id': self.client_id,
            'post_logout_redirect_uri': redirect_uri
        }

        logout_url = f"{self.logout_url}?{urlencode(params)}"
        logger.debug(f"Generated logout URL: {logout_url}")

        return logout_url

    def refresh_token(
        self,
        refresh_token: str
    ) -> Dict[str, Any]:
        """Refresh an access token using a refresh token.

        Args:
            refresh_token: The refresh token

        Returns:
            Dictionary containing new token response

        Raises:
            ValueError: If token refresh fails
        """
        try:
            logger.debug("Refreshing access token")

            data = {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(self.token_url, data=data, headers=headers, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            logger.debug("Token refresh successful")

            return token_data

        except requests.RequestException as e:
            logger.error(f"Failed to refresh token: {e}")
            raise ValueError(f"Token refresh failed: {e}")

    def validate_m2m_token(
        self,
        token: str
    ) -> Dict[str, Any]:
        """Validate a machine-to-machine token.

        Args:
            token: The M2M access token to validate

        Returns:
            Dictionary containing validation result

        Raises:
            ValueError: If token validation fails
        """
        return self.validate_token(token)

    def get_m2m_token(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        scope: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get machine-to-machine token using client credentials.

        This method is used for AI agent authentication using Azure AD service principals.
        Each AI agent should have its own service principal (app registration) in Azure AD.

        Args:
            client_id: Optional client ID (uses default if not provided)
            client_secret: Optional client secret (uses default if not provided)
            scope: Optional scope for the token (defaults to .default)

        Returns:
            Dictionary containing token response:
                - access_token: The M2M access token
                - token_type: "Bearer"
                - expires_in: Token expiration time in seconds

        Raises:
            ValueError: If token generation fails
        """
        try:
            logger.debug("Requesting M2M token using client credentials")

            # Default scope for Entra ID M2M tokens
            if not scope:
                scope = f'api://{client_id or self.client_id}/.default'

            data = {
                'grant_type': 'client_credentials',
                'client_id': client_id or self.client_id,
                'client_secret': client_secret or self.client_secret,
                'scope': scope
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(self.token_url, data=data, headers=headers, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            logger.debug("M2M token generation successful")

            return token_data

        except requests.RequestException as e:
            logger.error(f"Failed to get M2M token: {e}")
            raise ValueError(f"M2M token generation failed: {e}")

    def get_provider_info(self) -> Dict[str, Any]:
        """Get provider-specific information.

        Returns:
            Dictionary containing provider configuration and endpoints
        """
        return {
            'provider_type': 'entra',
            'tenant_id': self.tenant_id,
            'client_id': self.client_id,
            'endpoints': {
                'auth': self.auth_url,
                'token': self.token_url,
                'userinfo': self.userinfo_url,
                'jwks': self.jwks_url,
                'logout': self.logout_url
            },
            'issuers': {
                'v2': self.issuer_v2,
                'v1': self.issuer_v1
            }
        }
