"""
Tests for registry/core/telemetry_decorators.py

Tests for registry-specific telemetry decorators that provide automatic
metrics collection for API operations.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

from registry.core.telemetry_decorators import (
    track_registry_operation,
    track_auth_request,
    track_tool_execution,
    track_tool_discovery,
    AuthMetricsContext,
    ToolExecutionMetricsContext,
)

# Module path for mocking domain functions
DOMAIN_FUNCS_PATH = "registry.core.telemetry_decorators"


@pytest.mark.unit
@pytest.mark.metrics
class TestTrackRegistryOperation:
    """Test suite for track_registry_operation decorator."""

    @pytest.mark.asyncio
    async def test_tracks_successful_operation(self):
        """Test decorator tracks successful registry operations."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_registry_operation") as mock_record:
            @track_registry_operation("create", resource_type="server")
            async def create_server():
                return {"id": "123"}

            result = await create_server()

            assert result == {"id": "123"}
            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["operation"] == "create"
            assert call_kwargs["resource_type"] == "server"
            assert call_kwargs["success"] is True
            assert call_kwargs["duration_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_tracks_failed_operation(self):
        """Test decorator tracks failed registry operations."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_registry_operation") as mock_record:
            @track_registry_operation("delete", resource_type="server")
            async def delete_server():
                raise ValueError("Server not found")

            with pytest.raises(ValueError, match="Server not found"):
                await delete_server()

            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["operation"] == "delete"
            assert call_kwargs["success"] is False

    @pytest.mark.asyncio
    async def test_extracts_resource_dynamically(self):
        """Test decorator extracts resource type from args."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_registry_operation") as mock_record:
            def extract_resource(query, **kwargs):
                return query.get("entity_type", "unknown")

            @track_registry_operation("search", extract_resource=extract_resource)
            async def search(query):
                return []

            await search({"entity_type": "tool", "q": "test"})

            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["resource_type"] == "tool"

    @pytest.mark.asyncio
    async def test_handles_extract_resource_error(self):
        """Test decorator handles extract_resource errors gracefully."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_registry_operation") as mock_record:
            def failing_extract(*args, **kwargs):
                raise RuntimeError("Extraction failed")

            @track_registry_operation("list", extract_resource=failing_extract)
            async def list_items():
                return []

            await list_items()

            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["resource_type"] == "unknown"

    @pytest.mark.asyncio
    async def test_uses_function_name_as_fallback(self):
        """Test decorator uses function name when no resource_type."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_registry_operation") as mock_record:
            @track_registry_operation("read")
            async def get_config():
                return {}

            await get_config()

            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["resource_type"] == "get_config"


@pytest.mark.unit
@pytest.mark.metrics
class TestTrackAuthRequest:
    """Test suite for track_auth_request decorator."""

    @pytest.mark.asyncio
    async def test_tracks_successful_auth(self):
        """Test decorator tracks successful authentication."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_auth_request") as mock_record:
            @track_auth_request(default_mechanism="jwt")
            async def authenticate():
                return {"username": "test_user", "auth_source": "jwt"}

            result = await authenticate()

            assert result["username"] == "test_user"
            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["mechanism"] == "jwt"
            assert call_kwargs["success"] is True

    @pytest.mark.asyncio
    async def test_tracks_failed_auth(self):
        """Test decorator tracks failed authentication."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_auth_request") as mock_record:
            @track_auth_request(default_mechanism="session")
            async def authenticate():
                raise ValueError("Invalid credentials")

            with pytest.raises(ValueError):
                await authenticate()

            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["success"] is False

    @pytest.mark.asyncio
    async def test_extracts_mechanism_from_result(self):
        """Test decorator extracts mechanism from result dict."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_auth_request") as mock_record:
            @track_auth_request(default_mechanism="unknown")
            async def authenticate():
                return {"auth_source": "basic_auth"}

            await authenticate()

            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["mechanism"] == "basic_auth"

    @pytest.mark.asyncio
    async def test_uses_custom_mechanism_extractor(self):
        """Test decorator uses custom mechanism extractor."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_auth_request") as mock_record:
            def extract_mechanism(result):
                return result.get("provider", "default")

            @track_auth_request(extract_mechanism=extract_mechanism)
            async def authenticate():
                return {"provider": "oauth2"}

            await authenticate()

            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["mechanism"] == "oauth2"


@pytest.mark.unit
@pytest.mark.metrics
class TestTrackToolExecution:
    """Test suite for track_tool_execution decorator."""

    @pytest.mark.asyncio
    async def test_tracks_successful_execution(self):
        """Test decorator tracks successful tool execution."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_tool_execution") as mock_record:
            def get_tool_info(tool_name, server, **kwargs):
                return {
                    "tool_name": tool_name,
                    "server_name": server.name,
                    "method": "POST"
                }

            @track_tool_execution(extract_tool_info=get_tool_info)
            async def execute_tool(tool_name, server):
                return {"result": "success"}

            mock_server = MagicMock()
            mock_server.name = "test-server"

            result = await execute_tool("calculator", mock_server)

            assert result["result"] == "success"
            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["tool_name"] == "calculator"
            assert call_kwargs["server_name"] == "test-server"
            assert call_kwargs["method"] == "POST"
            assert call_kwargs["success"] is True

    @pytest.mark.asyncio
    async def test_tracks_failed_execution(self):
        """Test decorator tracks failed tool execution."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_tool_execution") as mock_record:
            @track_tool_execution()
            async def execute_tool():
                raise TimeoutError("Tool timed out")

            with pytest.raises(TimeoutError):
                await execute_tool()

            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["success"] is False

    @pytest.mark.asyncio
    async def test_uses_defaults_without_extractor(self):
        """Test decorator uses defaults when no extractor provided."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_tool_execution") as mock_record:
            @track_tool_execution()
            async def execute_tool():
                return {}

            await execute_tool()

            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["tool_name"] == "unknown"
            assert call_kwargs["server_name"] == "unknown"
            assert call_kwargs["method"] == "UNKNOWN"


@pytest.mark.unit
@pytest.mark.metrics
class TestTrackToolDiscovery:
    """Test suite for track_tool_discovery decorator."""

    @pytest.mark.asyncio
    async def test_tracks_successful_discovery(self):
        """Test decorator tracks successful tool discovery."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_tool_discovery") as mock_record:
            @track_tool_discovery(extract_query=lambda body, **kw: body.get("query", ""))
            async def discover_tools(body):
                return MagicMock(matches=[])

            result = await discover_tools({"query": "search tools"})

            mock_record.assert_called()
            # Check the overall operation was recorded
            calls = mock_record.call_args_list
            assert len(calls) >= 1
            # Last call should be for overall operation with duration
            last_call = calls[-1][1]
            assert last_call["tool_name"] == "search tools"
            assert last_call["success"] is True
            assert last_call["duration_seconds"] is not None

    @pytest.mark.asyncio
    async def test_tracks_failed_discovery(self):
        """Test decorator tracks failed tool discovery."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_tool_discovery") as mock_record:
            @track_tool_discovery(extract_query=lambda body, **kw: body.get("query", ""))
            async def discover_tools(body):
                raise ValueError("Search failed")

            with pytest.raises(ValueError):
                await discover_tools({"query": "test"})

            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["success"] is False

    @pytest.mark.asyncio
    async def test_records_individual_tool_discoveries(self):
        """Test decorator records metrics for each discovered tool."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_tool_discovery") as mock_record:
            @track_tool_discovery()
            async def discover_tools(body):
                mock_result = MagicMock()
                mock_match1 = MagicMock()
                mock_match1.tool_name = "tool1"
                mock_match2 = MagicMock()
                mock_match2.tool_name = "tool2"
                mock_result.matches = [mock_match1, mock_match2]
                return mock_result

            await discover_tools({})

            # Should have 3 calls: 2 for individual tools + 1 for overall
            assert mock_record.call_count == 3


@pytest.mark.unit
@pytest.mark.metrics
class TestAuthMetricsContext:
    """Test suite for AuthMetricsContext context manager."""

    @pytest.mark.asyncio
    async def test_records_metrics_on_exit(self):
        """Test context manager records auth metrics on exit."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_auth_request") as mock_record:
            async with AuthMetricsContext() as ctx:
                ctx.set_mechanism("jwt")
                ctx.set_success(True)

            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["mechanism"] == "jwt"
            assert call_kwargs["success"] is True
            assert call_kwargs["duration_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_records_failure_on_exception(self):
        """Test context manager records failure on exception."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_auth_request") as mock_record:
            with pytest.raises(ValueError):
                async with AuthMetricsContext(default_mechanism="session") as ctx:
                    raise ValueError("Auth error")

            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["success"] is False
            assert call_kwargs["mechanism"] == "session"

    @pytest.mark.asyncio
    async def test_uses_default_mechanism(self):
        """Test context manager uses default mechanism."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_auth_request") as mock_record:
            async with AuthMetricsContext(default_mechanism="api_key"):
                pass

            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["mechanism"] == "api_key"


@pytest.mark.unit
@pytest.mark.metrics
class TestToolExecutionMetricsContext:
    """Test suite for ToolExecutionMetricsContext context manager."""

    @pytest.mark.asyncio
    async def test_records_metrics_on_exit(self):
        """Test context manager records tool execution metrics on exit."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_tool_execution") as mock_record:
            async with ToolExecutionMetricsContext(
                tool_name="calculator",
                server_name="math-server",
                method="POST"
            ) as ctx:
                ctx.set_success(True)

            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["tool_name"] == "calculator"
            assert call_kwargs["server_name"] == "math-server"
            assert call_kwargs["method"] == "POST"
            assert call_kwargs["success"] is True

    @pytest.mark.asyncio
    async def test_allows_dynamic_updates(self):
        """Test context manager allows updating values dynamically."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_tool_execution") as mock_record:
            async with ToolExecutionMetricsContext() as ctx:
                ctx.set_tool_name("weather")
                ctx.set_server_name("weather-server")
                ctx.set_method("GET")
                ctx.set_success(True)

            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["tool_name"] == "weather"
            assert call_kwargs["server_name"] == "weather-server"
            assert call_kwargs["method"] == "GET"

    @pytest.mark.asyncio
    async def test_records_failure_on_exception(self):
        """Test context manager records failure on exception."""
        with patch(f"{DOMAIN_FUNCS_PATH}._record_tool_execution") as mock_record:
            with pytest.raises(TimeoutError):
                async with ToolExecutionMetricsContext(
                    tool_name="slow-tool",
                    server_name="slow-server"
                ):
                    raise TimeoutError("Timeout")

            call_kwargs = mock_record.call_args[1]
            assert call_kwargs["success"] is False
            assert call_kwargs["tool_name"] == "slow-tool"
