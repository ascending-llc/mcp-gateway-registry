import os
import logging
from typing import Optional
from opentelemetry import metrics
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import View
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation

from packages.telemetry.decorators import (
    track_duration,
    create_timed_context,
)

__all__ = [
    "setup_metrics",
    "shutdown_telemetry",
    "LATENCY_BUCKETS",
    "track_duration",
    "create_timed_context",
]



logger = logging.getLogger(__name__)

# Histogram bucket boundaries for latency metrics (in seconds)
# These buckets are designed to capture p50, p95, p99 accurately
LATENCY_BUCKETS = [
    0.005, 0.01, 0.025, 0.05, 0.075,
    0.1, 0.25, 0.5, 0.75,
    1.0, 2.5, 5.0, 7.5, 10.0
]

class SafeOTLPMetricExporter:
    """Wrapper that catches all exceptions during export."""
    
    def __init__(self, endpoint: str, timeout: int = 5):
        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            self._exporter = OTLPMetricExporter(endpoint=endpoint, timeout=timeout)
            self._endpoint = endpoint
        except Exception as e:
            logger.warning(f"Failed to create OTLP metric exporter: {e}")
            self._exporter = None
    
    @property
    def _preferred_temporality(self):
        """Delegate to underlying exporter."""
        if self._exporter:
            return self._exporter._preferred_temporality
        return {}
    
    @property
    def _preferred_aggregation(self):
        """Delegate to underlying exporter."""
        if self._exporter:
            return self._exporter._preferred_aggregation
        return {}
    
    def export(self, *args, **kwargs):
        """Export with error suppression."""
        if not self._exporter:
            return None
        try:
            return self._exporter.export(*args, **kwargs)
        except Exception:
            # Silently suppress export errors to prevent crashes
            # This can happen during test cleanup when streams are closed
            return None
    
    def shutdown(self, *args, **kwargs):
        """Shutdown with error suppression."""
        if not self._exporter:
            return
        try:
            return self._exporter.shutdown(*args, **kwargs)
        except Exception:
            pass
    
    def force_flush(self, *args, **kwargs):
        """Force flush with error suppression."""
        if not self._exporter:
            return
        try:
            return self._exporter.force_flush(*args, **kwargs)
        except Exception:
            pass


def setup_metrics(
    service_name: str,
    otlp_endpoint: Optional[str] = None,
    enable_metrics: bool = True
) -> None:
    """
    Configures OTel Metrics to send to a collector.
    Will NOT crash even if collector is unavailable - errors are suppressed.
    """
    logger.info("Setting up telemetry...")
    
    try:
        otlp_endpoint = otlp_endpoint or os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", 
            "http://otel-collector:4318"
        )
        
        resource = Resource.create(attributes={SERVICE_NAME: service_name})
        
        # Setup Metrics
        if enable_metrics:
            try:
                readers = []
                
                # Prometheus setup
                if os.getenv("OTEL_PROMETHEUS_ENABLED", "false").lower() == "true":
                    try:
                        from opentelemetry.exporter.prometheus import PrometheusMetricReader
                        from prometheus_client import start_http_server
                        
                        port = int(os.getenv("OTEL_PROMETHEUS_PORT", "9464"))
                        start_http_server(port=port, addr="0.0.0.0")
                        readers.append(PrometheusMetricReader())
                        logger.info(f"Prometheus metrics enabled on port {port}")
                    except Exception as e:
                        logger.warning(f"Prometheus setup failed: {e}")
                
                # OTLP setup with safe wrapper
                if otlp_endpoint:
                    try:
                        safe_exporter = SafeOTLPMetricExporter(
                            endpoint=f"{otlp_endpoint}/v1/metrics",
                            timeout=5
                        )
                        reader = PeriodicExportingMetricReader(
                            safe_exporter,
                            export_interval_millis=60000,
                            export_timeout_millis=5000
                        )
                        readers.append(reader)
                        logger.info(f"OTLP metrics configured for {otlp_endpoint}")
                    except Exception as e:
                        logger.warning(f"OTLP metrics setup failed: {e}")
                        
                views = [
                    View(
                        instrument_name="*duration*",
                        aggregation=ExplicitBucketHistogramAggregation(
                            boundaries=LATENCY_BUCKETS
                        )
                    )
                ]
                # Set meter provider if we have any readers
                if readers:
                    provider = MeterProvider(resource=resource, metric_readers=readers, views=views)
                    metrics.set_meter_provider(provider)
                    logger.info(f"Metrics initialized with {len(readers)} reader(s)")
                else:
                    logger.warning("No metric readers configured")
                    
            except Exception as e:
                logger.warning(f"Metrics setup failed: {e}")
        
        logger.info("Telemetry setup complete")
        
    except Exception as e:
        logger.warning(f"Telemetry initialization failed: {e}")


def shutdown_telemetry():
    """Gracefully shutdown telemetry providers."""
    try:
        provider = metrics.get_meter_provider()
        if hasattr(provider, 'shutdown'):
            provider.shutdown(timeout_millis=1000)
    except Exception:
        pass