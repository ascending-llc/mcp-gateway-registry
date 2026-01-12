# registry/instruments.py
from opentelemetry import metrics
import logging

logger = logging.getLogger(__name__)

class MetricsInstruments:
    """OpenTelemetry metric instruments for MCP metrics."""
    
    def __init__(self):
        # NOTE: get_meter returns a "proxy" meter. It is safe to call this 
        # before setup_otel() runs in main.py. It will activate later.
        self.meter = metrics.get_meter("mcp-metrics-service")
        
        self.love_counter = self.meter.create_counter(
            name="love_conuting",
            description="Total number of people who love counting requests",
            unit="1"
        )

        # --- COUNTERS ---
        self.auth_counter = self.meter.create_counter(
            name="mcp_auth_requests_total",
            description="Total number of authentication requests",
            unit="1"
        )
        self.request_counter = self.meter.create_counter(
            name="http_requests_total",
            description="Total HTTP requests",
            unit="1"
        )
        
        # --- HISTOGRAMS ---
        self.request_duration = self.meter.create_histogram(
            name="http_request_duration_seconds",
            description="HTTP request duration in seconds",
            unit="s"
        )
        
        # (Add your other existing counters/histograms here as needed)

# Create a global instance
mcp_metrics = MetricsInstruments()