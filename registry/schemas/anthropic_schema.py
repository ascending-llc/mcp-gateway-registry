"""
Pydantic models for Anthropic MCP Registry API schema.

Based on: https://raw.githubusercontent.com/modelcontextprotocol/registry/refs/heads/main/docs/reference/api/openapi.yaml
"""

import logging
from typing import Any

from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


class Repository(BaseModel):
    """Repository metadata for MCP server source code."""

    url: str = Field(..., description="Repository URL for browsing source code")
    source: str = Field(..., description="Repository hosting service identifier (e.g., 'github')")
    id: str | None = Field(None, description="Repository ID from hosting service")
    subfolder: str | None = Field(None, description="Path within monorepo")


class StdioTransport(BaseModel):
    """Standard I/O transport configuration."""

    type: str = Field(default="stdio")
    command: str | None = Field(None, description="Command to execute")
    args: list[str] | None = Field(None, description="Command arguments")
    env: dict[str, str] | None = Field(None, description="Environment variables")


class StreamableHttpTransport(BaseModel):
    """HTTP-based transport configuration."""

    type: str = Field(default="streamable-http")
    url: str = Field(..., description="HTTP endpoint URL")
    headers: dict[str, str] | None = Field(None, description="HTTP headers")


class SseTransport(BaseModel):
    """Server-Sent Events transport configuration."""

    type: str = Field(default="sse")
    url: str = Field(..., description="SSE endpoint URL")


class Package(BaseModel):
    """Package information for MCP server distribution."""

    registryType: str = Field(..., description="Registry type (npm, pypi, oci, etc.)")
    identifier: str = Field(..., description="Package identifier or URL")
    version: str = Field(..., description="Specific package version")
    registryBaseUrl: str | None = Field(None, description="Base URL of package registry")
    transport: dict[str, Any] = Field(..., description="Transport configuration")
    runtimeHint: str | None = Field(None, description="Runtime hint (npx, uvx, docker, etc.)")


class ServerDetail(BaseModel):
    """Detailed MCP server information."""

    model_config = {"populate_by_name": True}

    name: str = Field(..., description="Server name in reverse-DNS format")
    description: str = Field(..., description="Server description")
    version: str = Field(..., description="Server version")
    title: str | None = Field(None, description="Human-readable server name")
    repository: Repository | None = Field(None, description="Repository information")
    websiteUrl: str | None = Field(None, description="Server website URL")
    packages: list[Package] | None = Field(None, description="Package distributions")
    meta: dict[str, Any] | None = Field(
        None, alias="_meta", serialization_alias="_meta", description="Extensible metadata"
    )


class ServerResponse(BaseModel):
    """Response for single server query."""

    model_config = {"populate_by_name": True}

    server: ServerDetail = Field(..., description="Server details")
    meta: dict[str, Any] | None = Field(
        None, alias="_meta", serialization_alias="_meta", description="Registry-managed metadata"
    )


class PaginationMetadata(BaseModel):
    """Pagination information for server lists."""

    nextCursor: str | None = Field(None, description="Cursor for next page")
    count: int | None = Field(None, description="Number of items in current page")


class ServerList(BaseModel):
    """Response for server list queries."""

    servers: list[ServerResponse] = Field(..., description="List of servers")
    metadata: PaginationMetadata | None = Field(None, description="Pagination info")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error message")
