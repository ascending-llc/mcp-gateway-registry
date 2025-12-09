"""
Unit tests for rate_agent endpoint in agent_routes.py
"""

import pytest
from typing import Any, Dict
from unittest.mock import patch, Mock
from fastapi import status
from fastapi.testclient import TestClient

from registry.main import app
from registry.services.agent_service import agent_service
from registry.schemas.agent_models import AgentCard


@pytest.fixture
def mock_user_context() -> Dict[str, Any]:
    """Mock authenticated user context."""
    return {
        "username": "testuser",
        "groups": ["users"],
        "is_admin": False,
        "ui_permissions": {},
        "accessible_agents": ["all"],
    }


@pytest.fixture
def mock_admin_context() -> Dict[str, Any]:
    """Mock admin user context."""
    return {
        "username": "admin",
        "groups": ["admins"],
        "is_admin": True,
        "ui_permissions": {},
        "accessible_agents": ["all"],
    }


@pytest.fixture
def sample_agent_card() -> AgentCard:
    """Create a sample agent card for testing."""
    return AgentCard(
        protocol_version="1.0",
        name="Test Agent",
        description="A test agent",
        url="http://localhost:8080/test-agent",
        path="/test-agent",
        version="1.0.0",
        tags=["test"],
        skills=[],
        visibility="public",
        registered_by="admin",
        num_stars=0.0,
        rating_details=[],
    )


@pytest.mark.unit
class TestRateAgent:
    """Test suite for POST /agents/{path}/rate endpoint."""

    def test_rate_agent_success(
        self,
        mock_user_context: Dict[str, Any],
        sample_agent_card: AgentCard,
    ) -> None:
        """Test successfully rating an agent."""
        from registry.auth.dependencies import nginx_proxied_auth

        def _mock_auth(session=None):
            return mock_user_context

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=sample_agent_card,
        ), patch.object(
            agent_service,
            "update_rating",
            return_value=4.5,
        ):
            client = TestClient(app)
            response = client.post(
                "/agents/test-agent/rate",
                json={"rating": 5},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["message"] == "Rating added successfully"

        app.dependency_overrides.clear()

    def test_rate_agent_not_found(
        self,
        mock_user_context: Dict[str, Any],
    ) -> None:
        """Test rating a non-existent agent returns 404."""
        from registry.auth.dependencies import nginx_proxied_auth

        def _mock_auth(session=None):
            return mock_user_context

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=None,
        ):
            client = TestClient(app)
            response = client.post(
                "/agents/nonexistent/rate",
                json={"rating": 5},
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "not found" in response.json()["detail"].lower()

        app.dependency_overrides.clear()

    def test_rate_agent_no_access(
        self,
        sample_agent_card: AgentCard,
    ) -> None:
        """Test rating an agent without access returns 403."""
        from registry.auth.dependencies import nginx_proxied_auth

        # User with restricted access
        restricted_context = {
            "username": "restricted_user",
            "groups": [],
            "is_admin": False,
            "ui_permissions": {},
            "accessible_agents": ["other-agent"],  # Not the test agent
        }

        def _mock_auth(session=None):
            return restricted_context

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=sample_agent_card,
        ):
            client = TestClient(app)
            response = client.post(
                "/agents/test-agent/rate",
                json={"rating": 5},
            )

            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "access" in response.json()["detail"].lower()

        app.dependency_overrides.clear()

    def test_rate_agent_invalid_rating_type(
        self,
        mock_user_context: Dict[str, Any],
        sample_agent_card: AgentCard,
    ) -> None:
        """Test rating with invalid type returns validation error."""
        from registry.auth.dependencies import nginx_proxied_auth

        def _mock_auth(session=None):
            return mock_user_context

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=sample_agent_card,
        ):
            client = TestClient(app)
            response = client.post(
                "/agents/test-agent/rate",
                json={"rating": "five"},  # String instead of int
            )

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        app.dependency_overrides.clear()

    def test_rate_agent_missing_rating(
        self,
        mock_user_context: Dict[str, Any],
        sample_agent_card: AgentCard,
    ) -> None:
        """Test rating without rating field returns validation error."""
        from registry.auth.dependencies import nginx_proxied_auth

        def _mock_auth(session=None):
            return mock_user_context

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=sample_agent_card,
        ):
            client = TestClient(app)
            response = client.post(
                "/agents/test-agent/rate",
                json={},  # Missing rating field
            )

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        app.dependency_overrides.clear()

    def test_rate_agent_update_rating_fails(
        self,
        mock_user_context: Dict[str, Any],
        sample_agent_card: AgentCard,
    ) -> None:
        """Test handling when update_rating fails."""
        from registry.auth.dependencies import nginx_proxied_auth

        def _mock_auth(session=None):
            return mock_user_context

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=sample_agent_card,
        ), patch.object(
            agent_service,
            "update_rating",
            side_effect=ValueError("Failed to save rating"),
        ):
            client = TestClient(app)
            response = client.post(
                "/agents/test-agent/rate",
                json={"rating": 5},
            )

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Failed to save rating" in response.json()["detail"]

        app.dependency_overrides.clear()

    def test_rate_agent_with_different_ratings(
        self,
        mock_user_context: Dict[str, Any],
        sample_agent_card: AgentCard,
    ) -> None:
        """Test rating an agent with different valid rating values."""
        from registry.auth.dependencies import nginx_proxied_auth

        def _mock_auth(session=None):
            return mock_user_context

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth

        for rating_value in [1, 2, 3, 4, 5]:
            with patch.object(
                agent_service,
                "get_agent_info",
                return_value=sample_agent_card,
            ), patch.object(
                agent_service,
                "update_rating",
                return_value=float(rating_value),
            ):
                client = TestClient(app)
                response = client.post(
                    "/agents/test-agent/rate",
                    json={"rating": rating_value},
                )

                assert response.status_code == status.HTTP_200_OK
                assert response.json()["message"] == "Rating added successfully"

        app.dependency_overrides.clear()

    def test_rate_agent_path_normalization(
        self,
        mock_user_context: Dict[str, Any],
        sample_agent_card: AgentCard,
    ) -> None:
        """Test that agent path is normalized correctly."""
        from registry.auth.dependencies import nginx_proxied_auth

        def _mock_auth(session=None):
            return mock_user_context

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=sample_agent_card,
        ) as mock_get_agent, patch.object(
            agent_service,
            "update_rating",
            return_value=5.0,
        ) as mock_update:
            client = TestClient(app)
            # Test with path without leading slash
            response = client.post(
                "/agents/test-agent/rate",
                json={"rating": 5},
            )

            assert response.status_code == status.HTTP_200_OK
            # Verify the path was normalized (should have leading slash)
            mock_get_agent.assert_called_once_with("/test-agent")
            mock_update.assert_called_once_with("/test-agent", "testuser", 5)

        app.dependency_overrides.clear()

    def test_rate_agent_private_agent_by_owner(
        self,
        mock_user_context: Dict[str, Any],
    ) -> None:
        """Test that agent owner can rate their private agent."""
        from registry.auth.dependencies import nginx_proxied_auth

        # Create private agent owned by testuser
        private_agent = AgentCard(
            protocol_version="1.0",
            name="Private Agent",
            description="A private agent",
            url="http://localhost:8080/private-agent",
            path="/private-agent",
            version="1.0.0",
            tags=["test"],
            skills=[],
            visibility="private",
            registered_by="testuser",  # Same as mock_user_context username
            num_stars=0.0,
            rating_details=[],
        )

        def _mock_auth(session=None):
            return mock_user_context

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=private_agent,
        ), patch.object(
            agent_service,
            "update_rating",
            return_value=5.0,
        ):
            client = TestClient(app)
            response = client.post(
                "/agents/private-agent/rate",
                json={"rating": 5},
            )

            assert response.status_code == status.HTTP_200_OK

        app.dependency_overrides.clear()

    def test_rate_agent_group_restricted_with_access(
        self,
    ) -> None:
        """Test rating a group-restricted agent when user is in allowed group."""
        from registry.auth.dependencies import nginx_proxied_auth

        # User in the allowed group
        user_context = {
            "username": "groupuser",
            "groups": ["allowed-group"],
            "is_admin": False,
            "ui_permissions": {},
            "accessible_agents": ["all"],
        }

        # Group-restricted agent
        group_agent = AgentCard(
            protocol_version="1.0",
            name="Group Agent",
            description="A group-restricted agent",
            url="http://localhost:8080/group-agent",
            path="/group-agent",
            version="1.0.0",
            tags=["test"],
            skills=[],
            visibility="group-restricted",
            allowed_groups=["allowed-group"],
            registered_by="admin",
            num_stars=0.0,
            rating_details=[],
        )

        def _mock_auth(session=None):
            return user_context

        app.dependency_overrides[nginx_proxied_auth] = _mock_auth

        with patch.object(
            agent_service,
            "get_agent_info",
            return_value=group_agent,
        ), patch.object(
            agent_service,
            "update_rating",
            return_value=4.0,
        ):
            client = TestClient(app)
            response = client.post(
                "/agents/group-agent/rate",
                json={"rating": 4},
            )

            assert response.status_code == status.HTTP_200_OK

        app.dependency_overrides.clear()
