import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from registry.api.v1.server_routes import create_server
from registry.schemas.server_api_schemas import ServerCreateRequest

@pytest.mark.asyncio
async def test_create_server_route_creates_acl_entry():
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
        "user_id": "user123",
        "username": "testuser",
        "acl_permission_map": {},
    }
    mock_server = MagicMock()
    mock_server.id = "server123"


    with patch("registry.api.v1.server_routes.server_service_v1.create_server", new=AsyncMock(return_value=mock_server)) as mock_create_server, \
        patch("registry.api.v1.server_routes.acl_service.grant_permission", new=AsyncMock(return_value=MagicMock())) as mock_grant_permission, \
        patch("registry.api.v1.server_routes.convert_to_create_response", return_value={"id": "server123"}) as mock_convert, \
        patch("registry.api.v1.server_routes.make_user_principal_id_dict", return_value={"userId": "user123"}):

        response = await create_server(data, user_context)

        mock_create_server.assert_awaited_once_with(data=data, user_id="user123", username="testuser")
        mock_grant_permission.assert_awaited_once()
        assert response == {"id": "server123"}

        # Assert grant_permission called with owner permission bits (15)
        _, kwargs = mock_grant_permission.call_args
        assert kwargs.get("perm_bits") == 15
