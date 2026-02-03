"""
FastAPI middleware for comprehensive metrics collection in the auth server.

This middleware automatically tracks detailed authentication metrics including:
- Validation steps and scope checking
- Tool access control decisions
- Method/tool usage patterns
- Error analysis with specific reasons
"""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

# Import metrics client - use HTTP API instead of local import
import httpx
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class AuthMetricsMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive middleware to collect detailed authentication and tool execution metrics.

    Tracks:
    - Authentication flow with detailed validation steps
    - Scope checking and access control decisions
    - Tool and method execution patterns
    - Error analysis with specific failure reasons
    - User activity patterns (hashed for privacy)
    """

    def __init__(self, app, service_name: str = "auth-server"):
        super().__init__(app)
        self.service_name = service_name
        self.metrics_url = os.getenv("METRICS_SERVICE_URL", "http://localhost:8890")
        self.api_key = os.getenv("METRICS_API_KEY", "")
        self.client = httpx.AsyncClient(timeout=5.0)

        # Track request contexts for detailed metrics
        self.request_contexts: dict[str, dict[str, Any]] = {}

        # Track session timings for protocol flow analysis
        self.session_timings: dict[str, dict[str, float]] = {}

        # Track session client info for consistent metrics across requests
        self.session_client_info: dict[str, dict[str, str]] = {}

        # Scalability configuration
        self.max_sessions = 1000  # Limit concurrent sessions
        self.session_ttl = 3600  # 1 hour TTL
        self.cleanup_interval = 300  # Cleanup every 5 minutes
        self.last_cleanup = time.time()

    def hash_username(self, username: str) -> str:
        """Hash username for privacy in metrics."""
        if not username:
            return ""
        return hashlib.sha256(username.encode()).hexdigest()[:12]

    async def _cleanup_sessions_if_needed(self):
        """Perform periodic cleanup of old sessions to prevent memory leaks."""
        current_time = time.time()

        # Only cleanup every cleanup_interval seconds
        if current_time - self.last_cleanup < self.cleanup_interval:
            return

        self.last_cleanup = current_time

        # Clean up old session timings
        sessions_to_remove = []
        for session_key, methods in self.session_timings.items():
            # Remove if all methods are old
            if all(current_time - timestamp > self.session_ttl for timestamp in methods.values()):
                sessions_to_remove.append(session_key)

        # Also remove oldest sessions if we exceed max_sessions
        if len(self.session_timings) > self.max_sessions:
            # Sort by oldest timestamp and remove excess
            session_ages = [
                (session_key, min(methods.values()) if methods else 0)
                for session_key, methods in self.session_timings.items()
            ]
            session_ages.sort(key=lambda x: x[1])
            excess_count = len(self.session_timings) - self.max_sessions
            sessions_to_remove.extend([s[0] for s in session_ages[:excess_count]])

        # Remove sessions
        for session_key in sessions_to_remove:
            self.session_timings.pop(session_key, None)
            self.session_client_info.pop(session_key, None)

        if sessions_to_remove:
            logger.debug(f"Cleaned up {len(sessions_to_remove)} old sessions")

    def extract_server_name_from_url(self, original_url: str) -> str:
        """Extract server name from the original URL."""
        if not original_url:
            return "unknown"

        try:
            from urllib.parse import urlparse

            parsed_url = urlparse(original_url)
            path = parsed_url.path.strip("/")
            path_parts = path.split("/") if path else []
            return path_parts[0] if path_parts else "unknown"
        except Exception:
            return "unknown"

    async def extract_tool_and_method_info(self, request: Request) -> dict[str, Any]:
        """Extract detailed tool and method information from headers (X-Body) instead of consuming body."""
        tool_info = {
            "method": "unknown",
            "tool_name": None,
            "request_id": None,
            "protocol_version": None,
            "client_info": {},
            "params": {},
        }

        try:
            # Get the request body from X-Body header set by Lua script instead of consuming it
            x_body = request.headers.get("X-Body")
            if x_body:
                request_payload = json.loads(x_body)

                if isinstance(request_payload, dict):
                    tool_info["method"] = request_payload.get("method", "unknown")
                    tool_info["request_id"] = request_payload.get("id")
                    tool_info["jsonrpc"] = request_payload.get("jsonrpc")

                    # Extract parameters
                    params = request_payload.get("params", {})
                    tool_info["params"] = params

                    # For tools/call, extract the actual tool name from params
                    if tool_info["method"] == "tools/call" and isinstance(params, dict):
                        tool_info["tool_name"] = params.get("name", "")

                    # For initialize, extract client info and capabilities
                    elif tool_info["method"] == "initialize" and isinstance(params, dict):
                        tool_info["protocol_version"] = params.get("protocolVersion")
                        tool_info["client_info"] = params.get("clientInfo", {})

        except Exception as e:
            logger.debug(f"Could not extract tool information from X-Body header: {e}")

        return tool_info

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and collect comprehensive metrics.
        """
        # Skip metrics collection for non-validation endpoints
        if not request.url.path.startswith("/validate"):
            return await call_next(request)

        # Start timing and generate request ID
        start_time = time.perf_counter()
        current_timestamp = time.time()
        request_id = f"req_{uuid.uuid4().hex[:16]}"

        # Extract comprehensive request data
        server_name = "unknown"
        user_hash = ""
        auth_method = "unknown"
        tool_info = {}

        # Extract server name from original URL header
        original_url = request.headers.get("X-Original-URL")
        if original_url:
            server_name = self.extract_server_name_from_url(original_url)

        # Extract detailed tool/method information
        tool_info = await self.extract_tool_and_method_info(request)

        # Process the request
        response = None
        success = False
        error_code = None

        try:
            response = await call_next(request)

            # Determine success based on response status
            success = response.status_code == 200

            if success:
                # Extract user info from response headers if available
                username = response.headers.get("X-Username", "")
                user_hash = self.hash_username(username)
                auth_method = response.headers.get("X-Auth-Method", "unknown")

                # Track session timing for protocol flow analysis
                session_key = (
                    f"{server_name}:{user_hash}" if user_hash else f"{server_name}:anonymous"
                )
                method = tool_info.get("method", "unknown")

                # Perform periodic cleanup to prevent memory leaks
                await self._cleanup_sessions_if_needed()

                if session_key not in self.session_timings:
                    self.session_timings[session_key] = {}

                # Store timestamp for this method
                self.session_timings[session_key][method] = current_timestamp

                # Store client info for initialize requests
                if method == "initialize" and tool_info.get("client_info"):
                    self.session_client_info[session_key] = tool_info["client_info"]
            else:
                error_code = str(response.status_code)
                session_key = f"{server_name}:anonymous"

        except Exception as e:
            # Handle exceptions during request processing
            success = False
            error_code = type(e).__name__
            logger.error(f"Error in auth request: {e}")
            # Re-raise the exception to maintain normal error handling
            raise

        finally:
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Emit comprehensive metrics asynchronously (fire and forget)
            # 1. Main auth metric
            asyncio.create_task(
                self._emit_auth_metric(
                    success=success,
                    method=auth_method,
                    duration_ms=duration_ms,
                    server_name=server_name,
                    user_hash=user_hash,
                    error_code=error_code,
                    request_id=request_id,
                )
            )

            # 2. Tool execution metric (if applicable)
            if tool_info.get("method") and tool_info["method"] != "unknown":
                asyncio.create_task(
                    self._emit_tool_execution_metric(
                        tool_info=tool_info,
                        server_name=server_name,
                        success=success,
                        duration_ms=duration_ms,
                        user_hash=user_hash,
                        error_code=error_code,
                        request_id=request_id,
                        auth_method=auth_method,
                    )
                )

            # 3. Protocol flow latency metric (if we can calculate it)
            if success and session_key in self.session_timings:
                asyncio.create_task(
                    self._emit_protocol_latency_metric(
                        session_key=session_key,
                        current_method=method,
                        server_name=server_name,
                        user_hash=user_hash,
                        request_id=request_id,
                    )
                )

        return response

    async def _emit_auth_metric(
        self,
        success: bool,
        method: str,
        duration_ms: float,
        server_name: str,
        user_hash: str,
        error_code: str = None,
        request_id: str = None,
    ):
        """
        Emit authentication metric asynchronously.
        """
        try:
            if not self.api_key:
                return

            payload = {
                "service": self.service_name,
                "version": "1.0.0",
                "metrics": [
                    {
                        "type": "auth_request",
                        "timestamp": datetime.utcnow().isoformat(),
                        "value": 1.0,
                        "duration_ms": duration_ms,
                        "dimensions": {
                            "success": success,
                            "method": method,
                            "server": server_name,
                            "user_hash": user_hash,
                        },
                        "metadata": {
                            "error_code": error_code,
                            "request_id": request_id or f"req_{uuid.uuid4().hex[:16]}",
                        },
                    }
                ],
            }

            await self.client.post(
                f"{self.metrics_url}/metrics", json=payload, headers={"X-API-Key": self.api_key}
            )
        except Exception as e:
            logger.debug(f"Failed to emit auth metric: {e}")

    async def _emit_tool_execution_metric(
        self,
        tool_info: dict[str, Any],
        server_name: str,
        success: bool,
        duration_ms: float,
        user_hash: str,
        error_code: str = None,
        request_id: str = None,
        auth_method: str = "unknown",
    ):
        """
        Emit tool execution metric for the specialized tool_metrics table.
        """
        try:
            if not self.api_key:
                return

            # Extract tool/method details
            method_name = tool_info.get("method", "unknown")
            actual_tool_name = tool_info.get("tool_name")
            client_info = tool_info.get("client_info", {})

            # If no client_info in current request, try to get it from session
            if not client_info or client_info.get("name") == "unknown":
                session_key = (
                    f"{server_name}:{user_hash}" if user_hash else f"{server_name}:anonymous"
                )
                stored_client_info = self.session_client_info.get(session_key, {})
                if stored_client_info:
                    client_info = stored_client_info

            # Create tool execution metric payload
            metric_data = {
                "type": "tool_execution",
                "timestamp": datetime.utcnow().isoformat(),
                "value": 1.0,
                "duration_ms": duration_ms,
                "dimensions": {
                    "tool_name": actual_tool_name or method_name,
                    "server_name": server_name,
                    "success": success,
                    "method": method_name,
                    "user_hash": user_hash,
                    "server_path": f"/{server_name}/",
                    "client_name": client_info.get("name", "unknown"),
                    "client_version": client_info.get("version", "unknown"),
                },
                "metadata": {
                    "error_code": error_code,
                    "auth_method": auth_method,
                    "request_id": request_id or f"req_{uuid.uuid4().hex[:16]}",
                    "protocol_version": tool_info.get("protocol_version"),
                    "jsonrpc_id": tool_info.get("request_id"),
                    "actual_tool_name": actual_tool_name,
                    "method_type": method_name,
                    "input_size_bytes": len(json.dumps(tool_info.get("params", {})).encode()),
                    "output_size_bytes": 0,  # Will be updated if response available
                },
            }

            payload = {"service": self.service_name, "version": "1.0.0", "metrics": [metric_data]}

            await self.client.post(
                f"{self.metrics_url}/metrics", json=payload, headers={"X-API-Key": self.api_key}
            )
        except Exception as e:
            logger.debug(f"Failed to emit tool execution metric: {e}")

    async def _emit_protocol_latency_metric(
        self,
        session_key: str,
        current_method: str,
        server_name: str,
        user_hash: str,
        request_id: str,
    ):
        """
        Emit protocol flow latency metrics based on session timing data.
        """
        try:
            if not self.api_key:
                return

            session_data = self.session_timings.get(session_key, {})
            current_time = time.time()

            # Calculate latencies between protocol steps
            latency_metrics = []

            # Initialize -> Tools List latency
            if "initialize" in session_data and "tools/list" in session_data:
                init_to_list_latency = session_data["tools/list"] - session_data["initialize"]
                if (
                    init_to_list_latency > 0 and init_to_list_latency < 300
                ):  # Max 5 minutes reasonable
                    latency_metrics.append(
                        {
                            "type": "protocol_latency",
                            "timestamp": datetime.utcnow().isoformat(),
                            "value": init_to_list_latency,
                            "dimensions": {
                                "flow_step": "initialize_to_tools_list",
                                "server_name": server_name,
                                "user_hash": user_hash,
                                "session_key": session_key,
                            },
                            "metadata": {
                                "request_id": request_id,
                                "latency_seconds": init_to_list_latency,
                                "from_method": "initialize",
                                "to_method": "tools/list",
                            },
                        }
                    )

            # Tools List -> Tools Call latency
            if "tools/list" in session_data and "tools/call" in session_data:
                list_to_call_latency = session_data["tools/call"] - session_data["tools/list"]
                if (
                    list_to_call_latency > 0 and list_to_call_latency < 300
                ):  # Max 5 minutes reasonable
                    latency_metrics.append(
                        {
                            "type": "protocol_latency",
                            "timestamp": datetime.utcnow().isoformat(),
                            "value": list_to_call_latency,
                            "dimensions": {
                                "flow_step": "tools_list_to_tools_call",
                                "server_name": server_name,
                                "user_hash": user_hash,
                                "session_key": session_key,
                            },
                            "metadata": {
                                "request_id": request_id,
                                "latency_seconds": list_to_call_latency,
                                "from_method": "tools/list",
                                "to_method": "tools/call",
                            },
                        }
                    )

            # Initialize -> Tools Call (total flow latency)
            if "initialize" in session_data and "tools/call" in session_data:
                total_flow_latency = session_data["tools/call"] - session_data["initialize"]
                if total_flow_latency > 0 and total_flow_latency < 600:  # Max 10 minutes reasonable
                    latency_metrics.append(
                        {
                            "type": "protocol_latency",
                            "timestamp": datetime.utcnow().isoformat(),
                            "value": total_flow_latency,
                            "dimensions": {
                                "flow_step": "full_protocol_flow",
                                "server_name": server_name,
                                "user_hash": user_hash,
                                "session_key": session_key,
                            },
                            "metadata": {
                                "request_id": request_id,
                                "latency_seconds": total_flow_latency,
                                "from_method": "initialize",
                                "to_method": "tools/call",
                            },
                        }
                    )

            # Emit metrics if we have any
            if latency_metrics:
                payload = {
                    "service": self.service_name,
                    "version": "1.0.0",
                    "metrics": latency_metrics,
                }

                await self.client.post(
                    f"{self.metrics_url}/metrics", json=payload, headers={"X-API-Key": self.api_key}
                )

            # Cleanup is now handled by _cleanup_sessions_if_needed method

        except Exception as e:
            logger.debug(f"Failed to emit protocol latency metric: {e}")


def add_auth_metrics_middleware(app, service_name: str = "auth-server"):
    """
    Convenience function to add auth metrics middleware to a FastAPI app.

    Args:
        app: FastAPI application instance
        service_name: Name of the service for metrics identification
    """
    app.add_middleware(AuthMetricsMiddleware, service_name=service_name)
    logger.info(f"Auth metrics middleware added for service: {service_name}")
