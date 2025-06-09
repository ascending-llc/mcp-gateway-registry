"""
Unit tests for authentication routes.
"""
import pytest
import urllib.parse
from unittest.mock import Mock, patch, AsyncMock
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from registry.auth.routes import (
    router, 
    get_oauth2_providers,
    login_form,
    oauth2_login_redirect,
    oauth2_callback,
    login_submit,
    logout
)


@pytest.mark.unit
@pytest.mark.auth
class TestAuthRoutes:
    """Test suite for authentication routes."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request object."""
        request = Mock(spec=Request)
        request.base_url = "http://localhost:8000/"
        request.cookies = {}
        return request

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        with patch('registry.auth.routes.settings') as mock_settings:
            mock_settings.auth_server_url = "http://auth.example.com"
            mock_settings.session_cookie_name = "session"
            mock_settings.session_max_age_seconds = 3600
            mock_settings.templates_dir = "/templates"
            yield mock_settings

    @pytest.fixture
    def mock_templates(self):
        """Mock Jinja2Templates."""
        with patch('registry.auth.routes.templates') as mock_templates:
            yield mock_templates

    @pytest.mark.asyncio
    async def test_get_oauth2_providers_success(self):
        """Test successful OAuth2 providers fetch."""
        mock_providers = [
            {"name": "google", "display_name": "Google"},
            {"name": "github", "display_name": "GitHub"}
        ]
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"providers": mock_providers}
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            providers = await get_oauth2_providers()
            
            assert providers == mock_providers

    @pytest.mark.asyncio
    async def test_get_oauth2_providers_failure(self):
        """Test OAuth2 providers fetch failure."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = Exception("Network error")
            
            providers = await get_oauth2_providers()
            
            assert providers == []

    @pytest.mark.asyncio
    async def test_get_oauth2_providers_bad_response(self):
        """Test OAuth2 providers fetch with bad response."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 404
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            providers = await get_oauth2_providers()
            
            assert providers == []

    @pytest.mark.asyncio
    async def test_login_form_success(self, mock_request, mock_templates):
        """Test login form rendering."""
        mock_providers = [{"name": "google", "display_name": "Google"}]
        
        with patch('registry.auth.routes.get_oauth2_providers') as mock_get_providers:
            mock_get_providers.return_value = mock_providers
            mock_templates.TemplateResponse.return_value = HTMLResponse("login form")
            
            response = await login_form(mock_request)
            
            mock_templates.TemplateResponse.assert_called_once_with(
                "login.html",
                {
                    "request": mock_request,
                    "error": None,
                    "oauth_providers": mock_providers
                }
            )

    @pytest.mark.asyncio
    async def test_login_form_with_error(self, mock_request, mock_templates):
        """Test login form rendering with error message."""
        with patch('registry.auth.routes.get_oauth2_providers') as mock_get_providers:
            mock_get_providers.return_value = []
            
            response = await login_form(mock_request, error="Invalid credentials")
            
            mock_templates.TemplateResponse.assert_called_once_with(
                "login.html",
                {
                    "request": mock_request,
                    "error": "Invalid credentials",
                    "oauth_providers": []
                }
            )

    @pytest.mark.asyncio
    async def test_oauth2_login_redirect_success(self, mock_request, mock_settings):
        """Test successful OAuth2 login redirect."""
        provider = "google"
        
        response = await oauth2_login_redirect(provider, mock_request)
        
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302
        expected_url = f"{mock_settings.auth_server_url}/oauth2/login/{provider}?redirect_uri=http://localhost:8000/"
        assert response.headers["location"] == expected_url

    @pytest.mark.asyncio
    async def test_oauth2_login_redirect_exception(self, mock_request, mock_settings):
        """Test OAuth2 login redirect with exception."""
        provider = "invalid"
        
        with patch('registry.auth.routes.logger') as mock_logger:
            # Force an exception by making str() fail
            mock_request.base_url = Mock()
            mock_request.base_url.__str__ = Mock(side_effect=Exception("URL error"))
            
            response = await oauth2_login_redirect(provider, mock_request)
            
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 302
            assert "/login?error=oauth2_redirect_failed" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_success(self, mock_request, mock_settings):
        """Test successful OAuth2 callback."""
        # Mock valid session cookie
        session_data = {"username": "testuser", "auth_method": "google"}
        mock_request.cookies = {mock_settings.session_cookie_name: "valid_session"}
        
        with patch('registry.auth.dependencies.signer') as mock_signer:
            mock_signer.loads.return_value = session_data
            
            response = await oauth2_callback(mock_request)
            
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 302
            assert response.headers["location"] == "/"

    @pytest.mark.asyncio
    async def test_oauth2_callback_with_error(self, mock_request):
        """Test OAuth2 callback with error parameter."""
        response = await oauth2_callback(mock_request, error="oauth2_error", details="Provider error")
        
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302
        assert "error=" in response.headers["location"]
        assert "OAuth2%20provider%20error" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_oauth2_init_failed(self, mock_request):
        """Test OAuth2 callback with init failed error."""
        response = await oauth2_callback(mock_request, error="oauth2_init_failed")
        
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302
        assert "Failed%20to%20initiate%20OAuth2%20login" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_oauth2_callback_failed(self, mock_request):
        """Test OAuth2 callback with callback failed error."""
        response = await oauth2_callback(mock_request, error="oauth2_callback_failed")
        
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302
        assert "OAuth2%20authentication%20failed" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_no_session_cookie(self, mock_request, mock_settings):
        """Test OAuth2 callback without session cookie."""
        mock_request.cookies = {}
        
        response = await oauth2_callback(mock_request)
        
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302
        assert "oauth2_session_invalid" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_invalid_session(self, mock_request, mock_settings):
        """Test OAuth2 callback with invalid session cookie."""
        mock_request.cookies = {mock_settings.session_cookie_name: "invalid_session"}
        
        with patch('registry.auth.dependencies.signer') as mock_signer:
            mock_signer.loads.side_effect = Exception("Invalid signature")
            
            response = await oauth2_callback(mock_request)
            
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 302
            assert "oauth2_session_invalid" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_general_exception(self, mock_request):
        """Test OAuth2 callback with general exception."""
        with patch('registry.auth.routes.logger') as mock_logger:
            # Force exception by making cookies access fail
            mock_request.cookies = Mock()
            mock_request.cookies.get = Mock(side_effect=Exception("Cookie error"))
            
            response = await oauth2_callback(mock_request)
            
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 302
            assert "oauth2_callback_error" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_login_submit_success(self, mock_settings):
        """Test successful traditional login."""
        username = "testuser"
        password = "testpass"
        
        with patch('registry.auth.routes.validate_login_credentials') as mock_validate, \
             patch('registry.auth.routes.create_session_cookie') as mock_create_session:
            
            mock_validate.return_value = True
            mock_create_session.return_value = "session_data"
            
            response = await login_submit(username, password)
            
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 303
            assert response.headers["location"] == "/"
            
            # Check cookie was set
            assert mock_settings.session_cookie_name in response.raw_headers[2][1].decode()

    @pytest.mark.asyncio
    async def test_login_submit_failure(self):
        """Test failed traditional login."""
        username = "testuser"
        password = "wrongpass"
        
        with patch('registry.auth.routes.validate_login_credentials') as mock_validate:
            mock_validate.return_value = False
            
            response = await login_submit(username, password)
            
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 303
            assert "Invalid+username+or+password" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_logout(self, mock_settings):
        """Test logout functionality."""
        response = await logout()
        
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        
        # Check that cookie deletion header is present
        cookie_headers = [h for h in response.raw_headers if h[0] == b'set-cookie']
        assert len(cookie_headers) > 0
        cookie_value = cookie_headers[0][1].decode()
        assert mock_settings.session_cookie_name in cookie_value
        assert "expires=" in cookie_value.lower()  # Cookie deletion sets expires in past 