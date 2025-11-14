"""Authentication provider package for MCP Gateway Registry."""

from .base import AuthProvider
from .cognito import CognitoProvider
from .entra import EntraIDProvider
from .factory import get_auth_provider
from .keycloak import KeycloakProvider

__all__ = [
    "AuthProvider",
    "CognitoProvider",
    "EntraIDProvider",
    "KeycloakProvider",
    "get_auth_provider",
]