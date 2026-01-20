import os
from packages.telemetry.metrics_client import OTelMetricsClient

metrics = OTelMetricsClient(os.getenv("OTEL_SERVICE_NAME", "unknown-service"))
