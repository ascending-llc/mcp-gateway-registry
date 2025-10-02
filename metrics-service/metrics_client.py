"""
Metrics client library for sending metrics to the MCP Metrics Collection Service.

This module provides an HTTP client that other services can use to emit metrics
to the centralized metrics collection service.
"""

import httpx
import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
import json

logger = logging.getLogger(__name__)


class MetricsClient:
    """HTTP client for sending metrics to collection service."""
    
    def __init__(
        self, 
        metrics_url: str = None,
        api_key: str = None,
        service_name: str = "unknown",
        service_version: str = "1.0.0",
        instance_id: str = None,
        timeout: float = 5.0,
        max_retries: int = 3,
        enabled: bool = True
    ):
        self.metrics_url = metrics_url or os.getenv("METRICS_SERVICE_URL", "http://localhost:8890")
        self.metrics_endpoint = f"{self.metrics_url}/metrics"
        self.api_key = api_key or os.getenv("METRICS_API_KEY", "")
        self.service_name = service_name
        self.service_version = service_version
        self.instance_id = instance_id or f"{service_name}-{os.getpid()}"
        self.timeout = timeout
        self.max_retries = max_retries
        self.enabled = enabled and bool(self.api_key)
        self._client = None
        
        if not self.enabled:
            logger.warning(f"Metrics client disabled for {service_name} - no API key provided")
    
    async def _get_client(self):
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def _emit_metric(
        self,
        metric_type: str,
        value: float = 1.0,
        duration_ms: Optional[float] = None,
        dimensions: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """Internal method to emit a single metric."""
        if not self.enabled:
            return False
            
        try:
            client = await self._get_client()
            
            payload = {
                "service": self.service_name,
                "version": self.service_version,
                "instance_id": self.instance_id,
                "metrics": [{
                    "type": metric_type,
                    "timestamp": (timestamp or datetime.utcnow()).isoformat(),
                    "value": value,
                    "duration_ms": duration_ms,
                    "dimensions": dimensions or {},
                    "metadata": metadata or {}
                }]
            }
            
            headers = {"X-API-Key": self.api_key}
            
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post(
                        self.metrics_endpoint,
                        json=payload,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        logger.debug(f"Metric {metric_type} sent successfully")
                        return True
                    else:
                        logger.warning(f"Metrics API error: {response.status_code} - {response.text}")
                        return False
                        
                except (httpx.ConnectError, httpx.TimeoutException) as e:
                    if attempt < self.max_retries:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(f"Metrics API connection failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"Failed to emit metric after {self.max_retries + 1} attempts: {e}")
                        return False
            
        except Exception as e:
            # Never fail the main operation due to metrics
            logger.error(f"Failed to emit metric {metric_type}: {e}")
            return False
    
    def emit_metric_sync(self, *args, **kwargs):
        """Synchronous wrapper that creates a task for async emission."""
        if not self.enabled:
            return
        asyncio.create_task(self._emit_metric(*args, **kwargs))
    
    # Auth Server Metrics
    async def emit_auth_metric(
        self,
        success: bool,
        method: str,
        duration_ms: float,
        server_name: Optional[str] = None,
        user_hash: Optional[str] = None,
        error_code: Optional[str] = None
    ) -> bool:
        """Emit authentication metric."""
        return await self._emit_metric(
            metric_type="auth_request",
            value=1.0,
            duration_ms=duration_ms,
            dimensions={
                "success": success,
                "method": method,
                "server": server_name or "unknown",
                "user_hash": user_hash or ""
            },
            metadata={
                "error_code": error_code
            }
        )
    
    def emit_auth_metric_sync(self, *args, **kwargs):
        """Synchronous wrapper for auth metrics."""
        asyncio.create_task(self.emit_auth_metric(*args, **kwargs))
    
    # Registry Service Metrics
    async def emit_registry_metric(
        self,
        operation: str,  # create, read, update, delete, list, search
        resource_type: str,  # server, config, etc.
        success: bool,
        duration_ms: float,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        error_code: Optional[str] = None
    ) -> bool:
        """Emit registry operation metric."""
        return await self._emit_metric(
            metric_type="registry_operation",
            value=1.0,
            duration_ms=duration_ms,
            dimensions={
                "operation": operation,
                "resource_type": resource_type,
                "success": success,
                "resource_id": resource_id or "",
                "user_id": user_id or ""
            },
            metadata={
                "error_code": error_code
            }
        )
    
    def emit_registry_metric_sync(self, *args, **kwargs):
        """Synchronous wrapper for registry metrics."""
        asyncio.create_task(self.emit_registry_metric(*args, **kwargs))
    
    # Tool Discovery Metrics
    async def emit_discovery_metric(
        self,
        query: str,
        results_count: int,
        duration_ms: float,
        top_k_services: Optional[int] = None,
        top_n_tools: Optional[int] = None,
        embedding_time_ms: Optional[float] = None,
        faiss_search_time_ms: Optional[float] = None
    ) -> bool:
        """Emit tool discovery metric."""
        return await self._emit_metric(
            metric_type="tool_discovery",
            value=1.0,
            duration_ms=duration_ms,
            dimensions={
                "query": query[:100],  # Truncate long queries
                "results_count": results_count,
                "top_k_services": top_k_services,
                "top_n_tools": top_n_tools
            },
            metadata={
                "embedding_time_ms": embedding_time_ms,
                "faiss_search_time_ms": faiss_search_time_ms
            }
        )
    
    def emit_discovery_metric_sync(self, *args, **kwargs):
        """Synchronous wrapper for discovery metrics."""
        asyncio.create_task(self.emit_discovery_metric(*args, **kwargs))
    
    # Tool Execution Metrics
    async def emit_tool_execution_metric(
        self,
        tool_name: str,
        server_path: str,
        server_name: str,
        success: bool,
        duration_ms: float,
        input_size_bytes: Optional[int] = None,
        output_size_bytes: Optional[int] = None,
        error_code: Optional[str] = None
    ) -> bool:
        """Emit tool execution metric."""
        return await self._emit_metric(
            metric_type="tool_execution",
            value=1.0,
            duration_ms=duration_ms,
            dimensions={
                "tool_name": tool_name,
                "server_path": server_path,
                "server_name": server_name,
                "success": success
            },
            metadata={
                "error_code": error_code,
                "input_size_bytes": input_size_bytes,
                "output_size_bytes": output_size_bytes
            }
        )
    
    def emit_tool_execution_metric_sync(self, *args, **kwargs):
        """Synchronous wrapper for tool execution metrics."""
        asyncio.create_task(self.emit_tool_execution_metric(*args, **kwargs))
    
    # Health Check Metrics
    async def emit_health_metric(
        self,
        endpoint: str,
        status_code: int,
        duration_ms: float,
        healthy: bool = True
    ) -> bool:
        """Emit health check metric."""
        return await self._emit_metric(
            metric_type="health_check",
            value=1.0,
            duration_ms=duration_ms,
            dimensions={
                "endpoint": endpoint,
                "status_code": status_code,
                "healthy": healthy
            }
        )
    
    def emit_health_metric_sync(self, *args, **kwargs):
        """Synchronous wrapper for health metrics."""
        asyncio.create_task(self.emit_health_metric(*args, **kwargs))
    
    # Custom Metrics
    async def emit_custom_metric(
        self,
        metric_name: str,
        value: float,
        duration_ms: Optional[float] = None,
        dimensions: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Emit custom metric with arbitrary data."""
        custom_dimensions = {"metric_name": metric_name}
        if dimensions:
            custom_dimensions.update(dimensions)
            
        return await self._emit_metric(
            metric_type="custom",
            value=value,
            duration_ms=duration_ms,
            dimensions=custom_dimensions,
            metadata=metadata
        )
    
    def emit_custom_metric_sync(self, *args, **kwargs):
        """Synchronous wrapper for custom metrics."""
        asyncio.create_task(self.emit_custom_metric(*args, **kwargs))
    
    # Batch Metrics
    async def emit_metrics_batch(self, metrics: List[Dict[str, Any]]) -> bool:
        """Emit multiple metrics in a single request."""
        if not self.enabled or not metrics:
            return False
            
        try:
            client = await self._get_client()
            
            # Format metrics for API
            formatted_metrics = []
            for metric in metrics:
                formatted_metric = {
                    "type": metric.get("type", "custom"),
                    "timestamp": (metric.get("timestamp") or datetime.utcnow()).isoformat(),
                    "value": metric.get("value", 1.0),
                    "duration_ms": metric.get("duration_ms"),
                    "dimensions": metric.get("dimensions", {}),
                    "metadata": metric.get("metadata", {})
                }
                formatted_metrics.append(formatted_metric)
            
            payload = {
                "service": self.service_name,
                "version": self.service_version,
                "instance_id": self.instance_id,
                "metrics": formatted_metrics
            }
            
            headers = {"X-API-Key": self.api_key}
            
            response = await client.post(
                self.metrics_endpoint,
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                logger.debug(f"Batch of {len(metrics)} metrics sent successfully")
                return True
            else:
                logger.warning(f"Metrics API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to emit metrics batch: {e}")
            return False
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global client instances for each service (to be configured per service)
def create_metrics_client(
    service_name: str,
    service_version: str = "1.0.0", 
    **kwargs
) -> MetricsClient:
    """Factory function to create a configured metrics client."""
    return MetricsClient(
        service_name=service_name,
        service_version=service_version,
        **kwargs
    )


# Convenience functions for services that prefer functional interface
async def emit_auth_metric(success: bool, method: str, duration_ms: float, **kwargs):
    """Convenience function for auth metrics."""
    client = create_metrics_client("auth-server")
    try:
        return await client.emit_auth_metric(success, method, duration_ms, **kwargs)
    finally:
        await client.close()


async def emit_registry_metric(operation: str, resource_type: str, success: bool, duration_ms: float, **kwargs):
    """Convenience function for registry metrics."""
    client = create_metrics_client("registry")
    try:
        return await client.emit_registry_metric(operation, resource_type, success, duration_ms, **kwargs)
    finally:
        await client.close()


async def emit_discovery_metric(query: str, results_count: int, duration_ms: float, **kwargs):
    """Convenience function for discovery metrics."""
    client = create_metrics_client("registry")
    try:
        return await client.emit_discovery_metric(query, results_count, duration_ms, **kwargs)
    finally:
        await client.close()


async def emit_tool_execution_metric(tool_name: str, server_path: str, server_name: str, success: bool, duration_ms: float, **kwargs):
    """Convenience function for tool execution metrics."""
    client = create_metrics_client("mcp-server")
    try:
        return await client.emit_tool_execution_metric(tool_name, server_path, server_name, success, duration_ms, **kwargs)
    finally:
        await client.close()