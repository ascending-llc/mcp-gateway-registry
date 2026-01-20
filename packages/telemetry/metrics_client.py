from opentelemetry import metrics

class OTelMetricsClient:
    """
    Unified client for defining and recording OpenTelemetry metrics.
    """
    
    def __init__(self):
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

    def record_http_request(self, method: str, route: str, status_code: int):
        """Record an incoming HTTP request."""
        attributes = {
            "method": method,
            "route": route,
            "status_code": str(status_code)
        }
        self.http_requests.add(1, attributes)

    def record_http_duration(self, duration_seconds: float, method: str, route: str):
        """Record how long a request took."""
        attributes = {
            "method": method,
            "route": route
        }
        self.http_duration.record(duration_seconds, attributes)

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

    def record_tool_used(self, tool_name: str):
        """
        Record when a tool is used.
        """
        attributes = {
            "tool_name": tool_name
        }
        self.tool_discovery.add(1, attributes)
            
    def record_tool_discovery(self, tool_name: str, source: str = "registry"):
        """
        Record when a tool is discovered or registered.
        """
        attributes = {
            "tool_name": tool_name,
            "source": source
        }
        self.tool_discovery.add(1, attributes)

    def record_server_request(self, server_name: str):
        """
        Record a request to a specific MCP server.
        """
        attributes = {
            "server_name": server_name
        }
        self.server_requests.add(1, attributes)
