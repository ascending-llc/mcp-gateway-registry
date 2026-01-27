"""
Integration tests for proxy routes - specifically tool execution endpoint.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, Mock
import httpx

from registry.main import app
from registry.auth import dependencies as auth_dependencies
from fastapi import Request
from packages.models.extended_mcp_server import ExtendedMCPServer as Server


@pytest.mark.integration
@pytest.mark.proxy
class TestProxyToolExecutionRoutes:
    """Integration coverage for /proxy/tools/call endpoint."""

    def setup_method(self):
        """Override auth dependency for each test."""
        user_context = {
            "username": "test-user",
            "user_id": "test-user-id",
            "is_admin": False,
            "accessible_servers": ["/tavilysearch"],
            "accessible_agents": ["all"],
            "accessible_services": ["all"],
            "groups": ["registry-users"],
            "scopes": ["mcp:execute"],
            "ui_permissions": {},
            "can_modify_servers": False,
            "auth_method": "jwt",
            "provider": "keycloak",
        }

        def _mock_get_user(request: Request):
            request.state.user = user_context
            request.state.is_authenticated = True
            return user_context

        app.dependency_overrides[auth_dependencies.get_current_user_by_mid] = _mock_get_user

    def teardown_method(self):
        """Clean up dependency overrides."""
        app.dependency_overrides.clear()

    def test_execute_tool_success_json_response(self, test_client: TestClient):
        """Successful tool execution returns JSON response."""
        # Mock server lookup
        mock_server = Mock(spec=Server)
        mock_server.path = "/tavilysearch"
        mock_server.config = {
            "url": "http://localhost:8080/mcp",
            "transport": "streamable-http"
        }
        
        # Mock HTTP response from backend MCP server
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"result": "success"}'
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "Search results for Donald Trump..."
                    }
                ]
            }
        }
        mock_response.raise_for_status = Mock()
        
        with patch("registry.api.proxy_routes.server_service_v1.get_server_by_id", 
                   new_callable=AsyncMock) as mock_get_server, \
             patch("httpx.AsyncClient") as mock_client_cls:
            
            mock_get_server.return_value = mock_server
            
            # Setup mock HTTP client
            mock_client = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            
            response = test_client.post(
                "/proxy/tools/call",
                json={
                    "server_id": "6972e222755441652c23090f",
                    "server_path": "/tavilysearch",
                    "tool_name": "tavily_search",
                    "arguments": {
                        "query": "Donald Trump news"
                    }
                }
            )

        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert data["success"] is True
        assert data["server_id"] == "6972e222755441652c23090f"
        assert data["server_path"] == "/tavilysearch"
        assert data["tool_name"] == "tavily_search"
        assert "result" in data
        assert data["result"]["jsonrpc"] == "2.0"

    def test_execute_tool_success_sse_response(self, test_client: TestClient):
        """Tool execution returns SSE stream when backend sends SSE."""
        # Mock server lookup
        mock_server = Mock(spec=Server)
        mock_server.path = "/tavilysearch"
        mock_server.config = {
            "url": "http://localhost:8080/mcp",
            "transport": "streamable-http"
        }
        
        # Mock SSE response from backend
        sse_content = "event: message\ndata: {\"type\": \"progress\", \"value\": 50}\n\n"
        mock_response = Mock()
        mock_response.headers = {"content-type": "text/event-stream"}
        mock_response.text = sse_content
        mock_response.raise_for_status = Mock()
        
        with patch("registry.api.proxy_routes.server_service_v1.get_server_by_id", 
                   new_callable=AsyncMock) as mock_get_server, \
             patch("httpx.AsyncClient") as mock_client_cls:
            
            mock_get_server.return_value = mock_server
            
            mock_client = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            
            response = test_client.post(
                "/proxy/tools/call",
                json={
                    "server_id": "6972e222755441652c23090f",
                    "server_path": "/tavilysearch",
                    "tool_name": "tavily_search",
                    "arguments": {"query": "test"}
                }
            )

        assert response.status_code == 200
        # Check content-type allows charset parameter
        assert "text/event-stream" in response.headers["content-type"]
        assert "event:" in response.text or "data:" in response.text

    def test_execute_tool_server_not_found(self, test_client: TestClient):
        """Tool execution fails when server not found."""
        with patch("registry.api.proxy_routes.server_service_v1.get_server_by_id", 
                   new_callable=AsyncMock) as mock_get_server:
            
            mock_get_server.return_value = None
            
            response = test_client.post(
                "/proxy/tools/call",
                json={
                    "server_id": "nonexistent-id",
                    "server_path": "/tavilysearch",
                    "tool_name": "tavily_search",
                    "arguments": {"query": "test"}
                }
            )

        assert response.status_code == 404

    def test_execute_tool_missing_server_url(self, test_client: TestClient):
        """Tool execution fails with 500 when server URL not configured."""
        mock_server = Mock(spec=Server)
        mock_server.path = "/tavilysearch"
        mock_server.config = {}  # Missing url
        
        with patch("registry.api.proxy_routes.server_service_v1.get_server_by_id", 
                   new_callable=AsyncMock) as mock_get_server:
            
            mock_get_server.return_value = mock_server
            
            response = test_client.post(
                "/proxy/tools/call",
                json={
                    "server_id": "6972e222755441652c23090f",
                    "server_path": "/tavilysearch",
                    "tool_name": "tavily_search",
                    "arguments": {"query": "test"}
                }
            )

        assert response.status_code == 500
        assert "Server URL not configured" in response.json()["detail"]

    def test_execute_tool_http_error(self, test_client: TestClient):
        """Tool execution handles HTTP errors from backend server."""
        mock_server = Mock(spec=Server)
        mock_server.path = "/tavilysearch"
        mock_server.config = {"url": "http://localhost:8080/mcp"}
        
        with patch("registry.api.proxy_routes.server_service_v1.get_server_by_id", 
                   new_callable=AsyncMock) as mock_get_server, \
             patch("httpx.AsyncClient") as mock_client_cls:
            
            mock_get_server.return_value = mock_server
            
            # Simulate HTTP error
            mock_client = Mock()
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "500 Server Error",
                    request=Mock(),
                    response=Mock(status_code=500)
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            
            response = test_client.post(
                "/proxy/tools/call",
                json={
                    "server_id": "6972e222755441652c23090f",
                    "server_path": "/tavilysearch",
                    "tool_name": "tavily_search",
                    "arguments": {"query": "test"}
                }
            )

        assert response.status_code == 200  # Returns 200 but with error in body
        data = response.json()
        assert data["success"] is False
        assert "HTTP error" in data["error"]

    def test_execute_tool_with_authentication(self, test_client: TestClient):
        """Tool execution includes authentication headers for backend server."""
        mock_server = Mock(spec=Server)
        mock_server.path = "/tavilysearch"
        mock_server.config = {
            "url": "http://localhost:8080/mcp",
            "apiKey": {
                "key": "test-api-key",
                "authorization_type": "bearer"
            }
        }
        
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"result": "success"}'
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {}}
        mock_response.raise_for_status = Mock()
        
        with patch("registry.api.proxy_routes.server_service_v1.get_server_by_id", 
                   new_callable=AsyncMock) as mock_get_server, \
             patch("httpx.AsyncClient") as mock_client_cls, \
             patch("registry.api.proxy_routes.decrypt_auth_fields") as mock_decrypt, \
             patch("registry.api.proxy_routes._build_headers_for_server") as mock_build_headers:
            
            mock_get_server.return_value = mock_server
            mock_decrypt.return_value = mock_server.config
            mock_build_headers.return_value = {"Authorization": "Bearer test-api-key"}
            
            mock_client = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            
            response = test_client.post(
                "/proxy/tools/call",
                json={
                    "server_id": "6972e222755441652c23090f",
                    "server_path": "/tavilysearch",
                    "tool_name": "tavily_search",
                    "arguments": {"query": "test"}
                }
            )

        assert response.status_code == 200
        
        # Verify authentication functions were called
        mock_decrypt.assert_called_once()
        mock_build_headers.assert_called_once()

    def test_execute_tool_adds_tracking_headers(self, test_client: TestClient):
        """Tool execution adds user tracking headers to backend request."""
        mock_server = Mock(spec=Server)
        mock_server.path = "/tavilysearch"
        mock_server.config = {"url": "http://localhost:8080/mcp"}
        
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"result": "success"}'
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {}}
        mock_response.raise_for_status = Mock()
        
        captured_headers = {}
        
        async def capture_post(*args, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return mock_response
        
        with patch("registry.api.proxy_routes.server_service_v1.get_server_by_id", 
                   new_callable=AsyncMock) as mock_get_server, \
             patch("httpx.AsyncClient") as mock_client_cls:
            
            mock_get_server.return_value = mock_server
            
            mock_client = Mock()
            mock_client.post = AsyncMock(side_effect=capture_post)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            
            response = test_client.post(
                "/proxy/tools/call",
                json={
                    "server_id": "6972e222755441652c23090f",
                    "server_path": "/tavilysearch",
                    "tool_name": "tavily_search",
                    "arguments": {"query": "test"}
                }
            )

        assert response.status_code == 200
        
        # Verify tracking headers were added
        assert "X-User" in captured_headers
        assert "X-Username" in captured_headers
        assert "X-Tool-Name" in captured_headers
        assert captured_headers["X-User"] == "test-user"
        assert captured_headers["X-Username"] == "test-user"
        assert captured_headers["X-Tool-Name"] == "tavily_search"

    def test_execute_tool_builds_jsonrpc_request(self, test_client: TestClient):
        """Tool execution builds proper JSON-RPC request for MCP server."""
        mock_server = Mock(spec=Server)
        mock_server.path = "/tavilysearch"
        mock_server.config = {"url": "http://localhost:8080/mcp"}
        
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"result": "success"}'
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {}}
        mock_response.raise_for_status = Mock()
        
        captured_json = {}
        
        async def capture_post(*args, **kwargs):
            captured_json.update(kwargs.get("json", {}))
            return mock_response
        
        with patch("registry.api.proxy_routes.server_service_v1.get_server_by_id", 
                   new_callable=AsyncMock) as mock_get_server, \
             patch("httpx.AsyncClient") as mock_client_cls:
            
            mock_get_server.return_value = mock_server
            
            mock_client = Mock()
            mock_client.post = AsyncMock(side_effect=capture_post)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            
            response = test_client.post(
                "/proxy/tools/call",
                json={
                    "server_id": "6972e222755441652c23090f",
                    "server_path": "/tavilysearch",
                    "tool_name": "tavily_search",
                    "arguments": {
                        "query": "Donald Trump",
                        "max_results": 5
                    }
                }
            )

        assert response.status_code == 200
        
        # Verify JSON-RPC request structure
        assert captured_json["jsonrpc"] == "2.0"
        assert captured_json["id"] == 1
        assert captured_json["method"] == "tools/call"
        assert "params" in captured_json
        assert captured_json["params"]["name"] == "tavily_search"
        assert captured_json["params"]["arguments"]["query"] == "Donald Trump"
        assert captured_json["params"]["arguments"]["max_results"] == 5

    def test_execute_tool_timeout_configuration(self, test_client: TestClient):
        """Tool execution uses 60 second timeout for backend requests."""
        mock_server = Mock(spec=Server)
        mock_server.path = "/tavilysearch"
        mock_server.config = {"url": "http://localhost:8080/mcp"}
        
        with patch("registry.api.proxy_routes.server_service_v1.get_server_by_id", 
                   new_callable=AsyncMock) as mock_get_server, \
             patch("httpx.AsyncClient") as mock_client_cls:
            
            mock_get_server.return_value = mock_server
            
            # Simulate timeout
            mock_client = Mock()
            mock_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("Request timed out")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client
            
            response = test_client.post(
                "/proxy/tools/call",
                json={
                    "server_id": "6972e222755441652c23090f",
                    "server_path": "/tavilysearch",
                    "tool_name": "tavily_search",
                    "arguments": {"query": "test"}
                }
            )

        # Should handle timeout gracefully
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "HTTP error" in data["error"]
        
        # Verify AsyncClient was created with timeout
        mock_client_cls.assert_called_with(timeout=60.0)
