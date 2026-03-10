from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from registry.services.agentcore_import_service import AgentCoreImportService
from registry_pkgs.models import ExtendedMCPServer
from registry_pkgs.models._generated import ResourceType
from registry_pkgs.models.enums import FederationSource


class _FakeRepo:
    def __init__(self):
        self.synced = []

    async def sync_server_to_vector_db(self, server, is_delete=True):
        self.synced.append(server)
        return {"indexed_tools": 1, "failed_tools": 0, "deleted": 0}


class _FakeA2ARepo:
    def __init__(self):
        self.synced = []

    async def sync_agent_to_vector_db(self, agent, is_delete=True):
        self.synced.append((agent, is_delete))
        return {"indexed": 1, "failed": 0, "deleted": 0}


class _FakeAclService:
    def __init__(self):
        self.grants = []

    async def grant_permission(self, **kwargs):
        self.grants.append(kwargs)
        return SimpleNamespace(**kwargs)


class _FakeServer:
    def __init__(
        self,
        name: str,
        federation_id: str,
        title: str = "title",
        gateway_arn: str = "arn:aws:bedrock-agentcore:us-east-1:123:gateway/gw",
    ):
        self.id = None
        self.serverName = name
        self.path = f"/agentcore/{name}"
        self.tags = ["agentcore"]
        self.config = {
            "title": title,
            "description": f"desc-{name}",
            "type": "streamable-http",
            "url": "https://example.com/mcp",
            "requiresOAuth": True,
            "authProvider": "bedrock-agentcore",
            "timeout": 30000,
            "initDuration": 60000,
        }
        self.status = "active"
        self.numTools = 0
        self.author = PydanticObjectId()
        self.federationSource = FederationSource.AGENTCORE
        self.federationId = federation_id
        self.federationGatewayArn = gateway_arn
        self.federationSyncedAt = datetime.now(UTC)
        self.federationMetadata = {"sourceType": "gateway_target"}
        self.createdAt = datetime.now(UTC)
        self.updatedAt = datetime.now(UTC)
        self.save = AsyncMock()


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentCoreImportService:
    @pytest.fixture
    def repo(self):
        return _FakeRepo()

    @pytest.fixture
    def acl(self):
        return _FakeAclService()

    @pytest.fixture
    def a2a_repo(self):
        return _FakeA2ARepo()

    @pytest.fixture
    def service(self, repo, acl, a2a_repo):
        return AgentCoreImportService(
            federation_client=SimpleNamespace(),
            acl_service_instance=acl,
            mcp_server_repo=repo,
            a2a_agent_repo=a2a_repo,
        )

    async def test_import_single_server_dry_run_created(self, service, monkeypatch):
        discovered = _FakeServer(name="srv-new", federation_id="fed-new")
        monkeypatch.setattr(ExtendedMCPServer, "find_one", AsyncMock(return_value=None))

        result = await service._import_single_server(
            discovered_server=discovered,
            owner_id=None,
            viewer_id=None,
            dry_run=True,
        )

        assert result["action"] == "created"
        assert result["server_name"] == "srv-new"

    async def test_import_single_server_updates_existing(self, service, repo, monkeypatch):
        existing = _FakeServer(name="srv-upd", federation_id="fed-upd", title="old-title")
        existing.id = PydanticObjectId()
        discovered = _FakeServer(name="srv-upd", federation_id="fed-upd", title="new-title")

        monkeypatch.setattr(ExtendedMCPServer, "find_one", AsyncMock(return_value=existing))

        result = await service._import_single_server(
            discovered_server=discovered,
            owner_id=PydanticObjectId(),
            viewer_id=None,
            dry_run=False,
        )

        assert result["action"] == "updated"
        assert any("config" in item for item in result["changes"])
        existing.save.assert_awaited_once()
        assert len(repo.synced) == 1

    async def test_create_server_uses_server_service_create_server(self, service, repo, monkeypatch):
        discovered = _FakeServer(name="srv-create", federation_id="fed-create")
        owner_id = PydanticObjectId()
        viewer_id = PydanticObjectId()

        created_server = _FakeServer(name="created-from-service", federation_id="tmp")
        created_server.id = PydanticObjectId()
        created_server.save = AsyncMock()

        create_mock = AsyncMock(return_value=created_server)
        monkeypatch.setattr(
            "registry.services.agentcore_import_service.server_service_v1.create_server",
            create_mock,
        )

        await service._create_server(
            discovered_server=discovered,
            owner_id=owner_id,
            viewer_id=viewer_id,
        )

        create_mock.assert_awaited_once()
        kwargs = create_mock.await_args.kwargs
        assert kwargs["skip_post_registration_checks"] is True
        assert kwargs["user_id"] == str(owner_id)
        assert kwargs["data"].title == discovered.config["title"]
        assert kwargs["data"].url == discovered.config["url"]
        assert created_server.federationId == discovered.federationId
        assert len(repo.synced) == 1

    async def test_import_from_runtime_continues_on_error(self, service, monkeypatch):
        discovered_1 = _FakeServer(name="srv-1", federation_id="fed-1")
        discovered_2 = _FakeServer(name="srv-2", federation_id="fed-2")

        service.federation_client = SimpleNamespace(
            discover_runtime_entities=self._async_return(
                {
                    "mcp_servers": [discovered_1, discovered_2],
                    "a2a_agents": [],
                    "skipped_runtimes": [],
                }
            )
        )

        monkeypatch.setattr(
            service,
            "_resolve_identities",
            self._async_return((PydanticObjectId(), None)),
        )

        call_count = {"n": 0}

        async def _fake_import_single_server(**_kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {
                    "action": "created",
                    "server_name": "srv-1",
                    "server_id": "x1",
                    "changes": ["new server"],
                    "error": None,
                }
            raise RuntimeError("boom")

        monkeypatch.setattr(service, "_import_single_server_in_transaction", _fake_import_single_server)

        result = await service.import_from_runtime(
            runtime_arns=None,
            dry_run=False,
            user_id="dummy",
        )

        assert result["discovered"]["mcp_servers"] == 2
        assert result["imported"]["mcp_servers"] == 1
        assert result["skipped"]["mcp_servers"] == 1
        assert len(result["errors"]) == 1

    async def test_ensure_acl_permissions_grants_owner_and_viewer(self, service, acl):
        owner_id = PydanticObjectId()
        viewer_id = PydanticObjectId()

        await service._ensure_acl_permissions(
            resource_type=ResourceType.MCPSERVER,
            resource_id=PydanticObjectId(),
            owner_id=owner_id,
            viewer_id=viewer_id,
            dry_run=False,
        )

        assert len(acl.grants) == 2
        assert acl.grants[0]["perm_bits"] == 15  # OWNER
        assert acl.grants[1]["perm_bits"] == 1  # VIEW

    async def test_create_a2a_agent_syncs_to_vector_db(self, service, a2a_repo):
        owner_id = PydanticObjectId()
        discovered = SimpleNamespace(
            id=PydanticObjectId(),
            path="/agent/a2a",
            card=SimpleNamespace(name="a2a-new", model_dump=lambda **_: {"name": "a2a-new"}),
            tags=["agentcore"],
            status="active",
            isEnabled=True,
            wellKnown=None,
            federationId="fed-a2a-new",
            federationGatewayArn="arn:aws:bedrock-agentcore:us-east-1:123:gateway/test",
            federationMetadata={"sourceType": "runtime"},
            federationSource=FederationSource.AGENTCORE,
            createdAt=datetime.now(UTC),
            updatedAt=datetime.now(UTC),
            author=None,
            insert=AsyncMock(),
        )

        created = await service._create_a2a_agent(
            discovered_agent=discovered,
            owner_id=owner_id,
            viewer_id=None,
        )

        assert created is discovered
        discovered.insert.assert_awaited_once()
        assert len(a2a_repo.synced) == 1
        assert a2a_repo.synced[0][0] is discovered
        assert a2a_repo.synced[0][1] is False

    async def test_update_a2a_agent_syncs_to_vector_db(self, service, a2a_repo):
        existing = SimpleNamespace(
            id=PydanticObjectId(),
            path="/agent/a2a",
            card=SimpleNamespace(name="a2a-upd", model_dump=lambda **_: {"name": "a2a-upd-old"}),
            tags=["old"],
            status="inactive",
            isEnabled=False,
            wellKnown=None,
            federationId="fed-a2a-upd",
            federationGatewayArn="arn:old",
            federationMetadata={"v": 1},
            save=AsyncMock(),
        )
        new_data = SimpleNamespace(
            path="/agent/a2a",
            card=SimpleNamespace(name="a2a-upd", model_dump=lambda **_: {"name": "a2a-upd-new"}),
            tags=["new"],
            status="active",
            isEnabled=True,
            wellKnown=None,
            federationId="fed-a2a-upd",
            federationGatewayArn="arn:new",
            federationMetadata={"v": 2},
        )

        changes = await service._update_a2a_agent(existing=existing, new_data=new_data)

        assert changes
        existing.save.assert_awaited_once()
        assert len(a2a_repo.synced) == 1
        assert a2a_repo.synced[0][0] is existing
        assert a2a_repo.synced[0][1] is True

    @staticmethod
    def _async_return(value):
        async def _inner(*_args, **_kwargs):
            return value

        return _inner
