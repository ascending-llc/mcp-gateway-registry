import pytest
import time
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from registry.oauth.flow_manager import FlowStateManager
from registry.oauth.models import OAuthFlowStatus


@pytest.mark.unit
@pytest.mark.oauth
class TestFlowStateManager:
    """Test suite for FlowStateManager."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        manager = FlowStateManager()
        
        assert manager.namespace == 'oauth-flows'
        assert manager.ttl == 600
        assert manager._cache.maxsize == 1000
        assert manager._cache.ttl == 600

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        manager = FlowStateManager(namespace='test-namespace', ttl=300)
        
        assert manager.namespace == 'test-namespace'
        assert manager.ttl == 300
        assert manager._cache.ttl == 300

    def test_generate_flow_id(self):
        """Test flow ID generation."""
        manager = FlowStateManager()
        user_id = "test-user"
        server_name = "test-server"
        
        flow_id = manager.generate_flow_id(user_id, server_name)
        
        # Check format: user_id:server_name:timestamp:uuid_8_chars
        parts = flow_id.split(':')
        assert len(parts) == 4
        assert parts[0] == user_id
        assert parts[1] == server_name
        assert parts[2].isdigit()  # timestamp
        assert len(parts[3]) == 8  # first 8 chars of UUID

    @pytest.mark.asyncio
    async def test_create_flow_state_success(self):
        """Test successful creation of flow state."""
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        metadata = {"user_id": "test-user", "server_name": "test-server"}
        
        with patch('time.time', return_value=1234567890.0):
            await manager.create_flow_state(flow_id, flow_type, metadata)
        
        # Verify the flow state was created
        cache_key = f"{manager.namespace}:{flow_type}:{flow_id}"
        flow_data = manager._cache.get(cache_key)
        
        assert flow_data is not None
        assert flow_data["flow_id"] == flow_id
        assert flow_data["flow_type"] == flow_type
        assert flow_data["metadata"] == metadata
        assert flow_data["status"] == OAuthFlowStatus.PENDING
        assert flow_data["created_at"] == 1234567890.0
        assert flow_data["expires_at"] == 1234567890.0 + manager.ttl

    @pytest.mark.asyncio
    async def test_create_flow_state_with_custom_ttl(self):
        """Test creation of flow state with custom TTL."""
        manager = FlowStateManager(ttl=600)
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        metadata = {"user_id": "test-user"}
        custom_ttl = 300
        
        with patch('time.time', return_value=1234567890.0):
            await manager.create_flow_state(flow_id, flow_type, metadata, ttl=custom_ttl)
        
        cache_key = f"{manager.namespace}:{flow_type}:{flow_id}"
        flow_data = manager._cache.get(cache_key)
        
        assert flow_data["expires_at"] == 1234567890.0 + custom_ttl

    @pytest.mark.asyncio
    async def test_create_flow_state_exception(self):
        """Test exception handling during flow state creation."""
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        metadata = {"user_id": "test-user"}
        
        # Replace the entire cache with a mock that raises an exception
        mock_cache = MagicMock()
        mock_cache.__setitem__ = MagicMock(side_effect=Exception("Cache error"))
        manager._cache = mock_cache
        
        # The method should catch and re-raise the exception
        with pytest.raises(Exception, match="Cache error"):
            await manager.create_flow_state(flow_id, flow_type, metadata)

    @pytest.mark.asyncio
    async def test_get_flow_state_found(self):
        """Test retrieving an existing flow state."""
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        metadata = {"user_id": "test-user"}
        
        # First create a flow state
        await manager.create_flow_state(flow_id, flow_type, metadata)
        
        # Then retrieve it
        result = await manager.get_flow_state(flow_id, flow_type)
        
        assert result is not None
        assert result["flow_id"] == flow_id
        assert result["flow_type"] == flow_type
        assert result["metadata"] == metadata
        assert result["status"] == OAuthFlowStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_flow_state_not_found(self):
        """Test retrieving a non-existent flow state."""
        manager = FlowStateManager()
        flow_id = "non-existent-flow"
        flow_type = "authorization_code"
        
        result = await manager.get_flow_state(flow_id, flow_type)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_flow_state_expired(self):
        """Test retrieving an expired flow state."""
        manager = FlowStateManager(ttl=1)  # Very short TTL
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        metadata = {"user_id": "test-user"}
        
        # Create flow state
        await manager.create_flow_state(flow_id, flow_type, metadata)
        
        # Wait for it to expire
        time.sleep(1.1)
        
        # Try to retrieve (should return None due to TTL cache)
        result = await manager.get_flow_state(flow_id, flow_type)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_flow_state_exception(self):
        """Test exception handling during flow state retrieval."""
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        
        # Mock cache to raise an exception
        with patch.object(manager._cache, 'get', side_effect=Exception("Cache error")):
            result = await manager.get_flow_state(flow_id, flow_type)
            
            # Should return None on exception
            assert result is None

    @pytest.mark.asyncio
    async def test_complete_flow_success(self):
        """Test successfully completing a flow."""
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        metadata = {"user_id": "test-user"}
        result_data = {"access_token": "test-token"}
        
        # Create flow state first
        await manager.create_flow_state(flow_id, flow_type, metadata)
        
        # Complete the flow
        with patch('time.time', return_value=1234567890.0):
            await manager.complete_flow(flow_id, flow_type, result_data)
        
        # Verify the flow was updated
        flow_data = await manager.get_flow_state(flow_id, flow_type)
        
        assert flow_data is not None
        assert flow_data["status"] == OAuthFlowStatus.COMPLETED
        assert flow_data["result"] == result_data
        assert flow_data["completed_at"] == 1234567890.0

    @pytest.mark.asyncio
    async def test_complete_flow_not_found(self):
        """Test completing a non-existent flow."""
        manager = FlowStateManager()
        flow_id = "non-existent-flow"
        flow_type = "authorization_code"
        result_data = {"access_token": "test-token"}
        
        # Should not raise an exception, just log warning
        await manager.complete_flow(flow_id, flow_type, result_data)

    @pytest.mark.asyncio
    async def test_complete_flow_exception(self):
        """Test exception handling during flow completion."""
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        metadata = {"user_id": "test-user"}
        
        # Create flow state first
        await manager.create_flow_state(flow_id, flow_type, metadata)
        
        # Mock cache to raise an exception
        with patch.object(manager._cache, 'get', side_effect=Exception("Cache error")):
            # The method catches, logs, and re-raises the original exception
            with pytest.raises(Exception, match="Cache error"):
                await manager.complete_flow(flow_id, flow_type, {})

    @pytest.mark.asyncio
    async def test_fail_flow_success(self):
        """Test successfully failing a flow."""
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        metadata = {"user_id": "test-user"}
        error_message = "Authentication failed"
        
        # Create flow state first
        await manager.create_flow_state(flow_id, flow_type, metadata)
        
        # Fail the flow
        with patch('time.time', return_value=1234567890.0):
            await manager.fail_flow(flow_id, flow_type, error_message)
        
        # Verify the flow was updated
        flow_data = await manager.get_flow_state(flow_id, flow_type)
        
        assert flow_data is not None
        assert flow_data["status"] == OAuthFlowStatus.FAILED
        assert flow_data["error"] == error_message
        assert flow_data["failed_at"] == 1234567890.0

    @pytest.mark.asyncio
    async def test_fail_flow_not_found(self):
        """Test failing a non-existent flow."""
        manager = FlowStateManager()
        flow_id = "non-existent-flow"
        flow_type = "authorization_code"
        error_message = "Authentication failed"
        
        # Should not raise an exception, just log warning
        await manager.fail_flow(flow_id, flow_type, error_message)

    @pytest.mark.asyncio
    async def test_fail_flow_exception(self):
        """Test exception handling during flow failure."""
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        metadata = {"user_id": "test-user"}
        
        # Create flow state first
        await manager.create_flow_state(flow_id, flow_type, metadata)
        
        # Mock cache to raise an exception
        with patch.object(manager._cache, 'get', side_effect=Exception("Cache error")):
            # The method catches, logs, and re-raises the original exception
            with pytest.raises(Exception, match="Cache error"):
                await manager.fail_flow(flow_id, flow_type, "error")

    @pytest.mark.asyncio
    async def test_delete_flow_success(self):
        """Test successfully deleting a flow."""
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        metadata = {"user_id": "test-user"}
        
        # Create flow state first
        await manager.create_flow_state(flow_id, flow_type, metadata)
        
        # Verify it exists
        assert await manager.get_flow_state(flow_id, flow_type) is not None
        
        # Delete the flow
        result = await manager.delete_flow(flow_id, flow_type)
        
        assert result is True
        assert await manager.get_flow_state(flow_id, flow_type) is None

    @pytest.mark.asyncio
    async def test_delete_flow_not_found(self):
        """Test deleting a non-existent flow."""
        manager = FlowStateManager()
        flow_id = "non-existent-flow"
        flow_type = "authorization_code"
        
        result = await manager.delete_flow(flow_id, flow_type)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_flow_exception(self):
        """Test exception handling during flow deletion."""
        manager = FlowStateManager()
        flow_id = "test-flow-id"
        flow_type = "authorization_code"
        metadata = {"user_id": "test-user"}
        
        # Create flow state first
        await manager.create_flow_state(flow_id, flow_type, metadata)
        
        # Replace the cache with a mock that raises an exception
        mock_cache = MagicMock()
        mock_cache.__contains__ = MagicMock(side_effect=Exception("Cache error"))
        manager._cache = mock_cache
        
        result = await manager.delete_flow(flow_id, flow_type)
        
        # Should return False on exception
        assert result is False

    def test_get_stats(self):
        """Test getting statistics."""
        manager = FlowStateManager(namespace='test-namespace', ttl=300)
        
        stats = manager.get_stats()
        
        assert stats['active_flows'] == 0
        assert stats['max_size'] == 1000
        assert stats['ttl'] == 300
        assert stats['namespace'] == 'test-namespace'

    def test_get_stats_with_active_flows(self):
        """Test getting statistics with active flows."""
        manager = FlowStateManager()
        
        # Create some flow states
        import asyncio
        asyncio.run(manager.create_flow_state("flow1", "type1", {}))
        asyncio.run(manager.create_flow_state("flow2", "type2", {}))
        
        stats = manager.get_stats()
        
        assert stats['active_flows'] == 2

    def test_singleton_get_flow_manager(self):
        """Test the singleton get_flow_manager function."""
        from registry.oauth.flow_manager import get_flow_manager
        
        # First call should create instance
        manager1 = get_flow_manager()
        assert manager1 is not None
        
        # Second call should return same instance
        manager2 = get_flow_manager()
        assert manager2 is manager1
        
        # Verify it's a FlowStateManager instance
        assert isinstance(manager1, FlowStateManager)


@pytest.mark.unit
@pytest.mark.oauth
class TestFlowStateManagerIntegration:
    """Integration tests for FlowStateManager."""
    
    @pytest.mark.asyncio
    async def test_full_flow_lifecycle(self):
        """Test a complete OAuth flow lifecycle."""
        manager = FlowStateManager()
        user_id = "test-user"
        server_name = "test-server"
        flow_type = "authorization_code"
        
        # Generate flow ID
        flow_id = manager.generate_flow_id(user_id, server_name)
        
        # Create flow state
        metadata = {
            "user_id": user_id,
            "server_name": server_name,
            "redirect_uri": "https://example.com/callback"
        }
        await manager.create_flow_state(flow_id, flow_type, metadata)
        
        # Verify flow state exists and is pending
        flow_state = await manager.get_flow_state(flow_id, flow_type)
        assert flow_state is not None
        assert flow_state["status"] == OAuthFlowStatus.PENDING
        
        # Complete the flow
        result = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "expires_in": 3600
        }
        await manager.complete_flow(flow_id, flow_type, result)
        
        # Verify flow is completed
        completed_state = await manager.get_flow_state(flow_id, flow_type)
        assert completed_state["status"] == OAuthFlowStatus.COMPLETED
        assert completed_state["result"] == result
        
        # Delete the flow
        delete_result = await manager.delete_flow(flow_id, flow_type)
        assert delete_result is True
        
        # Verify flow is deleted
        assert await manager.get_flow_state(flow_id, flow_type) is None

    @pytest.mark.asyncio
    async def test_concurrent_flows(self):
        """Test handling multiple concurrent flows."""
        manager = FlowStateManager()
        flow_type = "authorization_code"
        
        # Create multiple flows
        flows = []
        for i in range(5):
            flow_id = f"flow-{i}"
            metadata = {"user_id": f"user-{i}", "server_name": f"server-{i}"}
            await manager.create_flow_state(flow_id, flow_type, metadata)
            flows.append(flow_id)
        
        # Verify all flows exist
        for flow_id in flows:
            flow_state = await manager.get_flow_state(flow_id, flow_type)
            assert flow_state is not None
            assert flow_state["flow_id"] == flow_id
        
        # Verify stats
        stats = manager.get_stats()
        assert stats['active_flows'] == 5
        
        # Delete all flows
        for flow_id in flows:
            await manager.delete_flow(flow_id, flow_type)
        
        # Verify all flows are deleted
        for flow_id in flows:
            assert await manager.get_flow_state(flow_id, flow_type) is None
        
        # Verify stats
        stats = manager.get_stats()
        assert stats['active_flows'] == 0
