from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from httpx import AsyncClient

if TYPE_CHECKING:
    from ...core.session_store import SessionStore
    from ...services.oauth.oauth_service import MCPOAuthService
    from ...services.server_service import ServerServiceV1


@dataclass
class McpAppContext:
    """MCP application context with typed dependencies."""

    proxy_client: AsyncClient
    server_service: "ServerServiceV1 | Any"
    oauth_service: "MCPOAuthService | Any"
    session_store: "SessionStore | Any"
