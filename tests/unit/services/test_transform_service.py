"""
Unit tests for Anthropic API transformation service.
"""

import pytest
from typing import Any, Dict, List

from registry.services.transform_service import (
    _create_server_name,
    _create_transport_config,
    _determine_version,
    transform_to_server_detail,
    transform_to_server_list,
    transform_to_server_response,
)
from registry.schemas.anthropic_schema import (
    Package,
    PaginationMetadata,
    ServerDetail,
    ServerList,
    ServerResponse,
)


@pytest.mark.unit
class TestTransformService:
    """Test suite for transformation service."""

    def test_create_server_name_simple_path(self):
        """Test creating reverse-DNS name from simple path."""
        server_info = {"path": "/example-server"}
        result = _create_server_name(server_info)
        assert result == "io.mcpgateway/example-server"

    def test_create_server_name_nested_path(self):
        """Test creating reverse-DNS name from nested path."""
        server_info = {"path": "/api/v1/example"}
        result = _create_server_name(server_info)
        assert result == "io.mcpgateway/api/v1/example"

    def test_create_server_name_trailing_slash(self):
        """Test creating reverse-DNS name with trailing slash."""
        server_info = {"path": "/example/"}
        result = _create_server_name(server_info)
        assert result == "io.mcpgateway/example"

    def test_create_transport_config(self):
        """Test creating transport configuration."""
        server_info = {"proxy_pass_url": "http://localhost:8000"}
        result = _create_transport_config(server_info)

        assert result["type"] == "streamable-http"
        assert result["url"] == "http://localhost:8000"

    def test_determine_version_default(self):
        """Test version determination with no metadata."""
        server_info = {}
        result = _determine_version(server_info)
        assert result == "1.0.0"

    def test_determine_version_from_meta(self):
        """Test version determination from metadata."""
        server_info = {"_meta": {"version": "2.3.4"}}
        result = _determine_version(server_info)
        assert result == "2.3.4"

    def test_transform_to_server_detail(self):
        """Test transforming internal server info to ServerDetail."""
        server_info = {
            "server_name": "Test Server",
            "description": "A test server",
            "path": "/test-server",
            "proxy_pass_url": "http://localhost:8000",
            "tags": ["test", "example"],
            "num_tools": 5,
            "license": "MIT",
            "is_enabled": True,
            "health_status": "healthy",
        }

        result = transform_to_server_detail(server_info)

        assert isinstance(result, ServerDetail)
        assert result.name == "io.mcpgateway/test-server"
        assert result.title == "Test Server"
        assert result.description == "A test server"
        assert result.version == "1.0.0"
        assert len(result.packages) == 1
        assert result.packages[0].registryType == "mcpb"
        assert result.packages[0].transport["type"] == "streamable-http"
        assert result.meta["io.mcpgateway/internal"]["num_tools"] == 5
        assert result.meta["io.mcpgateway/internal"]["tags"] == ["test", "example"]

    def test_transform_to_server_response_with_meta(self):
        """Test transforming to ServerResponse with registry metadata."""
        server_info = {
            "server_name": "Test Server",
            "description": "A test server",
            "path": "/test",
            "proxy_pass_url": "http://localhost:8000",
            "health_status": "healthy",
            "last_checked_iso": "2025-10-12T10:00:00Z",
            "is_enabled": True,
            "tags": [],
            "num_tools": 0,
            "license": "N/A",
        }

        result = transform_to_server_response(server_info, include_registry_meta=True)

        assert isinstance(result, ServerResponse)
        assert isinstance(result.server, ServerDetail)
        assert result.meta is not None
        assert "io.mcpgateway/registry" in result.meta
        assert result.meta["io.mcpgateway/registry"]["health_status"] == "healthy"
        assert (
            result.meta["io.mcpgateway/registry"]["last_checked"]
            == "2025-10-12T10:00:00Z"
        )

    def test_transform_to_server_response_without_meta(self):
        """Test transforming to ServerResponse without registry metadata."""
        server_info = {
            "server_name": "Test Server",
            "description": "A test server",
            "path": "/test",
            "proxy_pass_url": "http://localhost:8000",
            "health_status": "healthy",
            "is_enabled": True,
            "tags": [],
            "num_tools": 0,
            "license": "N/A",
        }

        result = transform_to_server_response(server_info, include_registry_meta=False)

        assert isinstance(result, ServerResponse)
        assert result.meta is None

    def test_transform_to_server_list_no_pagination(self):
        """Test transforming server list without pagination."""
        servers = [
            {
                "server_name": "Server A",
                "description": "First server",
                "path": "/server-a",
                "proxy_pass_url": "http://localhost:8001",
                "health_status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "is_enabled": True,
                "tags": [],
                "num_tools": 3,
                "license": "MIT",
            },
            {
                "server_name": "Server B",
                "description": "Second server",
                "path": "/server-b",
                "proxy_pass_url": "http://localhost:8002",
                "health_status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "is_enabled": True,
                "tags": [],
                "num_tools": 5,
                "license": "Apache-2.0",
            },
        ]

        result = transform_to_server_list(servers)

        assert isinstance(result, ServerList)
        assert len(result.servers) == 2
        assert result.metadata.count == 2
        assert result.metadata.nextCursor is None

    def test_transform_to_server_list_with_limit(self):
        """Test transforming server list with limit."""
        servers = [
            {
                "server_name": f"Server {i}",
                "description": f"Server {i}",
                "path": f"/server-{i}",
                "proxy_pass_url": f"http://localhost:800{i}",
                "health_status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "is_enabled": True,
                "tags": [],
                "num_tools": i,
                "license": "MIT",
            }
            for i in range(5)
        ]

        result = transform_to_server_list(servers, limit=2)

        assert isinstance(result, ServerList)
        assert len(result.servers) == 2
        assert result.metadata.count == 2
        assert result.metadata.nextCursor is not None

    def test_transform_to_server_list_with_cursor(self):
        """Test transforming server list with cursor for pagination."""
        servers = [
            {
                "server_name": "Server A",
                "description": "First server",
                "path": "/aaa",
                "proxy_pass_url": "http://localhost:8001",
                "health_status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "is_enabled": True,
                "tags": [],
                "num_tools": 1,
                "license": "MIT",
            },
            {
                "server_name": "Server B",
                "description": "Second server",
                "path": "/bbb",
                "proxy_pass_url": "http://localhost:8002",
                "health_status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "is_enabled": True,
                "tags": [],
                "num_tools": 2,
                "license": "MIT",
            },
            {
                "server_name": "Server C",
                "description": "Third server",
                "path": "/ccc",
                "proxy_pass_url": "http://localhost:8003",
                "health_status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "is_enabled": True,
                "tags": [],
                "num_tools": 3,
                "license": "MIT",
            },
        ]

        # Get first page
        page1 = transform_to_server_list(servers, limit=2)
        assert len(page1.servers) == 2
        assert page1.metadata.nextCursor is not None

        # Get second page using cursor
        cursor = page1.metadata.nextCursor
        page2 = transform_to_server_list(servers, cursor=cursor, limit=2)
        assert len(page2.servers) == 1
        assert page2.metadata.nextCursor is None

    def test_transform_to_server_list_sorting(self):
        """Test that server list is sorted by name for consistent pagination."""
        servers = [
            {
                "server_name": "Server Z",
                "path": "/zzz",
                "proxy_pass_url": "http://localhost:8001",
                "description": "",
                "health_status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "is_enabled": True,
                "tags": [],
                "num_tools": 0,
                "license": "N/A",
            },
            {
                "server_name": "Server A",
                "path": "/aaa",
                "proxy_pass_url": "http://localhost:8002",
                "description": "",
                "health_status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "is_enabled": True,
                "tags": [],
                "num_tools": 0,
                "license": "N/A",
            },
            {
                "server_name": "Server M",
                "path": "/mmm",
                "proxy_pass_url": "http://localhost:8003",
                "description": "",
                "health_status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "is_enabled": True,
                "tags": [],
                "num_tools": 0,
                "license": "N/A",
            },
        ]

        result = transform_to_server_list(servers)

        # Should be sorted alphabetically by reverse-DNS name
        assert result.servers[0].server.name == "io.mcpgateway/aaa"
        assert result.servers[1].server.name == "io.mcpgateway/mmm"
        assert result.servers[2].server.name == "io.mcpgateway/zzz"

    def test_transform_to_server_list_max_limit(self):
        """Test that limit is capped at 1000."""
        servers = [
            {
                "server_name": f"Server {i}",
                "description": "",
                "path": f"/server-{i}",
                "proxy_pass_url": f"http://localhost:800{i}",
                "health_status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "is_enabled": True,
                "tags": [],
                "num_tools": 0,
                "license": "N/A",
            }
            for i in range(10)
        ]

        # Request limit > 1000, should be capped at 1000
        result = transform_to_server_list(servers, limit=5000)

        # All 10 servers should be returned (less than 1000)
        assert len(result.servers) == 10

    def test_transform_to_server_list_empty_list(self):
        """Test transforming empty server list."""
        result = transform_to_server_list([])

        assert isinstance(result, ServerList)
        assert len(result.servers) == 0
        assert result.metadata.count == 0
        assert result.metadata.nextCursor is None
