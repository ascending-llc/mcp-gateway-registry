"""
Unit tests for proxy_to_mcp_server function.
"""
import pytest
import json
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import httpx
from fastapi import Request, HTTPException
from fastapi.responses import Response, StreamingResponse

from registry.api.proxy_routes import (
    proxy_to_mcp_server, 
    _proxy_json_rpc_request,
    _build_authenticated_headers,
    _build_target_url,
    MCPGW_PATH
)
from registry.schemas.errors import (
    OAuthReAuthRequiredError,
    OAuthTokenError,
    MissingUserIdError,
    AuthenticationError
)
from registry.schemas.proxy_tool_schema import (
    ToolExecutionRequest,
    ToolExecutionResponse
)
from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument


@pytest.mark.unit
class TestProxyToMCPServer:
    """Unit tests for proxy_to_mcp_server function."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request object."""
        request = Mock(spec=Request)
        request.method = "POST"
        request.url = "http://test/mcpgw/test"
        request.headers = {
            "content-type": "application/json",
            "accept": "application/json",
            "host": "test.example.com"
        }
        request.body = AsyncMock(return_value=b'{"test": "data"}')
        return request

    @pytest.fixture
    def auth_context(self):
        """Create test auth context."""
        return {
            "username": "test-user",
            "user_id": "user-123",
            "client_id": "test-client",
            "scopes": ["mcp:execute"],
            "auth_method": "jwt",
            "server_name": "test-server",
            "tool_name": "test-tool"
        }

    @pytest.fixture
    def mock_server(self):
        """Create mock MCPServerDocument."""
        server = Mock(spec=MCPServerDocument)
        server.serverName = "test-server"
        server.path = "/test"
        server.config = {
            "url": "http://backend:8080/mcp",
            "apiKey": {
                "key": "test-api-key",
                "authorization_type": "bearer"
            },
            "transport": "streamable-http"
        }
        return server

    @pytest.fixture
    def server_config(self):
        """Create test server configuration."""
        return {
            "url": "http://backend:8080/mcp",
            "apiKey": {
                "key": "test-api-key",
                "authorization_type": "bearer"
            },
            "transport": "streamable-http"
        }

    @pytest.mark.asyncio
    async def test_regular_json_response(self, mock_request, auth_context, mock_server):
        """Test proxying regular JSON response."""
        target_url = "http://backend:8080/mcp"
        
        # Mock backend response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"result": "success"}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            
            mock_client.request = AsyncMock(return_value=mock_response)
            # Mock returns complete headers with auth
            mock_build_headers.return_value = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": "Bearer test-api-key",
                "User-Agent": "MCP-Gateway-Registry/1.0"
            }
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server=mock_server
            )
        
        assert isinstance(response, Response)
        assert response.status_code == 200
        assert response.body == b'{"result": "success"}'
        
        # Verify context headers were added
        call_args = mock_client.request.call_args
        headers = call_args.kwargs["headers"]
        assert headers["X-User"] == "test-user"
        assert headers["X-Username"] == "test-user"
        assert headers["X-Client-Id"] == "test-client"
        assert headers["X-Server-Name"] == "test-server"
        assert headers["X-Tool-Name"] == "test-tool"
        
        # Verify host header was removed
        assert "host" not in headers
        
        # Verify auth headers were added
        assert "Authorization" in headers
        
        # Verify _build_complete_headers_for_server was called with user_id
        mock_build_headers.assert_called_once_with(mock_server, "user-123")

    @pytest.mark.asyncio
    async def test_mcpgw_preserves_authorization_header(self, mock_request, auth_context):
        """Test that MCPGW path preserves client's Authorization header."""
        target_url = "http://backend:8080/mcp"
        
        # Add Authorization header to request
        mock_request.headers = {
            **mock_request.headers,
            "Authorization": "Bearer client-token-123"
        }
        
        # Mock MCPGW server
        mock_server = Mock(spec=MCPServerDocument)
        mock_server.path = MCPGW_PATH
        mock_server.serverName = "mcpgw"
        
        # Mock backend response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"result": "success"}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.request = AsyncMock(return_value=mock_response)
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server=mock_server
            )
        
        assert response.status_code == 200
        
        # Verify Authorization header was preserved for MCPGW
        call_args = mock_client.request.call_args
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer client-token-123"

    @pytest.mark.asyncio
    async def test_non_mcpgw_removes_authorization_header(self, mock_request, auth_context, mock_server):
        """Test that non-MCPGW paths remove gateway Authorization header."""
        target_url = "http://backend:8080/mcp"
        
        # Add gateway Authorization header to request
        mock_request.headers = {
            **mock_request.headers,
            "Authorization": "Bearer gateway-jwt-token"
        }
        
        # Mock backend response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"result": "success"}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            
            mock_client.request = AsyncMock(return_value=mock_response)
            # Mock returns backend auth
            mock_build_headers.return_value = {
                "Content-Type": "application/json",
                "Authorization": "Bearer backend-api-key"
            }
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server=mock_server
            )
        
        assert response.status_code == 200
        
        # Verify gateway Authorization was removed and replaced with backend auth
        call_args = mock_client.request.call_args
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer backend-api-key"
        assert headers["Authorization"] != "Bearer gateway-jwt-token"
        
        # Verify _build_complete_headers_for_server was called
        mock_build_headers.assert_called_once_with(mock_server, "user-123")

    @pytest.mark.asyncio
    async def test_sse_streaming_response(self, mock_request, auth_context, mock_server):
        """Test SSE streaming when client accepts and backend returns SSE."""
        target_url = "http://backend:8080/mcp"
        
        # Client accepts SSE
        mock_request.headers = {
            **mock_request.headers,
            "accept": "application/json, text/event-stream"
        }
        
        # Mock SSE response
        async def async_iter_bytes():
            yield b'event: message\n'
            yield b'data: {"type": "progress"}\n\n'
        
        # Create mock server for non-MCPGW path
        mock_server_for_sse = Mock(spec=MCPServerDocument)
        mock_server_for_sse.path = "/sse-server"
        mock_server_for_sse.serverName = "sse-server"
        
        mock_backend_response = Mock()
        mock_backend_response.status_code = 200
        mock_backend_response.headers = {
            "content-type": "text/event-stream",
            "mcp-session-id": "test-session-123"
        }
        mock_backend_response.aiter_bytes = async_iter_bytes
        
        mock_stream_context = Mock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_backend_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            mock_client.stream = Mock(return_value=mock_stream_context)
            mock_build_headers.return_value = {"Authorization": "Bearer test"}
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server=mock_server_for_sse
            )
        
        assert isinstance(response, StreamingResponse)
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"
        assert response.headers["Mcp-Session-Id"] == "test-session-123"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["X-Accel-Buffering"] == "no"

    @pytest.mark.asyncio
    async def test_backend_returns_json_when_client_accepts_sse(self, mock_request, auth_context, mock_server):
        """Test when client accepts SSE but backend returns JSON."""
        target_url = "http://backend:8080/mcp"
        
        # Client accepts SSE
        mock_request.headers = {
            **mock_request.headers,
            "accept": "application/json, text/event-stream"
        }
        
        # Mock JSON response (not SSE)
        mock_backend_response = Mock()
        mock_backend_response.status_code = 200
        mock_backend_response.headers = {"content-type": "application/json"}
        mock_backend_response.aread = AsyncMock(return_value=b'{"result": "success"}')
        
        mock_stream_context = Mock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_backend_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            mock_client.stream = Mock(return_value=mock_stream_context)
            mock_build_headers.return_value = {"Authorization": "Bearer test"}
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server=mock_server
            )
        
        assert isinstance(response, Response)
        assert response.status_code == 200
        assert response.body == b'{"result": "success"}'
        # Stream should be closed
        mock_stream_context.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_backend_error_response_logging(self, mock_request, auth_context, mock_server):
        """Test that backend error responses are logged."""
        target_url = "http://backend:8080/mcp"
        
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"error": "Bad request"}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes.logger") as mock_logger, \
             patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_build_headers.return_value = {"Authorization": "Bearer test"}
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server=mock_server
            )
        
        assert response.status_code == 400
        # Verify error was logged
        mock_logger.error.assert_called()
        error_msg = mock_logger.error.call_args[0][0]
        assert "400" in error_msg

    @pytest.mark.asyncio
    async def test_timeout_handling(self, mock_request, auth_context, mock_server):
        """Test timeout error handling."""
        target_url = "http://backend:8080/mcp"
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            mock_client.request = AsyncMock(
                side_effect=httpx.TimeoutException("Request timed out")
            )
            mock_build_headers.return_value = {"Authorization": "Bearer test"}
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server=mock_server
            )
        
        assert response.status_code == 504
        assert b"Gateway timeout" in response.body

    @pytest.mark.asyncio
    async def test_generic_exception_handling(self, mock_request, auth_context, mock_server):
        """Test generic exception handling."""
        target_url = "http://backend:8080/mcp"
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            mock_client.request = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            mock_build_headers.return_value = {"Authorization": "Bearer test"}
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server=mock_server
            )
        
        assert response.status_code == 502
        assert b"Bad gateway" in response.body
        assert b"Connection refused" in response.body

    @pytest.mark.asyncio
    async def test_context_headers_added(self, mock_request, auth_context, mock_server):
        """Test that all context headers are properly added."""
        target_url = "http://backend:8080/mcp"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"result": "success"}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_build_headers.return_value = {"Authorization": "Bearer test"}
            
            await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server=mock_server
            )
        
        call_args = mock_client.request.call_args
        headers = call_args.kwargs["headers"]
        
        # Verify all context headers
        assert headers["X-User"] == "test-user"
        assert headers["X-Username"] == "test-user"
        assert headers["X-Client-Id"] == "test-client"
        assert headers["X-Scopes"] == "mcp:execute"
        assert headers["X-Auth-Method"] == "jwt"
        assert headers["X-Server-Name"] == "test-server"
        assert headers["X-Tool-Name"] == "test-tool"
        assert "X-Original-URL" in headers

    @pytest.mark.asyncio
    async def test_binary_content_error_response(self, mock_request, auth_context, mock_server):
        """Test handling of binary error responses."""
        target_url = "http://backend:8080/mcp"
        
        # Mock binary error response that cannot be decoded as UTF-8
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.headers = {"content-type": "application/octet-stream"}
        # Use actual non-UTF8 bytes that will fail decode
        mock_response.content = b'\x80\x81\x82\x83'  # Invalid UTF-8 sequences
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes.logger") as mock_logger, \
             patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_build_headers.return_value = {"Authorization": "Bearer test"}
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server=mock_server
            )
        
        assert response.status_code == 500
        # Verify binary content logging
        mock_logger.error.assert_called()
        error_msg = mock_logger.error.call_args[0][0]
        assert "binary content" in error_msg and "4 bytes" in error_msg

    @pytest.mark.asyncio
    async def test_oauth_reauth_required_exception(self, mock_request, auth_context, mock_server):
        """Test OAuthReAuthRequiredError is converted to HTTPException."""
        target_url = "http://backend:8080/mcp"
        
        with patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            # Simulate OAuth re-auth required
            mock_build_headers.side_effect = OAuthReAuthRequiredError(
                "Re-authentication required",
                auth_url="https://oauth.example.com/authorize",
                server_name="test-server"
            )
            
            with pytest.raises(HTTPException) as exc_info:
                await proxy_to_mcp_server(
                    request=mock_request,
                    target_url=target_url,
                    auth_context=auth_context,
                    server=mock_server
                )
            
            assert exc_info.value.status_code == 401
            assert "OAuth re-authentication required" in exc_info.value.detail
            assert exc_info.value.headers["X-OAuth-URL"] == "https://oauth.example.com/authorize"

    @pytest.mark.asyncio
    async def test_missing_user_id_exception(self, mock_request, auth_context, mock_server):
        """Test MissingUserIdError is converted to HTTPException."""
        target_url = "http://backend:8080/mcp"
        
        with patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            # Simulate missing user ID
            mock_build_headers.side_effect = MissingUserIdError(
                "User ID required for OAuth",
                server_name="test-server"
            )
            
            with pytest.raises(HTTPException) as exc_info:
                await proxy_to_mcp_server(
                    request=mock_request,
                    target_url=target_url,
                    auth_context=auth_context,
                    server=mock_server
                )
            
            assert exc_info.value.status_code == 401
            assert "User authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_oauth_token_error_exception(self, mock_request, auth_context, mock_server):
        """Test OAuthTokenError is converted to HTTPException."""
        target_url = "http://backend:8080/mcp"
        
        with patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            # Simulate OAuth token error
            mock_build_headers.side_effect = OAuthTokenError(
                "Token refresh failed",
                server_name="test-server"
            )
            
            with pytest.raises(HTTPException) as exc_info:
                await proxy_to_mcp_server(
                    request=mock_request,
                    target_url=target_url,
                    auth_context=auth_context,
                    server=mock_server
                )
            
            assert exc_info.value.status_code == 401
            assert "Authentication error" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_generic_authentication_error_exception(self, mock_request, auth_context, mock_server):
        """Test generic AuthenticationError is converted to HTTPException."""
        target_url = "http://backend:8080/mcp"
        
        with patch("registry.api.proxy_routes._build_complete_headers_for_server") as mock_build_headers:
            # Simulate generic auth error
            mock_build_headers.side_effect = AuthenticationError(
                "Generic authentication failure"
            )
            
            with pytest.raises(HTTPException) as exc_info:
                await proxy_to_mcp_server(
                    request=mock_request,
                    target_url=target_url,
                    auth_context=auth_context,
                    server=mock_server
                )
            
            assert exc_info.value.status_code == 401
            assert "Authentication error" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.proxy
class TestProxyJsonRpcRequest:
    """Unit tests for _proxy_json_rpc_request helper function."""

    @pytest.fixture
    def mock_server(self):
        """Create mock MCPServerDocument."""
        server = Mock(spec=MCPServerDocument)
        server.serverName = "test-server"
        server.path = "/test"
        server.config = {
            "url": "http://backend:8080/mcp",
            "transport": "streamable-http"
        }
        return server

    @pytest.mark.asyncio
    async def test_backend_4xx_error_response_without_exception(self, mock_server):
        """
        Test that backend 4xx responses are handled correctly.
        httpx doesn't raise exceptions for non-2xx by default, so we must handle the status code.
        """
        target_url = "http://backend:8080/mcp"
        json_body = {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
        headers = {"Content-Type": "application/json"}
        
        # Mock backend 400 error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"error": {"code": -32602, "message": "Invalid params"}}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            
            response = await _proxy_json_rpc_request(
                target_url=target_url,
                json_body=json_body,
                headers=headers,
                accept_sse=False
            )
        
        # Verify response preserves error status and body
        assert response.status_code == 400
        assert response.body == b'{"error": {"code": -32602, "message": "Invalid params"}}'
        assert json.loads(response.body.decode('utf-8'))["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_backend_5xx_error_response_without_exception(self, mock_server):
        """
        Test that backend 5xx responses are handled correctly.
        """
        target_url = "http://backend:8080/mcp"
        json_body = {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
        headers = {"Content-Type": "application/json"}
        
        # Mock backend 500 error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"error": "Internal server error"}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            
            response = await _proxy_json_rpc_request(
                target_url=target_url,
                json_body=json_body,
                headers=headers,
                accept_sse=False
            )
        
        # Verify response preserves error status and body
        assert response.status_code == 500
        assert response.body == b'{"error": "Internal server error"}'

    @pytest.mark.asyncio
    async def test_backend_4xx_error_with_sse_fallback(self, mock_server):
        """
        Test that backend 4xx responses are handled when client accepts SSE but backend returns JSON error.
        """
        target_url = "http://backend:8080/mcp"
        json_body = {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
        headers = {"Accept": "application/json, text/event-stream"}
        
        # Mock backend 404 error response (non-SSE)
        mock_backend_response = Mock()
        mock_backend_response.status_code = 404
        mock_backend_response.headers = {"content-type": "application/json"}
        mock_backend_response.aread = AsyncMock(return_value=b'{"error": "Tool not found"}')
        
        mock_stream_context = Mock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_backend_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.stream = Mock(return_value=mock_stream_context)
            
            response = await _proxy_json_rpc_request(
                target_url=target_url,
                json_body=json_body,
                headers=headers,
                accept_sse=True
            )
        
        # Verify error response is returned correctly
        assert response.status_code == 404
        assert response.body == b'{"error": "Tool not found"}'
        
        # Verify stream was closed
        mock_stream_context.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_json_response(self, mock_server):
        """Test successful JSON response without SSE."""
        target_url = "http://backend:8080/mcp"
        json_body = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "test"}}
        headers = {"Content-Type": "application/json"}
        
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"jsonrpc": "2.0", "result": {"data": "success"}}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)
            
            response = await _proxy_json_rpc_request(
                target_url=target_url,
                json_body=json_body,
                headers=headers,
                accept_sse=False
            )
        
        assert response.status_code == 200
        assert response.body == b'{"jsonrpc": "2.0", "result": {"data": "success"}}'

    @pytest.mark.asyncio
    async def test_sse_streaming_response(self, mock_server):
        """Test true SSE streaming without buffering."""
        target_url = "http://backend:8080/mcp"
        json_body = {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
        headers = {"Accept": "text/event-stream"}
        
        # Mock SSE streaming response
        async def async_iter_bytes():
            yield b'event: message\n'
            yield b'data: {"progress": 50}\n\n'
            yield b'event: complete\n'
            yield b'data: {"result": "done"}\n\n'
        
        mock_backend_response = Mock()
        mock_backend_response.status_code = 200
        mock_backend_response.headers = {
            "content-type": "text/event-stream",
            "mcp-session-id": "session-123"
        }
        mock_backend_response.aiter_bytes = async_iter_bytes
        
        mock_stream_context = Mock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_backend_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.stream = Mock(return_value=mock_stream_context)
            
            response = await _proxy_json_rpc_request(
                target_url=target_url,
                json_body=json_body,
                headers=headers,
                accept_sse=True
            )
        
        # Verify it returns StreamingResponse
        assert isinstance(response, StreamingResponse)
        assert response.status_code == 200
        assert response.media_type == "text/event-stream"
        assert response.headers["Mcp-Session-Id"] == "session-123"
        assert response.headers["Cache-Control"] == "no-cache"

    @pytest.mark.asyncio
    async def test_timeout_exception_handling(self, mock_server):
        """Test timeout exception is converted to 504."""
        target_url = "http://backend:8080/mcp"
        json_body = {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
        headers = {"Content-Type": "application/json"}
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            
            with pytest.raises(HTTPException) as exc_info:
                await _proxy_json_rpc_request(
                    target_url=target_url,
                    json_body=json_body,
                    headers=headers,
                    accept_sse=False
                )
            
            assert exc_info.value.status_code == 504
            assert "Gateway timeout" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_http_error_exception_handling(self, mock_server):
        """Test HTTP error exception is converted to 502."""
        target_url = "http://backend:8080/mcp"
        json_body = {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
        headers = {"Content-Type": "application/json"}
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))
            
            with pytest.raises(HTTPException) as exc_info:
                await _proxy_json_rpc_request(
                    target_url=target_url,
                    json_body=json_body,
                    headers=headers,
                    accept_sse=False
                )
            
            assert exc_info.value.status_code == 502
            assert "Bad gateway" in exc_info.value.detail
