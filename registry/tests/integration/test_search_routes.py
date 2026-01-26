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

        with patch("registry.api.v1.search_routes.faiss_service") as mock_faiss, \
                patch("registry.api.v1.search_routes.agent_service") as mock_agent_service:
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
                "/api/v1/search/semantic",
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
        with patch("registry.api.v1.search_routes.faiss_service") as mock_faiss:
            mock_faiss.search_mixed = AsyncMock(side_effect=RuntimeError("offline"))

            response = test_client.post("/api/v1/search/semantic", json={"query": "alpha"})

        assert response.status_code == 503
        assert "temporarily unavailable" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.search
class TestToolDiscoveryRoutes:
    """Integration coverage for /api/v1/search/tools endpoint."""

    def setup_method(self):
        """Override auth dependency for each test."""
        user_context = {
            "username": "test-user",
            "user_id": "test-user",
            "is_admin": False,
            "accessible_servers": ["/tavilysearch"],
            "accessible_agents": ["all"],
            "accessible_services": ["all"],
            "groups": ["registry-users"],
            "scopes": ["registry:read"],
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

    def test_discover_tools_success(self, test_client: TestClient):
        """Successful tool discovery returns matching tools with scores."""
        response = test_client.post(
            "/api/v1/search/tools",
            json={
                "query": "search web",
                "top_n": 3
            }
        )

        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "query" in data
        assert "total_matches" in data
        assert "matches" in data
        assert data["query"] == "search web"
        
        # Verify at least one match returned
        assert data["total_matches"] > 0
        assert len(data["matches"]) > 0
        
        # Verify match structure
        first_match = data["matches"][0]
        assert "tool_name" in first_match
        assert "server_id" in first_match
        assert "server_path" in first_match
        assert "description" in first_match
        assert "input_schema" in first_match
        assert "discovery_score" in first_match
        assert "transport_type" in first_match
        
        # Verify discovery score is valid
        assert 0.0 <= first_match["discovery_score"] <= 1.0
        
        # Verify server path matches expected
        assert first_match["server_path"] == "/tavilysearch"

    def test_discover_tools_with_keyword_matching(self, test_client: TestClient):
        """Tool discovery boosts scores for keyword matches."""
        # Query with specific keyword "search" that should match tavily_search
        response = test_client.post(
            "/api/v1/search/tools",
            json={
                "query": "search",
                "top_n": 5
            }
        )

        assert response.status_code == 200
        data = response.json()
        
        # Find the tavily_search tool
        search_tool = next(
            (m for m in data["matches"] if m["tool_name"] == "tavily_search"),
            None
        )
        assert search_tool is not None
        
        # Verify it has a high discovery score due to keyword matching
        assert search_tool["discovery_score"] >= 0.99

    def test_discover_tools_respects_top_n(self, test_client: TestClient):
        """Tool discovery respects the top_n parameter."""
        response = test_client.post(
            "/api/v1/search/tools",
            json={
                "query": "tavily",
                "top_n": 2
            }
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should return at most 2 results
        assert len(data["matches"]) <= 2

    def test_discover_tools_missing_query(self, test_client: TestClient):
        """Tool discovery requires query parameter."""
        response = test_client.post(
            "/api/v1/search/tools",
            json={
                "top_n": 5
            }
        )

        assert response.status_code == 400
        assert "query parameter is required" in response.json()["detail"]

    def test_discover_tools_empty_query(self, test_client: TestClient):
        """Tool discovery rejects empty query string."""
        response = test_client.post(
            "/api/v1/search/tools",
            json={
                "query": "",
                "top_n": 5
            }
        )

        assert response.status_code == 400
        assert "query parameter is required" in response.json()["detail"]

    def test_discover_tools_default_top_n(self, test_client: TestClient):
        """Tool discovery uses default top_n of 5 when not specified."""
        response = test_client.post(
            "/api/v1/search/tools",
            json={
                "query": "web search"
            }
        )

        assert response.status_code == 200
        data = response.json()
        
        # Default should return up to 5 results
        assert len(data["matches"]) <= 5

    def test_discover_tools_returns_all_required_fields(self, test_client: TestClient):
        """Tool discovery returns all required metadata fields."""
        response = test_client.post(
            "/api/v1/search/tools",
            json={
                "query": "extract content",
                "top_n": 1
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["matches"]) > 0
        
        match = data["matches"][0]
        
        # Verify all required fields are present
        required_fields = [
            "tool_name",
            "server_id",
            "server_path",
            "description",
            "input_schema",
            "discovery_score",
            "transport_type"
        ]
        
        for field in required_fields:
            assert field in match, f"Missing required field: {field}"
        
        # Verify input_schema structure
        assert isinstance(match["input_schema"], dict)
        assert "type" in match["input_schema"]
        assert "properties" in match["input_schema"]
        assert "required" in match["input_schema"]

    def test_discover_tools_sorts_by_score(self, test_client: TestClient):
        """Tool discovery returns results sorted by discovery score."""
        response = test_client.post(
            "/api/v1/search/tools",
            json={
                "query": "website",
                "top_n": 4
            }
        )

        assert response.status_code == 200
        data = response.json()
        
        if len(data["matches"]) > 1:
            # Verify scores are in descending order
            scores = [m["discovery_score"] for m in data["matches"]]
            assert scores == sorted(scores, reverse=True), "Results should be sorted by score descending"
