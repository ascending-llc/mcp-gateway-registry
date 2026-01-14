import pytest
from unittest.mock import patch, MagicMock

# Update this import to match the actual location of your OTelMetricsClient file
from packages.telemetry.metrics_client import OTelMetricsClient


@pytest.mark.unit
@pytest.mark.metrics
class TestOTelMetricsClient:
    """Test suite for OTelMetricsClient."""

    @pytest.fixture
    def mock_meter(self):
        """Fixture to mock the OpenTelemetry meter and its instruments."""
        with patch('opentelemetry.metrics.get_meter') as mock_get_meter:
            meter_instance = MagicMock()
            mock_get_meter.return_value = meter_instance
            
            meter_instance.create_counter.return_value = MagicMock()
            meter_instance.create_histogram.return_value = MagicMock()
            
            yield mock_get_meter, meter_instance

    def test_init_creates_instruments(self, mock_meter):
        """Test initialization creates all required metric instruments."""
        mock_get_meter, meter_instance = mock_meter
        service_name = "test-service"
        
        client = OTelMetricsClient(service_name)
        
        mock_get_meter.assert_called_once_with(service_name)
        
        assert meter_instance.create_counter.call_count == 3
        
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
            description="Total number of tools discovered/registered",
            unit="1"
        )

        meter_instance.create_histogram.assert_called_once_with(
            name="http_request_duration_seconds",
            description="HTTP request duration in seconds",
            unit="s"
        )

    def test_record_http_request(self, mock_meter):
        """Test recording an HTTP request."""
        _, meter_instance = mock_meter
        mock_counter = MagicMock()
        
        client = OTelMetricsClient("test-service")
        
        client.http_requests = MagicMock()
        
        method = "GET"
        route = "/api/v1/users"
        status_code = 200
        
        client.record_http_request(method, route, status_code)
        
        expected_attributes = {
            "method": method,
            "route": route,
            "status_code": "200" 
        }
        
        client.http_requests.add.assert_called_once_with(1, expected_attributes)

    def test_record_http_duration(self, mock_meter):
        """Test recording HTTP duration."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        
        client.http_duration = MagicMock()
        
        duration = 0.150
        method = "POST"
        route = "/api/v1/data"
        
        client.record_http_duration(duration, method, route)
        
        expected_attributes = {
            "method": method,
            "route": route
        }
        
        client.http_duration.record.assert_called_once_with(duration, expected_attributes)

    def test_record_auth_request_success(self, mock_meter):
        """Test recording a successful authentication attempt."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.auth_requests = MagicMock()
        
        client.record_auth_request("jwt", success=True)
        
        expected_attributes = {
            "mechanism": "jwt",
            "status": "success"
        }
        
        client.auth_requests.add.assert_called_once_with(1, expected_attributes)

    def test_record_auth_request_failure(self, mock_meter):
        """Test recording a failed authentication attempt."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.auth_requests = MagicMock()
        
        client.record_auth_request("api_key", success=False)
        
        expected_attributes = {
            "mechanism": "api_key",
            "status": "failure"
        }
        
        client.auth_requests.add.assert_called_once_with(1, expected_attributes)

    def test_record_tool_discovery_default(self, mock_meter):
        """Test recording tool discovery with default source."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.tool_discovery = MagicMock()
        
        client.record_tool_discovery("weather-tool")
        
        expected_attributes = {
            "tool_name": "weather-tool",
            "source": "registry"
        }
        
        client.tool_discovery.add.assert_called_once_with(1, expected_attributes)

    def test_record_tool_discovery_custom_source(self, mock_meter):
        """Test recording tool discovery with custom source."""
        _, meter_instance = mock_meter
        client = OTelMetricsClient("test-service")
        client.tool_discovery = MagicMock()
        
        client.record_tool_discovery("finance-tool", source="user-defined")
        
        expected_attributes = {
            "tool_name": "finance-tool",
            "source": "user-defined"
        }
        
        client.tool_discovery.add.assert_called_once_with(1, expected_attributes)