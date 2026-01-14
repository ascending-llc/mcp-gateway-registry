import pytest
import os
from unittest.mock import patch, MagicMock, call

from packages.telemetry import setup_metrics 

@pytest.mark.unit
@pytest.mark.telemetry
class TestTelemetrySetup:
    """Test suite for OpenTelemetry setup configuration."""

    @pytest.fixture
    def mock_otel_deps(self):
        """
        Fixture to mock all OpenTelemetry dependencies to prevent actual
        network calls, port binding, or global state modification.
        """
        # We patch the module where these are IMPORTED, not where they are defined.
        module_path = "packages.telemetry"
        
        with patch(f"{module_path}.metrics") as mock_metrics, \
             patch(f"{module_path}.Resource") as mock_resource, \
             patch(f"{module_path}.MeterProvider") as mock_meter_provider, \
             patch(f"{module_path}.PeriodicExportingMetricReader") as mock_periodic_reader, \
             patch(f"{module_path}.OTLPMetricExporter") as mock_otlp_metric_exporter, \
             patch(f"{module_path}.set_logger_provider") as mock_set_logger_provider, \
             patch(f"{module_path}.LoggerProvider") as mock_logger_provider, \
             patch(f"{module_path}.BatchLogRecordProcessor") as mock_batch_processor, \
             patch(f"{module_path}.OTLPLogExporter") as mock_otlp_log_exporter, \
             patch(f"{module_path}.LoggingHandler") as mock_logging_handler, \
             patch("logging.getLogger") as mock_get_logger:
            
            mock_resource_instance = MagicMock()
            mock_resource.create.return_value = mock_resource_instance
            
            mock_logger_provider_instance = MagicMock()
            mock_logger_provider.return_value = mock_logger_provider_instance
            
            mock_root_logger = MagicMock()
            mock_get_logger.return_value = mock_root_logger

            yield {
                "metrics": mock_metrics,
                "resource": mock_resource,
                "meter_provider": mock_meter_provider,
                "periodic_reader": mock_periodic_reader,
                "otlp_metric_exporter": mock_otlp_metric_exporter,
                "set_logger_provider": mock_set_logger_provider,
                "logger_provider": mock_logger_provider,
                "batch_processor": mock_batch_processor,
                "otlp_log_exporter": mock_otlp_log_exporter,
                "logging_handler": mock_logging_handler,
                "get_logger": mock_get_logger,
                "root_logger": mock_root_logger
            }
    def test_setup_metrics_defaults(self, mock_otel_deps):
        """Test setup with default arguments (metrics=True, logs=True)."""
        service_name = "test-service"
        otlp_endpoint = "http://localhost:4318"
        
        setup_metrics(service_name, otlp_endpoint=otlp_endpoint)

        mock_otel_deps["resource"].create.assert_called_once()
        _, kwargs = mock_otel_deps["resource"].create.call_args
        assert kwargs["attributes"]["service.name"] == service_name
        
        mock_otel_deps["otlp_metric_exporter"].assert_called_once_with(
            endpoint=f"{otlp_endpoint}/v1/metrics"
        )
        mock_otel_deps["metrics"].set_meter_provider.assert_called_once()
        mock_otel_deps["otlp_log_exporter"].assert_called_once_with(
            endpoint=f"{otlp_endpoint}/v1/logs"
        )
        mock_otel_deps["set_logger_provider"].assert_called_once()
        
        otel_handler_instance = mock_otel_deps["logging_handler"].return_value
        
        mock_otel_deps["root_logger"].addHandler.assert_any_call(otel_handler_instance)
        
    def test_setup_metrics_disabled(self, mock_otel_deps):
        """Test setup with metrics disabled."""
        setup_metrics("test-service", enable_metrics=False, enable_logs=True)
        
        mock_otel_deps["metrics"].set_meter_provider.assert_not_called()
        
        mock_otel_deps["set_logger_provider"].assert_called_once()

    def test_setup_logs_disabled(self, mock_otel_deps):
        """Test setup with logs disabled."""
        setup_metrics("test-service", enable_metrics=True, enable_logs=False)
        
        mock_otel_deps["metrics"].set_meter_provider.assert_called_once()
        
        mock_otel_deps["set_logger_provider"].assert_not_called()

    def test_setup_prometheus_enabled(self, mock_otel_deps):
        """Test that Prometheus reader is added when env var is set."""
        with patch.dict(os.environ, {"OTEL_PROMETHEUS_ENABLED": "true"}), \
             patch("packages.telemetry.PrometheusMetricReader") as mock_prom_reader, \
             patch("prometheus_client.start_http_server") as mock_start_server:
            
            setup_metrics("test-service")
            
            mock_start_server.assert_called_once_with(port=9464, addr="0.0.0.0")
            
            mock_otel_deps["meter_provider"].assert_called_once()

    def test_setup_no_endpoint_env_fallback(self, mock_otel_deps):
        """Test that it falls back to env var if no endpoint provided."""
        env_endpoint = "http://env-collector:4318"
        
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": env_endpoint}):
            setup_metrics("test-service", otlp_endpoint=None)
            
            mock_otel_deps["otlp_metric_exporter"].assert_called_with(
                endpoint=f"{env_endpoint}/v1/metrics"
            )

    def test_logging_initialization_failure(self, mock_otel_deps):
        """Test that logging initialization failure is caught and logged."""
        mock_otel_deps["logger_provider"].side_effect = Exception("Log Init Failed")
        
        setup_metrics("test-service", enable_logs=True)
        
        mock_otel_deps["set_logger_provider"].assert_not_called()