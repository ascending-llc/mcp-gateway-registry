"""Tests for rate limiting functionality."""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch

from app.core.rate_limiter import RateLimiter
from app.api.auth import verify_api_key, get_rate_limit_status
from app.utils.helpers import hash_api_key
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app.main import app


class TestRateLimiter:
    """Test the RateLimiter class."""
    
    @pytest.fixture
    def rate_limiter(self):
        """Create a fresh rate limiter for each test."""
        return RateLimiter()
    
    @pytest.mark.asyncio
    async def test_rate_limiter_initialization(self, rate_limiter):
        """Test rate limiter initializes correctly."""
        assert rate_limiter._buckets == {}
        assert rate_limiter._lock is not None
    
    @pytest.mark.asyncio
    async def test_first_request_allowed(self, rate_limiter):
        """Test first request is allowed."""
        key_hash = "test_key_hash"
        rate_limit = 1000
        
        allowed, remaining = await rate_limiter.check_rate_limit(key_hash, rate_limit)
        
        assert allowed is True
        assert remaining == rate_limit - 1  # Started with rate_limit, used 1
    
    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self, rate_limiter):
        """Test rate limit is enforced when exceeded."""
        key_hash = "test_key_hash"
        rate_limit = 2  # Very low limit for testing
        
        # First request allowed
        allowed, remaining = await rate_limiter.check_rate_limit(key_hash, rate_limit)
        assert allowed is True
        assert remaining == 1
        
        # Second request allowed
        allowed, remaining = await rate_limiter.check_rate_limit(key_hash, rate_limit)
        assert allowed is True
        assert remaining == 0
        
        # Third request blocked
        allowed, remaining = await rate_limiter.check_rate_limit(key_hash, rate_limit)
        assert allowed is False
        assert remaining == 0
    
    @pytest.mark.asyncio
    async def test_token_refill_over_time(self, rate_limiter):
        """Test tokens are refilled over time."""
        key_hash = "test_key_hash"
        rate_limit = 60  # 60 tokens per minute = 1 per second
        
        # Use up all tokens
        for _ in range(60):
            await rate_limiter.check_rate_limit(key_hash, rate_limit)
        
        # Should be blocked now
        allowed, remaining = await rate_limiter.check_rate_limit(key_hash, rate_limit)
        assert allowed is False
        
        # Simulate time passing by directly modifying the bucket
        # In real scenario, tokens would refill naturally
        rate_limiter._buckets[key_hash] = (10, time.time() - 10, rate_limit)  # 10 seconds ago
        
        # Should have tokens now
        allowed, remaining = await rate_limiter.check_rate_limit(key_hash, rate_limit)
        assert allowed is True
        assert remaining > 0
    
    @pytest.mark.asyncio
    async def test_different_keys_independent_limits(self, rate_limiter):
        """Test different API keys have independent rate limits."""
        key1 = "key_hash_1"
        key2 = "key_hash_2"
        rate_limit = 2
        
        # Use up key1's limit
        await rate_limiter.check_rate_limit(key1, rate_limit)
        await rate_limiter.check_rate_limit(key1, rate_limit)
        
        # key1 should be blocked
        allowed, _ = await rate_limiter.check_rate_limit(key1, rate_limit)
        assert allowed is False
        
        # key2 should still be allowed
        allowed, remaining = await rate_limiter.check_rate_limit(key2, rate_limit)
        assert allowed is True
        assert remaining == 1
    
    @pytest.mark.asyncio
    async def test_rate_limit_change(self, rate_limiter):
        """Test changing rate limits for existing keys."""
        key_hash = "test_key_hash"
        
        # Start with low limit
        allowed, remaining = await rate_limiter.check_rate_limit(key_hash, 2)
        assert allowed is True
        assert remaining == 1
        
        # Change to higher limit
        allowed, remaining = await rate_limiter.check_rate_limit(key_hash, 1000)
        assert allowed is True
        # Should scale up the remaining tokens
        assert remaining > 1
    
    @pytest.mark.asyncio
    async def test_get_bucket_status(self, rate_limiter):
        """Test getting bucket status without consuming tokens."""
        key_hash = "test_key_hash"
        rate_limit = 100
        
        # Use some tokens
        await rate_limiter.check_rate_limit(key_hash, rate_limit)
        await rate_limiter.check_rate_limit(key_hash, rate_limit)
        
        status = await rate_limiter.get_bucket_status(key_hash, rate_limit)
        
        assert status["rate_limit"] == rate_limit
        assert status["available_tokens"] == 98  # Used 2 tokens
        assert "reset_time_seconds" in status
    
    @pytest.mark.asyncio
    async def test_get_bucket_status_new_key(self, rate_limiter):
        """Test getting bucket status for new key."""
        key_hash = "new_key_hash"
        rate_limit = 100
        
        status = await rate_limiter.get_bucket_status(key_hash, rate_limit)
        
        assert status["rate_limit"] == rate_limit
        assert status["available_tokens"] == rate_limit
        assert status["reset_time_seconds"] == 0
    
    @pytest.mark.asyncio
    async def test_cleanup_old_buckets(self, rate_limiter):
        """Test cleanup of old unused buckets."""
        key_hash = "test_key_hash"
        rate_limit = 100
        
        # Create a bucket
        await rate_limiter.check_rate_limit(key_hash, rate_limit)
        assert len(rate_limiter._buckets) == 1
        
        # Simulate old bucket (25 hours ago)
        old_time = time.time() - (25 * 3600)
        rate_limiter._buckets[key_hash] = (50, old_time, rate_limit)
        
        # Clean up old buckets (max age 24 hours)
        await rate_limiter.cleanup_old_buckets(max_age_hours=24)
        
        # Bucket should be removed
        assert len(rate_limiter._buckets) == 0


class TestRateLimitIntegration:
    """Test rate limiting integration with API authentication."""
    
    @pytest.fixture(autouse=True)
    def clear_rate_limiter(self):
        """Clear rate limiter state before each test."""
        from app.core.rate_limiter import rate_limiter
        rate_limiter._buckets.clear()
    
    @pytest.fixture
    def client(self):
        """Test client for API endpoints."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_request(self):
        """Mock request object."""
        request = AsyncMock(spec=Request)
        request.headers = {"X-API-Key": "test_key_123"}
        request.state = AsyncMock()
        return request
    
    @patch('app.api.auth.MetricsStorage')
    @pytest.mark.asyncio
    async def test_auth_with_rate_limiting(self, mock_storage_class, mock_request):
        """Test API key verification with rate limiting."""
        # Mock storage
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = {
            'service_name': 'test-service',
            'is_active': True,
            'rate_limit': 10,
            'last_used_at': None
        }
        mock_storage.update_api_key_usage.return_value = None
        mock_storage_class.return_value = mock_storage
        
        # First request should be allowed
        service_name = await verify_api_key(mock_request)
        assert service_name == 'test-service'
        assert hasattr(mock_request.state, 'rate_limit_remaining')
        assert hasattr(mock_request.state, 'rate_limit_limit')
        assert mock_request.state.rate_limit_limit == 10
        assert mock_request.state.rate_limit_remaining == 9
    
    @patch('app.api.auth.MetricsStorage')
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, mock_storage_class, mock_request):
        """Test rate limit exceeded scenario."""
        # Mock storage
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = {
            'service_name': 'test-service',
            'is_active': True,
            'rate_limit': 1,  # Very low limit
            'last_used_at': None
        }
        mock_storage.update_api_key_usage.return_value = None
        mock_storage_class.return_value = mock_storage
        
        # First request allowed  
        service_name = await verify_api_key(mock_request)
        assert service_name == 'test-service'
        
        # Second request should be blocked
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(mock_request)
        
        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.detail
        assert exc_info.value.headers["X-RateLimit-Limit"] == "1"
        assert exc_info.value.headers["X-RateLimit-Remaining"] == "0"
        assert exc_info.value.headers["Retry-After"] == "60"
    
    @patch('app.api.auth.MetricsStorage')
    @pytest.mark.asyncio
    async def test_get_rate_limit_status_function(self, mock_storage_class):
        """Test get_rate_limit_status function."""
        # Mock storage
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = {
            'service_name': 'test-service',
            'is_active': True,
            'rate_limit': 100,
            'last_used_at': None
        }
        mock_storage_class.return_value = mock_storage
        
        status = await get_rate_limit_status("test_key_123")
        
        assert status["service"] == "test-service"
        assert status["rate_limit"] == 100
        assert status["available_tokens"] == 100
        assert "reset_time_seconds" in status
    
    @patch('app.api.auth.MetricsStorage')
    @pytest.mark.asyncio
    async def test_get_rate_limit_status_invalid_key(self, mock_storage_class):
        """Test get_rate_limit_status with invalid key."""
        # Mock storage returning None
        mock_storage = AsyncMock()
        mock_storage.get_api_key.return_value = None
        mock_storage_class.return_value = mock_storage
        
        with pytest.raises(HTTPException) as exc_info:
            await get_rate_limit_status("invalid_key")
        
        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail


class TestRateLimitEndpoint:
    """Test the rate limit status endpoint."""
    
    @pytest.fixture(autouse=True)
    def clear_rate_limiter(self):
        """Clear rate limiter state before each test."""
        from app.core.rate_limiter import rate_limiter
        rate_limiter._buckets.clear()
    
    @pytest.fixture
    def client(self):
        """Test client for API endpoints."""
        return TestClient(app)
    
    def test_rate_limit_endpoint_without_key(self, client):
        """Test rate limit endpoint without API key."""
        response = client.get("/rate-limit")
        assert response.status_code == 401
        assert "API key required" in response.json()["detail"]
    
    @patch('app.api.routes.get_rate_limit_status')
    def test_rate_limit_endpoint_with_key(self, mock_get_status, client):
        """Test rate limit endpoint with valid API key."""
        mock_get_status.return_value = {
            "service": "test-service",
            "rate_limit": 1000,
            "available_tokens": 950,
            "reset_time_seconds": 30
        }
        
        headers = {"X-API-Key": "test_key_123"}
        response = client.get("/rate-limit", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "test-service"
        assert data["rate_limit"] == 1000
        assert data["available_tokens"] == 950
        assert data["reset_time_seconds"] == 30
    
    @patch('app.api.routes.get_rate_limit_status')
    def test_rate_limit_endpoint_error(self, mock_get_status, client):
        """Test rate limit endpoint when status check fails."""
        mock_get_status.side_effect = Exception("Database error")
        
        headers = {"X-API-Key": "test_key_123"}
        response = client.get("/rate-limit", headers=headers)
        
        assert response.status_code == 500
        assert "Failed to get rate limit status" in response.json()["detail"]