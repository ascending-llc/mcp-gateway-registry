"""
Unit tests for proxy_to_mcp_server function.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx
from fastapi import Request
from fastapi.responses import Response, StreamingResponse

from registry.api.proxy_routes import proxy_to_mcp_server, MCPGW_PATH


@pytest.mark.unit
@pytest.mark.proxy
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
            "client_id": "test-client",
            "scopes": ["mcp:execute"],
            "auth_method": "jwt",
            "server_name": "test-server",
            "tool_name": "test-tool"
        }

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
    async def test_regular_json_response(self, mock_request, auth_context, server_config):
        """Test proxying regular JSON response."""
        target_url = "http://backend:8080/mcp"
        
        # Mock backend response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"result": "success"}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes.decrypt_auth_fields") as mock_decrypt, \
             patch("registry.api.proxy_routes._build_server_info_for_mcp_client") as mock_build_info, \
             patch("registry.api.proxy_routes._build_headers_for_server") as mock_build_headers:
            
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_decrypt.return_value = server_config
            mock_build_info.return_value = {"headers": [{"Authorization": "Bearer test-api-key"}]}
            mock_build_headers.return_value = {"Authorization": "Bearer test-api-key"}
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server_path="/test",
                server_config=server_config
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
        
        # Verify backend auth headers were added
        assert "Authorization" in headers
        
        # Verify both auth header building functions were called
        mock_decrypt.assert_called_once_with(server_config)
        mock_build_info.assert_called_once_with(server_config, [])
        mock_build_headers.assert_called_once_with(server_config)

    @pytest.mark.asyncio
    async def test_mcpgw_preserves_authorization_header(self, mock_request, auth_context):
        """Test that MCPGW path preserves client's Authorization header."""
        target_url = "http://backend:8080/mcp"
        
        # Add Authorization header to request
        mock_request.headers = {
            **mock_request.headers,
            "Authorization": "Bearer client-token-123"
        }
        
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
                server_path=MCPGW_PATH,  # Special MCPGW handling
                server_config=None
            )
        
        assert response.status_code == 200
        
        # Verify Authorization header was preserved for MCPGW
        call_args = mock_client.request.call_args
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer client-token-123"

    @pytest.mark.asyncio
    async def test_non_mcpgw_removes_authorization_header(self, mock_request, auth_context, server_config):
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
             patch("registry.api.proxy_routes.decrypt_auth_fields") as mock_decrypt, \
             patch("registry.api.proxy_routes._build_server_info_for_mcp_client") as mock_build_info, \
             patch("registry.api.proxy_routes._build_headers_for_server") as mock_build_headers:
            
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_decrypt.return_value = server_config
            mock_build_info.return_value = {"headers": [{"Authorization": "Bearer backend-api-key"}]}
            mock_build_headers.return_value = {"Authorization": "Bearer backend-api-key"}
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server_path="/tavilysearch",  # Regular path
                server_config=server_config
            )
        
        assert response.status_code == 200
        
        # Verify gateway Authorization was removed and replaced with backend auth
        call_args = mock_client.request.call_args
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer backend-api-key"
        assert headers["Authorization"] != "Bearer gateway-jwt-token"
        
        # Verify both auth header building functions were called
        mock_decrypt.assert_called_once_with(server_config)
        mock_build_info.assert_called_once_with(server_config, [])
        mock_build_headers.assert_called_once_with(server_config)

    @pytest.mark.asyncio
    async def test_sse_streaming_response(self, mock_request, auth_context):
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
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.stream = Mock(return_value=mock_stream_context)
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server_path="/test",
                server_config=None
            )
        
        assert isinstance(response, StreamingResponse)
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"
        assert response.headers["Mcp-Session-Id"] == "test-session-123"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["X-Accel-Buffering"] == "no"

    @pytest.mark.asyncio
    async def test_backend_returns_json_when_client_accepts_sse(self, mock_request, auth_context):
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
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.stream = Mock(return_value=mock_stream_context)
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server_path="/test",
                server_config=None
            )
        
        assert isinstance(response, Response)
        assert response.status_code == 200
        assert response.body == b'{"result": "success"}'
        # Stream should be closed
        mock_stream_context.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_backend_error_response_logging(self, mock_request, auth_context):
        """Test that backend error responses are logged."""
        target_url = "http://backend:8080/mcp"
        
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"error": "Bad request"}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes.logger") as mock_logger:
            
            mock_client.request = AsyncMock(return_value=mock_response)
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server_path="/test",
                server_config=None
            )
        
        assert response.status_code == 400
        # Verify error was logged
        mock_logger.error.assert_called()
        error_msg = mock_logger.error.call_args[0][0]
        assert "400" in error_msg

    @pytest.mark.asyncio
    async def test_timeout_handling(self, mock_request, auth_context):
        """Test timeout error handling."""
        target_url = "http://backend:8080/mcp"
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.request = AsyncMock(
                side_effect=httpx.TimeoutException("Request timed out")
            )
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server_path="/test",
                server_config=None
            )
        
        assert response.status_code == 504
        assert b"Gateway timeout" in response.body

    @pytest.mark.asyncio
    async def test_generic_exception_handling(self, mock_request, auth_context):
        """Test generic exception handling."""
        target_url = "http://backend:8080/mcp"
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.request = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server_path="/test",
                server_config=None
            )
        
        assert response.status_code == 502
        assert b"Bad gateway" in response.body
        assert b"Connection refused" in response.body

    @pytest.mark.asyncio
    async def test_context_headers_added(self, mock_request, auth_context):
        """Test that all context headers are properly added."""
        target_url = "http://backend:8080/mcp"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"result": "success"}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client:
            mock_client.request = AsyncMock(return_value=mock_response)
            
            await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server_path="/test",
                server_config=None
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
    async def test_binary_content_error_response(self, mock_request, auth_context):
        """Test handling of binary error responses."""
        target_url = "http://backend:8080/mcp"
        
        # Mock binary error response that cannot be decoded as UTF-8
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.headers = {"content-type": "application/octet-stream"}
        # Use actual non-UTF8 bytes that will fail decode
        mock_response.content = b'\x80\x81\x82\x83'  # Invalid UTF-8 sequences
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes.logger") as mock_logger:
            
            mock_client.request = AsyncMock(return_value=mock_response)
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server_path="/test",
                server_config=None
            )
        
        assert response.status_code == 500
        # Verify binary content logging
        mock_logger.error.assert_called()
        error_msg = mock_logger.error.call_args[0][0]
        assert "binary content" in error_msg and "4 bytes" in error_msg

    @pytest.mark.asyncio
    async def test_authentication_happy_path_both_functions_called(self, mock_request, auth_context, server_config):
        """Test that both _build_server_info_for_mcp_client and _build_headers_for_server are called."""
        target_url = "http://backend:8080/mcp"
        
        # Mock backend response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"result": "success"}'
        
        with patch("registry.api.proxy_routes.proxy_client") as mock_client, \
             patch("registry.api.proxy_routes.decrypt_auth_fields") as mock_decrypt, \
             patch("registry.api.proxy_routes._build_server_info_for_mcp_client") as mock_build_info, \
             patch("registry.api.proxy_routes._build_headers_for_server") as mock_build_headers:
            
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_decrypt.return_value = server_config
            
            # _build_server_info_for_mcp_client returns headers in server_info structure
            mock_build_info.return_value = {
                "headers": [
                    {"X-Custom-Header": "from-server-info"}
                ]
            }
            
            # _build_headers_for_server returns direct auth headers
            mock_build_headers.return_value = {
                "Authorization": "Bearer api-key-123"
            }
            
            response = await proxy_to_mcp_server(
                request=mock_request,
                target_url=target_url,
                auth_context=auth_context,
                server_path="/test",
                server_config=server_config
            )
        
        assert response.status_code == 200
        
        # Verify decrypt was called first
        mock_decrypt.assert_called_once_with(server_config)
        
        # Verify _build_server_info_for_mcp_client was called with decrypted config
        mock_build_info.assert_called_once_with(server_config, [])
        
        # Verify _build_headers_for_server was called with decrypted config
        mock_build_headers.assert_called_once_with(server_config)
        
        # Verify both sets of headers were merged into the request
        call_args = mock_client.request.call_args
        headers = call_args.kwargs["headers"]
        assert headers["X-Custom-Header"] == "from-server-info"  # From server_info
        assert headers["Authorization"] == "Bearer api-key-123"  # From _build_headers_for_server
        
        # Verify call order: decrypt → build_info → build_headers
        assert mock_decrypt.call_count == 1
        assert mock_build_info.call_count == 1
        assert mock_build_headers.call_count == 1
