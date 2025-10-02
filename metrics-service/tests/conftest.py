"""Test configuration and fixtures."""
import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Import the app modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import Settings
from app.storage.database import init_database, MetricsStorage
from app.core.models import MetricType, Metric, MetricRequest
from app.utils.helpers import hash_api_key
from datetime import datetime


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    # Override the settings to use temp database
    original_db_path = Settings.SQLITE_DB_PATH
    Settings.SQLITE_DB_PATH = db_path
    
    yield db_path
    
    # Cleanup
    Settings.SQLITE_DB_PATH = original_db_path
    try:
        os.unlink(db_path)
    except FileNotFoundError:
        pass


@pytest.fixture
async def initialized_db(temp_db):
    """Initialize a temporary database with schema."""
    await init_database()
    return temp_db


@pytest.fixture
def test_settings():
    """Test settings configuration."""
    return Settings(
        SQLITE_DB_PATH="/tmp/test_metrics.db",
        OTEL_PROMETHEUS_ENABLED=False,
        OTEL_OTLP_ENDPOINT=None,
        METRICS_RATE_LIMIT=100,
        BATCH_SIZE=10
    )


@pytest.fixture
def sample_metric():
    """Sample metric for testing."""
    return Metric(
        type=MetricType.AUTH_REQUEST,
        timestamp=datetime(2024, 1, 15, 10, 30, 0),
        value=1.0,
        duration_ms=45.2,
        dimensions={
            "method": "jwt",
            "success": True,
            "server": "mcpgw",
            "user_hash": "user_abc123"
        },
        metadata={
            "error_code": None,
            "request_size": 1024,
            "response_size": 512
        }
    )


@pytest.fixture
def sample_metric_request(sample_metric):
    """Sample metric request for testing."""
    return MetricRequest(
        service="auth-server",
        version="1.0.0",
        instance_id="auth-01",
        metrics=[sample_metric]
    )


@pytest.fixture
def test_api_key():
    """Test API key and its hash."""
    api_key = "test_api_key_12345"
    key_hash = hash_api_key(api_key)
    return {
        "key": api_key,
        "hash": key_hash,
        "service": "test-service"
    }


@pytest.fixture
async def storage_with_api_key(initialized_db, test_api_key):
    """Storage instance with a test API key inserted."""
    storage = MetricsStorage()
    
    # Insert test API key
    await storage.create_api_key(test_api_key["hash"], test_api_key["service"])
    
    return storage, test_api_key


@pytest.fixture
def mock_otel_instruments():
    """Mock OpenTelemetry instruments."""
    mock_instruments = MagicMock()
    mock_instruments.auth_counter = MagicMock()
    mock_instruments.auth_histogram = MagicMock()
    mock_instruments.discovery_counter = MagicMock()
    mock_instruments.discovery_histogram = MagicMock()
    mock_instruments.tool_counter = MagicMock()
    mock_instruments.tool_histogram = MagicMock()
    return mock_instruments