import os
import logging
from opentelemetry import metrics, trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

logger = logging.getLogger(__name__)

def setup_metrics(
    service_name: str,
    otlp_endpoint: str = None,  # e.g., "http://otel-collector:4318"
    enable_metrics: bool = True,
    enable_logs: bool = True
) -> None:
    """
    Configures OTel Metrics AND Logs to send to a collector.
    Safely handles errors during setup to prevent application crash.
    """
    logger.info("Setting up telemetry...")
    try:
        otlp_endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
        resource = Resource.create(attributes={SERVICE_NAME: service_name})
        
        if enable_metrics:
            try:
                readers = []

                if os.getenv("OTEL_PROMETHEUS_ENABLED", "false").lower() == "true":
                     from prometheus_client import start_http_server
                     start_http_server(port=9464, addr="0.0.0.0")
                     readers.append(PrometheusMetricReader())


                if otlp_endpoint:
                    metric_exporter = OTLPMetricExporter(endpoint=f"{otlp_endpoint}/v1/metrics")
                    readers.append(PeriodicExportingMetricReader(metric_exporter))

                provider = MeterProvider(resource=resource, metric_readers=readers)
                metrics.set_meter_provider(provider)
                logger.info(f"OTel Metrics initialized. Forwarding to {otlp_endpoint}")
            except Exception as e:
                logger.error(f"Failed to initialize OTel Metrics, skipping: {e}")

        if enable_logs and otlp_endpoint:
            try:
                logger_provider = LoggerProvider(resource=resource)
                set_logger_provider(logger_provider)

                log_exporter = OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs")
                
                logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
                
                handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
                
                logging.getLogger().addHandler(handler)
                
                logger.info(f"OTel Logging initialized. Forwarding to {otlp_endpoint}")
                
            except Exception as e:
                logger.error(f"Failed to initialize OTel Logging, skipping: {e}")

    except Exception as e:
        logger.error(f"Failed to setup telemetry, skipping: {e}")