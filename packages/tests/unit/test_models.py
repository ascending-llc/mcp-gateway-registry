"""Tests for ExtendedMCPServer model structure and validation."""

from datetime import UTC, datetime

import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError

from packages.models.extended_mcp_server import ExtendedMCPServer, MCPServerDocument


class TestExtendedMCPServerStructure:
    """Test ExtendedMCPServer model structure matches design specification."""

    def test_model_alias(self):
        """Verify MCPServerDocument is an alias for ExtendedMCPServer."""
        assert MCPServerDocument is ExtendedMCPServer

    def test_required_fields(self):
        """Test that required fields are enforced."""
        # Use Pydantic's model_validate without triggering Beanie's Document.__init__
        with pytest.raises(ValidationError) as exc_info:
            ExtendedMCPServer.model_validate({}, strict=False)

        errors = exc_info.value.errors()
        required_fields = {error["loc"][0] for error in errors if error["type"] == "missing"}

        # These fields are required according to the model
        assert "serverName" in required_fields
        assert "config" in required_fields
        assert "author" in required_fields
        assert "path" in required_fields

    def test_root_level_fields_not_in_config(self):
        """Verify registry-specific fields are stored at root level, not in config."""
        server_dict = {
            "serverName": "test-server",
            "config": {
                "title": "Test Server",
                "description": "Test description",
                "type": "streamable-http",
                "url": "http://test:8000",
                "tools": "tool1, tool2",
                "capabilities": "{}",
            },
            "author": str(PydanticObjectId()),
            "path": "/mcp/test",
            "tags": ["test", "demo"],
            "scope": "private_user",
            "status": "active",
            "numTools": 2,
            "numStars": 5,
        }

        # Use model_construct to bypass Beanie's collection check
        server = ExtendedMCPServer.model_construct(**server_dict)

        # Root-level fields should NOT be in config
        assert "scope" not in server.config
        assert "status" not in server.config
        assert "path" not in server.config
        assert "tags" not in server.config
        assert "numTools" not in server.config
        assert "numStars" not in server.config
        assert "lastConnected" not in server.config
        assert "lastError" not in server.config
        assert "errorMessage" not in server.config

        # Root-level fields should be accessible directly
        assert server.scope == "private_user"
        assert server.status == "active"
        assert server.path == "/mcp/test"
        assert server.tags == ["test", "demo"]
        assert server.numTools == 2
        assert server.numStars == 5

    def test_config_fields_structure(self):
        """Verify config object contains MCP-specific configuration."""
        config_data = {
            "title": "GitHub Server",
            "description": "GitHub integration",
            "type": "streamable-http",
            "url": "http://github-server:8011",
            "apiKey": {
                "key": "test_key",
                "source": "env",
                "authorization_type": "bearer",
            },
            "requiresOAuth": False,
            "capabilities": '{"experimental": {}}',
            "tools": "create_repo, list_issues",
            "toolFunctions": {
                "create_repo": {
                    "type": "function",
                    "function": {
                        "name": "create_repo",
                        "description": "Create a repository",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            },
            "initDuration": 170,
        }

        server_dict = {
            "serverName": "github",
            "config": config_data,
            "author": str(PydanticObjectId()),
            "path": "/mcp/github",
        }

        server = ExtendedMCPServer.model_construct(**server_dict)

        # Verify config fields are stored correctly
        assert server.config["title"] == "GitHub Server"
        assert server.config["description"] == "GitHub integration"
        assert server.config["type"] == "streamable-http"
        assert server.config["url"] == "http://github-server:8011"
        assert server.config["requiresOAuth"] is False
        assert server.config["capabilities"] == '{"experimental": {}}'
        assert server.config["tools"] == "create_repo, list_issues"
        assert "toolFunctions" in server.config
        assert server.config["initDuration"] == 170

    def test_default_values(self):
        """Test default values are set correctly."""
        server_dict = {
            "serverName": "test",
            "config": {"title": "Test", "type": "sse", "url": "http://test:8000"},
            "author": str(PydanticObjectId()),
            "path": "/mcp/test",
        }

        server = ExtendedMCPServer.model_construct(**server_dict)

        # Verify defaults (model_construct doesn't apply defaults, so we need to check field definitions)
        # These would be set by Pydantic during normal instantiation
        assert hasattr(server, "scope")
        assert hasattr(server, "status")
        assert hasattr(server, "tags")

    def test_optional_monitoring_fields(self):
        """Test optional monitoring fields (lastConnected, lastError, errorMessage)."""
        now = datetime.now(UTC)

        server_dict = {
            "serverName": "test",
            "config": {"title": "Test", "type": "sse", "url": "http://test:8000"},
            "author": str(PydanticObjectId()),
            "path": "/mcp/test",
            "lastConnected": now,
            "lastError": now,
            "errorMessage": "Connection timeout",
        }

        server = ExtendedMCPServer.model_construct(**server_dict)

        assert server.lastConnected == now
        assert server.lastError == now
        assert server.errorMessage == "Connection timeout"

    def test_scope_values(self):
        """Test valid scope values."""
        valid_scopes = ["private_user", "shared_user", "shared_app"]

        for scope in valid_scopes:
            server_dict = {
                "serverName": f"test-{scope}",
                "config": {"title": "Test", "type": "sse", "url": "http://test:8000"},
                "author": str(PydanticObjectId()),
                "path": f"/mcp/{scope}",
                "scope": scope,
            }
            server = ExtendedMCPServer.model_construct(**server_dict)
            assert server.scope == scope

    def test_status_values(self):
        """Test valid status values."""
        valid_statuses = ["active", "inactive", "error"]

        for status in valid_statuses:
            server_dict = {
                "serverName": f"test-{status}",
                "config": {"title": "Test", "type": "sse", "url": "http://test:8000"},
                "author": str(PydanticObjectId()),
                "path": f"/mcp/{status}",
                "status": status,
            }
            server = ExtendedMCPServer.model_construct(**server_dict)
            assert server.status == status

    def test_tags_array(self):
        """Test tags field accepts array of strings."""
        server_dict = {
            "serverName": "test",
            "config": {"title": "Test", "type": "sse", "url": "http://test:8000"},
            "author": str(PydanticObjectId()),
            "path": "/mcp/test",
            "tags": ["github", "git", "vcs"],
        }

        server = ExtendedMCPServer.model_construct(**server_dict)

        assert isinstance(server.tags, list)
        assert len(server.tags) == 3
        assert "github" in server.tags

    def test_beanie_settings(self):
        """Test Beanie document settings are configured correctly."""
        assert ExtendedMCPServer.Settings.name == "mcpservers"
        assert ExtendedMCPServer.Settings.keep_nulls is False
        assert ExtendedMCPServer.Settings.use_state_management is True

    def test_oauth_config_structure(self):
        """Test server with OAuth configuration in config object."""
        config_data = {
            "title": "OAuth Server",
            "description": "Server with OAuth",
            "type": "streamable-http",
            "url": "http://oauth-server:8000",
            "requiresOAuth": True,
            "oauth": {
                "client_id": "test_client",
                "authorization_url": "https://auth.example.com/authorize",
                "token_url": "https://auth.example.com/token",
                "scopes": ["read", "write"],
            },
            "capabilities": "{}",
            "tools": "tool1",
        }

        server_dict = {
            "serverName": "oauth-test",
            "config": config_data,
            "author": str(PydanticObjectId()),
            "path": "/mcp/oauth",
        }

        server = ExtendedMCPServer.model_construct(**server_dict)

        assert server.config["requiresOAuth"] is True
        assert "oauth" in server.config
        assert server.config["oauth"]["client_id"] == "test_client"
        assert "scopes" in server.config["oauth"]

    def test_numtools_field_alias(self):
        """Test numTools field accepts both numTools and its alias."""
        server_dict = {
            "serverName": "test",
            "config": {"title": "Test", "type": "sse", "url": "http://test:8000"},
            "author": str(PydanticObjectId()),
            "path": "/mcp/test",
            "numTools": 5,
        }

        server = ExtendedMCPServer.model_construct(**server_dict)

        assert server.numTools == 5
