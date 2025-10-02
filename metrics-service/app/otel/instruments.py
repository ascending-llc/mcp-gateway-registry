from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader
import logging

logger = logging.getLogger(__name__)


class MetricsInstruments:
    """OpenTelemetry metric instruments for MCP metrics."""
    
    def __init__(self):
        self.meter = metrics.get_meter("mcp-metrics-service")
        
        # Counter instruments
        self.auth_counter = self.meter.create_counter(
            name="mcp_auth_requests_total",
            description="Total number of authentication requests",
            unit="1"
        )
        
        self.discovery_counter = self.meter.create_counter(
            name="mcp_tool_discovery_total", 
            description="Total number of tool discovery requests",
            unit="1"
        )
        
        self.tool_counter = self.meter.create_counter(
            name="mcp_tool_executions_total",
            description="Total number of tool executions", 
            unit="1"
        )
        
        # Histogram instruments for duration tracking
        self.auth_histogram = self.meter.create_histogram(
            name="mcp_auth_request_duration_seconds",
            description="Duration of authentication requests in seconds",
            unit="s"
        )
        
        self.discovery_histogram = self.meter.create_histogram(
            name="mcp_tool_discovery_duration_seconds",
            description="Duration of tool discovery requests in seconds", 
            unit="s"
        )
        
        self.tool_histogram = self.meter.create_histogram(
            name="mcp_tool_execution_duration_seconds",
            description="Duration of tool executions in seconds",
            unit="s"
        )

        self.latency_histogram = self.meter.create_histogram(
            name="mcp_protocol_latency_seconds",
            description="Latency between MCP protocol steps in seconds",
            unit="s"
        )

        # Health check instruments
        self.health_counter = self.meter.create_counter(
            name="mcp_health_checks_total",
            description="Total number of health checks performed",
            unit="1"
        )

        self.health_histogram = self.meter.create_histogram(
            name="mcp_health_check_duration_seconds",
            description="Duration of health checks in seconds",
            unit="s"
        )

        logger.info("OpenTelemetry metric instruments initialized")