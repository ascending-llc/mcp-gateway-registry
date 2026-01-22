import logging
import functools
from typing import Optional
from opentelemetry import metrics

logger = logging.getLogger(__name__)

# Histogram bucket boundaries for latency metrics (in seconds)
# These buckets are designed to capture p50, p95, p99 accurately
LATENCY_BUCKETS_SECONDS = (
    0.005, 0.01, 0.025, 0.05, 0.075,
    0.1, 0.25, 0.5, 0.75,
    1.0, 2.5, 5.0, 7.5, 10.0
)

# Histogram bucket boundaries for latency metrics (in milliseconds)
LATENCY_BUCKETS_MS = (
    5, 10, 25, 50, 75,
    100, 250, 500, 750,
    1000, 2500, 5000, 7500, 10000
)


def safe_telemetry(func):
    """
    Decorator to safely execute telemetry methods.
    Swallows exceptions and logs them as warnings to prevent application crashes.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Telemetry error in {func.__name__}: {e}")
    return wrapper


class OTelMetricsClient:
    """
    Unified client for defining and recording OpenTelemetry metrics.
    Safe to use - methods swallow exceptions to prevent application crashes.

    Metrics provided for key requirements:
    - Auth request rate & success rate (counter + histogram)
    - Tool discovery latency p50/p95/p99 (histogram)
    - Tool execution success rate (counter + histogram)
    - Registry operation latency (histogram)
    """

    def __init__(self):
        try:
            self.meter = metrics.get_meter(__name__)

            # HTTP metrics
            self.http_requests = self.meter.create_counter(
                name="http_requests_total",
                description="Total number of HTTP requests",
                unit="1"
            )
            self.http_duration = self.meter.create_histogram(
                name="http_request_duration_seconds",
                description="HTTP request duration in seconds",
                unit="s"
            )

            # Auth metrics - counter for rate, histogram for latency percentiles
            self.auth_requests = self.meter.create_counter(
                name="auth_requests_total",
                description="Total number of authentication attempts",
                unit="1"
            )
            self.auth_duration = self.meter.create_histogram(
                name="auth_request_duration_seconds",
                description="Authentication request duration in seconds for p50/p95/p99",
                unit="s"
            )

            # Tool discovery metrics - counter for rate, histogram for latency percentiles
            self.tool_discovery = self.meter.create_counter(
                name="mcp_tool_discovery_total",
                description="Total number of tool discovery operations",
                unit="1"
            )
            self.tool_discovery_duration = self.meter.create_histogram(
                name="mcp_tool_discovery_duration_seconds",
                description="Tool discovery latency in seconds for p50/p95/p99",
                unit="s"
            )

            # Tool execution metrics - counter for success rate, histogram for latency
            self.tool_execution = self.meter.create_counter(
                name="mcp_tool_execution_total",
                description="Total number of tool executions",
                unit="1"
            )
            self.tool_execution_duration = self.meter.create_histogram(
                name="mcp_tool_execution_duration_seconds",
                description="Tool execution duration in seconds for p50/p95/p99",
                unit="s"
            )

            # Registry operation metrics - counter for rate, histogram for latency
            self.registry_operations = self.meter.create_counter(
                name="registry_operations_total",
                description="Total number of registry operations",
                unit="1"
            )
            self.registry_operation_duration = self.meter.create_histogram(
                name="registry_operation_duration_seconds",
                description="Registry operation latency in seconds for p50/p95/p99",
                unit="s"
            )

            # Server requests counter (legacy)
            self.server_requests = self.meter.create_counter(
                name="mcp_server_requests_total",
                description="Total number of requests to MCP servers",
                unit="1"
            )
        except Exception as e:
            logger.error(f"Failed to initialize OTelMetricsClient: {e}")

    @safe_telemetry
    def record_http_request(self, method: str, route: str, status_code: int):
        """Record an incoming HTTP request."""
        attributes = {
            "method": method,
            "route": route,
            "status_code": str(status_code)
        }
        self.http_requests.add(1, attributes)

    @safe_telemetry
    def record_http_duration(self, duration_seconds: float, method: str, route: str):
        """Record how long a request took."""
        attributes = {
            "method": method,
            "route": route
        }
        self.http_duration.record(duration_seconds, attributes)

    @safe_telemetry
    def record_auth_request(
        self,
        mechanism: str,
        success: bool,
        duration_seconds: Optional[float] = None
    ):
        """
        Record an authentication attempt with optional duration for latency percentiles.

        Args:
            mechanism: Authentication mechanism (e.g., "jwt", "api_key", "basic")
            success: Whether the auth attempt was successful
            duration_seconds: Request duration in seconds for p50/p95/p99 calculation

        Example:
            client.record_auth_request("jwt", success=True, duration_seconds=0.05)
        """
        attributes = {
            "mechanism": mechanism,
            "status": "success" if success else "failure"
        }
        self.auth_requests.add(1, attributes)

        # Record duration histogram for latency percentiles
        if duration_seconds is not None:
            self.auth_duration.record(duration_seconds, attributes)

    @safe_telemetry
    def record_tool_used(self, tool_name: str):
        """
        Record when a tool is used.
        """
        attributes = {
            "tool_name": tool_name
        }
        self.tool_discovery.add(1, attributes)

    @safe_telemetry
    def record_tool_discovery(
        self,
        tool_name: str,
        source: str = "registry",
        success: bool = True,
        duration_seconds: Optional[float] = None
    ):
        """
        Record tool discovery operation with optional duration for latency percentiles.

        Args:
            tool_name: Name of the tool discovered
            source: Source of discovery (e.g., "registry", "server", "search")
            success: Whether the discovery was successful
            duration_seconds: Discovery duration in seconds for p50/p95/p99 calculation

        Example:
            client.record_tool_discovery("my_tool", source="search", success=True, duration_seconds=0.15)
        """
        attributes = {
            "tool_name": tool_name,
            "source": source,
            "status": "success" if success else "failure"
        }
        self.tool_discovery.add(1, attributes)

        # Record duration histogram for latency percentiles
        if duration_seconds is not None:
            self.tool_discovery_duration.record(duration_seconds, attributes)

    @safe_telemetry
    def record_tool_execution(
        self,
        tool_name: str,
        server_name: str,
        success: bool,
        duration_seconds: Optional[float] = None,
        method: Optional[str] = None
    ):
        """
        Record tool execution with success rate and latency tracking.

        Args:
            tool_name: Name of the tool executed
            server_name: Name of the MCP server
            success: Whether the execution was successful
            duration_seconds: Execution duration in seconds for p50/p95/p99 calculation
            method: MCP method (e.g., "tools/call", "tools/list")

        Example:
            client.record_tool_execution(
                "my_tool",
                "my_server",
                success=True,
                duration_seconds=0.25
            )
        """
        attributes = {
            "tool_name": tool_name,
            "server_name": server_name,
            "status": "success" if success else "failure"
        }
        if method:
            attributes["method"] = method

        self.tool_execution.add(1, attributes)

        # Record duration histogram for latency percentiles
        if duration_seconds is not None:
            self.tool_execution_duration.record(duration_seconds, attributes)

    @safe_telemetry
    def record_registry_operation(
        self,
        operation: str,
        resource_type: str,
        success: bool,
        duration_seconds: Optional[float] = None
    ):
        """
        Record registry operation with latency tracking.

        Args:
            operation: Type of operation (e.g., "read", "create", "update", "delete", "list", "search")
            resource_type: Type of resource (e.g., "server", "tool", "search")
            success: Whether the operation was successful
            duration_seconds: Operation duration in seconds for p50/p95/p99 calculation

        Example:
            client.record_registry_operation(
                "search",
                "server",
                success=True,
                duration_seconds=0.08
            )
        """
        attributes = {
            "operation": operation,
            "resource_type": resource_type,
            "status": "success" if success else "failure"
        }
        self.registry_operations.add(1, attributes)

        # Record duration histogram for latency percentiles
        if duration_seconds is not None:
            self.registry_operation_duration.record(duration_seconds, attributes)

    @safe_telemetry
    def record_server_request(self, server_name: str):
        """
        Record a request to a specific MCP server.
        """
        attributes = {
            "server_name": server_name
        }
        self.server_requests.add(1, attributes)
