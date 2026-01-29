from unittest.mock import patch, MagicMock

from packages.telemetry.metrics_client import OTelMetricsClient


def test_metrics_client_instantiation():
    """Test that OTelMetricsClient can be instantiated with service_name."""
    with patch('packages.telemetry.metrics_client.metrics.get_meter') as mock_get_meter:
        mock_get_meter.return_value = MagicMock()

        client = OTelMetricsClient("test-service")

        mock_get_meter.assert_called_once_with("mcp.test-service")

        assert client.service_name == "test-service"
        assert client.http_requests is not None
        assert client.http_duration is not None
        assert client.auth_requests is not None
        assert client.auth_duration is not None
        assert client.tool_discovery is not None
        assert client.tool_discovery_duration is not None
        assert client.tool_execution is not None
        assert client.tool_execution_duration is not None
        assert client.registry_operations is not None
        assert client.registry_operation_duration is not None
        assert client.server_requests is not None


def test_record_auth_request():
    """Test recording an authentication request."""
    with patch('packages.telemetry.metrics_client.metrics.get_meter'):
        client = OTelMetricsClient("test-service")
        client.auth_requests = MagicMock()
        client.auth_duration = MagicMock()

        client.record_auth_request("jwt", success=True, duration_seconds=0.05)

        client.auth_requests.add.assert_called_with(1, {
            "mechanism": "jwt",
            "status": "success"
        })
        client.auth_duration.record.assert_called_with(0.05, {
            "mechanism": "jwt",
            "status": "success"
        })


def test_record_tool_execution():
    """Test recording a tool execution."""
    with patch('packages.telemetry.metrics_client.metrics.get_meter'):
        client = OTelMetricsClient("test-service")
        client.tool_execution = MagicMock()
        client.tool_execution_duration = MagicMock()

        client.record_tool_execution(
            tool_name="my-tool",
            server_name="my-server",
            success=True,
            duration_seconds=0.1,
            method="POST"
        )

        client.tool_execution.add.assert_called_with(1, {
            "tool_name": "my-tool",
            "server_name": "my-server",
            "status": "success",
            "method": "POST"
        })
        client.tool_execution_duration.record.assert_called_with(0.1, {
            "tool_name": "my-tool",
            "server_name": "my-server",
            "status": "success",
            "method": "POST"
        })
