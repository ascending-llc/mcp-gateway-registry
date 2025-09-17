"""Authentication provider package for MCP Gateway Registry."""

from .base import AuthProvider
from .factory import get_auth_provider

__all__ = ["AuthProvider", "get_auth_provider"]