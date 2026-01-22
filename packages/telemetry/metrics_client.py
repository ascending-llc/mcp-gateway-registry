import logging
import functools
from opentelemetry import metrics

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
    """
    
    def __init__(self):
        try:
            self.meter = metrics.get_meter(__name__)
            
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
            
            self.auth_requests = self.meter.create_counter(
                name="auth_requests_total",
                description="Total number of authentication attempts",
                unit="1"
            )
            self.tool_discovery = self.meter.create_counter(
                name="mcp_tool_discovery_total",
                description="Total number of tools discovered/registered",
                unit="1"
            )
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
    def record_auth_request(self, mechanism: str, success: bool):
        """
        Record an authentication attempt.
        ex: client.record_auth_request("jwt", success=True)
        """
        attributes = {
            "mechanism": mechanism,
            "status": "success" if success else "failure"
        }
        self.auth_requests.add(1, attributes)

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
    def record_tool_discovery(self, tool_name: str, source: str = "registry"):
        """
        Record when a tool is discovered or registered.
        """
        attributes = {
            "tool_name": tool_name,
            "source": source
        }
        self.tool_discovery.add(1, attributes)

    @safe_telemetry
    def record_server_request(self, server_name: str):
        """
        Record a request to a specific MCP server.
        """
        attributes = {
            "server_name": server_name
        }
        self.server_requests.add(1, attributes)
