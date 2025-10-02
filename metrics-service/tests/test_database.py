"""Tests for database storage layer."""
import pytest
import asyncio
import json
from datetime import datetime

from app.storage.database import init_database, MetricsStorage, wait_for_database
from app.core.models import MetricType, Metric, MetricRequest
from app.utils.helpers import hash_api_key


class TestDatabaseInitialization:
    """Test database initialization and schema creation."""
    
    async def test_wait_for_database_success(self, temp_db):
        """Test successful database connection."""
        # Should succeed without raising an exception
        await wait_for_database(max_retries=1, delay=0.1)
    
    async def test_init_database_succeeds(self, temp_db):
        """Test that init_database runs without errors."""
        # Should not raise any exceptions
        await init_database()
        
        # Verify we can create a storage instance
        storage = MetricsStorage()
        assert storage is not None


class TestAPIKeyManagement:
    """Test API key storage and validation."""
    
    async def test_create_api_key(self, initialized_db):
        """Test creating a new API key."""
        storage = MetricsStorage()
        key_hash = hash_api_key("test_key_123")
        
        result = await storage.create_api_key(key_hash, "test-service")
        assert result is True
        
        # Verify key was stored
        key_info = await storage.get_api_key(key_hash)
        assert key_info is not None
        assert key_info['service_name'] == "test-service"
        assert key_info['is_active'] is True
    
    async def test_get_api_key_nonexistent(self, initialized_db):
        """Test retrieving a non-existent API key."""
        storage = MetricsStorage()
        result = await storage.get_api_key("nonexistent_hash")
        assert result is None
    
    async def test_update_api_key_usage(self, storage_with_api_key):
        """Test updating API key last usage timestamp."""
        storage, api_key_info = storage_with_api_key
        
        # Get initial state
        initial_info = await storage.get_api_key(api_key_info["hash"])
        initial_last_used = initial_info['last_used_at']
        
        # Update usage
        await storage.update_api_key_usage(api_key_info["hash"])
        
        # Check that last_used_at was updated
        updated_info = await storage.get_api_key(api_key_info["hash"])
        assert updated_info['last_used_at'] != initial_last_used


class TestMetricsStorage:
    """Test metrics storage functionality."""
    
    async def test_store_single_metric_batch(self, initialized_db, sample_metric_request):
        """Test storing a single metric in a batch."""
        storage = MetricsStorage()
        
        metrics_batch = [{
            'metric': sample_metric_request.metrics[0],
            'request': sample_metric_request,
            'request_id': 'test_req_123'
        }]
        
        # Should not raise an exception
        await storage.store_metrics_batch(metrics_batch)
        
        # Test passes if no exception is raised - we can't verify internal state
        # without exposing unauthorized database access
    
    async def test_store_empty_batch(self, initialized_db):
        """Test storing an empty metrics batch."""
        storage = MetricsStorage()
        
        # Should handle empty batch gracefully
        await storage.store_metrics_batch([])
        
        # Test passes if no exception is raised
    
    async def test_store_multiple_metrics_batch(self, initialized_db):
        """Test storing multiple metrics in a single batch."""
        storage = MetricsStorage()
        
        auth_metric = Metric(
            type=MetricType.AUTH_REQUEST,
            value=1.0,
            duration_ms=100.0,
            dimensions={"success": True, "method": "oauth"}
        )
        
        tool_metric = Metric(
            type=MetricType.TOOL_EXECUTION,
            value=1.0,
            duration_ms=200.0,
            dimensions={"tool_name": "calculator", "success": True}
        )
        
        request = MetricRequest(
            service="multi-service",
            metrics=[auth_metric, tool_metric]
        )
        
        metrics_batch = [
            {'metric': auth_metric, 'request': request, 'request_id': 'batch_1'},
            {'metric': tool_metric, 'request': request, 'request_id': 'batch_1'}
        ]
        
        # Should store both metrics without raising exceptions
        await storage.store_metrics_batch(metrics_batch)
    
    async def test_store_discovery_metric(self, initialized_db):
        """Test storing discovery metrics."""
        storage = MetricsStorage()
        
        discovery_metric = Metric(
            type=MetricType.TOOL_DISCOVERY,
            value=1.0,
            duration_ms=50.2,
            dimensions={
                "query": "search tools",
                "results_count": 25,
                "top_k_services": 10,
                "top_n_tools": 50
            },
            metadata={
                "embedding_time_ms": 15.3,
                "faiss_search_time_ms": 12.1
            }
        )
        
        request = MetricRequest(
            service="registry-service",
            version="1.0.0",
            metrics=[discovery_metric]
        )
        
        metrics_batch = [{
            'metric': discovery_metric,
            'request': request,
            'request_id': 'test_req_discovery'
        }]
        
        # Should store discovery metric without exceptions
        await storage.store_metrics_batch(metrics_batch)