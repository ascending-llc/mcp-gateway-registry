import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock
from registry.api.v1.mcp.oauth_router import router
from registry.services.oauth.mcp_service import MCPService
from fastapi import Request

# Create a mock MCP service
mock_mcp_service = Mock(spec=MCPService)

# Create a mock OAuth service and attach it to MCP service
mock_oauth_service = Mock()
mock_mcp_service.oauth_service = mock_oauth_service

# Create a mock Connection service and attach it to MCP service
mock_connection_service = Mock()
mock_mcp_service.connection_service = mock_connection_service

# Wrap all mock methods to make them async
def make_async(func):
    async def async_func(*args, **kwargs):
        return func(*args, **kwargs)
    return async_func

# Make all mock methods async for oauth_service
for attr in dir(mock_oauth_service):
    if attr.startswith("mock_") or attr in ["initiate_oauth_flow", "get_tokens_by_flow_id", 
                                            "get_flow_status", "cancel_oauth_flow", "refresh_tokens",
                                            "complete_oauth_flow", "flow_manager"]:
        continue
    
    method = getattr(mock_oauth_service, attr, None)
    if callable(method) and not attr.startswith("_"):
        setattr(mock_oauth_service, attr, make_async(method))

# Make all mock methods async for connection_service
for attr in dir(mock_connection_service):
    if attr.startswith("mock_") or attr in ["update_connection_state", "get_connection", 
                                            "create_user_connection", "disconnect_user_connection"]:
        continue
    
    method = getattr(mock_connection_service, attr, None)
    if callable(method) and not attr.startswith("_"):
        setattr(mock_connection_service, attr, make_async(method))

# Also mock the flow_manager methods
mock_flow_manager = Mock()
mock_oauth_service.flow_manager = mock_flow_manager

# Make flow_manager methods async if any
for attr in dir(mock_flow_manager):
    method = getattr(mock_flow_manager, attr, None)
    if callable(method) and not attr.startswith("_"):
        setattr(mock_flow_manager, attr, make_async(method))


# Set up the TestClient with the necessary dependencies overridden
@pytest.fixture
def client():
    from fastapi import FastAPI
    
    app = FastAPI()
    
    app.include_router(router)

    @app.middleware("http")
    async def mock_authenticated_middleware(request: Request, call_next):
        # Set up authenticated user context
        request.state.user = {
            "username": "test_user",
            "user_id": "test_user",
            "id": "test_user_id",
            "groups": ["registry-admins"],
            "scopes": ["registry-admins"],
            "is_admin": True
        }
        request.state.is_authenticated = True
        response = await call_next(request)
        return response
    
    # Note: We need to override the actual get_mcp_service function from the module
    from registry.services.oauth.mcp_service import get_mcp_service
    
    # Override the get_mcp_service dependency
    app.dependency_overrides[get_mcp_service] = lambda: mock_mcp_service
    
    return TestClient(app)


class TestOAuthRouter:
    """Test cases for the OAuth router endpoints"""
    
    def test_initiate_oauth_flow_success(self, client):
        """Test successful initiation of OAuth flow"""
        # Mock the MCP service to return a valid response
        mock_mcp_service.oauth_service.initiate_oauth_flow = make_async(
            lambda *args, **kwargs: (
                "test_user-1234567890",
                "https://example.com/auth",
                None
            )
        )
        
        response = client.get("/v1/mcp/test_server/oauth/initiate")
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["flow_id"] == "test_user-1234567890"
        assert response_data["authorization_url"] == "https://example.com/auth"
        assert response_data["server_name"] == "test_server"
        assert response_data["user_id"] == "test_user"
        
    def test_initiate_oauth_flow_failure(self, client):
        """Test initiation of OAuth flow with error"""
        # Mock the MCP service to return an error
        mock_mcp_service.oauth_service.initiate_oauth_flow = make_async(
            lambda *args, **kwargs: (
                None,
                None,
                "Failed to initiate OAuth flow"
            )
        )
        
        response = client.get("/v1/mcp/test_server/oauth/initiate")
        
        assert response.status_code == 400
        assert "Failed to initiate OAuth flow" in response.json()["detail"]
        
    def test_get_oauth_tokens_success(self, client):
        """Test successful retrieval of OAuth tokens"""
        # Mock token response
        mock_token = Mock()
        mock_token.dict.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        mock_mcp_service.oauth_service.get_tokens_by_flow_id = make_async(
            lambda *args, **kwargs: mock_token
        )
        
        # The flow_id should start with the user_id to pass the validation
        flow_id = "test_user-1234567890"
        
        response = client.get(f"/v1/mcp/oauth/tokens/{flow_id}")
        
        assert response.status_code == 200
        response_data = response.json()
        assert "tokens" in response_data
        assert response_data["tokens"]["access_token"] == "test_access_token"
        
    def test_get_oauth_tokens_unauthorized(self, client):
        """Test retrieval of OAuth tokens for a different user"""
        # Flow ID doesn't match the current user
        flow_id = "other_user-1234567890"
        
        response = client.get(f"/v1/mcp/oauth/tokens/{flow_id}")
        
        assert response.status_code == 403
        
    def test_get_oauth_status_success(self, client):
        """Test successful retrieval of OAuth status"""
        # Mock status response
        mock_status = {
            "flow_id": "test_user-1234567890",
            "status": "completed",
            "server_name": "test_server"
        }
        mock_mcp_service.oauth_service.get_flow_status = make_async(
            lambda *args, **kwargs: mock_status
        )
        
        flow_id = "test_user-1234567890"
        
        response = client.get(f"/v1/mcp/oauth/status/{flow_id}")
        
        assert response.status_code == 200
        assert response.json() == mock_status
        
    def test_cancel_oauth_flow_success(self, client):
        """Test successful cancellation of OAuth flow"""
        # Mock successful cancellation
        mock_mcp_service.oauth_service.cancel_oauth_flow = make_async(
            lambda *args, **kwargs: (True, None)
        )
        
        # Mock connection service to verify it's called
        mock_mcp_service.connection_service.update_connection_state = make_async(
            lambda *args, **kwargs: None
        )
        
        response = client.post("/v1/mcp/oauth/cancel/test_server")
        
        assert response.status_code == 200
        assert response.json()["success"] == True
        assert response.json()["server_name"] == "test_server"
        assert "cancelled successfully" in response.json()["message"]
        
    def test_cancel_oauth_flow_failure(self, client):
        """Test failed cancellation of OAuth flow"""
        # Mock failed cancellation
        mock_mcp_service.oauth_service.cancel_oauth_flow = make_async(
            lambda *args, **kwargs: (False, "Failed to cancel flow")
        )
        
        response = client.post("/v1/mcp/oauth/cancel/test_server")
        
        assert response.status_code == 400
        assert "Failed to cancel flow" in response.json()["detail"]
        
    def test_refresh_oauth_tokens_success(self, client):
        """Test successful refresh of OAuth tokens"""
        # Mock successful refresh
        mock_mcp_service.oauth_service.refresh_tokens = make_async(
            lambda *args, **kwargs: (True, None)
        )
        
        # Mock connection service - simulate existing connection
        mock_connection = Mock()
        mock_mcp_service.connection_service.get_connection = make_async(
            lambda *args, **kwargs: mock_connection
        )
        mock_mcp_service.connection_service.update_connection_state = make_async(
            lambda *args, **kwargs: None
        )
        
        response = client.post("/v1/mcp/oauth/refresh/test_server")
        
        assert response.status_code == 200
        assert response.json()["success"] == True
        assert response.json()["server_name"] == "test_server"
        assert "refreshed successfully" in response.json()["message"]
        
    def test_refresh_oauth_tokens_failure(self, client):
        """Test failed refresh of OAuth tokens"""
        # Mock failed refresh
        mock_mcp_service.oauth_service.refresh_tokens = make_async(
            lambda *args, **kwargs: (False, "Failed to refresh tokens")
        )
        
        response = client.post("/v1/mcp/oauth/refresh/test_server")
        
        assert response.status_code == 400
        assert "Failed to refresh tokens" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
