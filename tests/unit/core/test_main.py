"""
Unit tests for main application module.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from registry.main import app, lifespan, health_check


@pytest.mark.unit
@pytest.mark.core
class TestMainApplication:
    """Test suite for main application functionality."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        with patch('registry.main.settings') as mock_settings:
            mock_settings.container_log_dir = Mock()
            mock_settings.container_log_dir.mkdir = Mock()
            mock_settings.static_dir = "/static"
            mock_settings.templates_dir = "/templates"
            yield mock_settings

    @pytest.fixture
    def mock_services(self):
        """Mock all services used in lifespan."""
        with patch('registry.main.server_service') as mock_server_service, \
             patch('registry.main.faiss_service') as mock_faiss_service, \
             patch('registry.main.health_service') as mock_health_service, \
             patch('registry.main.nginx_service') as mock_nginx_service:
            
            # Configure mocks
            mock_server_service.load_servers_and_state = Mock()
            mock_server_service.get_enabled_services.return_value = ["service1", "service2"]
            mock_server_service.get_server_info.return_value = {"name": "test_server"}
            
            mock_faiss_service.initialize = AsyncMock()
            
            mock_health_service.initialize = AsyncMock()
            mock_health_service.shutdown = AsyncMock()
            
            mock_nginx_service.generate_config = Mock()
            
            yield {
                'server_service': mock_server_service,
                'faiss_service': mock_faiss_service,
                'health_service': mock_health_service,
                'nginx_service': mock_nginx_service
            }

    @pytest.mark.asyncio
    async def test_lifespan_startup_success(self, mock_settings, mock_services):
        """Test successful application startup."""
        test_app = FastAPI()
        
        async with lifespan(test_app):
            # Verify all initialization steps were called
            mock_services['server_service'].load_servers_and_state.assert_called_once()
            mock_services['faiss_service'].initialize.assert_called_once()
            mock_services['health_service'].initialize.assert_called_once()
            mock_services['nginx_service'].generate_config.assert_called_once()
            
            # Verify log directory was created
            mock_settings.container_log_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @pytest.mark.asyncio
    async def test_lifespan_startup_server_service_failure(self, mock_settings, mock_services):
        """Test startup failure during server service initialization."""
        mock_services['server_service'].load_servers_and_state.side_effect = Exception("Server load failed")
        
        test_app = FastAPI()
        
        with pytest.raises(Exception, match="Server load failed"):
            async with lifespan(test_app):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_startup_faiss_service_failure(self, mock_settings, mock_services):
        """Test startup failure during FAISS service initialization."""
        mock_services['faiss_service'].initialize.side_effect = Exception("FAISS init failed")
        
        test_app = FastAPI()
        
        with pytest.raises(Exception, match="FAISS init failed"):
            async with lifespan(test_app):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_startup_health_service_failure(self, mock_settings, mock_services):
        """Test startup failure during health service initialization."""
        mock_services['health_service'].initialize.side_effect = Exception("Health init failed")
        
        test_app = FastAPI()
        
        with pytest.raises(Exception, match="Health init failed"):
            async with lifespan(test_app):
                pass

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_success(self, mock_settings, mock_services):
        """Test successful application shutdown."""
        test_app = FastAPI()
        
        async with lifespan(test_app):
            pass  # Startup completes normally
        
        # Verify shutdown was called
        mock_services['health_service'].shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_failure(self, mock_settings, mock_services):
        """Test shutdown with service failure."""
        mock_services['health_service'].shutdown.side_effect = Exception("Shutdown failed")
        
        test_app = FastAPI()
        
        # Should not raise exception, just log error
        async with lifespan(test_app):
            pass

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check endpoint."""
        response = await health_check()
        
        assert response == {"status": "healthy", "service": "mcp-gateway-registry"}

    def test_app_configuration(self):
        """Test FastAPI app configuration."""
        assert app.title == "MCP Gateway Registry"
        assert app.description == "A registry and management system for Model Context Protocol (MCP) servers"
        assert app.version == "1.0.0"

    def test_app_routes_registered(self):
        """Test that all routes are properly registered."""
        # Create test client
        client = TestClient(app)
        
        # Test basic health endpoint (should not require auth)
        with patch('registry.main.server_service'), \
             patch('registry.main.faiss_service'), \
             patch('registry.main.health_service'), \
             patch('registry.main.nginx_service'):
            
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy", "service": "mcp-gateway-registry"}

    def test_static_files_mounted(self):
        """Test that static files are properly mounted."""
        # Check if static files mount exists
        static_mounts = [mount for mount in app.routes if hasattr(mount, 'name') and mount.name == 'static']
        assert len(static_mounts) > 0
        assert static_mounts[0].path == "/static"

    def test_routers_included(self):
        """Test that all domain routers are included."""
        # Check that routes from different routers are present
        route_paths = [route.path for route in app.routes if hasattr(route, 'path')]
        
        # We can't easily test specific paths without mocking dependencies,
        # but we can test that multiple routes exist (more than just /health)
        assert len(route_paths) > 1

    @pytest.mark.asyncio
    async def test_nginx_config_generation(self, mock_settings, mock_services):
        """Test that Nginx configuration is generated with enabled servers."""
        test_app = FastAPI()
        
        # Setup enabled services
        enabled_services = ["service1", "service2"]
        mock_services['server_service'].get_enabled_services.return_value = enabled_services
        mock_services['server_service'].get_server_info.side_effect = lambda path: {"name": f"server_{path}"}
        
        async with lifespan(test_app):
            pass
        
        # Verify nginx config was generated with correct servers
        mock_services['nginx_service'].generate_config.assert_called_once()
        call_args = mock_services['nginx_service'].generate_config.call_args[0][0]
        
        # Check that enabled servers were passed to nginx config
        assert "service1" in call_args
        assert "service2" in call_args
        assert call_args["service1"]["name"] == "server_service1"
        assert call_args["service2"]["name"] == "server_service2"

    def test_logging_configuration(self):
        """Test that logging is properly configured."""
        import logging
        
        # Check that root logger has been configured
        root_logger = logging.getLogger()
        assert root_logger.level <= logging.INFO
        
        # Check that our module logger exists
        main_logger = logging.getLogger('registry.main')
        assert main_logger is not None 