"""
Integration tests for semantic search routes.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, Mock

from registry.main import app
from registry.auth import dependencies as auth_dependencies
from fastapi import Request


@pytest.mark.integration
@pytest.mark.search
class TestSearchRoutes:
    """Integration coverage for /api/search/semantic."""

    def setup_method(self):
        """Override auth dependency for each test."""
        user_context = {
            "username": "test-user",
            "user_id": "test-user",
            "is_admin": True,
            "accessible_servers": ["all"],
            "accessible_agents": ["all"],
            "accessible_services": ["all"],
            "groups": ["registry-admins"],
            "scopes": ["registry-admins"],
            "ui_permissions": {},
            "can_modify_servers": True,
            "auth_method": "traditional",
            "provider": "local",
        }

        def _mock_get_user(request: Request):
            request.state.user = user_context
            request.state.is_authenticated = True
            return user_context

        app.dependency_overrides[auth_dependencies.get_current_user_by_mid] = _mock_get_user

    def teardown_method(self):
        """Clean up dependency overrides."""
        app.dependency_overrides.clear()

    def test_semantic_search_success(self, test_client: TestClient):
        """Successful semantic search returns filtered data."""
        mock_results = {
            "servers": [
                {
                    "path": "/demo",
                    "server_name": "Demo",
                    "description": "Demo server",
                    "tags": ["demo"],
                    "num_tools": 1,
                    "is_enabled": True,
                    "relevance_score": 0.9,
                    "match_context": "Demo server",
                    "matching_tools": [
                        {
                            "tool_name": "alpha",
                            "description": "Alpha tool",
                            "relevance_score": 0.8,
                            "match_context": "Alpha tool",
                        }
                    ],
                }
            ],
            "tools": [
                {
                    "server_path": "/demo",
                    "server_name": "Demo",
                    "tool_name": "alpha",
                    "description": "Alpha tool",
                    "match_context": "Alpha tool",
                    "relevance_score": 0.85,
                }
            ],
            "agents": [
                {
                    "path": "/agent/demo",
                    "agent_name": "Demo Agent",
                    "description": "Helps with demos",
                    "tags": ["demo"],
                    "skills": ["explain"],
                    "visibility": "public",
                    "trust_level": "verified",
                    "is_enabled": True,
                    "relevance_score": 0.77,
                    "match_context": "Helps with demos",
                }
            ],
        }

        with patch("registry.api.search_routes.faiss_service") as mock_faiss, \
                patch("registry.api.search_routes.agent_service") as mock_agent_service:
            mock_faiss.search_mixed = AsyncMock(return_value=mock_results)
            mock_agent = Mock()
            mock_agent.model_dump.return_value = {
                "name": "Demo Agent",
                "description": "Helps with demos",
                "tags": ["demo"],
                "skills": [{"name": "explain"}],
                "visibility": "public",
                "trust_level": "verified",
                "is_enabled": True,
            }
            mock_agent_service.get_agent_info.return_value = mock_agent

            response = test_client.post(
                "/api/search/semantic",
                json={
                    "query": "alpha",
                    "entity_types": ["mcp_server", "tool", "a2a_agent"],
                    "max_results": 5,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total_servers"] == 1
        assert data["total_tools"] == 1
        assert data["total_agents"] == 1
        assert data["servers"][0]["server_name"] == "Demo"
        assert data["tools"][0]["tool_name"] == "alpha"
        assert data["agents"][0]["agent_name"] == "Demo Agent"

    def test_semantic_search_handles_service_errors(self, test_client: TestClient):
        """Service-level errors propagate as 503."""
        with patch("registry.api.search_routes.faiss_service") as mock_faiss:
            mock_faiss.search_mixed = AsyncMock(side_effect=RuntimeError("offline"))

            response = test_client.post("/api/search/semantic", json={"query": "alpha"})

        assert response.status_code == 503
        assert "temporarily unavailable" in response.json()["detail"]
