"""
MCP Client Configuration

Centralized configuration constants for MCP client operations.
Eliminates hardcoded values scattered across the codebase.
"""


class MCPClientConfig:
    """Stateless configuration constants for MCP client operations."""

    # Timeouts (in seconds)
    INIT_TIMEOUT = 30.0
    TOOLS_TIMEOUT = 45.0
    HEALTH_CHECK_TIMEOUT = 10.0
    OAUTH_METADATA_TIMEOUT = 10.0

    # Transport types
    TRANSPORT_HTTP = "streamable-http"
    TRANSPORT_SSE = "sse"
    TRANSPORT_STDIO = "stdio"

    # Endpoint paths
    ENDPOINT_MCP = "/mcp"
    ENDPOINT_SSE = "/sse"
    ENDPOINT_MESSAGES = "/messages/"

    # Well-known OAuth paths
    WELLKNOWN_OAUTH_RESOURCE = "/.well-known/oauth-protected-resource"
    WELLKNOWN_OAUTH_SERVER = "/.well-known/oauth-authorization-server"

    # Special server handling
    ANTHROPIC_QUERY_PARAM = "instance_id=default"
    ANTHROPIC_TAG = "anthropic-registry"

    # Header defaults
    DEFAULT_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

    # HTTP status codes considered healthy
    HEALTHY_STATUS_CODES = [200, 400, 405]
    AUTH_REQUIRED_STATUS_CODES = [401, 403]
