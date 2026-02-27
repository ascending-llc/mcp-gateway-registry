from enum import StrEnum


class TokenType(StrEnum):
    """Token type enumeration"""

    MCP_OAUTH = "mcp_oauth"  # Access token
    MCP_OAUTH_REFRESH = "mcp_oauth_refresh"  # Refresh token
    MCP_OAUTH_CLIENT = "mcp_oauth_client"  # Client credentials (client_id, client_secret)
