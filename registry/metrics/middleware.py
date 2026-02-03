"""
FastAPI middleware for registry metrics collection.

Tracks registry operations, request headers, and API usage patterns.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .client import create_metrics_client
from .utils import extract_headers_for_analysis, hash_user_id

logger = logging.getLogger(__name__)


class RegistryMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect registry operation and request metrics.

    Tracks:
    - Registry operations (server CRUD, search, health)
    - Request headers for nginx config analysis
    - API usage patterns
    """

    def __init__(self, app, service_name: str = "registry"):
        super().__init__(app)
        self.metrics_client = create_metrics_client(service_name=service_name)

    def extract_operation_info(self, request: Request) -> dict[str, Any]:
        """Extract operation type and resource information from the request."""
        path = request.url.path
        method = request.method

        # Skip non-API endpoints
        if not path.startswith("/api/"):
            return None

        # Determine operation and resource type
        operation = "unknown"
        resource_type = "unknown"
        resource_id = ""

        # Map HTTP methods to operations
        method_mapping = {
            "GET": "read",
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete",
        }

        operation = method_mapping.get(method, "unknown")

        # Parse path to determine resource type and ID
        path_parts = [p for p in path.split("/") if p]  # Remove empty parts

        if len(path_parts) >= 2 and path_parts[0] == "api":
            if path_parts[1] == "servers":
                resource_type = "server"
                if len(path_parts) >= 3:
                    resource_id = path_parts[2]
                # Special case for GET /api/servers - this is a list operation
                if method == "GET" and len(path_parts) == 2:
                    operation = "list"
            elif path_parts[1] == "search":
                resource_type = "search"
                operation = "search"
            elif path_parts[1] == "health":
                resource_type = "health"
                operation = "check"
            elif path_parts[1] == "auth":
                resource_type = "auth"
                if len(path_parts) >= 3:
                    if path_parts[2] == "login":
                        operation = "login"
                    elif path_parts[2] == "logout":
                        operation = "logout"
                    elif path_parts[2] == "me":
                        operation = "profile"

        return {
            "operation": operation,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "path": path,
        }

    def extract_user_info(self, request: Request) -> str:
        """Extract user information from request headers or auth context."""
        # Try to get user from various headers
        user_id = request.headers.get("X-User", "")
        if not user_id:
            user_id = request.headers.get("X-Username", "")

        return hash_user_id(user_id)

    def should_track_request(self, request: Request) -> bool:
        """Determine if the request should be tracked for metrics."""
        path = request.url.path

        # Skip static files and non-API endpoints
        if (
            path.startswith("/static/")
            or path.startswith("/favicon.ico")
            or path == "/"
            or path == "/docs"
            or path == "/openapi.json"
        ):
            return False

        return True

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and collect metrics."""
        # Skip tracking for certain endpoints
        if not self.should_track_request(request):
            return await call_next(request)

        # Start timing
        start_time = time.perf_counter()

        # Extract operation information
        operation_info = self.extract_operation_info(request)
        if not operation_info:
            return await call_next(request)

        # Extract user and header information
        user_hash = self.extract_user_info(request)
        headers_info = extract_headers_for_analysis(dict(request.headers))

        # Process the request
        response = None
        success = False
        error_code = None

        try:
            response = await call_next(request)

            # Determine success based on response status
            success = 200 <= response.status_code < 400

            if not success:
                error_code = str(response.status_code)

        except Exception as e:
            # Handle exceptions during request processing
            success = False
            error_code = type(e).__name__
            logger.error(f"Error in registry request: {e}")
            # Re-raise the exception to maintain normal error handling
            raise

        finally:
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Emit registry operation metric asynchronously
            asyncio.create_task(
                self._emit_registry_metric(
                    operation=operation_info["operation"],
                    resource_type=operation_info["resource_type"],
                    success=success,
                    duration_ms=duration_ms,
                    resource_id=operation_info["resource_id"],
                    user_id=user_hash,
                    error_code=error_code,
                )
            )

            # Emit headers analysis metric for nginx config insights
            if success and operation_info["resource_type"] != "health":
                asyncio.create_task(
                    self._emit_headers_metric(
                        path=operation_info["path"],
                        method=request.method,
                        headers_info=headers_info,
                        status_code=response.status_code if response else 500,
                    )
                )

            # If this is a search operation, emit discovery metric too
            if operation_info["resource_type"] == "search" and success:
                asyncio.create_task(
                    self._emit_discovery_metric_from_request(
                        request=request, duration_ms=duration_ms
                    )
                )

        return response

    async def _emit_registry_metric(
        self,
        operation: str,
        resource_type: str,
        success: bool,
        duration_ms: float,
        resource_id: str = "",
        user_id: str = "",
        error_code: str = None,
    ):
        """Emit registry operation metric asynchronously."""
        try:
            await self.metrics_client.emit_registry_metric(
                operation=operation,
                resource_type=resource_type,
                success=success,
                duration_ms=duration_ms,
                resource_id=resource_id,
                user_id=user_id,
                error_code=error_code,
            )
        except Exception as e:
            logger.debug(f"Failed to emit registry metric: {e}")

    async def _emit_headers_metric(
        self, path: str, method: str, headers_info: dict[str, Any], status_code: int
    ):
        """Emit custom metric with request header information for nginx config analysis."""
        try:
            await self.metrics_client.emit_custom_metric(
                metric_name="request_headers_analysis",
                value=1.0,
                dimensions={
                    "path": path,
                    "method": method,
                    "status_code": status_code,
                    "has_auth": headers_info.get("authorization_present", False),
                    "user_agent_type": headers_info.get("user_agent_type", "unknown"),
                    "content_type": headers_info.get("content_type", "unknown")[:50],
                    "has_origin": headers_info.get("origin", "unknown") != "unknown",
                },
                metadata={
                    "headers_sample": str(headers_info)[:500]  # Truncated sample
                },
            )
        except Exception as e:
            logger.debug(f"Failed to emit headers metric: {e}")

    async def _emit_discovery_metric_from_request(self, request: Request, duration_ms: float):
        """Emit discovery metric for search operations."""
        try:
            # Extract query from request parameters
            query_params = request.query_params
            query = query_params.get("q", query_params.get("query", "unknown"))

            # For now, we can't easily get the results count from the response
            # without parsing the response body, so we'll set a placeholder
            results_count = -1  # Indicates count not available

            await self.metrics_client.emit_discovery_metric(
                query=query, results_count=results_count, duration_ms=duration_ms
            )
        except Exception as e:
            logger.debug(f"Failed to emit discovery metric: {e}")


def add_registry_metrics_middleware(app, service_name: str = "registry"):
    """
    Convenience function to add registry metrics middleware to a FastAPI app.

    Args:
        app: FastAPI application instance
        service_name: Name of the service for metrics identification
    """
    app.add_middleware(RegistryMetricsMiddleware, service_name=service_name)
    logger.info(f"Registry metrics middleware added for service: {service_name}")
