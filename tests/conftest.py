"""
Pytest configuration and shared fixtures.
"""
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Import our application and services
from registry.main import app
from registry.core.config import Settings
from registry.services.server_service import ServerService
from registry.search.service import FaissService
from registry.health.service import HealthMonitoringService
from registry.core.nginx_service import NginxConfigService

# Import test utilities
from tests.fixtures.factories import (
    ServerInfoFactory,
    create_multiple_servers,
    create_server_with_tools,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def test_settings(temp_dir: Path) -> Settings:
    """Create test settings with temporary directories."""
    test_settings = Settings(
        secret_key="test-secret-key-for-testing-only",
        admin_user="testadmin",
        admin_password="testpassword",
        container_app_dir=temp_dir / "app",
        container_registry_dir=temp_dir / "app" / "registry",
        container_log_dir=temp_dir / "app" / "logs",
        health_check_interval_seconds=60,  # Longer for tests
        embeddings_model_name="all-MiniLM-L6-v2",
        embeddings_model_dimensions=384,
    )
    
    # Create necessary directories
    test_settings.container_app_dir.mkdir(parents=True, exist_ok=True)
    test_settings.container_registry_dir.mkdir(parents=True, exist_ok=True)
    test_settings.container_log_dir.mkdir(parents=True, exist_ok=True)
    test_settings.servers_dir.mkdir(parents=True, exist_ok=True)
    test_settings.static_dir.mkdir(parents=True, exist_ok=True)
    test_settings.templates_dir.mkdir(parents=True, exist_ok=True)
    
    return test_settings


@pytest.fixture
def mock_settings(test_settings: Settings, monkeypatch):
    """Mock the global settings for tests."""
    monkeypatch.setattr("registry.core.config.settings", test_settings)
    monkeypatch.setattr("registry.services.server_service.settings", test_settings)
    monkeypatch.setattr("registry.search.service.settings", test_settings)
    monkeypatch.setattr("registry.health.service.settings", test_settings)
    monkeypatch.setattr("registry.core.nginx_service.settings", test_settings)
    return test_settings


@pytest.fixture
def server_service(mock_settings: Settings) -> ServerService:
    """Create a fresh server service for testing."""
    service = ServerService()
    return service


@pytest.fixture
def mock_faiss_service() -> Mock:
    """Create a mock FAISS service."""
    mock_service = Mock(spec=FaissService)
    mock_service.initialize = AsyncMock()
    mock_service.add_or_update_service = AsyncMock()
    mock_service.search_services = AsyncMock(return_value=[])
    mock_service.save_data = AsyncMock()
    return mock_service


@pytest.fixture
def health_service() -> HealthMonitoringService:
    """Create a fresh health monitoring service for testing."""
    service = HealthMonitoringService()
    return service


@pytest.fixture
def nginx_service(mock_settings: Settings) -> NginxConfigService:
    """Create a fresh nginx service for testing."""
    service = NginxConfigService()
    return service


@pytest.fixture
def sample_server() -> Dict[str, Any]:
    """Create a sample server for testing."""
    return ServerInfoFactory()


@pytest.fixture
def sample_servers() -> Dict[str, Dict[str, Any]]:
    """Create multiple sample servers for testing."""
    return create_multiple_servers(count=3)


@pytest.fixture
def server_with_tools() -> Dict[str, Any]:
    """Create a server with tools for testing."""
    return create_server_with_tools(num_tools=5)


@pytest.fixture
def test_client() -> TestClient:
    """Create a test client for the FastAPI application."""
    return TestClient(app)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async client for testing."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def authenticated_headers() -> Dict[str, str]:
    """Create headers for authenticated requests."""
    # This would typically include a valid session cookie or JWT token
    return {
        "Cookie": "mcp_gateway_session=test-session-token"
    }


@pytest.fixture
def mock_authenticated_user(monkeypatch):
    """Mock an authenticated user for testing protected routes."""
    def mock_auth_dependency(session=None):
        return "testuser"
    
    # Override both auth functions and the get_current_user function
    monkeypatch.setattr("registry.auth.dependencies.web_auth", mock_auth_dependency)
    monkeypatch.setattr("registry.auth.dependencies.api_auth", mock_auth_dependency)
    monkeypatch.setattr("registry.auth.dependencies.get_current_user", mock_auth_dependency)
    
    # Also override the FastAPI dependency overrides
    from registry.auth.dependencies import web_auth, api_auth
    app.dependency_overrides[web_auth] = mock_auth_dependency
    app.dependency_overrides[api_auth] = mock_auth_dependency
    
    yield "testuser"
    
    # Clean up dependency overrides
    app.dependency_overrides.clear()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for testing."""
    mock_ws = Mock()
    mock_ws.client = Mock()
    mock_ws.client.host = "127.0.0.1"
    mock_ws.client.port = 12345
    mock_ws.accept = AsyncMock()
    mock_ws.send_text = AsyncMock()
    mock_ws.receive_text = AsyncMock()
    mock_ws.close = AsyncMock()
    return mock_ws


@pytest.fixture(autouse=True)
def cleanup_services():
    """Automatically cleanup services after each test."""
    yield
    # Reset global service states
    from registry.services.server_service import server_service
    from registry.health.service import health_service
    
    server_service.registered_servers.clear()
    server_service.service_state.clear()
    health_service.server_health_status.clear()
    health_service.server_last_check_time.clear()
    health_service.active_connections.clear()


# Test markers for different test categories
pytest_mark_unit = pytest.mark.unit
pytest_mark_integration = pytest.mark.integration
pytest_mark_e2e = pytest.mark.e2e
pytest_mark_auth = pytest.mark.auth
pytest_mark_servers = pytest.mark.servers
pytest_mark_search = pytest.mark.search
pytest_mark_health = pytest.mark.health
pytest_mark_slow = pytest.mark.slow 