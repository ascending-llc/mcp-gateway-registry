from enum import Enum


class TokenType(str, Enum):
    """Token type enumeration"""

    MCP_OAUTH_REFRESH = "mcp_oauth_refresh"
    MCP_OAUTH_CLIENT = "mcp_oauth_client"
