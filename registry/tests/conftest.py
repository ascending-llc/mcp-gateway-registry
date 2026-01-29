"""
Pytest configuration and shared fixtures.
"""
import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Any, AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Import our application and services
from registry.main import app
from registry.core.config import Settings
from registry.services.server_service import ServerServiceV1
from registry.health.service import HealthMonitoringService
from registry.services.search.base import VectorSearchService

# Import test utilities
from registry.tests.fixtures.factories import (
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
    # embedded_service doesn't have settings attribute, skip it
    # monkeypatch.setattr("registry.services.search.embedded_service.settings", test_settings)
    monkeypatch.setattr("registry.health.service.settings", test_settings)
    return test_settings


@pytest.fixture
def server_service(mock_settings: Settings) -> ServerServiceV1:
    """Create a fresh server service for testing."""
    service = ServerServiceV1()
    return service


@pytest.fixture
def mock_faiss_service() -> Mock:
    """Create a mock FAISS service."""
    mock_service = Mock(spec=VectorSearchService)
    mock_service.initialize = AsyncMock()
    mock_service.add_or_update_service = AsyncMock()
    mock_service.search = AsyncMock(return_value=[])
    mock_service.save_data = AsyncMock()
    return mock_service


@pytest.fixture
def health_service() -> HealthMonitoringService:
    """Create a fresh health monitoring service for testing."""
    service = HealthMonitoringService()
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
def admin_session_cookie():
    """Create a valid admin session cookie for testing."""
    from registry.auth.dependencies import create_session_cookie
    from registry.core.config import settings
    return create_session_cookie(
        settings.admin_user,
        auth_method="traditional",
        provider="local"
    )


@pytest.fixture
def test_client(admin_session_cookie) -> TestClient:
    """Create a test client for the FastAPI application with admin authentication."""
    from registry.core.config import settings
    return TestClient(app, cookies={settings.session_cookie_name: admin_session_cookie})


@pytest.fixture
async def async_client(admin_session_cookie) -> AsyncGenerator[AsyncClient, None]:
    """Create an async client for testing with admin authentication."""
    from registry.core.config import settings
    async with AsyncClient(
        app=app, 
        base_url="http://test",
        cookies={settings.session_cookie_name: admin_session_cookie}
    ) as client:
        yield client


@pytest.fixture
def authenticated_headers(admin_session_cookie) -> Dict[str, str]:
    """Create headers for authenticated requests."""
    from registry.core.config import settings
    return {
        "Cookie": f"{settings.session_cookie_name}={admin_session_cookie}"
    }


@pytest.fixture
def mock_authenticated_user():
    """Mock an authenticated user for testing protected routes."""
    from registry.auth.dependencies import get_current_user_by_mid
    from fastapi import Request
    
    # Create admin user context
    user_context = {
        "username": "testadmin",
        "user_id": "testadmin",
        "groups": ["registry-admins"],
        "scopes": ["registry-admins"],
        "is_admin": True,
        "auth_method": "traditional",
        "provider": "local",
        "accessible_servers": ["*"],
        "accessible_services": ["all"],
        "accessible_agents": ["all"],
        "ui_permissions": {
            "list_service": ["all"],
            "register_service": ["all"],
            "toggle_service": ["all"],
            "modify_service": ["all"],
            "health_check_service": ["all"],
        },
        "can_modify_servers": True,
    }
    
    def _mock_get_user(request: Request):
        request.state.user = user_context
        request.state.is_authenticated = True
        return user_context
    
    # Override the CurrentUser dependency
    app.dependency_overrides[get_current_user_by_mid] = _mock_get_user
    
    yield user_context
    
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
def mock_telemetry_metrics(monkeypatch):
    """
    Mock telemetry metrics to prevent background thread issues during tests.

    This prevents the OTel background exporter from trying to serialize
    mock objects (like AsyncMock) which causes encoding errors.
    """
    mock_metrics_client = Mock()
    mock_metrics_client.record_server_request = Mock()
    mock_metrics_client.record_tool_execution = Mock()
    mock_metrics_client.record_tool_discovery = Mock()
    mock_metrics_client.record_auth_request = Mock()
    mock_metrics_client.record_registry_operation = Mock()

    # Mock the metrics client at the source module
    monkeypatch.setattr(
        "registry.utils.otel_metrics.metrics",
        mock_metrics_client
    )
    # Also mock in all places where it's imported
    monkeypatch.setattr(
        "registry.api.proxy_routes.metrics",
        mock_metrics_client
    )
    monkeypatch.setattr(
        "registry.api.v1.search_routes.metrics",
        mock_metrics_client
    )
    monkeypatch.setattr(
        "registry.api.v1.server.server_routes.metrics",
        mock_metrics_client
    )
    monkeypatch.setattr(
        "registry.auth.middleware.metrics",
        mock_metrics_client
    )

    yield mock_metrics_client


@pytest.fixture(autouse=True)
def cleanup_services():
    """Automatically cleanup services after each test."""
    yield
    # Reset global service states
    from registry.services.server_service import server_service_v1
    from registry.health.service import health_service

    # Clear server service state if methods exist
    if hasattr(server_service_v1, 'registered_servers'):
        server_service_v1.registered_servers.clear()
    if hasattr(server_service_v1, 'service_state'):
        server_service_v1.service_state.clear()

    health_service.server_health_status.clear()
    health_service.server_last_check_time.clear()
    # Clear active_connections only if it exists (websocket feature)
    if hasattr(health_service, 'active_connections'):
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