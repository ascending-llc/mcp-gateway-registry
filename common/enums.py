from enum import Enum


class TransportType(str, Enum):
    """Supported transport types for MCP connections."""
    STDIO = "stdio"
    WEBSOCKET = "websocket"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"
