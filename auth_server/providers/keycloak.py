"""Keycloak authentication provider implementation."""

import json
import logging
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import jwt
import requests

from .base import AuthProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


class KeycloakProvider(AuthProvider):
    """Keycloak authentication provider implementation."""
    
    def __init__(
        self,
        keycloak_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        keycloak_external_url: Optional[str] = None,
        m2m_client_id: Optional[str] = None,
        m2m_client_secret: Optional[str] = None
    ):
        """Initialize Keycloak provider.

        Args:
            keycloak_url: Base URL of the Keycloak instance for server-to-server communication
            realm: Keycloak realm name
            client_id: OAuth2 client ID for web authentication
            client_secret: OAuth2 client secret for web authentication
            keycloak_external_url: External URL for browser redirects (defaults to keycloak_url)
            m2m_client_id: Optional M2M client ID (defaults to client_id)
            m2m_client_secret: Optional M2M client secret (defaults to client_secret)
        """
        self.keycloak_url = keycloak_url.rstrip('/')
        self.keycloak_external_url = (keycloak_external_url or keycloak_url).rstrip('/')
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.m2m_client_id = m2m_client_id or client_id
        self.m2m_client_secret = m2m_client_secret or client_secret

        # Cache for JWKS and configuration
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_time: float = 0
        self._jwks_cache_ttl: int = 3600  # 1 hour

        # Keycloak endpoints - use internal URL for server-to-server, external for browser redirects
        self.realm_url = f"{self.keycloak_url}/realms/{realm}"
        self.external_realm_url = f"{self.keycloak_external_url}/realms/{realm}"
        self.token_url = f"{self.realm_url}/protocol/openid-connect/token"
        self.auth_url = f"{self.external_realm_url}/protocol/openid-connect/auth"
        self.userinfo_url = f"{self.realm_url}/protocol/openid-connect/userinfo"
        self.jwks_url = f"{self.realm_url}/protocol/openid-connect/certs"
        self.logout_url = f"{self.external_realm_url}/protocol/openid-connect/logout"
        self.config_url = f"{self.realm_url}/.well-known/openid_configuration"

        logger.debug(f"Initialized Keycloak provider for realm '{realm}' at {keycloak_url} (external: {self.keycloak_external_url})")


    def validate_token(
        self,
        token: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Validate Keycloak JWT token."""
        try:
            logger.debug("Validating Keycloak JWT token")
            
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
            
            # Validate and decode token - accept multiple valid issuers
            valid_issuers = [
                self.external_realm_url,  # External URL: https://mcpgateway.ddns.net/realms/mcp-gateway
                self.realm_url,           # Internal URL: http://keycloak:8080/realms/mcp-gateway
                f"http://localhost:8080/realms/{self.realm}"  # Localhost URL for development
            ]

            claims = None
            last_error = None
            for issuer in valid_issuers:
                try:
                    claims = jwt.decode(
                        token,
                        signing_key,
                        algorithms=['RS256'],
                        issuer=issuer,
                        audience=['account', self.client_id, self.m2m_client_id],
                        options={
                            "verify_exp": True,
                            "verify_iat": True,
                            "verify_aud": True
                        }
                    )
                    logger.debug(f"Token validation successful with issuer: {issuer}")
                    break
                except jwt.InvalidIssuerError as e:
                    last_error = e
                    continue

            if claims is None:
                raise last_error or ValueError("Token validation failed with all valid issuers")
            
            logger.debug(f"Token validation successful for user: {claims.get('preferred_username', 'unknown')}")
            
            # Extract user info from claims
            return {
                'valid': True,
                'username': claims.get('preferred_username', claims.get('sub')),
                'email': claims.get('email'),
                'groups': claims.get('groups', []),
                'scopes': claims.get('scope', '').split() if claims.get('scope') else [],
                'client_id': claims.get('azp', claims.get('aud', self.client_id)),
                'method': 'keycloak',
                'data': claims
            }
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token validation failed: Token has expired")
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token validation failed: Invalid token - {e}")
            raise ValueError(f"Invalid token: {e}")
        except Exception as e:
            logger.error(f"Keycloak token validation error: {e}")
            raise ValueError(f"Token validation failed: {e}")


    def get_jwks(self) -> Dict[str, Any]:
        """Get JSON Web Key Set from Keycloak with caching."""
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
            logger.error(f"Failed to retrieve JWKS from Keycloak: {e}")
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
                'redirect_uri': redirect_uri
            }
            
            response = requests.post(self.token_url, data=data, timeout=10)
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
        """Get user information from Keycloak."""
        try:
            logger.debug("Fetching user info from Keycloak")
            
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
        """Get Keycloak authorization URL."""
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
        """Get Keycloak logout URL."""
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
        """Refresh an access token using a refresh token."""
        try:
            logger.debug("Refreshing access token")
            
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
            
            response = requests.post(self.token_url, data=data, timeout=10)
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
        # M2M tokens use the same validation as regular tokens
        return self.validate_token(token)


    def get_m2m_token(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        scope: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get machine-to-machine token using client credentials."""
        try:
            logger.debug("Requesting M2M token using client credentials")
            
            data = {
                'grant_type': 'client_credentials',
                'client_id': client_id or self.m2m_client_id,
                'client_secret': client_secret or self.m2m_client_secret,
                'scope': scope or 'openid'
            }
            
            response = requests.post(self.token_url, data=data, timeout=10)
            response.raise_for_status()
            
            token_data = response.json()
            logger.debug("M2M token generation successful")
            
            return token_data
            
        except requests.RequestException as e:
            logger.error(f"Failed to get M2M token: {e}")
            raise ValueError(f"M2M token generation failed: {e}")


    @lru_cache(maxsize=1)
    def _get_openid_configuration(self) -> Dict[str, Any]:
        """Get OpenID Connect configuration from Keycloak."""
        try:
            logger.debug(f"Fetching OpenID configuration from {self.config_url}")
            response = requests.get(self.config_url, timeout=10)
            response.raise_for_status()
            
            config = response.json()
            logger.debug("OpenID configuration retrieved successfully")
            
            return config
            
        except requests.RequestException as e:
            logger.error(f"Failed to get OpenID configuration: {e}")
            raise ValueError(f"OpenID configuration retrieval failed: {e}")


    def _check_keycloak_health(self) -> bool:
        """Check if Keycloak is healthy and accessible."""
        try:
            health_url = f"{self.keycloak_url}/health/ready"
            response = requests.get(health_url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False


    def get_provider_info(self) -> Dict[str, Any]:
        """Get provider-specific information."""
        return {
            'provider_type': 'keycloak',
            'keycloak_url': self.keycloak_url,
            'realm': self.realm,
            'client_id': self.client_id,
            'endpoints': {
                'auth': self.auth_url,
                'token': self.token_url,
                'userinfo': self.userinfo_url,
                'jwks': self.jwks_url,
                'logout': self.logout_url,
                'config': self.config_url
            },
            'healthy': self._check_keycloak_health()
        }