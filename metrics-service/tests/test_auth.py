"""Tests for API authentication."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.auth import verify_api_key
from app.utils.helpers import hash_api_key
from app.main import app


class TestAPIKeyVerification:
    """Test API key verification logic."""
    
    @patch('app.api.auth.MetricsStorage')
    async def test_verify_valid_api_key(self, mock_storage_class):
        """Test verification of valid API key."""
        # Mock storage
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = {
            'service_name': 'test-service',
            'is_active': True,
            'rate_limit': 1000,
            'last_used_at': None
        }
        mock_storage.update_api_key_usage.return_value = None
        mock_storage_class.return_value = mock_storage
        
        # Mock request with API key header
        from unittest.mock import MagicMock
        mock_request = MagicMock()
        mock_request.headers = {"X-API-Key": "test_key_123"}
        
        result = await verify_api_key(mock_request)
        
        assert result == 'test-service'
        mock_storage.get_api_key.assert_called_once_with(hash_api_key("test_key_123"))
        mock_storage.update_api_key_usage.assert_called_once()
    
    @patch('app.api.auth.MetricsStorage')
    async def test_verify_missing_api_key(self, mock_storage_class):
        """Test verification when API key is missing."""
        from unittest.mock import MagicMock
        mock_request = MagicMock()
        mock_request.headers = {}  # No API key header
        
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(mock_request)
        
        assert exc_info.value.status_code == 401
        assert "API key required" in str(exc_info.value.detail)
    
    @patch('app.api.auth.MetricsStorage')
    async def test_verify_invalid_api_key(self, mock_storage_class):
        """Test verification of invalid API key."""
        # Mock storage to return None (key not found)
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = None
        mock_storage_class.return_value = mock_storage
        
        from unittest.mock import MagicMock
        mock_request = MagicMock()
        mock_request.headers = {"X-API-Key": "invalid_key"}
        
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(mock_request)
        
        assert exc_info.value.status_code == 401
        assert "Invalid API key" in str(exc_info.value.detail)
    
    @patch('app.api.auth.MetricsStorage')
    async def test_verify_inactive_api_key(self, mock_storage_class):
        """Test verification of inactive API key."""
        # Mock storage to return inactive key
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = {
            'service_name': 'test-service',
            'is_active': False,  # Inactive
            'rate_limit': 1000,
            'last_used_at': None
        }
        mock_storage_class.return_value = mock_storage
        
        from unittest.mock import MagicMock
        mock_request = MagicMock()
        mock_request.headers = {"X-API-Key": "inactive_key"}
        
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(mock_request)
        
        assert exc_info.value.status_code == 401
        assert "API key is inactive" in str(exc_info.value.detail)
    
    @patch('app.api.auth.MetricsStorage')
    async def test_verify_api_key_updates_usage(self, mock_storage_class):
        """Test that API key verification updates usage timestamp."""
        # Mock storage
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = {
            'service_name': 'test-service',
            'is_active': True,
            'rate_limit': 1000,
            'last_used_at': '2024-01-01T00:00:00'
        }
        mock_storage.update_api_key_usage.return_value = None
        mock_storage_class.return_value = mock_storage
        
        from unittest.mock import MagicMock
        mock_request = MagicMock()
        mock_request.headers = {"X-API-Key": "test_key_123"}
        
        result = await verify_api_key(mock_request)
        
        # Verify usage was updated with correct key hash
        expected_hash = hash_api_key("test_key_123")
        mock_storage.update_api_key_usage.assert_called_once_with(expected_hash)


class TestAPIKeyHashingHelpers:
    """Test API key hashing helper functions."""
    
    def test_hash_api_key_consistency(self):
        """Test that hashing the same key produces consistent results."""
        key = "test_key_12345"
        hash1 = hash_api_key(key)
        hash2 = hash_api_key(key)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length
    
    def test_hash_different_keys_produce_different_hashes(self):
        """Test that different keys produce different hashes."""
        key1 = "test_key_1"
        key2 = "test_key_2"
        
        hash1 = hash_api_key(key1)
        hash2 = hash_api_key(key2)
        
        assert hash1 != hash2
    
    def test_hash_empty_string(self):
        """Test hashing empty string."""
        hash_result = hash_api_key("")
        assert len(hash_result) == 64
        assert hash_result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestAuthenticationIntegration:
    """Test authentication integration with API endpoints."""
    
    def test_metrics_endpoint_auth_integration(self):
        """Test that metrics endpoint properly integrates with auth."""
        client = TestClient(app)
        
        # Test without API key
        response = client.post("/metrics", json={"service": "test", "metrics": []})
        assert response.status_code == 401
        
        # Test with invalid API key  
        headers = {"X-API-Key": "invalid_key"}
        response = client.post("/metrics", json={"service": "test", "metrics": []}, headers=headers)
        assert response.status_code == 401
    
    def test_flush_endpoint_auth_integration(self):
        """Test that flush endpoint properly integrates with auth."""
        client = TestClient(app)
        
        # Test without API key
        response = client.post("/flush")
        assert response.status_code == 401
        
        # Test with invalid API key
        headers = {"X-API-Key": "invalid_key"}  
        response = client.post("/flush", headers=headers)
        assert response.status_code == 401
    
    def test_health_endpoint_no_auth_required(self):
        """Test that health endpoint doesn't require authentication."""
        client = TestClient(app)
        
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_root_endpoint_no_auth_required(self):
        """Test that root endpoint doesn't require authentication."""
        client = TestClient(app)
        
        response = client.get("/")
        assert response.status_code == 200


class TestSecurityBestPractices:
    """Test security best practices in authentication."""
    
    def test_api_key_not_logged_in_error_messages(self):
        """Test that API keys are not exposed in error messages."""
        from unittest.mock import MagicMock
        mock_request = MagicMock()
        mock_request.headers = {"X-API-Key": "secret_key_should_not_appear_in_logs"}
        
        with pytest.raises(HTTPException) as exc_info:
            # This will fail because no mock storage is set up
            import asyncio
            asyncio.run(verify_api_key(mock_request))
        
        # Error message should not contain the actual API key
        error_detail = str(exc_info.value.detail)
        assert "secret_key_should_not_appear_in_logs" not in error_detail
    
    @patch('app.api.auth.MetricsStorage')
    async def test_api_key_hashed_before_storage_lookup(self, mock_storage_class):
        """Test that API key is hashed before database lookup."""
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = None  # Will cause auth failure
        mock_storage_class.return_value = mock_storage
        
        from unittest.mock import MagicMock
        mock_request = MagicMock()
        api_key = "plaintext_key_123"
        mock_request.headers = {"X-API-Key": api_key}
        
        try:
            await verify_api_key(mock_request)
        except HTTPException:
            pass  # Expected to fail
        
        # Verify storage was called with hashed key, not plaintext
        expected_hash = hash_api_key(api_key)
        mock_storage.get_api_key.assert_called_once_with(expected_hash)
        
        # Verify plaintext key was not passed to storage
        call_args = mock_storage.get_api_key.call_args[0][0]
        assert call_args != api_key
        assert call_args == expected_hash