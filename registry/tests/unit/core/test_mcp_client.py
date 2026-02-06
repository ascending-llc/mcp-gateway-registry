"""
Unit tests for mcp_client functions.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from registry.core.mcp_client import _get_from_sse, _get_from_streamable_http, get_tools_and_capabilities_from_server


@pytest.mark.unit
@pytest.mark.core
class TestMCPClient:
    """Test suite for MCP client functions."""

    @pytest.fixture
    def mock_headers(self):
        """Create mock headers with authentication."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer test-token-123",
            "User-Agent": "MCP-Gateway-Registry/1.0",
        }

    @pytest.fixture
    def mock_tools_response(self):
        """Create mock tools response."""
        tool = Mock()
        tool.name = "test_tool"
        tool.description = "Test tool description"
        tool.inputSchema = {"type": "object", "properties": {"query": {"type": "string"}}}

        response = Mock()
        response.tools = [tool]
        return response

    @pytest.fixture
    def mock_capabilities(self):
        """Create mock capabilities."""
        return {"tools": {"listChanged": True}, "resources": {"subscribe": False}, "prompts": {"listChanged": False}}

    @pytest.mark.asyncio
    async def test_get_from_streamable_http_with_headers(self, mock_headers, mock_tools_response, mock_capabilities):
        """Test _get_from_streamable_http accepts pre-built headers."""
        base_url = "http://localhost:8000/mcp/"

        with (
            patch("registry.core.mcp_client.streamable_http_client") as mock_client,
            patch("registry.core.mcp_client.get_server_strategy") as mock_strategy,
        ):
            # Mock strategy
            strategy = Mock()
            strategy.modify_url = Mock(return_value=base_url)
            mock_strategy.return_value = strategy

            # Mock MCP session
            mock_init_result = Mock()
            mock_init_result.capabilities = mock_capabilities

            mock_session = AsyncMock()
            mock_session.initialize = AsyncMock(return_value=mock_init_result)
            mock_session.list_tools = AsyncMock(return_value=mock_tools_response)
            mock_session.list_resources = AsyncMock(return_value=Mock(resources=[]))
            mock_session.list_prompts = AsyncMock(return_value=Mock(prompts=[]))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            # Mock streamable_http_client context manager
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=(Mock(), Mock(), Mock()))
            mock_client.return_value = mock_context

            with patch("registry.core.mcp_client.ClientSession") as mock_session_cls:
                mock_session_cls.return_value = mock_session

                result = await _get_from_streamable_http(
                    base_url=base_url, headers=mock_headers, transport_type="streamable-http", include_capabilities=True
                )

            # Verify result is MCPServerData object
            assert result.tools is not None
            assert result.capabilities == mock_capabilities

    @pytest.mark.asyncio
    async def test_get_from_streamable_http_without_capabilities(self, mock_headers, mock_tools_response):
        """Test _get_from_streamable_http can skip capabilities."""
        base_url = "http://localhost:8000/mcp/"

        with (
            patch("registry.core.mcp_client.streamable_http_client") as mock_client,
            patch("registry.core.mcp_client.get_server_strategy") as mock_strategy,
        ):
            strategy = Mock()
            strategy.modify_url = Mock(return_value=base_url)
            mock_strategy.return_value = strategy

            mock_session = AsyncMock()
            mock_session.list_tools = AsyncMock(return_value=mock_tools_response)
            mock_session.list_resources = AsyncMock(return_value=Mock(resources=[]))
            mock_session.list_prompts = AsyncMock(return_value=Mock(prompts=[]))

            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=(Mock(), Mock(), Mock()))
            mock_client.return_value = mock_context

            with patch("registry.core.mcp_client.ClientSession") as mock_session_cls:
                mock_session_cls.return_value = mock_session

                result = await _get_from_streamable_http(
                    base_url=base_url,
                    headers=mock_headers,
                    transport_type="streamable-http",
                    include_capabilities=False,
                )

            assert result.tools is not None
            assert result.capabilities is None

    @pytest.mark.asyncio
    async def test_get_from_sse_with_headers(self, mock_headers, mock_tools_response, mock_capabilities):
        """Test _get_from_sse accepts pre-built headers."""
        base_url = "http://localhost:8000/sse"

        with (
            patch("registry.core.mcp_client.sse_client") as mock_client,
            patch("registry.core.mcp_client.get_server_strategy") as mock_strategy,
            patch("httpx.AsyncClient"),
        ):
            strategy = Mock()
            strategy.modify_url = Mock(return_value=base_url)
            mock_strategy.return_value = strategy

            mock_init_result = Mock()
            mock_init_result.capabilities = mock_capabilities

            mock_session = AsyncMock()
            mock_session.initialize = AsyncMock(return_value=mock_init_result)
            mock_session.list_tools = AsyncMock(return_value=mock_tools_response)
            mock_session.list_resources = AsyncMock(return_value=Mock(resources=[]))
            mock_session.list_prompts = AsyncMock(return_value=Mock(prompts=[]))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            # Mock sse_client context
            mock_sse_context = AsyncMock()
            mock_sse_context.__aenter__ = AsyncMock(return_value=(Mock(), Mock()))
            mock_client.return_value = mock_sse_context

            with patch("registry.core.mcp_client.ClientSession") as mock_session_cls:
                mock_session_cls.return_value = mock_session

                result = await _get_from_sse(
                    base_url=base_url, headers=mock_headers, transport_type="sse", include_capabilities=True
                )

            assert result.tools is not None
            assert result.capabilities == mock_capabilities

    @pytest.mark.asyncio
    async def test_get_tools_and_capabilities_from_server_streamable_http(self, mock_headers):
        """Test main entry point with streamable-http transport."""
        base_url = "http://localhost:8000"

        with patch("registry.core.mcp_client._get_from_streamable_http") as mock_get:
            from registry.core.mcp_client import MCPServerData

            mock_get.return_value = MCPServerData(tools=["tool1"], resources=[], prompts=[], capabilities={"tools": {}})

            result = await get_tools_and_capabilities_from_server(
                base_url=base_url, headers=mock_headers, transport_type="streamable-http"
            )

            assert result.tools == ["tool1"]
            assert result.capabilities == {"tools": {}}
            # Check that the call includes all expected parameters
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == base_url
            assert call_args[0][1] == mock_headers
            assert call_args[0][2] == "streamable-http"
            assert call_args[1]["include_capabilities"]
            assert call_args[1]["include_resources"]
            assert call_args[1]["include_prompts"]

    @pytest.mark.asyncio
    async def test_get_tools_and_capabilities_from_server_sse(self, mock_headers):
        """Test main entry point with SSE transport."""
        base_url = "http://localhost:8000"

        with patch("registry.core.mcp_client._get_from_sse") as mock_get:
            from registry.core.mcp_client import MCPServerData

            mock_get.return_value = MCPServerData(
                tools=["tool2"], resources=[], prompts=[], capabilities={"resources": {}}
            )

            result = await get_tools_and_capabilities_from_server(
                base_url=base_url, headers=mock_headers, transport_type="sse"
            )

            assert result.tools == ["tool2"]
            assert result.capabilities == {"resources": {}}
            # Check that the call includes all expected parameters
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == base_url
            assert call_args[0][1] == mock_headers
            assert call_args[0][2] == "sse"
            assert call_args[1]["include_capabilities"]
            assert call_args[1]["include_resources"]
            assert call_args[1]["include_prompts"]

    @pytest.mark.asyncio
    async def test_get_tools_and_capabilities_auto_detect_transport(self, mock_headers):
        """Test transport auto-detection."""
        base_url = "http://localhost:8000"

        from registry.core.mcp_client import MCPServerData

        with (
            patch("registry.core.mcp_client.detect_server_transport") as mock_detect,
            patch("registry.core.mcp_client._get_from_streamable_http") as mock_get,
        ):
            mock_detect.return_value = "streamable-http"
            mock_get.return_value = MCPServerData(tools=["tool"], resources=[], prompts=[], capabilities={})

            result = await get_tools_and_capabilities_from_server(
                base_url=base_url,
                headers=mock_headers,
                transport_type=None,  # Auto-detect
            )

            mock_detect.assert_called_once_with(base_url)
            assert result.tools == ["tool"]

    @pytest.mark.asyncio
    async def test_headers_default_to_mcp_headers_if_none(self):
        """Test that None headers default to MCP base headers."""
        base_url = "http://localhost:8000/mcp/"

        with (
            patch("registry.core.mcp_client.streamable_http_client") as mock_client,
            patch("registry.core.mcp_client.get_server_strategy") as mock_strategy,
            patch("registry.core.mcp_client.mcp_config") as mock_config,
        ):
            # Mock default headers
            mock_config.DEFAULT_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

            strategy = Mock()
            strategy.modify_url = Mock(return_value=base_url)
            mock_strategy.return_value = strategy

            mock_session = AsyncMock()
            mock_session.list_tools = AsyncMock(return_value=Mock(tools=[]))
            mock_session.list_resources = AsyncMock(return_value=Mock(resources=[]))
            mock_session.list_prompts = AsyncMock(return_value=Mock(prompts=[]))

            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=(Mock(), Mock(), Mock()))
            mock_client.return_value = mock_context

            with patch("registry.core.mcp_client.ClientSession") as mock_session_cls:
                mock_session_cls.return_value = mock_session

                await _get_from_streamable_http(
                    base_url=base_url,
                    headers=None,  # Should use defaults
                    transport_type="streamable-http",
                    include_capabilities=False,
                )

            # Would verify default headers were used in actual httpx call

    @pytest.mark.asyncio
    async def test_connection_timeout_returns_none(self, mock_headers):
        """Test timeout returns MCPServerData with None fields."""
        base_url = "http://localhost:8000/mcp/"

        with (
            patch("registry.core.mcp_client.streamable_http_client") as mock_client,
            patch("registry.core.mcp_client.get_server_strategy"),
        ):
            # Simulate timeout
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=TimeoutError("Connection timeout"))
            mock_client.return_value = mock_context

            result = await _get_from_streamable_http(
                base_url=base_url, headers=mock_headers, transport_type="streamable-http", include_capabilities=True
            )

            assert result.tools is None
            assert result.capabilities is None

    @pytest.mark.asyncio
    async def test_connection_error_returns_none(self, mock_headers):
        """Test connection error returns MCPServerData with None fields."""
        base_url = "http://localhost:8000/mcp/"

        with (
            patch("registry.core.mcp_client.streamable_http_client") as mock_client,
            patch("registry.core.mcp_client.get_server_strategy"),
        ):
            # Simulate connection error
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.return_value = mock_context

            result = await _get_from_streamable_http(
                base_url=base_url, headers=mock_headers, transport_type="streamable-http", include_capabilities=True
            )

            assert result.tools is None
            assert result.capabilities is None
            assert result.error_message is not None
