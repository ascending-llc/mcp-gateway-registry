"""
Tests for agent visibility filtering and access control.

This module provides comprehensive tests for the _filter_agents_by_access function
which implements the permission-based filtering logic:
- Public agents: All users can see
- Private agents: Only the registered user can see
- Group-restricted agents: Users in allowed groups can see
- Admins: Can see all agents
"""

import pytest
from typing import Any, Dict
from unittest.mock import patch
from fastapi import status
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from registry.main import app
from registry.schemas.agent_models import (
    AgentCard,
    Skill,
)


@pytest.fixture
def public_agent() -> AgentCard:
    """Create a public agent visible to all users."""
    return AgentCard(
        protocol_version="1.0",
        name="Public Code Reviewer",
        description="Reviews code publicly",
        url=HttpUrl("https://code-reviewer.example.com/api"),
        path="/agents/public-reviewer",
        visibility="public",
        trust_level="verified",
        skills=[
            Skill(
                id="review",
                name="Code Review",
                description="Reviews code",
                tags=["review"],
            ),
        ],
    )


@pytest.fixture
def private_agent_alice() -> AgentCard:
    """Create a private agent owned by alice."""
    return AgentCard(
        protocol_version="1.0",
        name="Alice's Private Agent",
        description="Private agent for alice only",
        url=HttpUrl("https://alice-agent.example.com/api"),
        path="/agents/alice-private",
        visibility="private",
        registered_by="alice",
        trust_level="trusted",
        skills=[
            Skill(
                id="private-task",
                name="Private Task",
                description="Only alice can see this",
                tags=["private"],
            ),
        ],
    )


@pytest.fixture
def private_agent_bob() -> AgentCard:
    """Create a private agent owned by bob."""
    return AgentCard(
        protocol_version="1.0",
        name="Bob's Private Agent",
        description="Private agent for bob only",
        url=HttpUrl("https://bob-agent.example.com/api"),
        path="/agents/bob-private",
        visibility="private",
        registered_by="bob",
        trust_level="trusted",
        skills=[
            Skill(
                id="private-task",
                name="Private Task",
                description="Only bob can see this",
                tags=["private"],
            ),
        ],
    )


@pytest.fixture
def group_agent_engineers() -> AgentCard:
    """Create a group-restricted agent for engineers group."""
    return AgentCard(
        protocol_version="1.0",
        name="Engineering Tools Agent",
        description="Restricted to engineers group",
        url=HttpUrl("https://eng-tools.example.com/api"),
        path="/agents/engineering-tools",
        visibility="group-restricted",
        allowed_groups=["engineers"],
        trust_level="verified",
        skills=[
            Skill(
                id="eng-task",
                name="Engineering Task",
                description="For engineers only",
                tags=["engineering"],
            ),
        ],
    )


@pytest.fixture
def group_agent_support() -> AgentCard:
    """Create a group-restricted agent for support group."""
    return AgentCard(
        protocol_version="1.0",
        name="Support Tools Agent",
        description="Restricted to support group",
        url=HttpUrl("https://support-tools.example.com/api"),
        path="/agents/support-tools",
        visibility="group-restricted",
        allowed_groups=["support"],
        trust_level="verified",
        skills=[
            Skill(
                id="support-task",
                name="Support Task",
                description="For support team only",
                tags=["support"],
            ),
        ],
    )


@pytest.fixture
def admin_user_context() -> Dict[str, Any]:
    """Create admin user context."""
    return {
        "username": "admin",
        "groups": ["admins"],
        "scopes": ["admin"],
        "auth_method": "traditional",
        "provider": "local",
        "ui_permissions": {"list_agents": ["all"]},
        "is_admin": True,
    }


@pytest.fixture
def alice_engineer_context() -> Dict[str, Any]:
    """Create alice user context (engineer group)."""
    return {
        "username": "alice",
        "groups": ["engineers"],
        "scopes": ["agent-user"],
        "auth_method": "oauth2",
        "provider": "cognito",
        "ui_permissions": {"list_agents": ["all"]},
        "is_admin": False,
    }


@pytest.fixture
def bob_support_context() -> Dict[str, Any]:
    """Create bob user context (support group)."""
    return {
        "username": "bob",
        "groups": ["support"],
        "scopes": ["agent-user"],
        "auth_method": "oauth2",
        "provider": "cognito",
        "ui_permissions": {"list_agents": ["all"]},
        "is_admin": False,
    }


@pytest.fixture
def charlie_no_group_context() -> Dict[str, Any]:
    """Create charlie user context (no special groups)."""
    return {
        "username": "charlie",
        "groups": [],
        "scopes": ["agent-user"],
        "auth_method": "oauth2",
        "provider": "cognito",
        "ui_permissions": {"list_agents": ["all"]},
        "is_admin": False,
    }


@pytest.fixture
def alice_multiple_groups_context() -> Dict[str, Any]:
    """Create alice user context (multiple groups)."""
    return {
        "username": "alice",
        "groups": ["engineers", "support"],
        "scopes": ["agent-user"],
        "auth_method": "oauth2",
        "provider": "cognito",
        "ui_permissions": {"list_agents": ["all"]},
        "is_admin": False,
    }


def _mock_auth_factory(user_context: Dict[str, Any]):
    """Factory to create mock auth dependency."""
    def _mock_auth(session=None):
        return user_context
    return _mock_auth


@pytest.mark.unit
class TestPublicAgentVisibility:
    """Tests for public agent visibility - accessible to all users."""

    def test_public_agent_visible_to_admin(
        self,
        public_agent,
        admin_user_context,
    ):
        """Public agent should be visible to admin."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(admin_user_context)

        with patch.object(agent_service, "get_all_agents", return_value=[public_agent]), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 1
            assert data["agents"][0]["path"] == public_agent.path

        app.dependency_overrides.clear()

    def test_public_agent_visible_to_engineer(
        self,
        public_agent,
        alice_engineer_context,
    ):
        """Public agent should be visible to engineer user."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(alice_engineer_context)

        with patch.object(agent_service, "get_all_agents", return_value=[public_agent]), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 1
            assert data["agents"][0]["path"] == public_agent.path

        app.dependency_overrides.clear()

    def test_public_agent_visible_to_user_no_groups(
        self,
        public_agent,
        charlie_no_group_context,
    ):
        """Public agent should be visible to user with no groups."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(charlie_no_group_context)

        with patch.object(agent_service, "get_all_agents", return_value=[public_agent]), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 1
            assert data["agents"][0]["path"] == public_agent.path

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestPrivateAgentVisibility:
    """Tests for private agent visibility - only owner can see."""

    def test_private_agent_visible_to_owner(
        self,
        private_agent_alice,
        alice_engineer_context,
    ):
        """Private agent should be visible to its owner."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(alice_engineer_context)

        with patch.object(agent_service, "get_all_agents", return_value=[private_agent_alice]), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 1
            assert data["agents"][0]["path"] == private_agent_alice.path

        app.dependency_overrides.clear()

    def test_private_agent_hidden_from_other_user(
        self,
        private_agent_alice,
        bob_support_context,
    ):
        """Private agent should be hidden from other users."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(bob_support_context)

        with patch.object(agent_service, "get_all_agents", return_value=[private_agent_alice]), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 0
            assert data["agents"] == []

        app.dependency_overrides.clear()

    def test_private_agent_hidden_from_user_no_groups(
        self,
        private_agent_alice,
        charlie_no_group_context,
    ):
        """Private agent should be hidden from user with no groups."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(charlie_no_group_context)

        with patch.object(agent_service, "get_all_agents", return_value=[private_agent_alice]), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 0
            assert data["agents"] == []

        app.dependency_overrides.clear()

    def test_admin_can_see_private_agent(
        self,
        private_agent_alice,
        admin_user_context,
    ):
        """Admin should be able to see private agents."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(admin_user_context)

        with patch.object(agent_service, "get_all_agents", return_value=[private_agent_alice]), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 1
            assert data["agents"][0]["path"] == private_agent_alice.path

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestGroupRestrictedAgentVisibility:
    """Tests for group-restricted agent visibility - members only."""

    def test_group_agent_visible_to_group_member(
        self,
        group_agent_engineers,
        alice_engineer_context,
    ):
        """Group-restricted agent should be visible to group members."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(alice_engineer_context)

        with patch.object(agent_service, "get_all_agents", return_value=[group_agent_engineers]), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 1
            assert data["agents"][0]["path"] == group_agent_engineers.path

        app.dependency_overrides.clear()

    def test_group_agent_hidden_from_non_member(
        self,
        group_agent_engineers,
        bob_support_context,
    ):
        """Group-restricted agent should be hidden from non-members."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(bob_support_context)

        with patch.object(agent_service, "get_all_agents", return_value=[group_agent_engineers]), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 0
            assert data["agents"] == []

        app.dependency_overrides.clear()

    def test_group_agent_visible_to_user_in_multiple_groups(
        self,
        group_agent_engineers,
        group_agent_support,
        alice_multiple_groups_context,
    ):
        """Group-restricted agents should be visible to users in any allowed group."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(alice_multiple_groups_context)

        agents = [group_agent_engineers, group_agent_support]

        with patch.object(agent_service, "get_all_agents", return_value=agents), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 2
            paths = [agent["path"] for agent in data["agents"]]
            assert group_agent_engineers.path in paths
            assert group_agent_support.path in paths

        app.dependency_overrides.clear()

    def test_group_agent_hidden_from_user_no_groups(
        self,
        group_agent_engineers,
        charlie_no_group_context,
    ):
        """Group-restricted agent should be hidden from user with no groups."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(charlie_no_group_context)

        with patch.object(agent_service, "get_all_agents", return_value=[group_agent_engineers]), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 0
            assert data["agents"] == []

        app.dependency_overrides.clear()

    def test_admin_can_see_group_restricted_agent(
        self,
        group_agent_engineers,
        admin_user_context,
    ):
        """Admin should be able to see group-restricted agents."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(admin_user_context)

        with patch.object(agent_service, "get_all_agents", return_value=[group_agent_engineers]), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 1
            assert data["agents"][0]["path"] == group_agent_engineers.path

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestMixedVisibilityFiltering:
    """Tests for mixed visibility scenarios with multiple agents."""

    def test_mixed_visibility_for_admin(
        self,
        public_agent,
        private_agent_alice,
        private_agent_bob,
        group_agent_engineers,
        group_agent_support,
        admin_user_context,
    ):
        """Admin should see all agents regardless of visibility."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(admin_user_context)

        agents = [
            public_agent,
            private_agent_alice,
            private_agent_bob,
            group_agent_engineers,
            group_agent_support,
        ]

        with patch.object(agent_service, "get_all_agents", return_value=agents), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total_count"] == 5

        app.dependency_overrides.clear()

    def test_mixed_visibility_for_alice_engineer(
        self,
        public_agent,
        private_agent_alice,
        private_agent_bob,
        group_agent_engineers,
        group_agent_support,
        alice_engineer_context,
    ):
        """Alice should see: public, her private, engineer group-restricted agents."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(alice_engineer_context)

        agents = [
            public_agent,
            private_agent_alice,
            private_agent_bob,
            group_agent_engineers,
            group_agent_support,
        ]

        with patch.object(agent_service, "get_all_agents", return_value=agents), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Should see: public (1) + alice's private (1) + engineers group (1) = 3
            assert data["total_count"] == 3
            paths = [agent["path"] for agent in data["agents"]]
            assert public_agent.path in paths
            assert private_agent_alice.path in paths
            assert group_agent_engineers.path in paths
            assert private_agent_bob.path not in paths
            assert group_agent_support.path not in paths

        app.dependency_overrides.clear()

    def test_mixed_visibility_for_bob_support(
        self,
        public_agent,
        private_agent_alice,
        private_agent_bob,
        group_agent_engineers,
        group_agent_support,
        bob_support_context,
    ):
        """Bob should see: public, his private, support group-restricted agents."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(bob_support_context)

        agents = [
            public_agent,
            private_agent_alice,
            private_agent_bob,
            group_agent_engineers,
            group_agent_support,
        ]

        with patch.object(agent_service, "get_all_agents", return_value=agents), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Should see: public (1) + bob's private (1) + support group (1) = 3
            assert data["total_count"] == 3
            paths = [agent["path"] for agent in data["agents"]]
            assert public_agent.path in paths
            assert private_agent_bob.path in paths
            assert group_agent_support.path in paths
            assert private_agent_alice.path not in paths
            assert group_agent_engineers.path not in paths

        app.dependency_overrides.clear()

    def test_mixed_visibility_for_charlie_no_groups(
        self,
        public_agent,
        private_agent_alice,
        private_agent_bob,
        group_agent_engineers,
        group_agent_support,
        charlie_no_group_context,
    ):
        """Charlie should see only public agents (no groups, no private agents)."""
        from registry.auth.dependencies import nginx_proxied_auth
        from registry.services.agent_service import agent_service

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth_factory(charlie_no_group_context)

        agents = [
            public_agent,
            private_agent_alice,
            private_agent_bob,
            group_agent_engineers,
            group_agent_support,
        ]

        with patch.object(agent_service, "get_all_agents", return_value=agents), \
             patch.object(agent_service, "is_agent_enabled", return_value=True):

            client = TestClient(app)
            response = client.get("/api/agents")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            # Should see only public agents
            assert data["total_count"] == 1
            assert data["agents"][0]["path"] == public_agent.path

        app.dependency_overrides.clear()
