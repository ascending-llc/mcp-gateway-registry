"""
Unit tests for authentication routes.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from registry.api.redirect_routes import signer
from itsdangerous import URLSafeTimedSerializer

from registry.api.redirect_routes import (
    get_oauth2_providers,
    login_form,
    oauth2_login_redirect,
    oauth2_callback,
    login_submit
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
        with patch('registry.api.redirect_routes.settings') as mock_settings:
            mock_settings.auth_server_url = "http://auth.example.com"
            mock_settings.auth_server_external_url = "http://auth.example.com"
            mock_settings.session_cookie_name = "session"
            mock_settings.session_max_age_seconds = 3600
            mock_settings.templates_dir = "/templates"
            mock_settings.registry_client_url = "http://localhost:8000/"
            yield mock_settings

    @pytest.fixture
    def mock_templates(self):
        """Mock Jinja2Templates."""
        with patch('registry.api.redirect_routes.templates') as mock_templates:
            yield mock_templates

    @pytest.fixture
    def mock_user_info(self):
        """Create properly signed user info using URLSafeTimedSerializer."""
        from registry.core.config import settings
        
        user_idp_data = {
            "username": "test.user@example.com",
            "email": "test.user@example.com",
            "name": "Test User",
            "groups": [],
            "provider": "entra",
            "auth_method": "oauth2",
            "idp_id": "12345-6789"
        }
        
        # Use the same signer as the auth routes
        signer = URLSafeTimedSerializer(settings.secret_key)
        signed_user_info = signer.dumps(user_idp_data)
        return signed_user_info

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
        
        with patch('registry.api.redirect_routes.get_oauth2_providers') as mock_get_providers:
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
        with patch('registry.api.redirect_routes.get_oauth2_providers') as mock_get_providers:
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
        # The route uses auth_server_external_url for the redirect
        expected_url = f"{mock_settings.auth_server_external_url}/oauth2/login/{provider}?redirect_uri=http://localhost:8000/&state="
        # The state param is dynamic, so just check the prefix
        assert response.headers["location"].startswith(expected_url)

    @pytest.mark.asyncio
    async def test_oauth2_login_redirect_exception(self, mock_request, mock_settings):
        """Test OAuth2 login redirect with exception."""
        provider = "invalid"
        
        with patch('registry.api.redirect_routes.logger') as mock_logger:
            # Force an exception by making str() fail
            mock_request.base_url = Mock()
            mock_request.base_url.__str__ = Mock(side_effect=Exception("URL error"))
            
            response = await oauth2_login_redirect(provider, mock_request)
            
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 302
            assert "/login?error=oauth2_redirect_failed" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_success(self, mock_request, mock_settings, mock_user_info):
        """Test successful OAuth2 callback with valid user."""
        mock_user = Mock()
        mock_user.id = "12345"
        mock_user.role = "user"
        mock_user.idp_id = "12345-6789"
        with patch("registry.api.redirect_routes.IUser.find_one", new=AsyncMock(return_value=mock_user)):
            response = await oauth2_callback(mock_request, mock_user_info)
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302
        assert response.headers["location"] == "http://localhost:8000"

    @pytest.mark.asyncio
    async def test_oauth2_callback_user_not_found(self, mock_request, mock_user_info):
        """Test OAuth2 callback when user is not found in DB."""
        with patch("registry.api.redirect_routes.IUser.find_one", new=AsyncMock(return_value=None)):
            response = await oauth2_callback(mock_request, mock_user_info)
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302
        assert "/login?error=User+not+found+in+registry" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_with_error(self, mock_request, mock_user_info):
        """Test OAuth2 callback with error parameter."""
        response = await oauth2_callback(mock_request, mock_user_info, error="oauth2_error", details="Provider error",)
        
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302
        assert "error=" in response.headers["location"]
        assert "OAuth2%20provider%20error" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_oauth2_init_failed(self, mock_request, mock_user_info):
        """Test OAuth2 callback with init failed error."""
        response = await oauth2_callback(mock_request, mock_user_info, error="oauth2_init_failed")
        
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302
        assert "Failed%20to%20initiate%20OAuth2%20login" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_oauth2_callback_failed(self, mock_request, mock_user_info):
        """Test OAuth2 callback with callback failed error."""
        response = await oauth2_callback(mock_request, mock_user_info, error="oauth2_callback_failed")
        
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302
        assert "OAuth2%20authentication%20failed" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth2_callback_general_exception(self, mock_request, mock_user_info):
        """Test OAuth2 callback with general exception."""
        with patch('registry.api.redirect_routes.logger') as mock_logger:
            # Force exception by making cookies access fail
            mock_request.cookies = Mock()
            mock_request.cookies.get = Mock(side_effect=Exception("Cookie error"))
            
            response = await oauth2_callback(mock_request, mock_user_info)
            
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 302
            assert "User+not+found+in+registry" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_login_submit_success(self, mock_request, mock_settings):
        """Test successful traditional login."""
        username = "testuser"
        password = "testpass"
        
        # Mock request headers to indicate traditional form submission (not API)
        mock_request.headers = {"accept": "text/html"}
        
        with patch('registry.api.redirect_routes.validate_login_credentials') as mock_validate, \
             patch('registry.api.redirect_routes.create_session_cookie') as mock_create_session:
            
            mock_validate.return_value = True
            mock_create_session.return_value = "session_data"
            
            response = await login_submit(mock_request, username, password)
            
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 303
            assert response.headers["location"] == "/"
            
            # Check cookie was set in response
            assert "set-cookie" in [h[0].decode().lower() for h in response.raw_headers]

    @pytest.mark.asyncio
    async def test_login_submit_failure(self, mock_request):
        """Test failed traditional login."""
        username = "testuser"
        password = "wrongpass"
        
        # Mock request headers to indicate traditional form submission
        mock_request.headers = {"accept": "text/html"}
        
        with patch('registry.api.redirect_routes.validate_login_credentials') as mock_validate:
            mock_validate.return_value = False
            
            response = await login_submit(mock_request, username, password)
            
            assert isinstance(response, RedirectResponse)
            assert response.status_code == 303
            assert "Invalid+username+or+password" in response.headers["location"]
