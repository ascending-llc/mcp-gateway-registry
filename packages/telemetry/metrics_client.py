import logging
import functools
from typing import (
    Dict,
    Optional,
    Any,
)
from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram

logger = logging.getLogger(__name__)


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

    This client supports two usage patterns:
    1. Pre-defined domain metrics (backwards compatible):
       - record_auth_request(), record_tool_discovery(), etc.

    2. Generic dynamic metrics (recommended for new code):
       - create_counter(), create_histogram()
       - record_counter(), record_histogram()
       - record_metric() for automatic type detection

    The generic approach keeps the telemetry package decoupled from business logic.
    """

    def __init__(
        self,
        service_name: str,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize metrics client for a specific service.

        Args:
            service_name: Name of the service (e.g., 'api', 'worker', 'registry')
            config: Optional configuration dict with 'counters' and 'histograms' lists
        """
        try:
            self.service_name = service_name
            self.meter = metrics.get_meter(f"mcp.{service_name}")

            # Dynamic metric registries
            self._counters: Dict[str, Counter] = {}
            self._histograms: Dict[str, Histogram] = {}

            # Initialize from config if provided
            if config:
                self._init_from_config(config)

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
            logger.error(f"Failed to initialize OTelMetricsClient for service '{service_name}': {e}")

    def _init_from_config(self, config: Dict[str, Any]) -> None:
        """
        Initialize metrics from configuration dictionary.

        Config format:
            {
                "counters": [
                    {"name": "my_counter", "description": "...", "unit": "1"}
                ],
                "histograms": [
                    {"name": "my_histogram", "description": "...", "unit": "s"}
                ]
            }
        """
        for counter_def in config.get("counters", []):
            self.create_counter(
                name=counter_def["name"],
                description=counter_def.get("description", ""),
                unit=counter_def.get("unit", "1"),
            )

        for histogram_def in config.get("histograms", []):
            self.create_histogram(
                name=histogram_def["name"],
                description=histogram_def.get("description", ""),
                unit=histogram_def.get("unit", "s"),
            )

    @safe_telemetry
    def create_counter(
        self,
        name: str,
        description: str = "",
        unit: str = "1",
    ) -> Optional[Counter]:
        """
        Dynamically create and register a counter metric.

        Args:
            name: Metric name (e.g., "requests_total")
            description: Human-readable description
            unit: Unit of measurement (default: "1" for counts)

        Returns:
            The created Counter instance, or None if creation failed
        """
        if name not in self._counters:
            counter = self.meter.create_counter(
                name=name,
                description=description,
                unit=unit,
            )
            self._counters[name] = counter
        return self._counters.get(name)

    @safe_telemetry
    def create_histogram(
        self,
        name: str,
        description: str = "",
        unit: str = "s",
    ) -> Optional[Histogram]:
        """
        Dynamically create and register a histogram metric.

        Args:
            name: Metric name (e.g., "request_duration_seconds")
            description: Human-readable description
            unit: Unit of measurement (default: "s" for seconds)

        Returns:
            The created Histogram instance, or None if creation failed
        """
        if name not in self._histograms:
            histogram = self.meter.create_histogram(
                name=name,
                description=description,
                unit=unit,
            )
            self._histograms[name] = histogram
        return self._histograms.get(name)

    @safe_telemetry
    def record_counter(
        self,
        name: str,
        value: float = 1.0,
        attributes: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a value to a counter metric.

        Args:
            name: Name of the counter metric
            value: Value to add (default: 1.0)
            attributes: Optional dictionary of label key-value pairs
        """
        counter = self._counters.get(name)
        if counter:
            counter.add(value, attributes or {})
        else:
            logger.warning(f"Counter '{name}' not registered")

    @safe_telemetry
    def record_histogram(
        self,
        name: str,
        value: float,
        attributes: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a value to a histogram metric.

        Args:
            name: Name of the histogram metric
            value: Value to record (e.g., duration in seconds)
            attributes: Optional dictionary of label key-value pairs
        """
        histogram = self._histograms.get(name)
        if histogram:
            histogram.record(value, attributes or {})
        else:
            logger.warning(f"Histogram '{name}' not registered")

    @safe_telemetry
    def record_metric(
        self,
        name: str,
        value: float = 1.0,
        attributes: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Generic method to record any metric by name.

        Automatically detects whether the metric is a counter or histogram
        and records the value appropriately.

        Args:
            name: Name of the metric (counter or histogram)
            value: Value to record
            attributes: Optional dictionary of label key-value pairs
        """
        attributes = attributes or {}

        if name in self._counters:
            self._counters[name].add(value, attributes)
        elif name in self._histograms:
            self._histograms[name].record(value, attributes)
        else:
            logger.warning(f"Metric '{name}' not registered as counter or histogram")

    def get_counter(self, name: str) -> Optional[Counter]:
        """Get a registered counter by name."""
        return self._counters.get(name)

    def get_histogram(self, name: str) -> Optional[Histogram]:
        """Get a registered histogram by name."""
        return self._histograms.get(name)

    # ========== Domain-Specific Methods (Backwards Compatible) ==========
    # These methods are kept for backwards compatibility with existing code.
    # New code should prefer the generic create_*/record_* methods above.

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
        method: str = "UNKNOWN"
    ):
        """
        Record tool execution with success rate and latency tracking.

        Args:
            tool_name: Name of the tool executed
            server_name: Name of the MCP server
            success: Whether the execution was successful
            duration_seconds: Execution duration in seconds for p50/p95/p99 calculation
            method: HTTP method (e.g., "POST", "GET") - defaults to "UNKNOWN"
        """
        attributes = {
            "tool_name": tool_name,
            "server_name": server_name,
            "status": "success" if success else "failure",
            "method": method  # Always include this
        }

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


def create_metrics_client(
    service_name: str,
    config: Optional[Dict[str, Any]] = None,
) -> OTelMetricsClient:
    """
    Create a metrics client for a specific service.

    This factory function creates a new OTelMetricsClient instance with
    service-specific meter identity for better observability in dashboards.

    Args:
        service_name: Identifier for the service (e.g., 'api', 'worker', 'registry')
        config: Optional configuration dict with 'counters' and 'histograms' lists

    Returns:
        Configured OTelMetricsClient instance

    Example:
        # Basic usage (uses pre-defined domain metrics)
        >>> from packages.telemetry.metrics_client import create_metrics_client
        >>> metrics = create_metrics_client("api")
        >>> metrics.record_auth_request("jwt", success=True, duration_seconds=0.05)

        # With custom metrics config
        >>> config = {
        ...     "counters": [{"name": "custom_total", "description": "Custom counter"}],
        ...     "histograms": [{"name": "custom_duration_seconds", "description": "Custom histogram"}]
        ... }
        >>> metrics = create_metrics_client("api", config=config)
        >>> metrics.record_counter("custom_total", 1, {"label": "value"})
    """
    return OTelMetricsClient(service_name, config=config)