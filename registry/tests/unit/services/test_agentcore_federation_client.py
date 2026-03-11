import pytest

from registry.services.federation.agentcore_client import AgentCoreFederationClient


class _FakeServer:
    def __init__(self, name: str):
        self.name = name

    def model_dump(self, by_alias: bool = True, exclude_none: bool = True):
        return {"serverName": self.name, "by_alias": by_alias, "exclude_none": exclude_none}


@pytest.mark.unit
class TestAgentCoreFederationClientCompatibilityWrappers:
    def test_fetch_server_returns_dict(self, monkeypatch):
        client = AgentCoreFederationClient()

        def _fake_run_async(coroutine):
            coroutine.close()
            return [_FakeServer("s1")]

        monkeypatch.setattr(client, "_run_async", _fake_run_async)

        result = client.fetch_server("arn:aws:bedrock-agentcore:us-east-1:123:gateway/g1")

        assert isinstance(result, dict)
        assert result["serverName"] == "s1"

    def test_fetch_server_returns_none_when_empty(self, monkeypatch):
        client = AgentCoreFederationClient()

        def _fake_run_async(coroutine):
            coroutine.close()
            return []

        monkeypatch.setattr(client, "_run_async", _fake_run_async)

        result = client.fetch_server("arn:aws:bedrock-agentcore:us-east-1:123:gateway/g1")

        assert result is None

    def test_fetch_all_servers_returns_list_of_dicts(self, monkeypatch):
        client = AgentCoreFederationClient()
        calls = {"count": 0}

        def _fake_run_async(coroutine):
            coroutine.close()
            calls["count"] += 1
            return [_FakeServer(f"s{calls['count']}")]

        monkeypatch.setattr(client, "_run_async", _fake_run_async)

        result = client.fetch_all_servers(
            [
                "arn:aws:bedrock-agentcore:us-east-1:123:gateway/g1",
                "arn:aws:bedrock-agentcore:us-east-1:123:gateway/g2",
            ]
        )

        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)
        assert [item["serverName"] for item in result] == ["s1", "s2"]


@pytest.mark.unit
class TestAgentCoreFederationClientAuthDetection:
    def test_detect_runtime_auth_mode_defaults_to_iam(self):
        client = AgentCoreFederationClient()
        mode = client._detect_runtime_auth_mode(metadata={})
        assert mode == "IAM"

    def test_detect_runtime_auth_mode_detects_jwt(self):
        client = AgentCoreFederationClient()
        mode = client._detect_runtime_auth_mode(
            metadata={"authorizerConfiguration": {"customJWTAuthorizerConfiguration": {"discoveryUrl": "x"}}}
        )
        assert mode == "JWT"

    def test_runtime_requires_oauth_false_for_iam(self):
        client = AgentCoreFederationClient()
        assert client._runtime_requires_oauth({"authorizerConfiguration": None}) is False

    def test_runtime_requires_oauth_true_for_jwt(self):
        client = AgentCoreFederationClient()
        assert (
            client._runtime_requires_oauth(
                {"authorizerConfiguration": {"customJWTAuthorizerConfiguration": {"discoveryUrl": "x"}}}
            )
            is True
        )

    def test_map_agentcore_status_to_registry_status(self):
        client = AgentCoreFederationClient()
        assert client._map_agentcore_status_to_registry_status("READY") == "active"
        assert client._map_agentcore_status_to_registry_status("FAILED") == "error"
        assert client._map_agentcore_status_to_registry_status("CREATING") == "inactive"

    def test_extract_a2a_card_payload_supports_wrapped_payload(self):
        client = AgentCoreFederationClient()
        payload = {"agentCard": {"name": "wrapped-agent"}}
        assert client._extract_a2a_card_payload(payload)["name"] == "wrapped-agent"
