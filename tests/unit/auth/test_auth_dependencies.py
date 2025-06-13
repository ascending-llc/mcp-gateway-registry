"""
Unit tests for authentication dependencies.
"""
import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException, status
from itsdangerous import SignatureExpired, BadSignature

from registry.auth.dependencies import (
    api_auth, web_auth, get_current_user, 
    create_session_cookie, validate_login_credentials
)


@pytest.mark.unit
@pytest.mark.auth
class TestAuthDependencies:
    """Test suite for authentication dependencies."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock()
        settings.secret_key = "test_secret_key_12345"
        settings.session_cookie_name = "session"
        settings.session_max_age_seconds = 3600
        settings.admin_user = "admin"
        settings.admin_password = "password123"
        return settings

    @pytest.fixture
    def valid_session_cookie(self):
        """Create a valid session cookie for testing."""
        return create_session_cookie("testuser", "traditional", "local")

    def test_create_session_cookie_success(self):
        """Test creating session cookie successfully."""
        username = "testuser"
        auth_method = "oauth2"
        provider = "google"
        
        cookie = create_session_cookie(username, auth_method, provider)
        
        assert isinstance(cookie, str)
        assert len(cookie) > 0

    def test_create_session_cookie_defaults(self):
        """Test creating session cookie with default values."""
        username = "testuser"
        
        cookie = create_session_cookie(username)
        
        assert isinstance(cookie, str)
        assert len(cookie) > 0

    def test_validate_login_credentials_success(self, mock_settings):
        """Test successful credential validation."""
        with patch('registry.auth.dependencies.settings', mock_settings):
            result = validate_login_credentials("admin", "password123")
            assert result is True

    def test_validate_login_credentials_wrong_username(self, mock_settings):
        """Test credential validation with wrong username."""
        with patch('registry.auth.dependencies.settings', mock_settings):
            result = validate_login_credentials("wronguser", "password123")
            assert result is False

    def test_validate_login_credentials_wrong_password(self, mock_settings):
        """Test credential validation with wrong password."""
        with patch('registry.auth.dependencies.settings', mock_settings):
            result = validate_login_credentials("admin", "wrongpassword")
            assert result is False

    def test_validate_login_credentials_both_wrong(self, mock_settings):
        """Test credential validation with both wrong."""
        with patch('registry.auth.dependencies.settings', mock_settings):
            result = validate_login_credentials("wronguser", "wrongpassword")
            assert result is False

    def test_get_current_user_success(self, mock_settings, valid_session_cookie):
        """Test getting current user with valid session."""
        with patch('registry.auth.dependencies.settings', mock_settings):
            username = get_current_user(valid_session_cookie)
            assert username == "testuser"

    def test_get_current_user_no_session(self, mock_settings):
        """Test getting current user with no session cookie."""
        with patch('registry.auth.dependencies.settings', mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                get_current_user(None)
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Not authenticated" in exc_info.value.detail

    def test_get_current_user_expired_session(self, mock_settings):
        """Test getting current user with expired session."""
        with patch('registry.auth.dependencies.settings', mock_settings), \
             patch('registry.auth.dependencies.signer') as mock_signer:
            
            mock_signer.loads.side_effect = SignatureExpired("Session expired")
            
            with pytest.raises(HTTPException) as exc_info:
                get_current_user("expired_session")
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Session expired" in exc_info.value.detail

    def test_get_current_user_invalid_signature(self, mock_settings):
        """Test getting current user with invalid signature."""
        with patch('registry.auth.dependencies.settings', mock_settings), \
             patch('registry.auth.dependencies.signer') as mock_signer:
            
            mock_signer.loads.side_effect = BadSignature("Invalid signature")
            
            with pytest.raises(HTTPException) as exc_info:
                get_current_user("invalid_session")
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid session" in exc_info.value.detail

    def test_get_current_user_no_username_in_session(self, mock_settings):
        """Test getting current user when session has no username."""
        with patch('registry.auth.dependencies.settings', mock_settings):
            # Create a session cookie without username field using the real signer
            from registry.auth.dependencies import signer
            session_data = {"other_field": "value"}  # No username field
            session_cookie = signer.dumps(session_data)
            
            with pytest.raises(HTTPException) as exc_info:
                get_current_user(session_cookie)
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Session validation failed" in exc_info.value.detail

    def test_api_auth_success(self, mock_settings, valid_session_cookie):
        """Test API authentication success."""
        with patch('registry.auth.dependencies.settings', mock_settings):
            username = api_auth(valid_session_cookie)
            assert username == "testuser"

    def test_api_auth_no_session(self, mock_settings):
        """Test API authentication with no session."""
        with patch('registry.auth.dependencies.settings', mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                api_auth(None)
            
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "API access requires authentication" in exc_info.value.detail

    def test_web_auth_success(self, mock_settings, valid_session_cookie):
        """Test web authentication success."""
        with patch('registry.auth.dependencies.settings', mock_settings):
            username = web_auth(valid_session_cookie)
            assert username == "testuser"

    def test_web_auth_no_session(self, mock_settings):
        """Test web authentication with no session - should redirect."""
        with patch('registry.auth.dependencies.settings', mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                web_auth(None)
            
            assert exc_info.value.status_code == status.HTTP_307_TEMPORARY_REDIRECT
            assert "Authentication required" in exc_info.value.detail
            assert exc_info.value.headers["Location"] == "/login" 