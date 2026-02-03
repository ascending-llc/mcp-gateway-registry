import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from beanie import PydanticObjectId

from registry.api.v1.server.server_routes import create_server
from registry.schemas.server_api_schemas import ServerCreateRequest
from registry.core.acl_constants import PrincipalType, ResourceType, RoleBits

@pytest.fixture
def sample_user_context():
    return {
        "user_id": PydanticObjectId(),
        "username": "testuser",
        "acl_permission_map": {},
    }


@pytest.fixture
def sample_server_request():
    return ServerCreateRequest(
        serverName="TestServer",
        path="/testserver",
        tags=["test"],
        url="http://localhost:8000",
        description="Test server description",
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


@pytest.fixture
def mock_created_server():
    mock_server = MagicMock()
    mock_server.id = PydanticObjectId()
    mock_server.serverName = "TestServer"
    return mock_server


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.__class__.__name__ = "AsyncClientSession"
    return session

@pytest.mark.asyncio
async def test_create_server_route_creates_acl_entry(
    sample_server_request,
    sample_user_context,
    mock_created_server,
):
    with patch(
        "registry.api.v1.server.server_routes.server_service_v1.create_server",
        new=AsyncMock(return_value=mock_created_server)
    ) as mock_create_server, \
    patch(
        "registry.api.v1.server.server_routes.acl_service.grant_permission",
        new=AsyncMock(return_value=MagicMock())
    ) as mock_grant_permission, \
    patch(
        "registry.api.v1.server.server_routes.convert_to_create_response",
        return_value={"id": str(mock_created_server.id)}
    ):
        
        await create_server(
            sample_server_request,
            sample_user_context,
            tx_session=None
        )

        # Verify server creation was called correctly
        mock_create_server.assert_awaited_once_with(
            data=sample_server_request,
            user_id=sample_user_context["user_id"],
            session=None
        )
        
        # Verify ACL permission was granted
        mock_grant_permission.assert_awaited_once()
        
        # Verify ACL call has correct parameters
        _, kwargs = mock_grant_permission.call_args
        assert kwargs["principal_type"] == PrincipalType.USER
        assert kwargs["principal_id"] == sample_user_context["user_id"]
        assert kwargs["resource_type"] == ResourceType.MCPSERVER
        assert kwargs["resource_id"] == mock_created_server.id
        assert kwargs["perm_bits"] == RoleBits.OWNER

@pytest.mark.asyncio
async def test_create_server_passes_session_to_services(
    sample_server_request,
    sample_user_context,
    mock_created_server,
    mock_session,
):
    with patch(
        "registry.api.v1.server.server_routes.server_service_v1.create_server",
        new=AsyncMock(return_value=mock_created_server)
    ) as mock_create, \
    patch(
        "registry.api.v1.server.server_routes.acl_service.grant_permission",
        new=AsyncMock(return_value=MagicMock())
    ) as mock_grant, \
    patch(
        "registry.api.v1.server.server_routes.convert_to_create_response",
        return_value={"id": str(mock_created_server.id)}
    ):
        
        await create_server(
            sample_server_request,
            sample_user_context,
            tx_session=mock_session
        )
        
        # Verify session was passed to server creation
        mock_create.assert_awaited_once()
        create_kwargs = mock_create.call_args.kwargs
        assert create_kwargs["session"] == mock_session, \
            "Session must be passed to server_service.create_server"
        
        # Verify session was passed to ACL grant
        mock_grant.assert_awaited_once()
        grant_kwargs = mock_grant.call_args.kwargs
        assert grant_kwargs["session"] == mock_session, \
            "Session must be passed to acl_service.grant_permission"
