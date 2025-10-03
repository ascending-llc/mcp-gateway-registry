"""
Constants and enums for the MCP Gateway Registry.
"""

from enum import Enum
from typing import List
from pydantic import BaseModel


class HealthStatus(str, Enum):
    """Health status constants for services."""
    
    HEALTHY = "healthy"
    HEALTHY_AUTH_EXPIRED = "healthy-auth-expired"
    UNHEALTHY_TIMEOUT = "unhealthy: timeout"
    UNHEALTHY_CONNECTION_ERROR = "unhealthy: connection error" 
    UNHEALTHY_ENDPOINT_CHECK_FAILED = "unhealthy: endpoint check failed"
    UNHEALTHY_MISSING_PROXY_URL = "unhealthy: missing proxy URL"
    CHECKING = "checking"
    UNKNOWN = "unknown"

    @classmethod
    def get_healthy_statuses(cls) -> List[str]:
        """Get list of statuses that should be considered healthy for nginx inclusion."""
        return [cls.HEALTHY, cls.HEALTHY_AUTH_EXPIRED]
    
    @classmethod
    def is_healthy(cls, status: str) -> bool:
        """Check if a status should be considered healthy."""
        return status in cls.get_healthy_statuses()


class TransportType(str, Enum):
    """Supported transport types for MCP servers."""
    
    STREAMABLE_HTTP = "streamable-http"
    SSE = "sse"


class RegistryConstants(BaseModel):
    """Registry configuration constants."""

    class Config:
        """Pydantic config."""
        frozen = True

    # Health check settings
    DEFAULT_HEALTH_CHECK_TIMEOUT: int = 30
    HEALTH_CHECK_INTERVAL: int = 30

    # SSL certificate paths
    SSL_CERT_PATH: str = "/etc/ssl/certs/fullchain.pem"
    SSL_KEY_PATH: str = "/etc/ssl/private/privkey.pem"

    # Nginx settings
    NGINX_CONFIG_PATH: str = "/etc/nginx/conf.d/nginx_rev_proxy.conf"
    NGINX_TEMPLATE_HTTP_ONLY: str = "/app/docker/nginx_rev_proxy_http_only.conf"
    NGINX_TEMPLATE_HTTP_AND_HTTPS: str = "/app/docker/nginx_rev_proxy_http_and_https.conf"
    NGINX_TEMPLATE_HTTP_ONLY_LOCAL: str = "docker/nginx_rev_proxy_http_only.conf"
    NGINX_TEMPLATE_HTTP_AND_HTTPS_LOCAL: str = "docker/nginx_rev_proxy_http_and_https.conf"

    # Server settings
    DEFAULT_TRANSPORT: str = TransportType.STREAMABLE_HTTP
    SUPPORTED_TRANSPORTS: List[str] = [TransportType.STREAMABLE_HTTP, TransportType.SSE]


# Global instance
REGISTRY_CONSTANTS = RegistryConstants()