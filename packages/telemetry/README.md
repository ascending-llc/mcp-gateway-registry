# Telemetry Package

A generic OpenTelemetry metrics package that provides configuration-driven metric collection. This package is intentionally decoupled from business logic - services define their own domain-specific metrics and recording functions.

## Architecture Overview

```
packages/telemetry/              # Generic, reusable across all services
  metrics_client.py              # OTelMetricsClient with generic methods
  decorators.py                  # Generic timing decorators
  setup.py                       # OpenTelemetry SDK configuration

your_service/utils/
  otel_metrics.py                # Service-specific domain functions

config/metrics/
  your_service.yml               # YAML config defining metrics to capture
```

## Quick Start

### 1. Create a YAML Configuration File

Create a config file at `config/metrics/<service_name>.yml`:

```yaml
service_name: my_service

counters:
  - name: requests_total
    description: Total number of requests
    unit: "1"
    capture: true

  - name: errors_total
    description: Total number of errors
    unit: "1"
    capture: true

histograms:
  - name: request_duration_seconds
    description: Request duration in seconds
    unit: "s"
    capture: true
```

The `capture` flag controls whether the metric is registered:
- `capture: true` (default) - metric is registered and will record data
- `capture: false` - metric is skipped, calls to record will be silent no-ops

### 2. Create a Service-Specific Metrics Module

Create `your_service/utils/otel_metrics.py`:

```python
"""
Metrics client and domain functions for My Service.
"""

import logging
from typing import Optional

from packages.telemetry.metrics_client import create_metrics_client, load_metrics_config

logger = logging.getLogger(__name__)


# Load configuration and create service-specific metrics client
_config = load_metrics_config("my_service")
metrics = create_metrics_client("my_service", config=_config)


# =============================================================================
# Domain-Specific Recording Functions
# =============================================================================


def record_request(
    endpoint: str,
    method: str,
    success: bool,
    duration_seconds: Optional[float] = None,
) -> None:
    """
    Record an API request.

    Args:
        endpoint: The API endpoint
        method: HTTP method (GET, POST, etc.)
        success: Whether the request was successful
        duration_seconds: Request duration in seconds
    """
    attributes = {
        "endpoint": endpoint,
        "method": method,
        "status": "success" if success else "failure",
    }

    metrics.record_counter("requests_total", 1, attributes)

    if duration_seconds is not None:
        metrics.record_histogram("request_duration_seconds", duration_seconds, attributes)


def record_error(error_type: str, endpoint: str) -> None:
    """Record an error occurrence."""
    attributes = {"error_type": error_type, "endpoint": endpoint}
    metrics.record_counter("errors_total", 1, attributes)
```

### 3. Use Domain Functions in Your Code

```python
from your_service.utils.otel_metrics import record_request, record_error

async def handle_request(request):
    start_time = time.perf_counter()
    try:
        result = await process_request(request)
        duration = time.perf_counter() - start_time
        record_request("/api/data", "GET", success=True, duration_seconds=duration)
        return result
    except Exception as e:
        duration = time.perf_counter() - start_time
        record_request("/api/data", "GET", success=False, duration_seconds=duration)
        record_error(type(e).__name__, "/api/data")
        raise
```

## Using Decorators

The package provides generic decorators for automatic timing. You can also create service-specific decorators.

### Generic Decorators

```python
from packages.telemetry.decorators import track_duration, create_timed_context

# Using track_duration with a custom record function
def record_func(duration: float, labels: dict) -> None:
    metrics.record_histogram("operation_duration", duration, labels)

@track_duration(record_func, extract_labels=lambda x: {"type": x.type})
async def my_operation(request):
    ...

# Using create_timed_context for code blocks
async with create_timed_context(record_func, labels={"operation": "fetch"}) as ctx:
    result = await fetch_data()
    if result.error:
        ctx.set_success(False)
```

### Creating Service-Specific Decorators

Create decorators in your service that wrap the domain functions:

```python
# your_service/core/telemetry_decorators.py

import time
from functools import wraps
from typing import Callable, TypeVar

from your_service.utils.otel_metrics import record_request

F = TypeVar("F", bound=Callable)


def track_request(endpoint: str, method: str = "GET") -> Callable[[F], F]:
    """Decorator to automatically track API requests."""

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            success = False

            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception:
                raise
            finally:
                duration = time.perf_counter() - start_time
                record_request(endpoint, method, success, duration)

        return wrapper
    return decorator


# Usage
@track_request("/api/users", "GET")
async def get_users():
    return await db.fetch_users()
```

## OpenTelemetry Setup

Call `setup_metrics` during your application's startup phase:

```python
from packages.telemetry import setup_metrics

setup_metrics(
    service_name="your-service-name",
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    enable_metrics=True,
    enable_logs=True
)
```

This must be called before creating any metrics clients.

## Generic Client Methods

The `OTelMetricsClient` provides only generic methods:

| Method | Description |
|--------|-------------|
| `create_counter(name, description, unit)` | Register a counter metric |
| `create_histogram(name, description, unit)` | Register a histogram metric |
| `record_counter(name, value, attributes)` | Record a counter value |
| `record_histogram(name, value, attributes)` | Record a histogram value |
| `record_metric(name, value, attributes)` | Auto-detect type and record |
| `get_counter(name)` | Get a registered counter |
| `get_histogram(name)` | Get a registered histogram |

All methods are safe - they swallow exceptions and log warnings to prevent application crashes.

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | `http://otel-collector:4318` |
| `OTEL_PROMETHEUS_ENABLED` | Enable Prometheus exporter | `false` |

## How It Works

1. **Config Loading**: At module import time, the YAML config is loaded
2. **Metric Registration**: Metrics with `capture: true` are registered with OpenTelemetry
3. **Recording**: Domain functions call `metrics.record_counter()` / `metrics.record_histogram()`
4. **Graceful Degradation**: If a metric isn't registered (config missing, `capture: false`), the call is a silent no-op

```
YAML Config                    Service Module                 Decorators/Code
    |                               |                              |
    v                               v                              v
[counters]  ──> create_metrics_client() ──> record_request() <── @track_request
[histograms]         |                           |
                     v                           v
              _counters: {...}           metrics.record_counter()
              _histograms: {...}                 |
                     |                           v
                     └──────> counter.add() / histogram.record()
```

## Example: Adding a New Service

1. Create `config/metrics/new_service.yml` with your metrics
2. Create `new_service/utils/otel_metrics.py` with:
   - Config loading
   - `metrics = create_metrics_client("new_service", config=_config)`
   - Domain-specific recording functions
3. Optionally create `new_service/core/telemetry_decorators.py` for decorators
4. Import and use your domain functions throughout your service

This keeps the telemetry package generic while allowing each service to define its own domain-specific metrics vocabulary.
