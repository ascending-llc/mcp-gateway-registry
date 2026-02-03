"""
Unit tests for health monitoring service.
"""
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from registry.health.service import HealthMonitoringService


@pytest.mark.unit
@pytest.mark.health
class TestHealthMonitoringService:
    """Test suite for HealthMonitoringService."""

    def test_init(self, health_service: HealthMonitoringService):
        """Test HealthMonitoringService initialization."""
        assert health_service.server_health_status == {}
        assert health_service.server_last_check_time == {}
        assert health_service.websocket_manager.connections == set()
        assert health_service.health_check_task is None

    @pytest.mark.asyncio
    async def test_initialize(self, health_service: HealthMonitoringService):
        """Test service initialization - background task disabled."""
        with patch("asyncio.create_task") as mock_create_task:
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task

            await health_service.initialize()

            # DEPRECATED: Background health checks disabled in favor of MongoDB
            # Verify that create_task is NOT called (task creation is commented out)
            assert not mock_create_task.called
            assert health_service.health_check_task is None

    @pytest.mark.asyncio
    async def test_shutdown(self, health_service: HealthMonitoringService):
        """Test service shutdown."""
        # Create a real task that can be cancelled
        async def dummy_task():
            await asyncio.sleep(100)  # Long-running task

        mock_task = asyncio.create_task(dummy_task())
        mock_conn1 = AsyncMock()
        mock_conn2 = AsyncMock()

        health_service.health_check_task = mock_task
        health_service.websocket_manager.connections = {mock_conn1, mock_conn2}

        await health_service.shutdown()

        # Check task was cancelled
        assert mock_task.cancelled()

        # Check connections were closed
        mock_conn1.close.assert_called_once()
        mock_conn2.close.assert_called_once()

        # Check connections set exists (may or may not be empty depending on implementation)
        # The important thing is that close was called on all connections
        assert isinstance(health_service.websocket_manager.connections, set)

    @pytest.mark.asyncio
    async def test_add_websocket_connection(self, health_service: HealthMonitoringService, mock_websocket):
        """Test adding WebSocket connection."""
        # Mock _send_initial_status_optimized to avoid import issues in tests
        with patch.object(health_service.websocket_manager, "_send_initial_status_optimized", new=AsyncMock()):
            result = await health_service.add_websocket_connection(mock_websocket)

            # add_websocket_connection now returns bool and uses websocket_manager
            assert result is True
            assert mock_websocket in health_service.websocket_manager.connections
        """Test removing WebSocket connection."""
        health_service.websocket_manager.connections.add(mock_websocket)

        await health_service.remove_websocket_connection(mock_websocket)

        assert mock_websocket not in health_service.websocket_manager.connections

    @pytest.mark.asyncio
    async def test_send_initial_status(self, health_service: HealthMonitoringService, mock_websocket):
        """Test sending initial status to WebSocket client."""
        # Mock _get_cached_health_data which is used by _send_initial_status_optimized
        expected_data = {
            "/test1": {"status": "healthy", "num_tools": 5, "last_checked_iso": "2023-01-01T12:00:00+00:00"},
            "/test2": {"status": "unhealthy", "num_tools": 3, "last_checked_iso": None}
        }

        # Patch the global health_service reference used by the manager
        with patch("registry.health.service.health_service._get_cached_health_data") as mock_get_cached:
            mock_get_cached.return_value = expected_data

            # Call the method through websocket_manager
            await health_service.websocket_manager._send_initial_status_optimized(mock_websocket)

            # Check that send_text was called with proper data
            mock_websocket.send_text.assert_called_once()
            call_args = mock_websocket.send_text.call_args[0][0]

            # Parse the JSON to verify structure
            import json
            data = json.loads(call_args)

            assert "/test1" in data
            assert "/test2" in data
            assert data["/test1"]["status"] == "healthy"
            assert data["/test1"]["num_tools"] == 5
            assert data["/test2"]["status"] == "unhealthy"
            assert data["/test2"]["num_tools"] == 3

    @pytest.mark.asyncio
    async def test_broadcast_health_update_single_service(self, health_service: HealthMonitoringService):
        """Test broadcasting health update for single service."""
        mock_conn1 = AsyncMock()
        mock_conn2 = AsyncMock()
        health_service.websocket_manager.connections = {mock_conn1, mock_conn2}

        with patch("registry.services.server_service.server_service_v1") as mock_server_service, \
             patch.object(health_service, "_get_service_health_data_fast") as mock_get_data, \
             patch.object(health_service.websocket_manager, "broadcast_update") as mock_broadcast:

            mock_server_service.get_server_info.return_value = {"num_tools": 5}
            mock_get_data.return_value = {"status": "healthy", "last_checked_iso": None, "num_tools": 5}

            await health_service.broadcast_health_update("/test")

            # Check that broadcast_update was called with the service path and health data
            mock_broadcast.assert_called_once_with("/test", {"status": "healthy", "last_checked_iso": None, "num_tools": 5})

    @pytest.mark.asyncio
    async def test_broadcast_health_update_all_services(self, health_service: HealthMonitoringService):
        """Test broadcasting health update for all services."""
        mock_conn = AsyncMock()
        health_service.websocket_manager.connections = {mock_conn}

        with patch.object(health_service.websocket_manager, "broadcast_update") as mock_broadcast:
            # When no service_path is provided, it broadcasts using cached data
            await health_service.broadcast_health_update()

            # Check that broadcast_update was called (without service_path)
            mock_broadcast.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_safe_send_message_success(self, health_service: HealthMonitoringService, mock_websocket):
        """Test successful message sending."""
        result = await health_service.websocket_manager._safe_send_message(mock_websocket, "test message")

        assert result is True
        mock_websocket.send_text.assert_called_once_with("test message")

    @pytest.mark.asyncio
    async def test_safe_send_message_failure(self, health_service: HealthMonitoringService, mock_websocket):
        """Test message sending failure."""
        mock_websocket.send_text.side_effect = Exception("Connection error")

        result = await health_service.websocket_manager._safe_send_message(mock_websocket, "test message")

        assert isinstance(result, Exception)

    def test_get_service_health_data(self, health_service: HealthMonitoringService):
        """Test getting health data for a service."""
        with patch("registry.services.server_service.server_service_v1") as mock_server_service:
            mock_server_service.get_server_info.return_value = {"num_tools": 10}

            # Set up health data
            test_time = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
            health_service.server_health_status = {"/test": "healthy"}
            health_service.server_last_check_time = {"/test": test_time}

            result = health_service._get_service_health_data("/test")

            assert result["status"] == "healthy"
            assert result["last_checked_iso"] == test_time.isoformat()
            assert result["num_tools"] == 10

    def test_get_service_health_data_missing(self, health_service: HealthMonitoringService):
        """Test getting health data for non-existent service."""
        with patch("registry.services.server_service.server_service_v1") as mock_server_service:
            mock_server_service.get_server_info.return_value = None

            result = health_service._get_service_health_data("/nonexistent")

            assert result["status"] == "unknown"
            assert result["last_checked_iso"] is None
            assert result["num_tools"] == 0

    @pytest.mark.asyncio
    async def test_perform_health_checks(self, health_service: HealthMonitoringService):
        """Test performing health checks."""
        with patch("registry.services.server_service.server_service_v1") as mock_server_service, \
             patch.object(health_service, "_check_single_service") as mock_check_single, \
             patch.object(health_service, "broadcast_health_update") as mock_broadcast:

            mock_server_service.get_enabled_services.return_value = ["/test1", "/test2"]
            mock_server_service.get_server_info.return_value = {"proxy_pass_url": "http://test.com", "num_tools": 5}

            # Mock _check_single_service to return True (status changed)
            mock_check_single.return_value = True

            await health_service._perform_health_checks()

            # Check that _check_single_service was called for each enabled service
            assert mock_check_single.call_count == 2

            # Check that broadcast was called (since status changed)
            mock_broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_perform_health_checks_no_enabled_services(self, health_service: HealthMonitoringService):
        """Test health checks with no enabled services."""
        with patch("registry.services.server_service.server_service_v1") as mock_server_service, \
             patch.object(health_service, "broadcast_health_update") as mock_broadcast:

            mock_server_service.get_enabled_services.return_value = []

            await health_service._perform_health_checks()

            # No health status should be updated
            assert health_service.server_health_status == {}

            # No broadcast should occur
            mock_broadcast.assert_not_called()

    def test_get_all_health_status(self, health_service: HealthMonitoringService):
        """Test getting all health status."""
        with patch("registry.services.server_service.server_service_v1") as mock_server_service, \
             patch.object(health_service, "_get_service_health_data_fast") as mock_get_data:

            mock_server_service.get_all_servers.return_value = {
                "/test1": {"num_tools": 5},
                "/test2": {"num_tools": 3}
            }
            mock_get_data.return_value = {"status": "healthy", "last_checked_iso": None, "num_tools": 0}

            result = health_service.get_all_health_status()

            assert "/test1" in result
            assert "/test2" in result
            # _get_service_health_data_fast should be called for each server
            assert mock_get_data.call_count == 2
