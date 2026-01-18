"""
Pytest configuration and shared fixtures for auth_server tests.
"""
import os
import pytest
from typing import Generator
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def auth_server_app():
    """Import and return the auth server FastAPI app."""
    # Set required environment variables
    os.environ["AUTH_SERVER_EXTERNAL_URL"] = "http://localhost:8888"
    os.environ["AUTH_PROVIDER"] = "keycloak"
    os.environ["SECRET_KEY"] = "test-secret-key-for-testing"
    
    from auth_server.server import app
    return app


@pytest.fixture
def test_client(auth_server_app) -> Generator[TestClient, None, None]:
    """Create a test client for the auth server."""
    with TestClient(auth_server_app) as client:
        yield client


@pytest.fixture
def mock_auth_provider():
    """Mock authentication provider for testing."""
    mock_provider = Mock()
    mock_provider.get_jwks.return_value = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": "test-key-id",
                "n": "test-modulus",
                "e": "AQAB"
            }
        ]
    }
    
    with patch('auth_server.providers.factory.get_auth_provider', return_value=mock_provider):
        yield mock_provider


@pytest.fixture
def clear_device_storage():
    """Clear device flow and client registration storage before and after each test."""
    from auth_server.routes.oauth_device import (
        device_codes_storage,
        user_codes_storage,
        registered_clients
    )
    
    device_codes_storage.clear()
    user_codes_storage.clear()
    registered_clients.clear()
    
    yield
    
    device_codes_storage.clear()
    user_codes_storage.clear()
    registered_clients.clear()


# Test markers
pytest.mark.auth = pytest.mark.auth
pytest.mark.oauth_device = pytest.mark.oauth_device
pytest.mark.well_known = pytest.mark.well_known
pytest.mark.integration = pytest.mark.integration
pytest.mark.unit = pytest.mark.unit
