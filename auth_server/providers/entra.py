import logging
import time
import jwt
import requests
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from .base import AuthProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


class EntraIDProvider(AuthProvider):
    """Microsoft Entra ID authentication provider implementation."""

    def __init__(
            self,
            tenant_id: str,
            client_id: str,
            client_secret: str,
            authority: Optional[str] = None
    ):
        """Initialize Entra ID provider.
        
        Args:
            tenant_id: Azure AD tenant ID (or 'common' for multi-tenant)
            client_id: Azure AD application (client) ID
            client_secret: Azure AD client secret
            authority: Optional custom authority URL (defaults to global Azure AD)
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret

        # Cache for JWKS
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_time: float = 0
        self._jwks_cache_ttl: int = 3600  # 1 hour

        # Microsoft Entra ID endpoints
        self.authority = authority or f"https://login.microsoftonline.com/{tenant_id}"
        self.token_url = f"{self.authority}/oauth2/v2.0/token"
        self.auth_url = f"{self.authority}/oauth2/v2.0/authorize"
        self.jwks_url = f"{self.authority}/discovery/v2.0/keys"
        self.logout_url = f"{self.authority}/oauth2/v2.0/logout"
        self.userinfo_url = "https://graph.microsoft.com/v1.0/me"
        self.issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"

        logger.debug(f"Initialized Entra ID provider for tenant '{tenant_id}'")

    def validate_token(
            self,
            token: str,
            **kwargs: Any
    ) -> Dict[str, Any]:
        """Validate Entra ID JWT token."""
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

            # Validate and decode token
            # Note: Entra ID tokens may have audience as the client_id or api://{client_id}
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=['RS256'],
                issuer=self.issuer,
                audience=[self.client_id, f"api://{self.client_id}"],
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_aud": True
                }
            )

            logger.debug(f"Token validation successful for user:"
                         f" {claims.get('preferred_username', claims.get('upn', 'unknown'))}")

            # Extract user info from claims
            # Entra ID tokens can have different claim structures
            username = (
                    claims.get('preferred_username') or
                    claims.get('upn') or
                    claims.get('unique_name') or
                    claims.get('email') or
                    claims.get('sub')
            )
            return {
                'valid': True,
                'username': username,
                'email': claims.get('email') or claims.get('upn') or claims.get('preferred_username'),
                'groups': claims.get('groups', []),
                'scopes': claims.get('scp', '').split() if claims.get('scp') else [],
                'client_id': claims.get('azp', claims.get('appid', self.client_id)),
                'method': 'entra_id',
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
        """Get JSON Web Key Set from Entra ID with caching."""
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
        """Exchange authorization code for access token."""
        try:
            logger.debug("Exchanging authorization code for token")

            data = {
                'grant_type': 'authorization_code',
                'code': code,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': redirect_uri,
                'scope': 'openid profile email User.Read'
            }

            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            response = requests.post(self.token_url, data=data, headers=headers, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            logger.debug("Token exchange successful")
            return token_data

        except requests.RequestException as e:
            logger.error(f"Failed to exchange code for token: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Error details: {error_detail}")
                except Exception:
                    logger.error(f"Response text: {e.response.text}")
            raise ValueError(f"Token exchange failed: {e}")

    def get_user_info(
            self,
            access_token: str
    ) -> Dict[str, Any]:
        """Get user information from Microsoft Graph API."""
        try:
            logger.debug("Fetching user info from Microsoft Graph")

            headers = {'Authorization': f'Bearer {access_token}'}
            response = requests.get(self.userinfo_url, headers=headers, timeout=10)
            response.raise_for_status()

            user_info = response.json()
            logger.debug(f"User info retrieved for: {user_info.get('userPrincipalName', 'unknown')}")

            # Transform Microsoft Graph response to standard format
            return {
                'username': user_info.get('userPrincipalName'),
                'email': user_info.get('mail') or user_info.get('userPrincipalName'),
                'name': user_info.get('displayName'),
                'given_name': user_info.get('givenName'),
                'family_name': user_info.get('surname'),
                'id': user_info.get('id'),
                'job_title': user_info.get('jobTitle'),
                'office_location': user_info.get('officeLocation')
            }

        except requests.RequestException as e:
            logger.error(f"Failed to get user info: {e}")
            raise ValueError(f"User info retrieval failed: {e}")

    def get_auth_url(
            self,
            redirect_uri: str,
            state: str,
            scope: Optional[str] = None
    ) -> str:
        """Get Entra ID authorization URL."""
        logger.debug(f"Generating auth URL with redirect_uri: {redirect_uri}")

        params = {'client_id': self.client_id,
                  'response_type': 'code',
                  'scope': scope or 'openid profile email User.Read',
                  'redirect_uri': redirect_uri,
                  'state': state,
                  'response_mode': 'query'
                  }

        auth_url = f"{self.auth_url}?{urlencode(params)}"
        logger.debug(f"Generated auth URL: {auth_url}")
        return auth_url

    def get_logout_url(
            self,
            redirect_uri: str
    ) -> str:
        """Get Entra ID logout URL."""
        logger.debug(f"Generating logout URL with redirect_uri: {redirect_uri}")

        params = {'post_logout_redirect_uri': redirect_uri}
        logout_url = f"{self.logout_url}?{urlencode(params)}"
        logger.debug(f"Generated logout URL: {logout_url}")

        return logout_url

    def refresh_token(
            self,
            refresh_token: str
    ) -> Dict[str, Any]:
        """Refresh an access token using a refresh token."""
        try:
            logger.debug("Refreshing access token")

            data = {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'scope': 'openid profile email User.Read offline_access'
            }

            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

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
        """Validate a machine-to-machine token."""
        # M2M tokens use the same validation as regular tokens in Entra ID
        return self.validate_token(token)

    def get_m2m_token(
            self,
            client_id: Optional[str] = None,
            client_secret: Optional[str] = None,
            scope: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get machine-to-machine token using client credentials.
        
        For Entra ID, the default scope for client credentials is '.default'
        which requests all permissions configured for the app registration.
        """
        try:
            logger.debug("Requesting M2M token using client credentials")
            # For Entra ID client credentials, use .default scope or specified scope
            default_scope = f"https://graph.microsoft.com/.default"

            data = {
                'grant_type': 'client_credentials',
                'client_id': client_id or self.client_id,
                'client_secret': client_secret or self.client_secret,
                'scope': scope or default_scope
            }
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            response = requests.post(self.token_url, data=data, headers=headers, timeout=10)
            response.raise_for_status()
            token_data = response.json()
            logger.debug("M2M token generation successful")
            return token_data

        except requests.RequestException as e:
            logger.error(f"Failed to get M2M token: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"Error details: {error_detail}")
                except Exception as e:
                    logger.error(f"Response text: {e.response.text}")
            raise ValueError(f"M2M token generation failed: {e}")

    def get_provider_info(self) -> Dict[str, Any]:
        """Get provider-specific information."""
        return {
            'provider_type': 'entra_id',
            'tenant_id': self.tenant_id,
            'client_id': self.client_id,
            'endpoints': {
                'auth': self.auth_url,
                'token': self.token_url,
                'userinfo': self.userinfo_url,
                'jwks': self.jwks_url,
                'logout': self.logout_url
            },
            'issuer': self.issuer
        }
