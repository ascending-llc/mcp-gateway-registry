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

    def test_init_creates_instruments(self, mock_meter):
        """Test initialization creates all required metric instruments."""
        mock_get_meter, meter_instance = mock_meter
        service_name = "test-service"

        OTelMetricsClient(service_name)

        mock_get_meter.assert_called_once_with(f"mcp.{service_name}")

        # 6 counters: http_requests, auth_requests, tool_discovery,
        # tool_execution, registry_operations, server_requests
        assert meter_instance.create_counter.call_count == 6

        meter_instance.create_counter.assert_any_call(
            name="http_requests_total",
            description="Total number of HTTP requests",
            unit="1"
        )
        meter_instance.create_counter.assert_any_call(
            name="auth_requests_total",
            description="Total number of authentication attempts",
            unit="1"
        )
        meter_instance.create_counter.assert_any_call(
            name="mcp_tool_discovery_total",
            description="Total number of tool discovery operations",
            unit="1"
        )
        meter_instance.create_counter.assert_any_call(
            name="mcp_tool_execution_total",
            description="Total number of tool executions",
            unit="1"
        )
        meter_instance.create_counter.assert_any_call(
            name="registry_operations_total",
            description="Total number of registry operations",
            unit="1"
        )
        meter_instance.create_counter.assert_any_call(
            name="mcp_server_requests_total",
            description="Total number of requests to MCP servers",
            unit="1"
        )

        # 5 histograms: http_duration, auth_duration, tool_discovery_duration,
        # tool_execution_duration, registry_operation_duration
        assert meter_instance.create_histogram.call_count == 5

        meter_instance.create_histogram.assert_any_call(
            name="http_request_duration_seconds",
            description="HTTP request duration in seconds",
            unit="s"
        )
        meter_instance.create_histogram.assert_any_call(
            name="auth_request_duration_seconds",
            description="Authentication request duration in seconds for p50/p95/p99",
            unit="s"
        )
        meter_instance.create_histogram.assert_any_call(
            name="mcp_tool_discovery_duration_seconds",
            description="Tool discovery latency in seconds for p50/p95/p99",
            unit="s"
        )
        meter_instance.create_histogram.assert_any_call(
            name="mcp_tool_execution_duration_seconds",
            description="Tool execution duration in seconds for p50/p95/p99",
            unit="s"
        )
        meter_instance.create_histogram.assert_any_call(
            name="registry_operation_duration_seconds",
            description="Registry operation latency in seconds for p50/p95/p99",
            unit="s"
        )

    def test_init_logs_error_on_failure(self, mock_meter):
        """Test initialization logs error when meter creation fails."""
        mock_get_meter, _ = mock_meter
        mock_get_meter.side_effect = Exception("Meter creation failed")

        with patch('packages.telemetry.metrics_client.logger') as mock_logger:
            OTelMetricsClient("test-service")
            mock_logger.error.assert_called_once()

    def test_record_auth_request_success(self, mock_meter):
        """Test recording a successful authentication attempt."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.auth_requests = MagicMock()
        client.auth_duration = MagicMock()

        client.record_auth_request("jwt", success=True)

        expected_attributes = {
            "mechanism": "jwt",
            "status": "success"
        }

        client.auth_requests.add.assert_called_once_with(1, expected_attributes)
        client.auth_duration.record.assert_not_called()

    def test_record_auth_request_failure(self, mock_meter):
        """Test recording a failed authentication attempt."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.auth_requests = MagicMock()
        client.auth_duration = MagicMock()

        client.record_auth_request("api_key", success=False)

        expected_attributes = {
            "mechanism": "api_key",
            "status": "failure"
        }

        client.auth_requests.add.assert_called_once_with(1, expected_attributes)

    def test_record_auth_request_with_duration(self, mock_meter):
        """Test recording authentication attempt with duration for latency tracking."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.auth_requests = MagicMock()
        client.auth_duration = MagicMock()

        client.record_auth_request("jwt", success=True, duration_seconds=0.05)

        expected_attributes = {
            "mechanism": "jwt",
            "status": "success"
        }

        client.auth_requests.add.assert_called_once_with(1, expected_attributes)
        client.auth_duration.record.assert_called_once_with(0.05, expected_attributes)

    def test_record_tool_discovery_default(self, mock_meter):
        """Test recording tool discovery with default parameters."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.tool_discovery = MagicMock()
        client.tool_discovery_duration = MagicMock()

        client.record_tool_discovery("weather-tool")

        expected_attributes = {
            "tool_name": "weather-tool",
            "source": "registry",
            "status": "success"
        }

        client.tool_discovery.add.assert_called_once_with(1, expected_attributes)
        client.tool_discovery_duration.record.assert_not_called()

    def test_record_tool_discovery_custom_source(self, mock_meter):
        """Test recording tool discovery with custom source."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.tool_discovery = MagicMock()
        client.tool_discovery_duration = MagicMock()

        client.record_tool_discovery("finance-tool", source="user-defined")

        expected_attributes = {
            "tool_name": "finance-tool",
            "source": "user-defined",
            "status": "success"
        }

        client.tool_discovery.add.assert_called_once_with(1, expected_attributes)

    def test_record_tool_discovery_failure_with_duration(self, mock_meter):
        """Test recording failed tool discovery with duration."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.tool_discovery = MagicMock()
        client.tool_discovery_duration = MagicMock()

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

        client.tool_discovery.add.assert_called_once_with(1, expected_attributes)
        client.tool_discovery_duration.record.assert_called_once_with(
            0.15, expected_attributes
        )

    def test_record_tool_execution_success(self, mock_meter):
        """Test recording a successful tool execution."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.tool_execution = MagicMock()
        client.tool_execution_duration = MagicMock()

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

        client.tool_execution.add.assert_called_once_with(1, expected_attributes)
        client.tool_execution_duration.record.assert_not_called()

    def test_record_tool_execution_failure_with_duration(self, mock_meter):
        """Test recording a failed tool execution with duration and method."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.tool_execution = MagicMock()
        client.tool_execution_duration = MagicMock()

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

        client.tool_execution.add.assert_called_once_with(1, expected_attributes)
        client.tool_execution_duration.record.assert_called_once_with(
            1.5, expected_attributes
        )

    def test_record_registry_operation_success(self, mock_meter):
        """Test recording a successful registry operation."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.registry_operations = MagicMock()
        client.registry_operation_duration = MagicMock()

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

        client.registry_operations.add.assert_called_once_with(1, expected_attributes)
        client.registry_operation_duration.record.assert_not_called()

    def test_record_registry_operation_with_duration(self, mock_meter):
        """Test recording registry operation with duration for latency tracking."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.registry_operations = MagicMock()
        client.registry_operation_duration = MagicMock()

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

        client.registry_operations.add.assert_called_once_with(1, expected_attributes)
        client.registry_operation_duration.record.assert_called_once_with(
            0.08, expected_attributes
        )

    def test_record_registry_operation_failure(self, mock_meter):
        """Test recording a failed registry operation."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.registry_operations = MagicMock()
        client.registry_operation_duration = MagicMock()

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

        client.registry_operations.add.assert_called_once_with(1, expected_attributes)
        client.registry_operation_duration.record.assert_called_once_with(
            0.02, expected_attributes
        )

    def test_record_server_request(self, mock_meter):
        """Test recording a server request."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.server_requests = MagicMock()

        client.record_server_request("weather-server")

        expected_attributes = {"server_name": "weather-server"}
        client.server_requests.add.assert_called_once_with(1, expected_attributes)


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
