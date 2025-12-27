import pytest
import asyncio
import logging
import sys
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from registry.oauth.reconn_manager import OAuthReconnectionManager
from registry.oauth.tracker import OAuthReconnectionTracker
from registry.oauth.mcp_manager import TokenMethods, User
from registry.oauth.flow_manager import FlowStateManager
from registry.oauth.registry import MCPServersRegistry

# Configure logging
logging.basicConfig(level=logging.WARNING)  # Reduce noise for tests
logger = logging.getLogger(__name__)


# Test fixtures
@pytest.fixture
def mock_flow_manager():
    """Mock FlowStateManager."""
    return Mock(spec=FlowStateManager)


@pytest.fixture
def mock_token_methods():
    """Mock TokenMethods."""
    return TokenMethods(
        find_token=AsyncMock(return_value=None),
        update_token=AsyncMock(return_value=True),
        create_token=AsyncMock(return_value=True),
        delete_tokens=AsyncMock(return_value=True)
    )


@pytest.fixture
def mock_mcp_servers_registry():
    """Mock MCPServersRegistry."""
    registry = Mock(spec=MCPServersRegistry)
    registry.get_oauth_servers = AsyncMock(return_value=[])
    registry.get_server_config = AsyncMock(return_value=None)
    return registry


@pytest.fixture
def mock_mcp_manager():
    """Mock MCPManager."""
    manager = Mock()
    manager.get_user_connections = Mock(return_value={})
    manager.get_user_connection = AsyncMock(return_value=None)
    manager.disconnect_user_connection = AsyncMock()
    return manager


@pytest.fixture
def sample_token():
    """Sample token for testing."""
    token = Mock()
    token.expires_at = datetime.now() + timedelta(hours=1)  # Not expired
    return token


# Test classes
class TestOAuthReconnectionManagerSingleton:
    """Test OAuthReconnectionManager singleton pattern."""

    def setup_method(self):
        """Reset singleton before each test."""
        OAuthReconnectionManager._instance = None

    @pytest.mark.asyncio
    async def test_create_instance_success(self, mock_flow_manager, mock_token_methods, mock_mcp_servers_registry):
        """Test successful creation of OAuthReconnectionManager instance."""
        # Create instance
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        assert manager is not None
        assert manager.flow_manager is mock_flow_manager
        assert manager.token_methods is mock_token_methods
        assert manager.mcp_servers_registry is mock_mcp_servers_registry

        # Verify singleton
        manager2 = OAuthReconnectionManager.get_instance()
        assert manager is manager2

    @pytest.mark.asyncio
    async def test_create_instance_already_initialized(self, mock_flow_manager, mock_token_methods,
                                                       mock_mcp_servers_registry):
        """Test that create_instance raises error when already initialized."""
        # Create first instance
        await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Try to create second instance
        with pytest.raises(RuntimeError, match="OAuthReconnectionManager already initialized"):
            await OAuthReconnectionManager.create_instance(
                flow_manager=mock_flow_manager,
                token_methods=mock_token_methods,
                mcp_servers_registry=mock_mcp_servers_registry
            )

    @pytest.mark.asyncio
    async def test_get_instance_not_initialized(self):
        """Test that get_instance raises error when not initialized."""
        # Reset singleton
        OAuthReconnectionManager._instance = None

        with pytest.raises(RuntimeError, match="OAuthReconnectionManager not initialized"):
            OAuthReconnectionManager.get_instance()


class TestOAuthReconnectionManagerReconnectionLogic:
    """Test OAuthReconnectionManager reconnection logic."""

    def setup_method(self):
        """Reset singleton before each test."""
        OAuthReconnectionManager._instance = None

    @pytest.mark.asyncio
    async def test_is_reconnecting_initial_state(self, mock_flow_manager, mock_token_methods,
                                                 mock_mcp_servers_registry):
        """Test is_reconnecting returns False for non-reconnecting server."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Should return False initially
        assert not manager.is_reconnecting("user1", "server1")

    @pytest.mark.asyncio
    async def test_is_reconnecting_with_active_reconnection(self, mock_flow_manager, mock_token_methods,
                                                            mock_mcp_servers_registry):
        """Test is_reconnecting returns True for active reconnection."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Set active reconnection
        manager.reconnections_tracker.set_active("user1", "server1")

        # Should return True
        assert manager.is_reconnecting("user1", "server1")

    @pytest.mark.asyncio
    async def test_clear_reconnection(self, mock_flow_manager, mock_token_methods, mock_mcp_servers_registry):
        """Test clear_reconnection removes reconnection state."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Set active and failed reconnections
        manager.reconnections_tracker.set_active("user1", "server1")
        manager.reconnections_tracker.set_failed("user1", "server2")

        # Clear reconnections
        manager.clear_reconnection("user1", "server1")
        manager.clear_reconnection("user1", "server2")

        # Should return False after clearing
        assert not manager.is_reconnecting("user1", "server1")
        assert not manager.reconnections_tracker.is_failed("user1", "server2")

    @pytest.mark.asyncio
    async def test_can_reconnect_with_valid_token(self, mock_flow_manager, mock_token_methods,
                                                  mock_mcp_servers_registry, sample_token):
        """Test _can_reconnect returns True with valid token."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={})
        manager.mcp_manager = mock_mcp_manager

        # Mock token methods
        mock_token_methods.find_token = AsyncMock(return_value=sample_token)

        # Should return True
        result = await manager._can_reconnect("user1", "server1")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_reconnect_without_mcp_manager(self, mock_flow_manager, mock_token_methods,
                                                     mock_mcp_servers_registry):
        """Test _can_reconnect returns False without MCPManager."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Set mcp_manager to None
        manager.mcp_manager = None

        # Should return False
        result = await manager._can_reconnect("user1", "server1")
        assert result is False

    @pytest.mark.asyncio
    async def test_can_reconnect_with_failed_reconnection(self, mock_flow_manager, mock_token_methods,
                                                          mock_mcp_servers_registry):
        """Test _can_reconnect returns False for failed reconnection."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={})
        manager.mcp_manager = mock_mcp_manager

        # Set failed reconnection
        manager.reconnections_tracker.set_failed("user1", "server1")

        # Should return False
        result = await manager._can_reconnect("user1", "server1")
        assert result is False

    @pytest.mark.asyncio
    async def test_can_reconnect_with_active_reconnection(self, mock_flow_manager, mock_token_methods,
                                                          mock_mcp_servers_registry):
        """Test _can_reconnect returns False for active reconnection."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={})
        manager.mcp_manager = mock_mcp_manager

        # Set active reconnection
        manager.reconnections_tracker.set_active("user1", "server1")

        # Should return False
        result = await manager._can_reconnect("user1", "server1")
        assert result is False

    @pytest.mark.asyncio
    async def test_can_reconnect_with_existing_connection(self, mock_flow_manager, mock_token_methods,
                                                          mock_mcp_servers_registry):
        """Test _can_reconnect returns False when connection already exists."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager with existing connection
        mock_connection = Mock()
        mock_connection.is_connected = AsyncMock(return_value=True)

        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={"server1": mock_connection})
        manager.mcp_manager = mock_mcp_manager

        # Should return False
        result = await manager._can_reconnect("user1", "server1")
        assert result is False

    @pytest.mark.asyncio
    async def test_can_reconnect_without_token(self, mock_flow_manager, mock_token_methods, mock_mcp_servers_registry):
        """Test _can_reconnect returns False when token is None."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={})
        manager.mcp_manager = mock_mcp_manager

        # Mock token methods to return None
        mock_token_methods.find_token = AsyncMock(return_value=None)

        # Should return False
        result = await manager._can_reconnect("user1", "server1")
        assert result is False

    @pytest.mark.asyncio
    async def test_can_reconnect_with_expired_token(self, mock_flow_manager, mock_token_methods,
                                                    mock_mcp_servers_registry):
        """Test _can_reconnect returns False with expired token."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={})
        manager.mcp_manager = mock_mcp_manager

        # Create expired token
        expired_token = Mock()
        expired_token.expires_at = datetime.now() - timedelta(hours=1)  # Expired

        # Mock token methods
        mock_token_methods.find_token = AsyncMock(return_value=expired_token)

        # Should return False
        result = await manager._can_reconnect("user1", "server1")
        assert result is False


class TestOAuthReconnectionManagerReconnectServers:
    """Test OAuthReconnectionManager reconnect_servers method."""

    def setup_method(self):
        """Reset singleton before each test."""
        OAuthReconnectionManager._instance = None

    @pytest.mark.asyncio
    async def test_reconnect_servers_without_mcp_manager(self, mock_flow_manager, mock_token_methods,
                                                         mock_mcp_servers_registry):
        """Test reconnect_servers does nothing without MCPManager."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Set mcp_manager to None
        manager.mcp_manager = None

        # Mock registry to return servers
        mock_mcp_servers_registry.get_oauth_servers = AsyncMock(return_value=["server1", "server2"])

        # Should not raise any errors
        await manager.reconnect_servers("user1")

    @pytest.mark.asyncio
    async def test_reconnect_servers_concurrent_reconnection(self, mock_flow_manager, mock_token_methods,
                                                             mock_mcp_servers_registry, sample_token):
        """Test concurrent reconnection of multiple servers."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={})
        manager.mcp_manager = mock_mcp_manager

        # Mock registry to return multiple servers
        mock_mcp_servers_registry.get_oauth_servers = AsyncMock(return_value=["server1", "server2", "server3"])
        mock_mcp_servers_registry.get_server_config = AsyncMock(return_value=Mock(init_timeout=5000))

        # Mock token methods
        mock_token_methods.find_token = AsyncMock(return_value=sample_token)

        # Mock _can_reconnect to return True for all servers
        with patch.object(manager, '_can_reconnect', AsyncMock(return_value=True)):
            # Mock _try_reconnect to track calls
            reconnect_calls = []

            async def mock_try_reconnect(user_id, server_name):
                reconnect_calls.append((user_id, server_name))
                await asyncio.sleep(0.01)  # Simulate async work

            with patch.object(manager, '_try_reconnect', mock_try_reconnect):
                # Start reconnection
                await manager.reconnect_servers("user1")

                # Wait a bit for tasks to start
                await asyncio.sleep(0.05)

                # Verify all servers were marked as active
                assert manager.reconnections_tracker.is_still_reconnecting("user1", "server1")
                assert manager.reconnections_tracker.is_still_reconnecting("user1", "server2")
                assert manager.reconnections_tracker.is_still_reconnecting("user1", "server3")

                # Verify _try_reconnect was called for all servers
                assert len(reconnect_calls) == 3
                server_names = [call[1] for call in reconnect_calls]
                assert "server1" in server_names
                assert "server2" in server_names
                assert "server3" in server_names

    @pytest.mark.asyncio
    async def test_reconnect_servers_with_no_oauth_servers(self, mock_flow_manager, mock_token_methods,
                                                           mock_mcp_servers_registry):
        """Test reconnect_servers with no OAuth servers."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        manager.mcp_manager = mock_mcp_manager

        # Mock registry to return empty list
        mock_mcp_servers_registry.get_oauth_servers = AsyncMock(return_value=[])

        # Should not start any reconnection tasks
        await manager.reconnect_servers("user1")

        # Verify no tasks were created
        mock_mcp_servers_registry.get_oauth_servers.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconnect_servers_with_reconnectable_servers(self, mock_flow_manager, mock_token_methods,
                                                                mock_mcp_servers_registry, sample_token):
        """Test reconnect_servers with reconnectable servers."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={})
        manager.mcp_manager = mock_mcp_manager

        # Mock registry to return servers
        mock_mcp_servers_registry.get_oauth_servers = AsyncMock(return_value=["server1", "server2"])
        mock_mcp_servers_registry.get_server_config = AsyncMock(return_value=Mock(init_timeout=5000))

        # Mock token methods
        mock_token_methods.find_token = AsyncMock(return_value=sample_token)

        # Mock _can_reconnect to return True for both servers
        with patch.object(manager, '_can_reconnect', AsyncMock(return_value=True)):
            # Mock _try_reconnect to do nothing
            with patch.object(manager, '_try_reconnect', AsyncMock()):
                await manager.reconnect_servers("user1")

                # Verify servers were marked as active
                assert manager.reconnections_tracker.is_still_reconnecting("user1", "server1")
                assert manager.reconnections_tracker.is_still_reconnecting("user1", "server2")

                # Verify _try_reconnect was called for both servers
                assert manager._try_reconnect.call_count == 2

    @pytest.mark.asyncio
    async def test_reconnect_servers_with_non_reconnectable_servers(self, mock_flow_manager, mock_token_methods,
                                                                    mock_mcp_servers_registry):
        """Test reconnect_servers with non-reconnectable servers."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={})
        manager.mcp_manager = mock_mcp_manager

        # Mock registry to return servers
        mock_mcp_servers_registry.get_oauth_servers = AsyncMock(return_value=["server1", "server2"])

        # Mock _can_reconnect to return False for both servers
        with patch.object(manager, '_can_reconnect', AsyncMock(return_value=False)):
            await manager.reconnect_servers("user1")

            # Verify servers were NOT marked as active
            assert not manager.reconnections_tracker.is_still_reconnecting("user1", "server1")
            assert not manager.reconnections_tracker.is_still_reconnecting("user1", "server2")


class TestOAuthReconnectionManagerTryReconnect:
    """Test OAuthReconnectionManager _try_reconnect method."""

    def setup_method(self):
        """Reset singleton before each test."""
        OAuthReconnectionManager._instance = None

    @pytest.mark.asyncio
    async def test_try_reconnect_success(self, mock_flow_manager, mock_token_methods, mock_mcp_servers_registry):
        """Test successful reconnection."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_connection = Mock()
        mock_connection.is_connected = AsyncMock(return_value=True)

        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connection = AsyncMock(return_value=mock_connection)
        manager.mcp_manager = mock_mcp_manager

        # Mock registry
        mock_mcp_servers_registry.get_server_config = AsyncMock(return_value=Mock(init_timeout=5000))

        # Set as active
        manager.reconnections_tracker.set_active("user1", "server1")

        # Try reconnect
        await manager._try_reconnect("user1", "server1")

        # Verify reconnection was cleared
        assert not manager.reconnections_tracker.is_still_reconnecting("user1", "server1")
        assert not manager.reconnections_tracker.is_failed("user1", "server1")

    @pytest.mark.asyncio
    async def test_try_reconnect_failure_no_connection(self, mock_flow_manager, mock_token_methods,
                                                       mock_mcp_servers_registry):
        """Test reconnection failure when connection is None."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager to return None connection
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connection = AsyncMock(return_value=None)
        mock_mcp_manager.disconnect_user_connection = AsyncMock()  # Make it async
        manager.mcp_manager = mock_mcp_manager

        # Mock registry
        mock_mcp_servers_registry.get_server_config = AsyncMock(return_value=Mock(init_timeout=5000))

        # Set as active
        manager.reconnections_tracker.set_active("user1", "server1")

        # Try reconnect
        await manager._try_reconnect("user1", "server1")

        # Verify reconnection was marked as failed
        assert manager.reconnections_tracker.is_failed("user1", "server1")
        assert not manager.reconnections_tracker.is_still_reconnecting("user1", "server1")

    @pytest.mark.asyncio
    async def test_try_reconnect_failure_not_connected(self, mock_flow_manager, mock_token_methods,
                                                       mock_mcp_servers_registry):
        """Test reconnection failure when connection is not connected."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock connection that is not connected
        mock_connection = Mock()
        mock_connection.is_connected = AsyncMock(return_value=False)
        mock_connection.close = AsyncMock()

        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connection = AsyncMock(return_value=mock_connection)
        mock_mcp_manager.disconnect_user_connection = AsyncMock()  # Make it async
        manager.mcp_manager = mock_mcp_manager

        # Mock registry
        mock_mcp_servers_registry.get_server_config = AsyncMock(return_value=Mock(init_timeout=5000))

        # Set as active
        manager.reconnections_tracker.set_active("user1", "server1")

        # Try reconnect
        await manager._try_reconnect("user1", "server1")

        # Verify reconnection was marked as failed
        assert manager.reconnections_tracker.is_failed("user1", "server1")
        assert not manager.reconnections_tracker.is_still_reconnecting("user1", "server1")
        mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_try_reconnect_failure_exception(self, mock_flow_manager, mock_token_methods,
                                                   mock_mcp_servers_registry):
        """Test reconnection failure when exception occurs."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager to raise exception
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connection = AsyncMock(side_effect=Exception("Connection error"))
        mock_mcp_manager.disconnect_user_connection = AsyncMock()  # Make it async
        manager.mcp_manager = mock_mcp_manager

        # Mock registry
        mock_mcp_servers_registry.get_server_config = AsyncMock(return_value=Mock(init_timeout=5000))

        # Set as active
        manager.reconnections_tracker.set_active("user1", "server1")

        # Try reconnect - should handle exception gracefully
        await manager._try_reconnect("user1", "server1")

        # Verify reconnection was marked as failed
        assert manager.reconnections_tracker.is_failed("user1", "server1")
        assert not manager.reconnections_tracker.is_still_reconnecting("user1", "server1")

    @pytest.mark.asyncio
    async def test_try_reconnect_without_mcp_manager(self, mock_flow_manager, mock_token_methods,
                                                     mock_mcp_servers_registry):
        """Test _try_reconnect does nothing without MCPManager."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Set mcp_manager to None
        manager.mcp_manager = None

        # Should not raise any errors
        await manager._try_reconnect("user1", "server1")

    @pytest.mark.asyncio
    async def test_can_reconnect_token_string_expires_at(self, mock_flow_manager, mock_token_methods,
                                                         mock_mcp_servers_registry):
        """Test _can_reconnect with token expires_at as string."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={})
        manager.mcp_manager = mock_mcp_manager

        # Create token with string expires_at
        from datetime import datetime, timedelta
        expires_at_str = (datetime.now() + timedelta(hours=1)).isoformat()
        token = Mock()
        token.expires_at = expires_at_str

        mock_token_methods.find_token = AsyncMock(return_value=token)

        # Should return True (not expired)
        result = await manager._can_reconnect("user1", "server1")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_reconnect_token_invalid_expires_at(self, mock_flow_manager, mock_token_methods,
                                                          mock_mcp_servers_registry):
        """Test _can_reconnect with invalid expires_at format."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={})
        manager.mcp_manager = mock_mcp_manager

        # Create token with invalid expires_at
        token = Mock()
        token.expires_at = "invalid-date-format"

        mock_token_methods.find_token = AsyncMock(return_value=token)

        # Should return True (assumes not expired if can't parse)
        result = await manager._can_reconnect("user1", "server1")
        assert result is True

    @pytest.mark.asyncio
    async def test_can_reconnect_token_none_expires_at(self, mock_flow_manager, mock_token_methods,
                                                       mock_mcp_servers_registry):
        """Test _can_reconnect with token expires_at as None."""
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )

        # Mock MCPManager
        mock_mcp_manager = Mock()
        mock_mcp_manager.get_user_connections = Mock(return_value={})
        manager.mcp_manager = mock_mcp_manager

        # Create token with None expires_at
        token = Mock()
        token.expires_at = None

        mock_token_methods.find_token = AsyncMock(return_value=token)

        # Should return True (no expiration check)
        result = await manager._can_reconnect("user1", "server1")
        assert result is True


# Main test function for backward compatibility
@pytest.mark.asyncio
async def test_oauth_reconnection_manager():
    """Test OAuthReconnectionManager basic functionality (legacy test)."""
    print("Testing OAuthReconnectionManager...")

    # Create mock dependencies
    mock_flow_manager = Mock(spec=FlowStateManager)
    mock_token_methods = TokenMethods(
        find_token=AsyncMock(return_value=None),
        update_token=AsyncMock(return_value=True),
        create_token=AsyncMock(return_value=True),
        delete_tokens=AsyncMock(return_value=True)
    )
    mock_mcp_servers_registry = Mock(spec=MCPServersRegistry)
    mock_mcp_servers_registry.get_oauth_servers = AsyncMock(return_value=[])

    try:
        # Create OAuthReconnectionManager instance
        print("Creating OAuthReconnectionManager instance...")
        manager = await OAuthReconnectionManager.create_instance(
            flow_manager=mock_flow_manager,
            token_methods=mock_token_methods,
            mcp_servers_registry=mock_mcp_servers_registry
        )
        print("✓ OAuthReconnectionManager created successfully")

        print("Testing singleton pattern...")
        manager2 = OAuthReconnectionManager.get_instance()
        assert manager is manager2
        print("\nTesting is_reconnecting...")

        # Test is_reconnecting
        print("Testing is_reconnecting...")
        assert not manager.is_reconnecting("user1", "server1")
        print("✓ is_reconnecting returns False for non-reconnecting server")

        print("✅ All basic tests passed!")

    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
