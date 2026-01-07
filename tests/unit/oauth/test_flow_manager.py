import pytest
import time
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from registry.auth.oauth.flow_state_manager import FlowStateManager
from registry.schemas.enums import OAuthFlowStatus
from registry.models.oauth_models import OAuthFlow


@pytest.mark.unit
@pytest.mark.oauth
class TestFlowStateManager:
    """Test suite for FlowStateManager."""

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_init_default_values(self, mock_init_redis):
        """Test initialization with default values."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        manager = FlowStateManager()
        
        # Verify default configuration
        assert manager.DEFAULT_FLOW_TTL == 600

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_generate_flow_id(self, mock_init_redis):
        """Test flow ID generation."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        manager = FlowStateManager()
        user_id = "test-user"
        server_name = "test-server"
        
        flow_id = manager.generate_flow_id(user_id, server_name)
        
        # Check format: user_id-server_name-timestamp-random_hex
        # Note: user_id and server_name may contain '-' characters
        # So we need to extract the last two parts (timestamp and random_hex) first
        parts = flow_id.split('-')
        assert len(parts) >= 4
        
        # The last part should be random hex (8 characters)
        random_hex = parts[-1]
        assert len(random_hex) == 8
        
        # The second last part should be timestamp (digits only)
        timestamp = parts[-2]
        assert timestamp.isdigit()
        
        # The remaining parts should form user_id-server_name
        user_server_part = '-'.join(parts[:-2])
        assert user_id in user_server_part
        assert server_name in user_server_part

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_create_flow(self, mock_init_redis):
        """Test flow creation."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        server_name = "test-server"
        user_id = "test-user"
        code_verifier = "test-verifier"
        
        # Create mock metadata
        metadata = MagicMock()
        metadata.state = "encoded-state"
        
        flow = manager.create_flow(flow_id, server_name, user_id, code_verifier, metadata)
        
        assert isinstance(flow, OAuthFlow)
        assert flow.flow_id == flow_id
        assert flow.server_name == server_name
        assert flow.user_id == user_id
        assert flow.code_verifier == code_verifier
        assert flow.status == "pending"
        assert flow.state == "encoded-state"

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_get_flow_found(self, mock_init_redis):
        """Test retrieving an existing flow state."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        server_name = "test-server"
        user_id = "test-user"
        code_verifier = "test-verifier"
        
        metadata = MagicMock()
        metadata.state = "encoded-state"
        
        # Create flow state
        manager.create_flow(flow_id, server_name, user_id, code_verifier, metadata)
        
        # Then retrieve it
        flow = manager.get_flow(flow_id)
        
        assert flow is not None
        assert flow.flow_id == flow_id
        assert flow.server_name == server_name
        assert flow.user_id == user_id

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_get_flow_not_found(self, mock_init_redis):
        """Test retrieving a non-existent flow state."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        manager = FlowStateManager()
        flow_id = "non-existent-flow"
        
        flow = manager.get_flow(flow_id)
        
        assert flow is None

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_complete_flow(self, mock_init_redis):
        """Test completing a flow."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        server_name = "test-server"
        user_id = "test-user"
        code_verifier = "test-verifier"
        
        metadata = MagicMock()
        metadata.state = "encoded-state"
        
        manager.create_flow(flow_id, server_name, user_id, code_verifier, metadata)
        
        # Complete the flow
        tokens = MagicMock()
        manager.complete_flow(flow_id, tokens)
        
        # Verify the flow was updated
        flow = manager.get_flow(flow_id)
        
        assert flow is not None
        assert flow.status == OAuthFlowStatus.COMPLETED
        assert flow.tokens == tokens

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_fail_flow(self, mock_init_redis):
        """Test failing a flow."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        server_name = "test-server"
        user_id = "test-user"
        code_verifier = "test-verifier"
        
        metadata = MagicMock()
        metadata.state = "encoded-state"
        
        manager.create_flow(flow_id, server_name, user_id, code_verifier, metadata)
        
        # Fail the flow
        error_message = "Authentication failed"
        manager.fail_flow(flow_id, error_message)
        
        # Verify the flow was updated
        flow = manager.get_flow(flow_id)
        
        assert flow is not None
        assert flow.status == OAuthFlowStatus.FAILED
        assert flow.error == error_message

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_delete_flow(self, mock_init_redis):
        """Test deleting a flow."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        server_name = "test-server"
        user_id = "test-user"
        code_verifier = "test-verifier"
        
        metadata = MagicMock()
        metadata.state = "encoded-state"
        
        # Create flow state first
        manager.create_flow(flow_id, server_name, user_id, code_verifier, metadata)
        
        # Verify it exists
        assert manager.get_flow(flow_id) is not None
        
        # Delete the flow
        manager.delete_flow(flow_id)
        
        assert manager.get_flow(flow_id) is None

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_cancel_user_flow(self, mock_init_redis):
        """Test canceling user flow."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        manager = FlowStateManager()
        user_id = "test-user"
        server_name = "test-server"
        
        # Create multiple pending flows
        for i in range(3):
            flow_id = f"test-flow-id-{i}"
            metadata = MagicMock()
            metadata.state = f"encoded-state-{i}"
            manager.create_flow(flow_id, server_name, user_id, f"verifier-{i}", metadata)
        
        # Cancel user flow
        result = manager.cancel_user_flow(user_id, server_name)
        
        assert result is True
        
        # Verify that at least one flow was canceled
        flows = manager.get_user_flows(user_id, server_name)
        canceled_flows = [f for f in flows if f.status == OAuthFlowStatus.FAILED and f.error and "cancelled" in f.error]
        assert len(canceled_flows) >= 1

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_get_user_flows(self, mock_init_redis):
        """Test getting user flows."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        manager = FlowStateManager()
        user_id = "test-user"
        server_name = "test-server"
        
        # Create some flow states
        for i in range(2):
            flow_id = f"test-flow-id-{i}"
            metadata = MagicMock()
            metadata.state = f"encoded-state-{i}"
            manager.create_flow(flow_id, server_name, user_id, f"verifier-{i}", metadata)
        
        # Get user flows
        flows = manager.get_user_flows(user_id, server_name)
        
        assert len(flows) == 2
        for flow in flows:
            assert flow.user_id == user_id
            assert flow.server_name == server_name

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_encode_decode_state(self, mock_init_redis):
        """Test state encoding/decoding with CSRF protection."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        security_token = "test-security-token"
        
        encoded = manager.encode_state(flow_id, security_token)
        decoded_flow_id, decoded_token = manager.decode_state(encoded)
        
        assert decoded_flow_id == flow_id
        assert decoded_token == security_token

    @patch('registry.auth.oauth.flow_state_manager.init_redis_connection')
    def test_singleton_get_flow_state_manager(self, mock_init_redis):
        """Test the singleton get_flow_state_manager function."""
        # Mock Redis connection to fail, forcing memory storage
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis unavailable")
        mock_init_redis.return_value = mock_redis
        
        from registry.auth.oauth.flow_state_manager import get_flow_state_manager
        
        # First call should create instance
        manager1 = get_flow_state_manager()
        assert manager1 is not None
        
        # Second call should return same instance
        manager2 = get_flow_state_manager()
        assert manager2 is manager1
        
        # Verify it's a FlowStateManager instance
        assert isinstance(manager1, FlowStateManager)
