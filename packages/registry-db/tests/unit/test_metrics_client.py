from unittest.mock import MagicMock, patch

from registry_db.telemetry.metrics_client import OTelMetricsClient, create_metrics_client


def test_metrics_client_instantiation():
    """Test that OTelMetricsClient can be instantiated with service name."""
    with patch("opentelemetry.metrics.get_meter") as mock_get_meter:
        client = OTelMetricsClient("test-service")

        mock_get_meter.assert_called_once_with("mcp.test-service")
        assert client.service_name == "test-service"
        assert client._counters == {}
        assert client._histograms == {}


def test_metrics_client_with_config():
    """Test that OTelMetricsClient initializes metrics from config."""
    config = {
        "counters": [{"name": "requests_total", "description": "Total requests", "unit": "1", "capture": True}],
        "histograms": [
            {"name": "request_duration_seconds", "description": "Request duration", "unit": "s", "capture": True}
        ],
    }

    with patch("opentelemetry.metrics.get_meter") as mock_get_meter:
        mock_meter = MagicMock()
        mock_get_meter.return_value = mock_meter

        client = OTelMetricsClient("test-service", config=config)

        # Verify counter was created eagerly
        mock_meter.create_counter.assert_called_once_with(name="requests_total", description="Total requests", unit="1")

        # Histogram is deferred - not created at init time
        mock_meter.create_histogram.assert_not_called()
        assert "request_duration_seconds" in client._histogram_configs


def test_metrics_client_skips_disabled_metrics():
    """Test that metrics with capture=false are skipped."""
    config = {
        "counters": [
            {"name": "enabled_counter", "description": "Enabled", "capture": True},
            {"name": "disabled_counter", "description": "Disabled", "capture": False},
        ],
        "histograms": [
            {"name": "enabled_histogram", "description": "Enabled", "capture": True},
            {"name": "disabled_histogram", "description": "Disabled", "capture": False},
        ],
    }

    with patch("opentelemetry.metrics.get_meter") as mock_get_meter:
        mock_meter = MagicMock()
        mock_get_meter.return_value = mock_meter

        client = OTelMetricsClient("test-service", config=config)

        # Only enabled counter should be created eagerly
        assert mock_meter.create_counter.call_count == 1
        # Histograms are deferred - none created at init
        assert mock_meter.create_histogram.call_count == 0

        # Verify correct counter was created
        mock_meter.create_counter.assert_called_with(name="enabled_counter", description="Enabled", unit="1")
        # Enabled histogram should be deferred, disabled should be skipped
        assert "enabled_histogram" in client._histogram_configs
        assert "disabled_histogram" not in client._histogram_configs


def test_record_counter():
    """Test recording a counter metric."""
    with patch("opentelemetry.metrics.get_meter") as mock_get_meter:
        mock_meter = MagicMock()
        mock_counter = MagicMock()
        mock_meter.create_counter.return_value = mock_counter
        mock_get_meter.return_value = mock_meter

        client = OTelMetricsClient("test-service")
        client.create_counter("test_counter", "Test counter")
        client.record_counter("test_counter", 1, {"label": "value"})

        mock_counter.add.assert_called_with(1, {"label": "value"})


def test_record_histogram():
    """Test recording a histogram metric."""
    with patch("opentelemetry.metrics.get_meter") as mock_get_meter:
        mock_meter = MagicMock()
        mock_histogram = MagicMock()
        mock_meter.create_histogram.return_value = mock_histogram
        mock_get_meter.return_value = mock_meter

        client = OTelMetricsClient("test-service")
        client.create_histogram("test_histogram", "Test histogram")
        client.record_histogram("test_histogram", 0.5, {"endpoint": "/api"})

        mock_histogram.record.assert_called_with(0.5, {"endpoint": "/api"})


def test_record_unregistered_metric_logs_warning():
    """Test that recording an unregistered metric logs a warning."""
    with patch("opentelemetry.metrics.get_meter"), patch("registry_db.telemetry.metrics_client.logger") as mock_logger:
        client = OTelMetricsClient("test-service")
        client.record_counter("nonexistent_counter", 1)

        mock_logger.warning.assert_called_with("Counter 'nonexistent_counter' not registered")


def test_create_metrics_client_factory():
    """Test the create_metrics_client factory function."""
    config = {"counters": [{"name": "test_counter", "description": "Test"}]}

    with patch("opentelemetry.metrics.get_meter") as mock_get_meter:
        mock_meter = MagicMock()
        mock_get_meter.return_value = mock_meter

        client = create_metrics_client("my-service", config=config)

        assert isinstance(client, OTelMetricsClient)
        assert client.service_name == "my-service"
        mock_get_meter.assert_called_with("mcp.my-service")
