"""
Unit tests for server service.
"""
import json
import os
import pytest
from pathlib import Path, PosixPath, WindowsPath
from typing import Dict, Any
from unittest.mock import patch, mock_open, Mock

from registry.services.server_service import ServerServiceV1
from registry.core.config import settings
from registry.tests.fixtures.factories import ServerInfoFactory, create_multiple_servers


@pytest.mark.unit
@pytest.mark.servers
@pytest.mark.skip(reason="ServerServiceV1 refactored to use MongoDB - tests need rewrite")
class TestServerService:
    """Test suite for ServerService."""

    def test_init(self, server_service: ServerServiceV1):
        """Test ServerService initialization."""
        assert server_service.registered_servers == {}
        assert server_service.service_state == {}

    def test_path_to_filename(self, server_service: ServerServiceV1):
        """Test path to filename conversion."""
        assert server_service._path_to_filename("/api/v1/test") == "api_v1_test.json"
        assert server_service._path_to_filename("api/v1/test") == "api_v1_test.json"
        assert server_service._path_to_filename("/simple") == "simple.json"
        assert server_service._path_to_filename("/test.json") == "test.json"

    def test_register_server_success(self, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test successful server registration."""
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            
            result = server_service.register_server(sample_server)
            
            assert result is True
            assert sample_server["path"] in server_service.registered_servers
            assert server_service.registered_servers[sample_server["path"]] == sample_server
            assert server_service.service_state[sample_server["path"]] is False

    def test_register_server_duplicate_path(self, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test registering server with duplicate path fails."""
        # First registration
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            server_service.register_server(sample_server)
        
        # Second registration with same path should fail
        result = server_service.register_server(sample_server)
        assert result is False

    def test_register_server_save_failure(self, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test server registration fails when file save fails."""
        with patch.object(server_service, 'save_server_to_file', return_value=False):
            result = server_service.register_server(sample_server)
            assert result is False
            assert sample_server["path"] not in server_service.registered_servers

    def test_update_server_success(self, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test successful server update."""
        # First register the server
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            server_service.register_server(sample_server)
        
        # Update the server
        updated_server = sample_server.copy()
        updated_server["server_name"] = "Updated Name"
        
        with patch.object(server_service, 'save_server_to_file', return_value=True):
            result = server_service.update_server(sample_server["path"], updated_server)
            
            assert result is True
            assert server_service.registered_servers[sample_server["path"]]["server_name"] == "Updated Name"

    def test_update_server_not_found(self, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test updating non-existent server fails."""
        result = server_service.update_server("/nonexistent", sample_server)
        assert result is False

    def test_update_server_save_failure(self, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test server update fails when file save fails."""
        # First register the server
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            server_service.register_server(sample_server)
        
        # Try to update with save failure
        with patch.object(server_service, 'save_server_to_file', return_value=False):
            result = server_service.update_server(sample_server["path"], sample_server)
            assert result is False

    def test_toggle_service_success(self, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test successful service toggle."""
        # Register server first
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            server_service.register_server(sample_server)
        
        # Toggle to enabled
        with patch.object(server_service, 'save_service_state'):
            result = server_service.toggle_service(sample_server["path"], True)
            assert result is True
            assert server_service.service_state[sample_server["path"]] is True
        
        # Toggle to disabled
        with patch.object(server_service, 'save_service_state'):
            result = server_service.toggle_service(sample_server["path"], False)
            assert result is True
            assert server_service.service_state[sample_server["path"]] is False

    def test_toggle_service_not_found(self, server_service: ServerServiceV1):
        """Test toggling non-existent service fails."""
        result = server_service.toggle_service("/nonexistent", True)
        assert result is False

    def test_get_server_info(self, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test getting server info."""
        # Test non-existent server
        assert server_service.get_server_info("/nonexistent") is None
        
        # Register server and test retrieval
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            server_service.register_server(sample_server)
        
        result = server_service.get_server_info(sample_server["path"])
        assert result == sample_server

    def test_get_all_servers(self, server_service: ServerServiceV1, sample_servers: Dict[str, Dict[str, Any]]):
        """Test getting all servers."""
        # Empty case
        assert server_service.get_all_servers() == {}
        
        # Add servers
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            for server in sample_servers.values():
                server_service.register_server(server)
        
        result = server_service.get_all_servers()
        assert len(result) == len(sample_servers)

    def test_is_service_enabled(self, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test checking if service is enabled."""
        # Non-existent service
        assert server_service.is_service_enabled("/nonexistent") is False
        
        # Register server (defaults to disabled)
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            server_service.register_server(sample_server)
        
        assert server_service.is_service_enabled(sample_server["path"]) is False
        
        # Enable service
        with patch.object(server_service, 'save_service_state'):
            server_service.toggle_service(sample_server["path"], True)
            assert server_service.is_service_enabled(sample_server["path"]) is True

    def test_get_enabled_services(self, server_service: ServerServiceV1, sample_servers: Dict[str, Dict[str, Any]]):
        """Test getting enabled services."""
        # Empty case
        assert server_service.get_enabled_services() == []
        
        # Register servers
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            for server in sample_servers.values():
                server_service.register_server(server)
        
        # Enable some services
        paths = list(sample_servers.keys())
        with patch.object(server_service, 'save_service_state'):
            server_service.toggle_service(paths[0], True)
            server_service.toggle_service(paths[1], True)
        
        enabled = server_service.get_enabled_services()
        assert len(enabled) == 2
        assert paths[0] in enabled
        assert paths[1] in enabled
        assert paths[2] not in enabled

    @patch("builtins.open", new_callable=mock_open)
    @patch("json.dump")
    def test_save_server_to_file(self, mock_json_dump, mock_file, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test saving server to file."""
        result = server_service.save_server_to_file(sample_server)
        
        assert result is True
        mock_file.assert_called_once()
        mock_json_dump.assert_called_once_with(sample_server, mock_file.return_value, indent=2)

    @patch("builtins.open", side_effect=IOError("File error"))
    def test_save_server_to_file_failure(self, mock_file, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test server file save failure."""
        result = server_service.save_server_to_file(sample_server)
        assert result is False

    @patch("builtins.open", new_callable=mock_open)
    @patch("json.dump")
    def test_save_service_state(self, mock_json_dump, mock_file, server_service: ServerServiceV1):
        """Test saving service state."""
        server_service.service_state = {"/test": True, "/test2": False}
        server_service.save_service_state()
        
        mock_file.assert_called_once()
        mock_json_dump.assert_called_once_with(server_service.service_state, mock_file.return_value, indent=2)

    @patch("builtins.open", side_effect=IOError("File error"))
    def test_save_service_state_failure(self, mock_file, server_service: ServerServiceV1):
        """Test saving service state failure."""
        server_service.service_state = {"/test": True}
        # Should not raise exception
        server_service.save_service_state()

    def test_load_service_state_no_file(self, server_service: ServerServiceV1, temp_dir):
        """Test loading service state when no state file exists."""
        # Set up some registered servers
        server_service.registered_servers = {"/test": {"server_name": "Test"}}
        
        # Call the method
        server_service._load_service_state()
        
        # Verify state was initialized properly
        assert server_service.service_state == {"/test": False}

    @patch("builtins.open", new_callable=mock_open, read_data='{"test": true, "test2": false}')
    @patch("json.load")
    def test_load_service_state_with_file(self, mock_json_load, mock_file, server_service: ServerServiceV1):
        """Test loading service state from existing file."""
        mock_json_load.return_value = {"/test": True, "/test2": False}
        
        # Set up registered servers
        server_service.registered_servers = {"/test": {"server_name": "Test"}, "/test2": {"server_name": "Test2"}}
        
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_settings.service_state_file.exists.return_value = True
            server_service._load_service_state()
        
        assert server_service.service_state == {"/test": True, "/test2": False}

    @patch("builtins.open", side_effect=IOError("File error"))
    def test_load_service_state_file_error(self, mock_file, server_service: ServerServiceV1):
        """Test loading service state with file error."""
        server_service.registered_servers = {"/test": {"server_name": "Test"}}
        
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_settings.service_state_file.exists.return_value = True
            server_service._load_service_state()
        
        # Should fall back to default state
        assert server_service.service_state == {"/test": False}

    @patch("json.load", side_effect=json.JSONDecodeError("Bad JSON", "", 0))
    @patch("builtins.open", new_callable=mock_open)
    def test_load_service_state_json_error(self, mock_file, mock_json_load, server_service: ServerServiceV1):
        """Test loading service state with JSON decode error."""
        server_service.registered_servers = {"/test": {"server_name": "Test"}}
        
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_settings.service_state_file.exists.return_value = True
            server_service._load_service_state()
        
        # Should fall back to default state
        assert server_service.service_state == {"/test": False}

    def test_load_servers_and_state_empty_directory(self, server_service: ServerServiceV1):
        """Test loading servers when directory is empty."""
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_servers_dir = Mock()
            mock_servers_dir.mkdir = Mock()
            mock_servers_dir.glob.return_value = []
            mock_settings.servers_dir = mock_servers_dir
            
            with patch.object(server_service, '_load_service_state'):
                server_service.load_servers_and_state()
            
            assert server_service.registered_servers == {}

    def test_load_servers_and_state_with_servers(self, server_service: ServerServiceV1, sample_server: Dict[str, Any]):
        """Test loading servers from files."""
        test_fixtures_dir = Path(__file__).parent.parent.parent / "fixtures" / "servers"
        
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_settings.servers_dir = test_fixtures_dir
            mock_settings.state_file_path.name = "state.json"
            
            with patch.object(server_service, '_load_service_state'):
                server_service.load_servers_and_state()
                
                # Should have loaded test_server_1.json, test_server_2.json, and currenttime.json
                assert len(server_service.registered_servers) >= 3
                assert "/test1" in server_service.registered_servers
                assert "/test2" in server_service.registered_servers
                assert "/currenttime" in server_service.registered_servers
                assert server_service.registered_servers["/test1"]["server_name"] == "Test Server 1"
                assert server_service.registered_servers["/test2"]["server_name"] == "Test Server 2"

    def test_load_servers_and_state_file_error(self, server_service: ServerServiceV1):
        """Test loading servers with file read error."""
        mock_file = Mock()
        mock_file.name = "bad.json"
        mock_file.relative_to.return_value = Path("bad.json")
        mock_files = [mock_file]
        
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_servers_dir = Mock()
            mock_servers_dir.mkdir = Mock()
            mock_servers_dir.glob.return_value = mock_files
            mock_settings.servers_dir = mock_servers_dir
            mock_settings.state_file_path.name = "state.json"
            
            with patch("builtins.open", side_effect=IOError("File error")), \
                 patch.object(server_service, '_load_service_state'):
                
                server_service.load_servers_and_state()
                
                # Should continue loading other files and not crash
                assert server_service.registered_servers == {}

    def test_load_servers_and_state_json_error(self, server_service: ServerServiceV1):
        """Test loading servers with JSON decode error."""
        mock_file = Mock()
        mock_file.name = "invalid.json"
        mock_file.relative_to.return_value = Path("invalid.json")
        mock_files = [mock_file]
        
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_servers_dir = Mock()
            mock_servers_dir.mkdir = Mock()
            mock_servers_dir.glob.return_value = mock_files
            mock_settings.servers_dir = mock_servers_dir
            mock_settings.state_file_path.name = "state.json"
            
            with patch("builtins.open", new_callable=mock_open), \
                 patch("json.load", side_effect=json.JSONDecodeError("Bad JSON", "", 0)), \
                 patch.object(server_service, '_load_service_state'):
                
                server_service.load_servers_and_state()
                
                # Should continue and not crash
                assert server_service.registered_servers == {}

    def test_load_servers_and_state_missing_path(self, server_service: ServerServiceV1):
        """Test loading servers with missing path field."""
        mock_file = Mock()
        mock_file.name = "nopath.json"
        mock_file.relative_to.return_value = Path("nopath.json")
        mock_files = [mock_file]
        
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_servers_dir = Mock()
            mock_servers_dir.mkdir = Mock()
            mock_servers_dir.glob.return_value = mock_files
            mock_settings.servers_dir = mock_servers_dir
            mock_settings.state_file_path.name = "state.json"
            
            with patch("builtins.open", new_callable=mock_open), \
                 patch("json.load") as mock_json_load, \
                 patch.object(server_service, '_load_service_state'):
                
                mock_json_load.return_value = {"server_name": "No Path Server"}
                
                server_service.load_servers_and_state()
                
                # Should skip servers without path
                assert server_service.registered_servers == {}

    def test_load_servers_and_state_directory_not_exists(self, server_service: ServerServiceV1):
        """Test loading servers when directory doesn't exist."""
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_servers_dir = Mock()
            mock_servers_dir.mkdir = Mock()
            mock_servers_dir.glob.return_value = []
            mock_settings.servers_dir = mock_servers_dir
            
            with patch.object(server_service, '_load_service_state'):
                server_service.load_servers_and_state()
            
            assert server_service.registered_servers == {}


@pytest.mark.unit
@pytest.mark.servers
class TestBuildCompleteHeaders:
    """Test suite for _build_complete_headers_for_server function."""

    @pytest.fixture
    def mock_oauth_server(self):
        """Create mock OAuth server."""
        from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument
        server = Mock(spec=MCPServerDocument)
        server.serverName = "oauth-server"
        server.config = {
            "requiresOAuth": True,
            "oauth": {
                "authorizationUrl": "https://oauth.example.com/authorize",
                "tokenUrl": "https://oauth.example.com/token"
            }
        }
        return server

    @pytest.fixture
    def mock_apikey_server(self):
        """Create mock API key server."""
        from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument
        server = Mock(spec=MCPServerDocument)
        server.serverName = "apikey-server"
        server.config = {
            "apiKey": {
                "key": "test-api-key-123",
                "authorization_type": "bearer"
            }
        }
        return server

    @pytest.fixture
    def mock_basic_auth_server(self):
        """Create mock Basic auth server."""
        from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument
        server = Mock(spec=MCPServerDocument)
        server.serverName = "basic-auth-server"
        server.config = {
            "apiKey": {
                "key": "username:password",
                "authorization_type": "basic"
            }
        }
        return server

    @pytest.fixture
    def mock_custom_auth_server(self):
        """Create mock custom auth server."""
        from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument
        server = Mock(spec=MCPServerDocument)
        server.serverName = "custom-auth-server"
        server.config = {
            "apiKey": {
                "key": "custom-token-xyz",
                "authorization_type": "custom",
                "custom_header": "X-API-Key"
            }
        }
        return server

    @pytest.fixture
    def mock_custom_headers_server(self):
        """Create mock server with custom headers."""
        from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument
        server = Mock(spec=MCPServerDocument)
        server.serverName = "custom-headers-server"
        server.config = {
            "headers": [
                {"X-Custom-Header": "value1"},
                {"X-Another-Header": "value2"}
            ]
        }
        return server

    @pytest.mark.asyncio
    async def test_oauth_server_success(self, mock_oauth_server):
        """Test OAuth server returns valid access token."""
        from registry.services.server_service import _build_complete_headers_for_server
        from unittest.mock import AsyncMock
        
        with patch("registry.services.oauth.oauth_service.get_oauth_service") as mock_oauth_svc, \
             patch("registry.utils.crypto_utils.decrypt_auth_fields") as mock_decrypt:
            
            mock_decrypt.return_value = mock_oauth_server.config
            
            # Mock OAuth service
            oauth_service = AsyncMock()
            oauth_service.get_valid_access_token = AsyncMock(
                return_value=("access-token-123", None, None)
            )
            mock_oauth_svc.return_value = oauth_service
            
            headers = await _build_complete_headers_for_server(mock_oauth_server, "user-123")
            
            assert headers["Authorization"] == "Bearer access-token-123"
            assert headers["Content-Type"] == "application/json"
            assert headers["Accept"] == "application/json"
            oauth_service.get_valid_access_token.assert_called_once_with(
                user_id="user-123",
                server=mock_oauth_server
            )

    @pytest.mark.asyncio
    async def test_oauth_server_missing_user_id(self, mock_oauth_server):
        """Test OAuth server raises error when user_id is missing."""
        from registry.services.server_service import _build_complete_headers_for_server
        from registry.schemas.errors import MissingUserIdError
        
        with patch("registry.utils.crypto_utils.decrypt_auth_fields") as mock_decrypt:
            mock_decrypt.return_value = mock_oauth_server.config
            
            with pytest.raises(MissingUserIdError) as exc_info:
                await _build_complete_headers_for_server(mock_oauth_server, None)
            
            assert "User ID required" in str(exc_info.value)
            assert exc_info.value.server_name == "oauth-server"

    @pytest.mark.asyncio
    async def test_oauth_server_reauth_required(self, mock_oauth_server):
        """Test OAuth server raises error when re-authentication is required."""
        from registry.services.server_service import _build_complete_headers_for_server
        from registry.schemas.errors import OAuthReAuthRequiredError
        from unittest.mock import AsyncMock
        
        with patch("registry.services.oauth.oauth_service.get_oauth_service") as mock_oauth_svc, \
             patch("registry.utils.crypto_utils.decrypt_auth_fields") as mock_decrypt:
            
            mock_decrypt.return_value = mock_oauth_server.config
            
            # Mock OAuth service returns auth_url
            oauth_service = AsyncMock()
            oauth_service.get_valid_access_token = AsyncMock(
                return_value=(None, "https://oauth.example.com/authorize", None)
            )
            mock_oauth_svc.return_value = oauth_service
            
            with pytest.raises(OAuthReAuthRequiredError) as exc_info:
                await _build_complete_headers_for_server(mock_oauth_server, "user-123")
            
            assert "re-authentication required" in str(exc_info.value).lower()
            assert exc_info.value.auth_url == "https://oauth.example.com/authorize"
            assert exc_info.value.server_name == "oauth-server"

    @pytest.mark.asyncio
    async def test_oauth_server_token_error(self, mock_oauth_server):
        """Test OAuth server raises error when token retrieval fails."""
        from registry.services.server_service import _build_complete_headers_for_server
        from registry.schemas.errors import OAuthTokenError
        from unittest.mock import AsyncMock
        
        with patch("registry.services.oauth.oauth_service.get_oauth_service") as mock_oauth_svc, \
             patch("registry.utils.crypto_utils.decrypt_auth_fields") as mock_decrypt:
            
            mock_decrypt.return_value = mock_oauth_server.config
            
            # Mock OAuth service returns error
            oauth_service = AsyncMock()
            oauth_service.get_valid_access_token = AsyncMock(
                return_value=(None, None, "Token refresh failed")
            )
            mock_oauth_svc.return_value = oauth_service
            
            with pytest.raises(OAuthTokenError) as exc_info:
                await _build_complete_headers_for_server(mock_oauth_server, "user-123")
            
            assert "OAuth token error" in str(exc_info.value)
            assert exc_info.value.server_name == "oauth-server"

    @pytest.mark.asyncio
    async def test_oauth_server_no_token(self, mock_oauth_server):
        """Test OAuth server raises error when no token available."""
        from registry.services.server_service import _build_complete_headers_for_server
        from registry.schemas.errors import OAuthTokenError
        from unittest.mock import AsyncMock
        
        with patch("registry.services.oauth.oauth_service.get_oauth_service") as mock_oauth_svc, \
             patch("registry.utils.crypto_utils.decrypt_auth_fields") as mock_decrypt:
            
            mock_decrypt.return_value = mock_oauth_server.config
            
            # Mock OAuth service returns None for all
            oauth_service = AsyncMock()
            oauth_service.get_valid_access_token = AsyncMock(
                return_value=(None, None, None)
            )
            mock_oauth_svc.return_value = oauth_service
            
            with pytest.raises(OAuthTokenError) as exc_info:
                await _build_complete_headers_for_server(mock_oauth_server, "user-123")
            
            assert "No valid OAuth token" in str(exc_info.value)
            assert exc_info.value.server_name == "oauth-server"

    @pytest.mark.asyncio
    async def test_apikey_bearer_auth(self, mock_apikey_server):
        """Test API key with Bearer authorization."""
        from registry.services.server_service import _build_complete_headers_for_server
        
        with patch("registry.utils.crypto_utils.decrypt_auth_fields") as mock_decrypt:
            mock_decrypt.return_value = mock_apikey_server.config
            
            headers = await _build_complete_headers_for_server(mock_apikey_server, None)
            
            assert headers["Authorization"] == "Bearer test-api-key-123"
            assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_apikey_basic_auth(self, mock_basic_auth_server):
        """Test API key with Basic authorization."""
        from registry.services.server_service import _build_complete_headers_for_server
        
        with patch("registry.utils.crypto_utils.decrypt_auth_fields") as mock_decrypt:
            mock_decrypt.return_value = mock_basic_auth_server.config
            
            headers = await _build_complete_headers_for_server(mock_basic_auth_server, None)
            
            # Basic auth should be base64 encoded
            assert headers["Authorization"].startswith("Basic ")
            assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_apikey_custom_auth(self, mock_custom_auth_server):
        """Test API key with custom header."""
        from registry.services.server_service import _build_complete_headers_for_server
        
        with patch("registry.utils.crypto_utils.decrypt_auth_fields") as mock_decrypt:
            mock_decrypt.return_value = mock_custom_auth_server.config
            
            headers = await _build_complete_headers_for_server(mock_custom_auth_server, None)
            
            assert headers["X-API-Key"] == "custom-token-xyz"
            assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_custom_headers_only(self, mock_custom_headers_server):
        """Test server with only custom headers."""
        from registry.services.server_service import _build_complete_headers_for_server
        
        with patch("registry.utils.crypto_utils.decrypt_auth_fields") as mock_decrypt:
            mock_decrypt.return_value = mock_custom_headers_server.config
            
            headers = await _build_complete_headers_for_server(mock_custom_headers_server, None)
            
            assert headers["X-Custom-Header"] == "value1"
            assert headers["X-Another-Header"] == "value2"
            assert headers["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_oauth_with_custom_headers(self, mock_oauth_server):
        """Test OAuth server also processes custom headers."""
        from registry.services.server_service import _build_complete_headers_for_server
        from unittest.mock import AsyncMock
        
        # Add custom headers to OAuth config
        mock_oauth_server.config["headers"] = [
            {"X-Custom-Header": "custom-value"}
        ]
        
        with patch("registry.services.oauth.oauth_service.get_oauth_service") as mock_oauth_svc, \
             patch("registry.utils.crypto_utils.decrypt_auth_fields") as mock_decrypt:
            
            mock_decrypt.return_value = mock_oauth_server.config
            
            oauth_service = AsyncMock()
            oauth_service.get_valid_access_token = AsyncMock(
                return_value=("access-token", None, None)
            )
            mock_oauth_svc.return_value = oauth_service
            
            headers = await _build_complete_headers_for_server(mock_oauth_server, "user-123")
            
            # Should have both OAuth and custom headers
            assert headers["Authorization"] == "Bearer access-token"
            assert headers["X-Custom-Header"] == "custom-value"

    @pytest.mark.asyncio
    async def test_no_auth_returns_base_headers(self):
        """Test server with no authentication returns base MCP headers."""
        from registry.services.server_service import _build_complete_headers_for_server
        from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument
        
        server = Mock(spec=MCPServerDocument)
        server.serverName = "no-auth-server"
        server.config = {}
        
        with patch("registry.utils.crypto_utils.decrypt_auth_fields") as mock_decrypt:
            mock_decrypt.return_value = {}
            
            headers = await _build_complete_headers_for_server(server, None)
            
            assert headers["Content-Type"] == "application/json"
            assert headers["Accept"] == "application/json"
            assert headers["User-Agent"] == "MCP-Gateway-Registry/1.0"
            assert "Authorization" not in headers
