# Telemetry Package

This package provides utilities for configuring OpenTelemetry metrics and logs within the application. It uses OpenTelemetry SDKs to export telemetry data to a collector or expose it via Prometheus.

## Setup and Usage

To set up OpenTelemetry for metrics and logs, import and call the `setup_metrics` function from `packages.telemetry`:

```python
from packages.telemetry import setup_metrics

# Call this function during your application's startup phase
setup_metrics(
    service_name="your-service-name",
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"), # Optional, will use env var or default
    enable_metrics=True, # Set to False to disable metrics
    enable_logs=True # Set to False to disable logs
)
```

The `service_name` parameter is crucial for identifying your service in telemetry systems.

## Using the Metrics Client

To record custom metrics, you need to import and instantiate the `OTelMetricsClient`:

```python
from packages.telemetry.metrics_client import OTelMetricsClient

# Instantiate the client with your service name
# This should typically be done once per service/application
metrics_client = OTelMetricsClient(service_name="your-service-name")

# Example of recording an HTTP request metric
metrics_client.record_http_request(method="GET", route="/api/data", status_code=200)

# Example of recording an authentication attempt
metrics_client.record_auth_request(mechanism="jwt", success=True)
```

You should ensure that `setup_metrics` has been called *before* instantiating `OTelMetricsClient` to properly configure the OpenTelemetry MeterProvider.

## Environment Variables

The behavior of the telemetry package can be configured using the following environment variables:

*   `OTEL_EXPORTER_OTLP_ENDPOINT`:
    *   **Purpose:** Specifies the endpoint URL for the OpenTelemetry Protocol (OTLP) collector where metrics and logs will be sent.
    *   **Default Value:** `http://otel-collector:4318`
    *   **Example:** `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`

*   `OTEL_PROMETHEUS_ENABLED`:
    *   **Purpose:** If set to `true`, enables the Prometheus metrics exporter. When enabled, a simple HTTP server starts to expose metrics in a Prometheus-compatible format.
    *   **Default Value:** `false`
    *   **Impact:** If `true`, a Prometheus metrics endpoint will be available typically on port `9464` at `0.0.0.0:9464`.
    *   **Example:** `OTEL_PROMETHEUS_ENABLED=true`
