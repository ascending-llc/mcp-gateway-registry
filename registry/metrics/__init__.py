"""
Registry Metrics Integration Package

Provides metrics collection for registry operations, MCP client calls,
and request header analysis for dynamic nginx configuration.
"""

from .client import (
    MetricsClient, 
    create_metrics_client,
    MetricsCollector,
    EnhancedMCPClientService,
    get_metrics_collector,
    get_enhanced_mcp_client,
    MetricsCollectorDep,
    EnhancedMCPClientDep
)
from .middleware import RegistryMetricsMiddleware, add_registry_metrics_middleware
from .utils import extract_server_name_from_url, hash_user_id

__all__ = [
    "MetricsClient",
    "create_metrics_client",
    "MetricsCollector",
    "EnhancedMCPClientService", 
    "get_metrics_collector",
    "get_enhanced_mcp_client",
    "MetricsCollectorDep",
    "EnhancedMCPClientDep",
    "RegistryMetricsMiddleware", 
    "add_registry_metrics_middleware",
    "extract_server_name_from_url",
    "hash_user_id"
]