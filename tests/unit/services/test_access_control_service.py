"""
Unit tests for access control service.
"""
import pytest
from unittest.mock import Mock, patch, mock_open
import yaml

from registry.services.access_control_service import AccessControlService


@pytest.mark.unit
@pytest.mark.auth
class TestAccessControlService:
    """Test suite for access control service."""

    @pytest.fixture
    def mock_scopes_config(self):
        """Mock scopes configuration for testing."""
        return {
            'mcp-servers-unrestricted/read': [
                {'server': 'auth_server', 'methods': ['initialize', 'tools/list'], 'tools': ['validate_request']},
                {'server': 'currenttime', 'methods': ['initialize', 'tools/list'], 'tools': ['current_time_by_timezone']},
                {'server': 'mcpgw', 'methods': ['initialize', 'tools/list'], 'tools': ['intelligent_tool_finder']},
                {'server': 'fininfo', 'methods': ['initialize', 'tools/list'], 'tools': ['get_stock_aggregates']},
            ],
            'mcp-servers-unrestricted/execute': [
                {'server': 'auth_server', 'methods': ['tools/call'], 'tools': ['validate_request']},
                {'server': 'currenttime', 'methods': ['tools/call'], 'tools': ['current_time_by_timezone']},
                {'server': 'mcpgw', 'methods': ['tools/call'], 'tools': ['intelligent_tool_finder']},
                {'server': 'fininfo', 'methods': ['tools/call'], 'tools': ['get_stock_aggregates']},
            ],
            'mcp-servers-restricted/read': [
                {'server': 'auth_server', 'methods': ['initialize', 'tools/list'], 'tools': ['validate_request']},
                {'server': 'currenttime', 'methods': ['initialize', 'tools/list'], 'tools': ['current_time_by_timezone']},
                {'server': 'fininfo', 'methods': ['initialize', 'tools/list'], 'tools': ['get_stock_aggregates']},
            ],
            'mcp-servers-restricted/execute': [
                {'server': 'currenttime', 'methods': ['tools/call'], 'tools': ['current_time_by_timezone']},
                {'server': 'fininfo', 'methods': ['tools/call'], 'tools': ['get_stock_aggregates']},
            ]
        }

    @pytest.fixture
    def access_control_service_with_config(self, mock_scopes_config):
        """Create access control service with mock configuration."""
        with patch('builtins.open', mock_open(read_data=yaml.dump(mock_scopes_config))):
            with patch('pathlib.Path.exists', return_value=True):
                service = AccessControlService()
                return service

    def test_get_user_scopes_admin(self):
        """Test scope mapping for admin users."""
        service = AccessControlService()
        groups = ['mcp-admin']
        scopes = service.get_user_scopes(groups)
        
        expected_scopes = ['mcp-servers-unrestricted/read', 'mcp-servers-unrestricted/execute']
        assert scopes == expected_scopes

    def test_get_user_scopes_regular_user(self):
        """Test scope mapping for regular users."""
        service = AccessControlService()
        groups = ['mcp-user']
        scopes = service.get_user_scopes(groups)
        
        expected_scopes = ['mcp-servers-restricted/read']
        assert scopes == expected_scopes

    def test_get_user_scopes_server_specific(self):
        """Test scope mapping for server-specific groups."""
        service = AccessControlService()
        groups = ['mcp-server-currenttime']
        scopes = service.get_user_scopes(groups)
        
        expected_scopes = ['mcp-servers-restricted/execute']
        assert scopes == expected_scopes

    def test_get_user_scopes_multiple_groups(self):
        """Test scope mapping for users with multiple groups."""
        service = AccessControlService()
        groups = ['mcp-user', 'mcp-server-currenttime']
        scopes = service.get_user_scopes(groups)
        
        expected_scopes = ['mcp-servers-restricted/read', 'mcp-servers-restricted/execute']
        assert scopes == expected_scopes

    def test_get_accessible_servers_admin(self, access_control_service_with_config):
        """Test accessible servers for admin users."""
        groups = ['mcp-admin']
        accessible = access_control_service_with_config.get_accessible_servers(groups)
        
        expected_servers = {'auth_server', 'currenttime', 'mcpgw', 'fininfo'}
        assert accessible == expected_servers

    def test_get_accessible_servers_regular_user(self, access_control_service_with_config):
        """Test accessible servers for regular users."""
        groups = ['mcp-user']
        accessible = access_control_service_with_config.get_accessible_servers(groups)
        
        expected_servers = {'auth_server', 'currenttime', 'fininfo'}
        assert accessible == expected_servers

    def test_get_accessible_servers_no_groups(self, access_control_service_with_config):
        """Test accessible servers for users with no groups."""
        groups = []
        accessible = access_control_service_with_config.get_accessible_servers(groups)
        
        assert accessible == set()

    def test_can_user_access_server_admin(self, access_control_service_with_config):
        """Test server access for admin users."""
        groups = ['mcp-admin']
        
        # Admin should have access to all servers
        assert access_control_service_with_config.can_user_access_server('auth_server', groups)
        assert access_control_service_with_config.can_user_access_server('currenttime', groups)
        assert access_control_service_with_config.can_user_access_server('mcpgw', groups)
        assert access_control_service_with_config.can_user_access_server('fininfo', groups)

    def test_can_user_access_server_regular_user(self, access_control_service_with_config):
        """Test server access for regular users."""
        groups = ['mcp-user']
        
        # Regular user should have access to restricted servers
        assert access_control_service_with_config.can_user_access_server('auth_server', groups)
        assert access_control_service_with_config.can_user_access_server('currenttime', groups)
        assert access_control_service_with_config.can_user_access_server('fininfo', groups)
        
        # But not to unrestricted servers like mcpgw
        assert not access_control_service_with_config.can_user_access_server('mcpgw', groups)

    def test_can_user_access_server_no_config(self):
        """Test server access when no configuration is loaded."""
        with patch('pathlib.Path.exists', return_value=False):
            service = AccessControlService()
            
            # Should allow access when no config is available (fail open)
            assert service.can_user_access_server('any_server', ['any_group'])

    def test_can_user_access_server_unknown_server(self, access_control_service_with_config):
        """Test access to unknown server."""
        groups = ['mcp-user']
        
        # Unknown server should be denied access
        assert not access_control_service_with_config.can_user_access_server('unknown_server', groups)

    def test_reload_config(self, mock_scopes_config):
        """Test configuration reload functionality."""
        with patch('builtins.open', mock_open(read_data=yaml.dump(mock_scopes_config))):
            with patch('pathlib.Path.exists', return_value=True):
                service = AccessControlService()
                
                # Verify initial config
                assert service._scopes_config is not None
                
                # Reload config
                service.reload_config()
                
                # Verify config is still loaded
                assert service._scopes_config is not None 