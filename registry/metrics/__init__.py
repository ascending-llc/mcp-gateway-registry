"""
Registry Metrics Integration Package

Provides metrics collection for registry operations, MCP client calls,
and request header analysis for dynamic nginx configuration.
"""

from .client import (
    EnhancedMCPClientDep,
    EnhancedMCPClientService,
    MetricsClient,
    MetricsCollector,
    MetricsCollectorDep,
    create_metrics_client,
    get_enhanced_mcp_client,
    get_metrics_collector,
)
from .middleware import RegistryMetricsMiddleware, add_registry_metrics_middleware
from .utils import extract_server_name_from_url, hash_user_id

__all__ = [
    "EnhancedMCPClientDep",
    "EnhancedMCPClientService",
    "MetricsClient",
    "MetricsCollector",
    "MetricsCollectorDep",
    "RegistryMetricsMiddleware",
    "add_registry_metrics_middleware",
    "create_metrics_client",
    "extract_server_name_from_url",
    "get_enhanced_mcp_client",
    "get_metrics_collector",
    "hash_user_id",
]
