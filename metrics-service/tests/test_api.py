"""Tests for API endpoints."""
import pytest
import json
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.models import MetricType, Metric, MetricRequest
from app.utils.helpers import hash_api_key


@pytest.fixture
def client():
    """Test client for API endpoints."""
    return TestClient(app)


@pytest.fixture
def valid_metric_request():
    """Valid metric request payload."""
    return {
        "service": "auth-server",
        "version": "1.0.0",
        "instance_id": "auth-01",
        "metrics": [
            {
                "type": "auth_request",
                "value": 1.0,
                "duration_ms": 45.2,
                "dimensions": {
                    "method": "jwt",
                    "success": True,
                    "server": "mcpgw",
                    "user_hash": "user_abc123"
                },
                "metadata": {
                    "error_code": None,
                    "request_size": 1024,
                    "response_size": 512
                }
            }
        ]
    }


class TestHealthEndpoints:
    """Test health and info endpoints."""
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "service": "metrics-collection"}
    
    def test_root_endpoint(self, client):
        """Test root info endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "MCP Metrics Collection Service"
        assert data["version"] == "1.0.0"
        assert data["status"] == "running"
        assert "endpoints" in data


class TestMetricsEndpoint:
    """Test metrics collection endpoint."""
    
    def test_metrics_without_api_key(self, client, valid_metric_request):
        """Test metrics endpoint without API key."""
        response = client.post("/metrics", json=valid_metric_request)
        assert response.status_code == 401
        assert "API key required" in response.json()["detail"]
    
    def test_metrics_with_invalid_api_key(self, client, valid_metric_request):
        """Test metrics endpoint with invalid API key."""
        headers = {"X-API-Key": "invalid_key"}
        response = client.post("/metrics", json=valid_metric_request, headers=headers)
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]
    
    @patch('app.api.auth.MetricsStorage')
    @patch('app.api.routes.MetricsProcessor')
    def test_metrics_with_valid_api_key(self, mock_processor_class, mock_storage_class, client, valid_metric_request):
        """Test metrics endpoint with valid API key."""
        # Mock storage for API key validation
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = {
            'service_name': 'test-service',
            'is_active': True,
            'rate_limit': 1000,
            'last_used_at': None
        }
        mock_storage.update_api_key_usage.return_value = None
        mock_storage_class.return_value = mock_storage
        
        # Mock processor for metrics processing
        mock_processor = AsyncMock()
        mock_result = AsyncMock()
        mock_result.accepted = 1
        mock_result.rejected = 0
        mock_result.errors = []
        mock_processor.process_metrics.return_value = mock_result
        mock_processor_class.return_value = mock_processor
        
        headers = {"X-API-Key": "test_key_123"}
        response = client.post("/metrics", json=valid_metric_request, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["accepted"] == 1
        assert data["rejected"] == 0
        assert data["errors"] == []
        assert "request_id" in data
    
    def test_metrics_with_invalid_payload(self, client):
        """Test metrics endpoint with invalid payload."""
        headers = {"X-API-Key": "test_key_123"}
        invalid_payload = {"invalid": "payload"}
        
        response = client.post("/metrics", json=invalid_payload, headers=headers)
        assert response.status_code == 422  # Validation error
    
    def test_metrics_with_missing_required_fields(self, client):
        """Test metrics endpoint with missing required fields."""
        headers = {"X-API-Key": "test_key_123"}
        invalid_payload = {
            "service": "test-service",
            # Missing metrics array
        }
        
        response = client.post("/metrics", json=invalid_payload, headers=headers)
        assert response.status_code == 422  # Validation error
    
    def test_metrics_with_invalid_metric_type(self, client):
        """Test metrics endpoint with invalid metric type."""
        headers = {"X-API-Key": "test_key_123"}
        invalid_payload = {
            "service": "test-service",
            "metrics": [
                {
                    "type": "invalid_type",  # Invalid metric type
                    "value": 1.0
                }
            ]
        }
        
        response = client.post("/metrics", json=invalid_payload, headers=headers)
        assert response.status_code == 422  # Validation error
    
    @patch('app.api.auth.MetricsStorage')
    @patch('app.api.routes.MetricsProcessor')
    def test_metrics_processor_error(self, mock_processor_class, mock_storage_class, client, valid_metric_request):
        """Test metrics endpoint when processor raises an error."""
        # Mock storage for API key validation
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = {
            'service_name': 'test-service',
            'is_active': True,
            'rate_limit': 1000,
            'last_used_at': None
        }
        mock_storage.update_api_key_usage.return_value = None
        mock_storage_class.return_value = mock_storage
        
        # Mock processor to raise an error
        mock_processor = AsyncMock()
        mock_processor.process_metrics.side_effect = Exception("Processing error")
        mock_processor_class.return_value = mock_processor
        
        headers = {"X-API-Key": "test_key_123"}
        response = client.post("/metrics", json=valid_metric_request, headers=headers)
        
        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]
    
    def test_metrics_with_multiple_metrics(self, client):
        """Test metrics endpoint with multiple metrics in one request."""
        payload = {
            "service": "multi-service",
            "metrics": [
                {
                    "type": "auth_request",
                    "value": 1.0,
                    "dimensions": {"success": True}
                },
                {
                    "type": "tool_discovery", 
                    "value": 1.0,
                    "dimensions": {"query": "test"}
                },
                {
                    "type": "tool_execution",
                    "value": 1.0,
                    "dimensions": {"tool_name": "calculator"}
                }
            ]
        }
        
        headers = {"X-API-Key": "test_key_123"}
        response = client.post("/metrics", json=payload, headers=headers)
        # Will fail auth but payload structure should be valid
        assert response.status_code == 401


class TestFlushEndpoint:
    """Test metrics flush endpoint."""
    
    def test_flush_without_api_key(self, client):
        """Test flush endpoint without API key."""
        response = client.post("/flush")
        assert response.status_code == 401
        assert "API key required" in response.json()["detail"]
    
    @patch('app.api.auth.MetricsStorage')
    @patch('app.api.routes.MetricsProcessor')
    def test_flush_with_valid_api_key(self, mock_processor_class, mock_storage_class, client):
        """Test flush endpoint with valid API key."""
        # Mock storage for API key validation
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = {
            'service_name': 'test-service',
            'is_active': True,
            'rate_limit': 1000,
            'last_used_at': None
        }
        mock_storage.update_api_key_usage.return_value = None
        mock_storage_class.return_value = mock_storage
        
        # Mock processor for flush
        mock_processor = AsyncMock()
        mock_processor.force_flush.return_value = None
        mock_processor_class.return_value = mock_processor
        
        headers = {"X-API-Key": "test_key_123"}
        response = client.post("/flush", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "flushed" in data["message"]