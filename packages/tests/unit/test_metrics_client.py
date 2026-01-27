import pytest
from packages.telemetry.metrics_client import OTelMetricsClient
from unittest.mock import patch, MagicMock

def test_metrics_client_instantiation():
    """Test that OTelMetricsClient can be instantiated without arguments."""
    with patch('opentelemetry.metrics.get_meter') as mock_get_meter:
        client = OTelMetricsClient()
        
        mock_get_meter.assert_called_once()
        # Verify it uses the module name or similar
        assert mock_get_meter.call_args[0][0] == "packages.telemetry.metrics_client"
        
        assert client.http_requests is not None
        assert client.http_duration is not None
        assert client.auth_requests is not None
        assert client.tool_discovery is not None
        assert client.server_requests is not None

def test_record_http_request():
    """Test recording an HTTP request."""
    with patch('opentelemetry.metrics.get_meter') as mock_get_meter:
        client = OTelMetricsClient()
        client.http_requests = MagicMock()
        
        client.record_http_request("GET", "/api/test", 200)
        
        client.http_requests.add.assert_called_with(1, {
            "method": "GET",
            "route": "/api/test",
            "status_code": "200"
        })
