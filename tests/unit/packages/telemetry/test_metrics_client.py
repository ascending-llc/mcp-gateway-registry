import pytest
from unittest.mock import patch, MagicMock

from packages.telemetry.metrics_client import (
    OTelMetricsClient,
    create_metrics_client,
    safe_telemetry,
)


@pytest.mark.unit
@pytest.mark.metrics
class TestOTelMetricsClient:
    """Test suite for OTelMetricsClient."""

    @pytest.fixture
    def mock_meter(self):
        """Fixture to mock the OpenTelemetry meter and its instruments."""
        with patch('packages.telemetry.metrics_client.metrics.get_meter') as mock_get_meter:
            meter_instance = MagicMock()
            mock_get_meter.return_value = meter_instance

            meter_instance.create_counter.return_value = MagicMock()
            meter_instance.create_histogram.return_value = MagicMock()

            yield mock_get_meter, meter_instance

    @pytest.fixture
    def sample_config(self):
        """Sample config with common metrics."""
        return {
            "counters": [
                {"name": "auth_requests_total", "description": "Auth attempts", "unit": "1"},
                {"name": "mcp_tool_discovery_total", "description": "Tool discovery", "unit": "1"},
                {"name": "mcp_tool_execution_total", "description": "Tool execution", "unit": "1"},
                {"name": "registry_operations_total", "description": "Registry ops", "unit": "1"},
                {"name": "mcp_server_requests_total", "description": "Server requests", "unit": "1"},
            ],
            "histograms": [
                {"name": "auth_request_duration_seconds", "description": "Auth duration", "unit": "s"},
                {"name": "mcp_tool_discovery_duration_seconds", "description": "Discovery duration", "unit": "s"},
                {"name": "mcp_tool_execution_duration_seconds", "description": "Execution duration", "unit": "s"},
                {"name": "registry_operation_duration_seconds", "description": "Registry duration", "unit": "s"},
            ]
        }

    def test_init_creates_meter(self, mock_meter):
        """Test initialization creates meter with service name."""
        mock_get_meter, meter_instance = mock_meter
        service_name = "test-service"

        OTelMetricsClient(service_name)

        mock_get_meter.assert_called_once_with(f"mcp.{service_name}")

    def test_init_with_config_creates_metrics(self, mock_meter, sample_config):
        """Test initialization with config creates all defined metrics."""
        mock_get_meter, meter_instance = mock_meter

        client = OTelMetricsClient("test-service", config=sample_config)

        # Should create 5 counters from config
        assert meter_instance.create_counter.call_count == 5
        # Should create 4 histograms from config
        assert meter_instance.create_histogram.call_count == 4

        # Verify metrics are registered
        assert "auth_requests_total" in client._counters
        assert "registry_operations_total" in client._counters
        assert "auth_request_duration_seconds" in client._histograms

    def test_init_without_config_creates_empty_registries(self, mock_meter):
        """Test initialization without config creates empty registries."""
        mock_get_meter, meter_instance = mock_meter

        client = OTelMetricsClient("test-service")

        # No metrics created without config
        assert meter_instance.create_counter.call_count == 0
        assert meter_instance.create_histogram.call_count == 0
        assert len(client._counters) == 0
        assert len(client._histograms) == 0

    def test_init_logs_error_on_failure(self, mock_meter):
        """Test initialization logs error when meter creation fails."""
        mock_get_meter, _ = mock_meter
        mock_get_meter.side_effect = Exception("Meter creation failed")

        with patch('packages.telemetry.metrics_client.logger') as mock_logger:
            OTelMetricsClient("test-service")
            mock_logger.error.assert_called_once()

    def test_record_auth_request_success(self, mock_meter, sample_config):
        """Test recording a successful authentication attempt."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        # Mock the counter in the registry
        mock_counter = MagicMock()
        client._counters["auth_requests_total"] = mock_counter

        client.record_auth_request("jwt", success=True)

        expected_attributes = {
            "mechanism": "jwt",
            "status": "success"
        }

        mock_counter.add.assert_called_once_with(1, expected_attributes)

    def test_record_auth_request_failure(self, mock_meter, sample_config):
        """Test recording a failed authentication attempt."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        mock_counter = MagicMock()
        client._counters["auth_requests_total"] = mock_counter

        client.record_auth_request("api_key", success=False)

        expected_attributes = {
            "mechanism": "api_key",
            "status": "failure"
        }

        mock_counter.add.assert_called_once_with(1, expected_attributes)

    def test_record_auth_request_with_duration(self, mock_meter, sample_config):
        """Test recording authentication attempt with duration for latency tracking."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        mock_counter = MagicMock()
        mock_histogram = MagicMock()
        client._counters["auth_requests_total"] = mock_counter
        client._histograms["auth_request_duration_seconds"] = mock_histogram

        client.record_auth_request("jwt", success=True, duration_seconds=0.05)

        expected_attributes = {
            "mechanism": "jwt",
            "status": "success"
        }

        mock_counter.add.assert_called_once_with(1, expected_attributes)
        mock_histogram.record.assert_called_once_with(0.05, expected_attributes)

    def test_record_auth_request_no_op_without_config(self, mock_meter):
        """Test record_auth_request is no-op when metrics not configured."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")  # No config

        # Should not raise, just do nothing
        client.record_auth_request("jwt", success=True, duration_seconds=0.05)

    def test_record_tool_discovery_default(self, mock_meter, sample_config):
        """Test recording tool discovery with default parameters."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        mock_counter = MagicMock()
        client._counters["mcp_tool_discovery_total"] = mock_counter

        client.record_tool_discovery("weather-tool")

        expected_attributes = {
            "tool_name": "weather-tool",
            "source": "registry",
            "status": "success"
        }

        mock_counter.add.assert_called_once_with(1, expected_attributes)

    def test_record_tool_discovery_custom_source(self, mock_meter, sample_config):
        """Test recording tool discovery with custom source."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        mock_counter = MagicMock()
        client._counters["mcp_tool_discovery_total"] = mock_counter

        client.record_tool_discovery("finance-tool", source="user-defined")

        expected_attributes = {
            "tool_name": "finance-tool",
            "source": "user-defined",
            "status": "success"
        }

        mock_counter.add.assert_called_once_with(1, expected_attributes)

    def test_record_tool_discovery_failure_with_duration(self, mock_meter, sample_config):
        """Test recording failed tool discovery with duration."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        mock_counter = MagicMock()
        mock_histogram = MagicMock()
        client._counters["mcp_tool_discovery_total"] = mock_counter
        client._histograms["mcp_tool_discovery_duration_seconds"] = mock_histogram

        client.record_tool_discovery(
            "unknown-tool",
            source="search",
            success=False,
            duration_seconds=0.15
        )

        expected_attributes = {
            "tool_name": "unknown-tool",
            "source": "search",
            "status": "failure"
        }

        mock_counter.add.assert_called_once_with(1, expected_attributes)
        mock_histogram.record.assert_called_once_with(0.15, expected_attributes)

    def test_record_tool_execution_success(self, mock_meter, sample_config):
        """Test recording a successful tool execution."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        mock_counter = MagicMock()
        client._counters["mcp_tool_execution_total"] = mock_counter

        client.record_tool_execution(
            tool_name="calculator",
            server_name="math-server",
            success=True
        )

        expected_attributes = {
            "tool_name": "calculator",
            "server_name": "math-server",
            "status": "success",
            "method": "UNKNOWN"
        }

        mock_counter.add.assert_called_once_with(1, expected_attributes)

    def test_record_tool_execution_failure_with_duration(self, mock_meter, sample_config):
        """Test recording a failed tool execution with duration and method."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        mock_counter = MagicMock()
        mock_histogram = MagicMock()
        client._counters["mcp_tool_execution_total"] = mock_counter
        client._histograms["mcp_tool_execution_duration_seconds"] = mock_histogram

        client.record_tool_execution(
            tool_name="weather",
            server_name="weather-server",
            success=False,
            duration_seconds=1.5,
            method="POST"
        )

        expected_attributes = {
            "tool_name": "weather",
            "server_name": "weather-server",
            "status": "failure",
            "method": "POST"
        }

        mock_counter.add.assert_called_once_with(1, expected_attributes)
        mock_histogram.record.assert_called_once_with(1.5, expected_attributes)

    def test_record_registry_operation_success(self, mock_meter, sample_config):
        """Test recording a successful registry operation."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        mock_counter = MagicMock()
        client._counters["registry_operations_total"] = mock_counter

        client.record_registry_operation(
            operation="read",
            resource_type="server",
            success=True
        )

        expected_attributes = {
            "operation": "read",
            "resource_type": "server",
            "status": "success"
        }

        mock_counter.add.assert_called_once_with(1, expected_attributes)

    def test_record_registry_operation_with_duration(self, mock_meter, sample_config):
        """Test recording registry operation with duration for latency tracking."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        mock_counter = MagicMock()
        mock_histogram = MagicMock()
        client._counters["registry_operations_total"] = mock_counter
        client._histograms["registry_operation_duration_seconds"] = mock_histogram

        client.record_registry_operation(
            operation="search",
            resource_type="tool",
            success=True,
            duration_seconds=0.08
        )

        expected_attributes = {
            "operation": "search",
            "resource_type": "tool",
            "status": "success"
        }

        mock_counter.add.assert_called_once_with(1, expected_attributes)
        mock_histogram.record.assert_called_once_with(0.08, expected_attributes)

    def test_record_registry_operation_failure(self, mock_meter, sample_config):
        """Test recording a failed registry operation."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        mock_counter = MagicMock()
        mock_histogram = MagicMock()
        client._counters["registry_operations_total"] = mock_counter
        client._histograms["registry_operation_duration_seconds"] = mock_histogram

        client.record_registry_operation(
            operation="delete",
            resource_type="server",
            success=False,
            duration_seconds=0.02
        )

        expected_attributes = {
            "operation": "delete",
            "resource_type": "server",
            "status": "failure"
        }

        mock_counter.add.assert_called_once_with(1, expected_attributes)
        mock_histogram.record.assert_called_once_with(0.02, expected_attributes)

    def test_record_server_request(self, mock_meter, sample_config):
        """Test recording a server request."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service", config=sample_config)

        mock_counter = MagicMock()
        client._counters["mcp_server_requests_total"] = mock_counter

        client.record_server_request("weather-server")

        expected_attributes = {"server_name": "weather-server"}
        mock_counter.add.assert_called_once_with(1, expected_attributes)


@pytest.mark.unit
@pytest.mark.metrics
class TestSafeTelemetryDecorator:
    """Test suite for safe_telemetry decorator."""

    def test_safe_telemetry_swallows_exception(self):
        """Test that safe_telemetry decorator swallows exceptions."""
        @safe_telemetry
        def failing_function():
            raise ValueError("Test error")

        # Should not raise, returns None
        result = failing_function()
        assert result is None

    def test_safe_telemetry_returns_value_on_success(self):
        """Test that safe_telemetry returns value when no exception."""
        @safe_telemetry
        def successful_function():
            return "success"

        result = successful_function()
        assert result == "success"

    def test_safe_telemetry_logs_warning_on_exception(self):
        """Test that safe_telemetry logs warning when exception occurs."""
        @safe_telemetry
        def failing_function():
            raise ValueError("Test error")

        with patch('packages.telemetry.metrics_client.logger') as mock_logger:
            failing_function()
            mock_logger.warning.assert_called_once()
            assert "Test error" in str(mock_logger.warning.call_args)

    def test_safe_telemetry_preserves_function_metadata(self):
        """Test that safe_telemetry preserves function name and docstring."""
        @safe_telemetry
        def my_function():
            """My docstring."""
            pass

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."


@pytest.mark.unit
@pytest.mark.metrics
class TestCreateMetricsClient:
    """Test suite for create_metrics_client factory function."""

    def test_create_metrics_client_returns_client(self):
        """Test that factory function returns OTelMetricsClient instance."""
        with patch('packages.telemetry.metrics_client.metrics.get_meter'):
            client = create_metrics_client("api")
            assert isinstance(client, OTelMetricsClient)
            assert client.service_name == "api"

    def test_create_metrics_client_uses_service_name(self):
        """Test that factory function passes service_name to client."""
        with patch('packages.telemetry.metrics_client.metrics.get_meter') as mock_get_meter:
            create_metrics_client("worker")
            mock_get_meter.assert_called_once_with("mcp.worker")

    def test_create_metrics_client_with_config(self):
        """Test that factory function accepts config parameter."""
        config = {
            "counters": [
                {"name": "custom_counter", "description": "Custom counter", "unit": "1"}
            ],
            "histograms": [
                {"name": "custom_histogram", "description": "Custom histogram", "unit": "s"}
            ]
        }
        with patch('packages.telemetry.metrics_client.metrics.get_meter') as mock_get_meter:
            meter_instance = MagicMock()
            mock_get_meter.return_value = meter_instance
            meter_instance.create_counter.return_value = MagicMock()
            meter_instance.create_histogram.return_value = MagicMock()

            client = create_metrics_client("api", config=config)

            assert isinstance(client, OTelMetricsClient)
            # Should have created the custom counter and histogram
            assert "custom_counter" in client._counters
            assert "custom_histogram" in client._histograms


@pytest.mark.unit
@pytest.mark.metrics
class TestGenericMetricMethods:
    """Test suite for generic metric creation and recording methods."""

    @pytest.fixture
    def mock_meter(self):
        """Fixture to mock the OpenTelemetry meter and its instruments."""
        with patch('packages.telemetry.metrics_client.metrics.get_meter') as mock_get_meter:
            meter_instance = MagicMock()
            mock_get_meter.return_value = meter_instance

            meter_instance.create_counter.return_value = MagicMock()
            meter_instance.create_histogram.return_value = MagicMock()

            yield mock_get_meter, meter_instance

    def test_create_counter_registers_metric(self, mock_meter):
        """Test that create_counter registers a new counter."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        counter = client.create_counter(
            name="test_counter",
            description="Test counter",
            unit="1"
        )

        assert counter is not None
        assert "test_counter" in client._counters

    def test_create_counter_returns_existing(self, mock_meter):
        """Test that create_counter returns existing counter if already registered."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        counter1 = client.create_counter("test_counter", "Test counter")
        counter2 = client.create_counter("test_counter", "Different description")

        assert counter1 is counter2

    def test_create_histogram_registers_metric(self, mock_meter):
        """Test that create_histogram registers a new histogram."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        histogram = client.create_histogram(
            name="test_histogram",
            description="Test histogram",
            unit="s"
        )

        assert histogram is not None
        assert "test_histogram" in client._histograms

    def test_create_histogram_returns_existing(self, mock_meter):
        """Test that create_histogram returns existing histogram if already registered."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        histogram1 = client.create_histogram("test_histogram", "Test histogram")
        histogram2 = client.create_histogram("test_histogram", "Different description")

        assert histogram1 is histogram2

    def test_record_counter_adds_value(self, mock_meter):
        """Test that record_counter adds value to registered counter."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        mock_counter = MagicMock()
        client._counters["my_counter"] = mock_counter

        client.record_counter("my_counter", 5.0, {"label": "value"})

        mock_counter.add.assert_called_once_with(5.0, {"label": "value"})

    def test_record_counter_warns_for_unregistered(self, mock_meter):
        """Test that record_counter warns when counter not registered."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        with patch('packages.telemetry.metrics_client.logger') as mock_logger:
            client.record_counter("nonexistent_counter", 1.0)
            mock_logger.warning.assert_called_once()
            assert "nonexistent_counter" in str(mock_logger.warning.call_args)

    def test_record_histogram_records_value(self, mock_meter):
        """Test that record_histogram records value to registered histogram."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        mock_histogram = MagicMock()
        client._histograms["my_histogram"] = mock_histogram

        client.record_histogram("my_histogram", 0.5, {"label": "value"})

        mock_histogram.record.assert_called_once_with(0.5, {"label": "value"})

    def test_record_histogram_warns_for_unregistered(self, mock_meter):
        """Test that record_histogram warns when histogram not registered."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        with patch('packages.telemetry.metrics_client.logger') as mock_logger:
            client.record_histogram("nonexistent_histogram", 1.0)
            mock_logger.warning.assert_called_once()
            assert "nonexistent_histogram" in str(mock_logger.warning.call_args)

    def test_record_metric_detects_counter(self, mock_meter):
        """Test that record_metric auto-detects and records to counter."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        mock_counter = MagicMock()
        client._counters["auto_counter"] = mock_counter

        client.record_metric("auto_counter", 3.0, {"key": "val"})

        mock_counter.add.assert_called_once_with(3.0, {"key": "val"})

    def test_record_metric_detects_histogram(self, mock_meter):
        """Test that record_metric auto-detects and records to histogram."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        mock_histogram = MagicMock()
        client._histograms["auto_histogram"] = mock_histogram

        client.record_metric("auto_histogram", 0.25, {"key": "val"})

        mock_histogram.record.assert_called_once_with(0.25, {"key": "val"})

    def test_record_metric_warns_for_unregistered(self, mock_meter):
        """Test that record_metric warns when metric not registered."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        with patch('packages.telemetry.metrics_client.logger') as mock_logger:
            client.record_metric("unknown_metric", 1.0)
            mock_logger.warning.assert_called_once()
            assert "unknown_metric" in str(mock_logger.warning.call_args)

    def test_get_counter_returns_registered(self, mock_meter):
        """Test that get_counter returns registered counter."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        mock_counter = MagicMock()
        client._counters["my_counter"] = mock_counter

        result = client.get_counter("my_counter")
        assert result is mock_counter

    def test_get_counter_returns_none_for_unregistered(self, mock_meter):
        """Test that get_counter returns None for unregistered counter."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        result = client.get_counter("nonexistent")
        assert result is None

    def test_get_histogram_returns_registered(self, mock_meter):
        """Test that get_histogram returns registered histogram."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        mock_histogram = MagicMock()
        client._histograms["my_histogram"] = mock_histogram

        result = client.get_histogram("my_histogram")
        assert result is mock_histogram

    def test_get_histogram_returns_none_for_unregistered(self, mock_meter):
        """Test that get_histogram returns None for unregistered histogram."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")

        result = client.get_histogram("nonexistent")
        assert result is None

    def test_init_from_config(self, mock_meter):
        """Test that _init_from_config creates metrics from config dict."""
        _, meter_instance = mock_meter

        config = {
            "counters": [
                {"name": "config_counter_1", "description": "Counter 1", "unit": "1"},
                {"name": "config_counter_2", "description": "Counter 2"},
            ],
            "histograms": [
                {"name": "config_histogram_1", "description": "Histogram 1", "unit": "ms"},
            ]
        }

        client = OTelMetricsClient("test-service", config=config)

        assert "config_counter_1" in client._counters
        assert "config_counter_2" in client._counters
        assert "config_histogram_1" in client._histograms

    def test_capture_flag_true_creates_metric(self, mock_meter):
        """Test that capture=true (default) creates the metric."""
        _, meter_instance = mock_meter

        config = {
            "counters": [
                {"name": "enabled_counter", "description": "Enabled", "capture": True},
            ],
            "histograms": [
                {"name": "enabled_histogram", "description": "Enabled", "capture": True},
            ]
        }

        client = OTelMetricsClient("test-service", config=config)

        assert "enabled_counter" in client._counters
        assert "enabled_histogram" in client._histograms

    def test_capture_flag_false_skips_metric(self, mock_meter):
        """Test that capture=false skips the metric registration."""
        _, meter_instance = mock_meter

        config = {
            "counters": [
                {"name": "disabled_counter", "description": "Disabled", "capture": False},
                {"name": "enabled_counter", "description": "Enabled", "capture": True},
            ],
            "histograms": [
                {"name": "disabled_histogram", "description": "Disabled", "capture": False},
                {"name": "enabled_histogram", "description": "Enabled"},  # Default is true
            ]
        }

        client = OTelMetricsClient("test-service", config=config)

        # Disabled metrics should not be registered
        assert "disabled_counter" not in client._counters
        assert "disabled_histogram" not in client._histograms

        # Enabled metrics should be registered
        assert "enabled_counter" in client._counters
        assert "enabled_histogram" in client._histograms

    def test_capture_flag_defaults_to_true(self, mock_meter):
        """Test that missing capture flag defaults to true."""
        _, meter_instance = mock_meter

        config = {
            "counters": [
                {"name": "no_capture_flag", "description": "No flag specified"},
            ]
        }

        client = OTelMetricsClient("test-service", config=config)

        # Should be registered since capture defaults to true
        assert "no_capture_flag" in client._counters
