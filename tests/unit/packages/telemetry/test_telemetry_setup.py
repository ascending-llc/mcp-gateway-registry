import pytest
import os
from unittest.mock import patch, MagicMock

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
        module_path = "packages.telemetry"

        with patch(f"{module_path}.metrics") as mock_metrics, \
             patch(f"{module_path}.Resource") as mock_resource, \
             patch(f"{module_path}.MeterProvider") as mock_meter_provider, \
             patch(f"{module_path}.PeriodicExportingMetricReader") as mock_periodic_reader, \
             patch(f"{module_path}.SafeOTLPMetricExporter") as mock_safe_exporter:

            mock_resource_instance = MagicMock()
            mock_resource.create.return_value = mock_resource_instance

            mock_safe_exporter_instance = MagicMock()
            mock_safe_exporter.return_value = mock_safe_exporter_instance

            yield {
                "metrics": mock_metrics,
                "resource": mock_resource,
                "meter_provider": mock_meter_provider,
                "periodic_reader": mock_periodic_reader,
                "safe_exporter": mock_safe_exporter,
            }

    def test_setup_metrics_defaults(self, mock_otel_deps):
        """Test setup with default arguments (metrics=True)."""
        service_name = "test-service"
        otlp_endpoint = "http://localhost:4318"

        setup_metrics(service_name, otlp_endpoint=otlp_endpoint)

        mock_otel_deps["resource"].create.assert_called_once()
        _, kwargs = mock_otel_deps["resource"].create.call_args
        assert kwargs["attributes"]["service.name"] == service_name

        mock_otel_deps["safe_exporter"].assert_called_once_with(
            endpoint=f"{otlp_endpoint}/v1/metrics",
            timeout=5
        )
        mock_otel_deps["metrics"].set_meter_provider.assert_called_once()

    def test_setup_metrics_disabled(self, mock_otel_deps):
        """Test setup with metrics disabled."""
        setup_metrics("test-service", enable_metrics=False)

        mock_otel_deps["metrics"].set_meter_provider.assert_not_called()

    def test_setup_prometheus_enabled(self, mock_otel_deps):
        """Test that Prometheus reader is added when env var is set."""
        with patch.dict(os.environ, {"OTEL_PROMETHEUS_ENABLED": "true"}), \
             patch(
                 "opentelemetry.exporter.prometheus.PrometheusMetricReader"
             ) as mock_prom_reader, \
             patch("prometheus_client.start_http_server") as mock_start_server:

            setup_metrics("test-service")

            mock_start_server.assert_called_once_with(port=9464, addr="0.0.0.0")

            mock_otel_deps["meter_provider"].assert_called_once()

    def test_setup_no_endpoint_env_fallback(self, mock_otel_deps):
        """Test that it falls back to env var if no endpoint provided."""
        env_endpoint = "http://env-collector:4318"

        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": env_endpoint}):
            setup_metrics("test-service", otlp_endpoint=None)

            mock_otel_deps["safe_exporter"].assert_called_with(
                endpoint=f"{env_endpoint}/v1/metrics",
                timeout=5
            )

    def test_setup_handles_initialization_failure(self, mock_otel_deps):
        """Test that initialization failure is caught and logged."""
        mock_otel_deps["meter_provider"].side_effect = Exception("Init Failed")

        # Should not raise - errors are suppressed
        setup_metrics("test-service", enable_metrics=True)

        # set_meter_provider should not be called since MeterProvider failed
        mock_otel_deps["metrics"].set_meter_provider.assert_not_called()


@pytest.mark.unit
@pytest.mark.telemetry
class TestSafeOTLPMetricExporter:
    """Test suite for SafeOTLPMetricExporter wrapper."""

    def test_safe_exporter_suppresses_export_errors(self):
        """Test that export errors are suppressed."""
        from packages.telemetry import SafeOTLPMetricExporter

        with patch(
            "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter"
        ) as mock_exporter_class:
            mock_exporter = MagicMock()
            mock_exporter.export.side_effect = Exception("Export failed")
            mock_exporter_class.return_value = mock_exporter

            safe_exporter = SafeOTLPMetricExporter(
                endpoint="http://localhost:4318/v1/metrics"
            )

            # Should not raise
            result = safe_exporter.export(MagicMock())
            assert result is None

    def test_safe_exporter_returns_value_on_success(self):
        """Test that export returns value when successful."""
        from packages.telemetry import SafeOTLPMetricExporter

        with patch(
            "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter"
        ) as mock_exporter_class:
            mock_exporter = MagicMock()
            mock_exporter.export.return_value = "success"
            mock_exporter_class.return_value = mock_exporter

            safe_exporter = SafeOTLPMetricExporter(
                endpoint="http://localhost:4318/v1/metrics"
            )

            result = safe_exporter.export(MagicMock())
            assert result == "success"

    def test_safe_exporter_handles_creation_failure(self):
        """Test that exporter creation failure is handled gracefully."""
        from packages.telemetry import SafeOTLPMetricExporter

        with patch(
            "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter"
        ) as mock_exporter_class:
            mock_exporter_class.side_effect = Exception("Connection refused")

            safe_exporter = SafeOTLPMetricExporter(
                endpoint="http://localhost:4318/v1/metrics"
            )

            # Should not raise, and export should be a no-op
            result = safe_exporter.export(MagicMock())
            assert result is None

    def test_safe_exporter_shutdown_suppresses_errors(self):
        """Test that shutdown errors are suppressed."""
        from packages.telemetry import SafeOTLPMetricExporter

        with patch(
            "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter"
        ) as mock_exporter_class:
            mock_exporter = MagicMock()
            mock_exporter.shutdown.side_effect = Exception("Shutdown failed")
            mock_exporter_class.return_value = mock_exporter

            safe_exporter = SafeOTLPMetricExporter(
                endpoint="http://localhost:4318/v1/metrics"
            )

            # Should not raise
            safe_exporter.shutdown()


@pytest.mark.unit
@pytest.mark.telemetry
class TestShutdownTelemetry:
    """Test suite for shutdown_telemetry function."""

    def test_shutdown_telemetry_calls_provider_shutdown(self):
        """Test that shutdown calls the meter provider's shutdown method."""
        from packages.telemetry import shutdown_telemetry

        with patch("packages.telemetry.metrics.get_meter_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_get_provider.return_value = mock_provider

            shutdown_telemetry()

            mock_provider.shutdown.assert_called_once_with(timeout_millis=1000)

    def test_shutdown_telemetry_handles_missing_shutdown(self):
        """Test that shutdown handles providers without shutdown method."""
        from packages.telemetry import shutdown_telemetry

        with patch("packages.telemetry.metrics.get_meter_provider") as mock_get_provider:
            mock_provider = MagicMock(spec=[])  # No shutdown method
            mock_get_provider.return_value = mock_provider

            # Should not raise
            shutdown_telemetry()

    def test_shutdown_telemetry_suppresses_errors(self):
        """Test that shutdown errors are suppressed."""
        from packages.telemetry import shutdown_telemetry

        with patch("packages.telemetry.metrics.get_meter_provider") as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.shutdown.side_effect = Exception("Shutdown error")
            mock_get_provider.return_value = mock_provider

            # Should not raise
            shutdown_telemetry()
