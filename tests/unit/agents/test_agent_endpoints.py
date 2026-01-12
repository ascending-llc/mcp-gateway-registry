"""
Integration tests for A2A agent endpoints.

This module provides comprehensive tests for all agent API endpoints including
registration, listing, retrieval, updates, deletion, and discovery operations.
"""

import pytest
from datetime import datetime
from typing import Any, Dict
from unittest.mock import Mock, patch, AsyncMock
from fastapi import status
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from registry.main import app
from registry.schemas.agent_models import (
    AgentCard,
    Skill,
    AgentInfo,
    SecurityScheme,
)
from registry.services.agent_service import agent_service


@pytest.fixture
def mock_enhanced_auth_admin():
    """Mock enhanced_auth for admin user."""

    def _mock_auth(session=None):
        return {
            "username": "admin_user",
            "groups": ["agents-admin"],
            "scopes": ["agent-admin"],
            "auth_method": "traditional",
            "provider": "local",
            "ui_permissions": {
                "register_service": ["all"],
                "modify_service": ["all"],
                "toggle_service": ["all"],
            },
            "can_modify_servers": True,
            "is_admin": True,
        }

    return _mock_auth


@pytest.fixture
def mock_enhanced_auth_user():
    """Mock enhanced_auth for regular user."""

    def _mock_auth(session=None):
        return {
            "username": "test_user",
            "groups": ["agents-users"],
            "scopes": ["agent-read"],
            "auth_method": "oauth2",
            "provider": "cognito",
            "ui_permissions": {
                "register_service": ["all"],
                "modify_service": ["all"],
                "toggle_service": ["all"],
            },
            "can_modify_servers": False,
            "is_admin": False,
        }

    return _mock_auth


@pytest.fixture
def mock_enhanced_auth_viewer():
    """Mock enhanced_auth for viewer-only user."""

    def _mock_auth(session=None):
        return {
            "username": "viewer_user",
            "groups": ["agents-viewers"],
            "scopes": ["agent-read"],
            "auth_method": "oauth2",
            "provider": "cognito",
            "ui_permissions": {},
            "can_modify_servers": False,
            "is_admin": False,
        }

    return _mock_auth


@pytest.fixture
def sample_agent_card() -> AgentCard:
    """Create a public agent card for testing."""
    return AgentCard(
        protocol_version="1.0",
        name="Code Reviewer Agent",
        description="Reviews code and provides feedback",
        url=HttpUrl("https://code-reviewer.example.com/api"),
        path="/agents/code-reviewer",
        version="1.0.0",
        provider="TechCorp",
        tags=["review", "code"],
        is_enabled=False,
        visibility="public",
        trust_level="community",
        skills=[
            Skill(
                id="review-code",
                name="Review Code",
                description="Reviews source code",
                tags=["code", "review"],
            ),
            Skill(
                id="suggest-improvements",
                name="Suggest Improvements",
                description="Suggests code improvements",
                tags=["suggestions", "code"],
            ),
        ],
    )


@pytest.fixture
def private_agent_card() -> AgentCard:
    """Create a private agent card for testing."""
    return AgentCard(
        protocol_version="1.0",
        name="Data Analyzer Agent",
        description="Analyzes data and generates reports",
        url=HttpUrl("https://analyzer.example.com/api"),
        path="/agents/data-analyzer",
        visibility="private",
        registered_by="test_user",
        trust_level="verified",
        skills=[
            Skill(
                id="analyze-data",
                name="Analyze Data",
                description="Performs data analysis",
                tags=["analysis", "data"],
            ),
        ],
    )


@pytest.fixture
def group_agent_card() -> AgentCard:
    """Create a group-restricted agent card for testing."""
    return AgentCard(
        protocol_version="1.0",
        name="Task Runner Agent",
        description="Executes tasks within group context",
        url=HttpUrl("https://taskrunner.example.com/api"),
        path="/agents/task-runner",
        visibility="group-restricted",
        allowed_groups=["agents-users"],
        trust_level="trusted",
        skills=[
            Skill(
                id="run-task",
                name="Run Task",
                description="Executes a task",
                tags=["tasks", "execution"],
            ),
        ],
    )


@pytest.mark.unit
class TestAgentRegistration:
    """Tests for agent registration endpoint POST /api/agents/register."""

    def test_register_valid_agent_success(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test successful registration with valid agent card."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            agent_service,
            "register_agent",
            return_value=sample_agent_card,
        ), patch.object(
            agent_service,
            "is_agent_enabled",
            return_value=False,
        ), patch(
            "registry.services.search.service.faiss_service.add_or_update_agent",
            new_callable=AsyncMock,
        ):

            client = TestClient(app)
            response = client.post(
                "/api/agents/register",
                json={
                    "name": sample_agent_card.name,
                    "description": sample_agent_card.description,
                    "url": str(sample_agent_card.url),
                    "path": sample_agent_card.path,
                    "protocol_version": sample_agent_card.protocol_version,
                    "provider": sample_agent_card.provider,
                    "tags": ",".join(sample_agent_card.tags),
                    "visibility": sample_agent_card.visibility,
                },
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["agent"]["name"] == sample_agent_card.name
            assert data["agent"]["path"] == sample_agent_card.path

        app.dependency_overrides.clear()

    def test_register_duplicate_path_returns_409(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test registering duplicate path returns 409 conflict."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=sample_agent_card,
        ):

            client = TestClient(app)
            response = client.post(
                "/api/agents/register",
                json={
                    "name": sample_agent_card.name,
                    "description": sample_agent_card.description,
                    "url": str(sample_agent_card.url),
                    "path": sample_agent_card.path,
                    "protocol_version": sample_agent_card.protocol_version,
                },
            )

            assert response.status_code == status.HTTP_409_CONFLICT
            data = response.json()
            assert "already exists" in data["detail"]

        app.dependency_overrides.clear()

    def test_register_invalid_protocol_version(
        self,
        mock_enhanced_auth_admin,
    ):
        """Test invalid protocol version format."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        client = TestClient(app)
        response = client.post(
            "/api/agents/register",
            json={
                "name": "Test Agent",
                "description": "Test",
                "url": "https://test.example.com/api",
                "path": "/agents/test",
                "protocol_version": "invalid",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        app.dependency_overrides.clear()

    def test_register_invalid_url_non_https(
        self,
        mock_enhanced_auth_admin,
    ):
        """Test invalid URL without HTTPS."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        client = TestClient(app)
        response = client.post(
            "/api/agents/register",
            json={
                "name": "Test Agent",
                "description": "Test",
                "url": "http://test.example.com/api",
                "path": "/agents/test",
                "protocol_version": "1.0",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        app.dependency_overrides.clear()

    def test_register_missing_required_fields(
        self,
        mock_enhanced_auth_admin,
    ):
        """Test registration with missing required fields."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        client = TestClient(app)
        response = client.post(
            "/api/agents/register",
            json={
                "name": "Test Agent",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        app.dependency_overrides.clear()

    def test_register_with_tags(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test registration with tags."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            agent_service,
            "register_agent",
            return_value=sample_agent_card,
        ), patch("registry.services.search.service.faiss_service.add_or_update_agent", new_callable=AsyncMock):

            client = TestClient(app)
            response = client.post(
                "/api/agents/register",
                json={
                    "name": sample_agent_card.name,
                    "description": sample_agent_card.description,
                    "url": str(sample_agent_card.url),
                    "path": sample_agent_card.path,
                    "tags": "code,review,testing",
                },
            )

            assert response.status_code == status.HTTP_201_CREATED

        app.dependency_overrides.clear()

    def test_register_unauthorized_user(
        self,
        mock_enhanced_auth_viewer,
        sample_agent_card,
    ):
        """Test registration without permission."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_viewer

        client = TestClient(app)
        response = client.post(
            "/api/agents/register",
            json={
                "name": sample_agent_card.name,
                "description": sample_agent_card.description,
                "url": str(sample_agent_card.url),
                "path": sample_agent_card.path,
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestAgentList:
    """Tests for agent listing endpoint GET /api/agents."""

    def test_list_all_agents(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
        private_agent_card,
    ):
        """Test listing all agents."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        agents = [sample_agent_card, private_agent_card]

        with patch.object(agent_service, "get_all_agents", return_value=agents), \
             patch.object(agent_service, "is_agent_enabled", return_value=False):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "agents" in data
            assert "total_count" in data
            assert data["total_count"] == 2

        app.dependency_overrides.clear()

    def test_list_agents_empty(
        self,
        mock_enhanced_auth_admin,
    ):
        """Test listing agents when none exist."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(agent_service, "get_all_agents", return_value=[]):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 0
            assert data["agents"] == []

        app.dependency_overrides.clear()

    def test_list_agents_enabled_only(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
        private_agent_card,
    ):
        """Test filtering by enabled_only=true."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        agents = [sample_agent_card, private_agent_card]

        def is_enabled_side_effect(path):
            return path == sample_agent_card.path

        with patch.object(agent_service, "get_all_agents", return_value=agents), \
             patch.object(agent_service, "is_agent_enabled", side_effect=is_enabled_side_effect):

            client = TestClient(app)
            response = client.get("/api/agents?enabled_only=true")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 1

        app.dependency_overrides.clear()

    def test_list_agents_by_visibility(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
        private_agent_card,
    ):
        """Test filtering by visibility."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        agents = [sample_agent_card, private_agent_card]

        with patch.object(agent_service, "get_all_agents", return_value=agents), \
             patch.object(agent_service, "is_agent_enabled", return_value=False):

            client = TestClient(app)
            response = client.get("/api/agents?visibility=public")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 1

        app.dependency_overrides.clear()

    def test_list_agents_with_search_query(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test search by query parameter."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        agents = [sample_agent_card]

        with patch.object(agent_service, "get_all_agents", return_value=agents), \
             patch.object(agent_service, "is_agent_enabled", return_value=False):

            client = TestClient(app)
            response = client.get("/api/agents?query=code")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 1

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestGetAgent:
    """Tests for get single agent endpoint GET /api/agents/{path}."""

    def test_get_existing_public_agent(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test getting existing public agent."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(agent_service, "get_agent_info", return_value=sample_agent_card):

            client = TestClient(app)
            response = client.get(f"/api/agents{sample_agent_card.path}")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["name"] == sample_agent_card.name
            assert data["path"] == sample_agent_card.path

        app.dependency_overrides.clear()

    def test_get_nonexistent_agent_returns_404(
        self,
        mock_enhanced_auth_admin,
    ):
        """Test getting non-existent agent returns 404."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(agent_service, "get_agent_info", return_value=None):

            client = TestClient(app)
            response = client.get("/api/agents/nonexistent")

            assert response.status_code == status.HTTP_404_NOT_FOUND

        app.dependency_overrides.clear()

    def test_get_agent_path_normalization(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test path normalization (with/without trailing slash)."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(agent_service, "get_agent_info", return_value=sample_agent_card):

            client = TestClient(app)
            response = client.get(f"/api/agents{sample_agent_card.path}/")

            assert response.status_code == status.HTTP_200_OK

        app.dependency_overrides.clear()

    def test_get_private_agent_owner_access(
        self,
        mock_enhanced_auth_user,
        private_agent_card,
    ):
        """Test private agent only accessible to owner."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_user

        with patch.object(agent_service, "get_agent_info", return_value=private_agent_card):

            client = TestClient(app)
            response = client.get(f"/api/agents{private_agent_card.path}")

            assert response.status_code == status.HTTP_200_OK

        app.dependency_overrides.clear()

    def test_get_private_agent_non_owner_denied(
        self,
        mock_enhanced_auth_viewer,
        private_agent_card,
    ):
        """Test private agent denied to non-owner non-admin."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_viewer

        with patch.object(agent_service, "get_agent_info", return_value=private_agent_card):

            client = TestClient(app)
            response = client.get(f"/api/agents{private_agent_card.path}")

            assert response.status_code == status.HTTP_403_FORBIDDEN

        app.dependency_overrides.clear()

    def test_get_group_restricted_agent_member(
        self,
        mock_enhanced_auth_user,
        group_agent_card,
    ):
        """Test group-restricted agent accessible to group members."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_user

        with patch.object(agent_service, "get_agent_info", return_value=group_agent_card):

            client = TestClient(app)
            response = client.get(f"/api/agents{group_agent_card.path}")

            assert response.status_code == status.HTTP_200_OK

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestUpdateAgent:
    """Tests for update agent endpoint PUT /api/agents/{path}."""

    def test_update_existing_agent_success(
        self,
        mock_enhanced_auth_user,
        private_agent_card,
    ):
        """Test successful agent update."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_user

        updated_card = private_agent_card.model_copy()
        updated_card.description = "Updated description"

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=private_agent_card,
        ), patch.object(
            agent_service,
            "update_agent",
            return_value=updated_card,
        ), patch("registry.services.search.service.faiss_service.add_or_update_agent", new_callable=AsyncMock):

            client = TestClient(app)
            response = client.put(
                f"/api/agents{private_agent_card.path}",
                json={
                    "name": updated_card.name,
                    "description": updated_card.description,
                    "url": str(updated_card.url),
                    "path": updated_card.path,
                },
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["description"] == "Updated description"

        app.dependency_overrides.clear()

    def test_update_nonexistent_agent_returns_404(
        self,
        mock_enhanced_auth_user,
    ):
        """Test updating non-existent agent returns 404."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_user

        with patch.object(agent_service, "get_agent_info", return_value=None):

            client = TestClient(app)
            response = client.put(
                "/api/agents/nonexistent",
                json={
                    "name": "Test",
                    "description": "Test",
                    "url": "https://test.example.com/api",
                    "path": "/agents/test",
                },
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND

        app.dependency_overrides.clear()

    def test_update_agent_path_cannot_change(
        self,
        mock_enhanced_auth_user,
        private_agent_card,
    ):
        """Test path cannot be changed on update."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_user

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=private_agent_card,
        ), patch.object(
            agent_service,
            "update_agent",
            return_value=private_agent_card,
        ), patch("registry.services.search.service.faiss_service.add_or_update_agent", new_callable=AsyncMock):

            client = TestClient(app)
            response = client.put(
                f"/api/agents{private_agent_card.path}",
                json={
                    "name": private_agent_card.name,
                    "description": private_agent_card.description,
                    "url": str(private_agent_card.url),
                    "path": "/agents/different-path",
                },
            )

            assert response.status_code == status.HTTP_200_OK

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestDeleteAgent:
    """Tests for delete agent endpoint DELETE /api/agents/{path}."""

    def test_delete_existing_agent_returns_204(
        self,
        mock_enhanced_auth_user,
        private_agent_card,
    ):
        """Test successful deletion returns 204."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_user

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=private_agent_card,
        ), patch.object(
            agent_service,
            "remove_agent",
            return_value=True,
        ), patch("registry.services.search.service.faiss_service.remove_agent", new_callable=AsyncMock):

            client = TestClient(app)
            response = client.delete(f"/api/agents{private_agent_card.path}")

            assert response.status_code == status.HTTP_204_NO_CONTENT

        app.dependency_overrides.clear()

    def test_delete_nonexistent_agent_returns_404(
        self,
        mock_enhanced_auth_user,
    ):
        """Test deleting non-existent agent returns 404."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_user

        with patch.object(agent_service, "get_agent_info", return_value=None):

            client = TestClient(app)
            response = client.delete("/api/agents/nonexistent")

            assert response.status_code == status.HTTP_404_NOT_FOUND

        app.dependency_overrides.clear()

    def test_delete_agent_permission_check(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test deletion respects ownership."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=sample_agent_card,
        ), patch.object(
            agent_service,
            "remove_agent",
            return_value=True,
        ), patch("registry.search.service.faiss_service.remove_agent", new_callable=AsyncMock):

            client = TestClient(app)
            response = client.delete(f"/api/agents{sample_agent_card.path}")

            assert response.status_code == status.HTTP_204_NO_CONTENT

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestToggleAgent:
    """Tests for toggle agent endpoint POST /api/agents/{path}/toggle."""

    def test_toggle_agent_enable(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test enabling agent toggle."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=sample_agent_card,
        ), patch.object(
            agent_service,
            "toggle_agent",
            return_value=True,
        ), patch("registry.search.service.faiss_service.add_or_update_agent", new_callable=AsyncMock):

            client = TestClient(app)
            response = client.post(
                f"/api/agents{sample_agent_card.path}/toggle?enabled=true"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["is_enabled"] is True

        app.dependency_overrides.clear()

    def test_toggle_agent_disable(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test disabling agent toggle."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=sample_agent_card,
        ), patch.object(
            agent_service,
            "toggle_agent",
            return_value=True,
        ), patch("registry.search.service.faiss_service.add_or_update_agent", new_callable=AsyncMock):

            client = TestClient(app)
            response = client.post(
                f"/api/agents{sample_agent_card.path}/toggle?enabled=false"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["is_enabled"] is False

        app.dependency_overrides.clear()

    def test_toggle_nonexistent_agent_returns_404(
        self,
        mock_enhanced_auth_admin,
    ):
        """Test toggle non-existent agent returns 404."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(agent_service, "get_agent_info", return_value=None):

            client = TestClient(app)
            response = client.post(
                "/api/agents/nonexistent/toggle?enabled=true"
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestDiscoverAgentsBySkills:
    """Tests for skill-based discovery POST /api/agents/discover."""

    def test_discover_by_skill_id(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test discover by skill ID."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        agents = [sample_agent_card]

        with patch.object(
            agent_service,
            "get_all_agents",
            return_value=agents,
        ), patch.object(
            agent_service,
            "is_agent_enabled",
            return_value=True,
        ):

            client = TestClient(app)
            response = client.post(
                "/api/agents/discover",
                json={"skills": ["review-code"]},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "agents" in data
            assert data["query"]["skills"] == ["review-code"]

        app.dependency_overrides.clear()

    def test_discover_by_multiple_skills(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test discover by multiple skills."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        agents = [sample_agent_card]

        with patch.object(
            agent_service,
            "get_all_agents",
            return_value=agents,
        ), patch.object(
            agent_service,
            "is_agent_enabled",
            return_value=True,
        ):

            client = TestClient(app)
            response = client.post(
                "/api/agents/discover",
                json={"skills": ["review-code", "suggest-improvements"]},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data["agents"]) > 0

        app.dependency_overrides.clear()

    def test_discover_with_tags_filter(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test discover with tags filter."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        agents = [sample_agent_card]

        with patch.object(
            agent_service,
            "get_all_agents",
            return_value=agents,
        ), patch.object(
            agent_service,
            "is_agent_enabled",
            return_value=True,
        ):

            client = TestClient(app)
            response = client.post(
                "/api/agents/discover",
                json={
                    "skills": ["review-code"],
                    "tags": ["code"],
                },
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["query"]["tags"] == ["code"]

        app.dependency_overrides.clear()

    def test_discover_max_results_parameter(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test max_results parameter."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        agents = [sample_agent_card]

        with patch.object(
            agent_service,
            "get_all_agents",
            return_value=agents,
        ), patch.object(
            agent_service,
            "is_agent_enabled",
            return_value=True,
        ):

            client = TestClient(app)
            response = client.post(
                "/api/agents/discover?max_results=5",
                json={"skills": ["review-code"]},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data["agents"]) <= 5

        app.dependency_overrides.clear()

    def test_discover_returns_only_enabled_agents(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test discover returns only enabled agents."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        agents = [sample_agent_card]

        def is_enabled_side_effect(path):
            return path == sample_agent_card.path

        with patch.object(
            agent_service,
            "get_all_agents",
            return_value=agents,
        ), patch.object(
            agent_service,
            "is_agent_enabled",
            side_effect=is_enabled_side_effect,
        ):

            client = TestClient(app)
            response = client.post(
                "/api/agents/discover",
                json={"skills": ["review-code"]},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            for agent in data["agents"]:
                assert agent["is_enabled"] is True

        app.dependency_overrides.clear()

    def test_discover_empty_skills_returns_400(
        self,
        mock_enhanced_auth_admin,
    ):
        """Test empty skills parameter returns 400."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        client = TestClient(app)
        response = client.post(
            "/api/agents/discover",
            json={"skills": []},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestSemanticDiscovery:
    """Tests for semantic discovery POST /api/agents/discover/semantic."""

    def test_discover_semantic_with_query(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test semantic search by natural language query."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        search_results = [
            {
                "path": sample_agent_card.path,
                "score": 0.92,
            }
        ]

        with patch("registry.search.service.faiss_service.search_entities", new_callable=AsyncMock, return_value=search_results), \
             patch.object(
                 agent_service,
                 "get_all_agents",
                 return_value=[sample_agent_card],
             ):

            client = TestClient(app)
            response = client.post(
                "/api/agents/discover/semantic?query=I%20need%20to%20review%20code"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "agents" in data
            assert data["query"] == "I need to review code"

        app.dependency_overrides.clear()

    def test_discover_semantic_max_results(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test max_results parameter in semantic search."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        search_results = [
            {
                "path": sample_agent_card.path,
                "score": 0.92,
            }
        ]

        with patch("registry.search.service.faiss_service.search_entities", new_callable=AsyncMock, return_value=search_results), \
             patch.object(
                 agent_service,
                 "get_all_agents",
                 return_value=[sample_agent_card],
             ):

            client = TestClient(app)
            response = client.post(
                "/api/agents/discover/semantic?query=review%20code&max_results=5"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data["agents"]) <= 5

        app.dependency_overrides.clear()

    def test_discover_semantic_empty_query_returns_400(
        self,
        mock_enhanced_auth_admin,
    ):
        """Test empty query returns 400."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        client = TestClient(app)
        response = client.post(
            "/api/agents/discover/semantic?query="
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        app.dependency_overrides.clear()

    def test_discover_semantic_returns_only_enabled(
        self,
        mock_enhanced_auth_admin,
        sample_agent_card,
    ):
        """Test semantic discovery returns only enabled agents."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        search_results = [
            {
                "path": sample_agent_card.path,
                "score": 0.92,
            }
        ]

        with patch("registry.search.service.faiss_service.search_entities", new_callable=AsyncMock, return_value=search_results), \
             patch.object(
                 agent_service,
                 "get_all_agents",
                 return_value=[sample_agent_card],
             ):

            client = TestClient(app)
            response = client.post(
                "/api/agents/discover/semantic?query=review%20code"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            for agent in data["agents"]:
                assert agent["is_enabled"] is True

        app.dependency_overrides.clear()
