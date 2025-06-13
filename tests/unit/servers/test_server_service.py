"""
Unit tests for server service.
"""
import json
import os
import pytest
from pathlib import Path, PosixPath, WindowsPath
from typing import Dict, Any
from unittest.mock import patch, mock_open, Mock

from registry.services.server_service import ServerService
from registry.core.config import settings
from tests.fixtures.factories import ServerInfoFactory, create_multiple_servers


@pytest.mark.unit
@pytest.mark.servers
class TestServerService:
    """Test suite for ServerService."""

    def test_init(self, server_service: ServerService):
        """Test ServerService initialization."""
        assert server_service.registered_servers == {}
        assert server_service.service_state == {}

    def test_path_to_filename(self, server_service: ServerService):
        """Test path to filename conversion."""
        assert server_service._path_to_filename("/api/v1/test") == "api_v1_test.json"
        assert server_service._path_to_filename("api/v1/test") == "api_v1_test.json"
        assert server_service._path_to_filename("/simple") == "simple.json"
        assert server_service._path_to_filename("/test.json") == "test.json"

    def test_register_server_success(self, server_service: ServerService, sample_server: Dict[str, Any]):
        """Test successful server registration."""
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            
            result = server_service.register_server(sample_server)
            
            assert result is True
            assert sample_server["path"] in server_service.registered_servers
            assert server_service.registered_servers[sample_server["path"]] == sample_server
            assert server_service.service_state[sample_server["path"]] is False

    def test_register_server_duplicate_path(self, server_service: ServerService, sample_server: Dict[str, Any]):
        """Test registering server with duplicate path fails."""
        # First registration
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            server_service.register_server(sample_server)
        
        # Second registration with same path should fail
        result = server_service.register_server(sample_server)
        assert result is False

    def test_register_server_save_failure(self, server_service: ServerService, sample_server: Dict[str, Any]):
        """Test server registration fails when file save fails."""
        with patch.object(server_service, 'save_server_to_file', return_value=False):
            result = server_service.register_server(sample_server)
            assert result is False
            assert sample_server["path"] not in server_service.registered_servers

    def test_update_server_success(self, server_service: ServerService, sample_server: Dict[str, Any]):
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

    def test_update_server_not_found(self, server_service: ServerService, sample_server: Dict[str, Any]):
        """Test updating non-existent server fails."""
        result = server_service.update_server("/nonexistent", sample_server)
        assert result is False

    def test_update_server_save_failure(self, server_service: ServerService, sample_server: Dict[str, Any]):
        """Test server update fails when file save fails."""
        # First register the server
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            server_service.register_server(sample_server)
        
        # Try to update with save failure
        with patch.object(server_service, 'save_server_to_file', return_value=False):
            result = server_service.update_server(sample_server["path"], sample_server)
            assert result is False

    def test_toggle_service_success(self, server_service: ServerService, sample_server: Dict[str, Any]):
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

    def test_toggle_service_not_found(self, server_service: ServerService):
        """Test toggling non-existent service fails."""
        result = server_service.toggle_service("/nonexistent", True)
        assert result is False

    def test_get_server_info(self, server_service: ServerService, sample_server: Dict[str, Any]):
        """Test getting server info."""
        # Test non-existent server
        assert server_service.get_server_info("/nonexistent") is None
        
        # Register server and test retrieval
        with patch.object(server_service, 'save_server_to_file', return_value=True), \
             patch.object(server_service, 'save_service_state'):
            server_service.register_server(sample_server)
        
        result = server_service.get_server_info(sample_server["path"])
        assert result == sample_server

    def test_get_all_servers(self, server_service: ServerService, sample_servers: Dict[str, Dict[str, Any]]):
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

    def test_is_service_enabled(self, server_service: ServerService, sample_server: Dict[str, Any]):
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

    def test_get_enabled_services(self, server_service: ServerService, sample_servers: Dict[str, Dict[str, Any]]):
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
    def test_save_server_to_file(self, mock_json_dump, mock_file, server_service: ServerService, sample_server: Dict[str, Any]):
        """Test saving server to file."""
        result = server_service.save_server_to_file(sample_server)
        
        assert result is True
        mock_file.assert_called_once()
        mock_json_dump.assert_called_once_with(sample_server, mock_file.return_value, indent=2)

    @patch("builtins.open", side_effect=IOError("File error"))
    def test_save_server_to_file_failure(self, mock_file, server_service: ServerService, sample_server: Dict[str, Any]):
        """Test server file save failure."""
        result = server_service.save_server_to_file(sample_server)
        assert result is False

    @patch("builtins.open", new_callable=mock_open)
    @patch("json.dump")
    def test_save_service_state(self, mock_json_dump, mock_file, server_service: ServerService):
        """Test saving service state."""
        server_service.service_state = {"/test": True, "/test2": False}
        server_service.save_service_state()
        
        mock_file.assert_called_once()
        mock_json_dump.assert_called_once_with(server_service.service_state, mock_file.return_value, indent=2)

    @patch("builtins.open", side_effect=IOError("File error"))
    def test_save_service_state_failure(self, mock_file, server_service: ServerService):
        """Test saving service state failure."""
        server_service.service_state = {"/test": True}
        # Should not raise exception
        server_service.save_service_state()

    def test_load_service_state_no_file(self, server_service: ServerService, temp_dir):
        """Test loading service state when no state file exists."""
        # Set up some registered servers
        server_service.registered_servers = {"/test": {"server_name": "Test"}}
        
        # Call the method
        server_service._load_service_state()
        
        # Verify state was initialized properly
        assert server_service.service_state == {"/test": False}

    @patch("builtins.open", new_callable=mock_open, read_data='{"test": true, "test2": false}')
    @patch("json.load")
    def test_load_service_state_with_file(self, mock_json_load, mock_file, server_service: ServerService):
        """Test loading service state from existing file."""
        mock_json_load.return_value = {"/test": True, "/test2": False}
        
        # Set up registered servers
        server_service.registered_servers = {"/test": {"server_name": "Test"}, "/test2": {"server_name": "Test2"}}
        
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_settings.service_state_file.exists.return_value = True
            server_service._load_service_state()
        
        assert server_service.service_state == {"/test": True, "/test2": False}

    @patch("builtins.open", side_effect=IOError("File error"))
    def test_load_service_state_file_error(self, mock_file, server_service: ServerService):
        """Test loading service state with file error."""
        server_service.registered_servers = {"/test": {"server_name": "Test"}}
        
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_settings.service_state_file.exists.return_value = True
            server_service._load_service_state()
        
        # Should fall back to default state
        assert server_service.service_state == {"/test": False}

    @patch("json.load", side_effect=json.JSONDecodeError("Bad JSON", "", 0))
    @patch("builtins.open", new_callable=mock_open)
    def test_load_service_state_json_error(self, mock_file, mock_json_load, server_service: ServerService):
        """Test loading service state with JSON decode error."""
        server_service.registered_servers = {"/test": {"server_name": "Test"}}
        
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_settings.service_state_file.exists.return_value = True
            server_service._load_service_state()
        
        # Should fall back to default state
        assert server_service.service_state == {"/test": False}

    def test_load_servers_and_state_empty_directory(self, server_service: ServerService):
        """Test loading servers when directory is empty."""
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_servers_dir = Mock()
            mock_servers_dir.mkdir = Mock()
            mock_servers_dir.glob.return_value = []
            mock_settings.servers_dir = mock_servers_dir
            
            with patch.object(server_service, '_load_service_state'):
                server_service.load_servers_and_state()
            
            assert server_service.registered_servers == {}

    def test_load_servers_and_state_with_servers(self, server_service: ServerService, sample_server: Dict[str, Any]):
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

    def test_load_servers_and_state_file_error(self, server_service: ServerService):
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

    def test_load_servers_and_state_json_error(self, server_service: ServerService):
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

    def test_load_servers_and_state_missing_path(self, server_service: ServerService):
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

    def test_load_servers_and_state_directory_not_exists(self, server_service: ServerService):
        """Test loading servers when directory doesn't exist."""
        with patch('registry.services.server_service.settings') as mock_settings:
            mock_servers_dir = Mock()
            mock_servers_dir.mkdir = Mock()
            mock_servers_dir.glob.return_value = []
            mock_settings.servers_dir = mock_servers_dir
            
            with patch.object(server_service, '_load_service_state'):
                server_service.load_servers_and_state()
            
            assert server_service.registered_servers == {} 