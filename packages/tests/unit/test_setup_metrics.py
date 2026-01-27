import pytest
from unittest.mock import patch, MagicMock
from packages.telemetry import setup_metrics

def test_setup_metrics_requires_service_name():
    """Test that setup_metrics requires service_name and uses it."""
    # Test that missing service_name raises TypeError (standard python behavior for missing required arg)
    with pytest.raises(TypeError):
        setup_metrics()

@patch('packages.telemetry.Resource')
@patch('packages.telemetry.MeterProvider')
@patch('packages.telemetry.metrics')
def test_setup_metrics_uses_service_name(mock_metrics, mock_provider, mock_resource):
    """Verify setup_metrics uses the provided service_name."""
    
    setup_metrics(service_name="test-service", enable_logs=False)
    
    # Verify Resource was created with the correct service name
    mock_resource.create.assert_called_once()
    call_kwargs = mock_resource.create.call_args[1]
    assert call_kwargs['attributes']['service.name'] == "test-service"
