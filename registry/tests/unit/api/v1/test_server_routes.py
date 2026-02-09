from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from beanie import PydanticObjectId

from registry.api.v1.server.server_routes import check_server_connection, create_server
from registry.core.acl_constants import PrincipalType, ResourceType
from registry.schemas.server_api_schemas import ServerConnectionTestRequest, ServerCreateRequest


@pytest.mark.unit
@pytest.mark.servers
class TestServerRoutes:
    """Test suite for server routes."""

    @pytest.mark.asyncio
    async def test_create_server_route_creates_acl_entry(self):
        data = ServerCreateRequest(
            serverName="TestServer",
            path="/testserver",
            tags=["tag1"],
            url="http://localhost:8000",
            description="desc",
            supported_transports=["streamable-http"],
            timeout=None,
            init_timeout=None,
            server_instructions=None,
            oauth=None,
            apiKey=None,
            custom_user_vars=None,
            tool_list=[],
            requires_oauth=False,
        )
        user_context = {
            "user_id": PydanticObjectId(),
            "username": "testuser",
            "acl_permission_map": {},
        }
        mock_server = MagicMock()
        mock_server.id = "server123"

        with (
            patch(
                "registry.api.v1.server.server_routes.server_service_v1.create_server",
                new=AsyncMock(return_value=mock_server),
            ) as mock_create_server,
            patch(
                "registry.api.v1.server.server_routes.acl_service.grant_permission",
                new=AsyncMock(return_value=MagicMock()),
            ) as mock_grant_permission,
            patch("registry.api.v1.server.server_routes.convert_to_create_response", return_value={"id": "server123"}),
        ):
            response = await create_server(data, user_context)

            mock_create_server.assert_awaited_once_with(data=data, user_id=user_context.get("user_id", ""))
            mock_grant_permission.assert_awaited_once()
            assert response == {"id": "server123"}

            # Assert grant_permission called with owner permission bits (15)
            _, kwargs = mock_grant_permission.call_args
            assert kwargs.get("principal_type") == PrincipalType.USER
            assert kwargs.get("principal_id") == user_context.get("user_id")
            assert kwargs.get("resource_type") == ResourceType.MCPSERVER
            assert kwargs.get("resource_id") == mock_server.id
            assert kwargs.get("perm_bits") == 15

    @pytest.mark.asyncio
    async def test_connection_endpoint_success(self):
        """Test successful connection test."""
        request = ServerConnectionTestRequest(url="http://localhost:8000/mcp", transport="streamable-http")

        mock_init_result = Mock()
        mock_init_result.serverInfo = Mock()
        mock_init_result.serverInfo.name = "test-server"
        mock_init_result.protocolVersion = "2024-11-05"
        mock_init_result.capabilities = {"tools": {}}

        with patch(
            "registry.api.v1.server.server_routes.perform_health_check",
            new=AsyncMock(return_value=(True, "initialize handshake successful", 150, mock_init_result)),
        ):
            response = await check_server_connection(request)

            assert response.success is True
            assert response.serverName == "test-server"
            assert response.protocolVersion == "2024-11-05"
            assert response.responseTimeMs == 150
            assert response.capabilities == {"tools": {}}
            assert response.error is None

    @pytest.mark.asyncio
    async def test_connection_endpoint_failure(self):
        """Test connection test failure."""
        request = ServerConnectionTestRequest(url="http://localhost:8000/mcp", transport="streamable-http")

        with patch(
            "registry.api.v1.server.server_routes.perform_health_check",
            new=AsyncMock(return_value=(False, "unhealthy: connection timeout", 5000, None)),
        ):
            response = await check_server_connection(request)

            assert response.success is False
            assert "connection timeout" in response.message.lower()
            assert response.serverName is None
            assert response.responseTimeMs == 5000
            assert response.error == "unhealthy: connection timeout"

    @pytest.mark.asyncio
    async def test_connection_endpoint_no_url(self):
        """Test connection test with missing URL."""
        request = ServerConnectionTestRequest(url="", transport="streamable-http")

        response = await check_server_connection(request)

        assert response.success is False
        assert response.message == "URL is required"
        assert response.error == "URL is required"

    @pytest.mark.asyncio
    async def test_connection_endpoint_401_unauthorized(self):
        """Test connection test when server returns 401 (should be considered healthy)."""
        request = ServerConnectionTestRequest(url="http://localhost:8000/mcp", transport="streamable-http")

        with patch(
            "registry.api.v1.server.server_routes.perform_health_check",
            new=AsyncMock(return_value=(True, "connected (initialize requires authentication)", 150, None)),
        ):
            response = await check_server_connection(request)

            assert response.success is True
            assert "initialize requires authentication" in response.message.lower()
            assert response.serverName is None  # No init_result for 401
            assert response.responseTimeMs == 150
            assert response.error is None
