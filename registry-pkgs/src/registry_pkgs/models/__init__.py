"""
Beanie ODM Models

Exports auto-generated models from _generated/ and static models
"""

from .a2a_agent import A2AAgent
from .agentcore_gateway import AgentCoreGateway
from .enums import ToolDiscoveryMode
from .extended_mcp_server import ExtendedMCPServer, MCPServerDocument
from .oauth_provider_config import OAuthProviderConfig

# Export auto-generated models from _generated/
try:
    from ._generated import *  # noqa: F403, F401
    from ._generated import __all__ as _generated_all

    __all__ = [
        "A2AAgent",
        "AgentCoreGateway",
        "ExtendedMCPServer",
        "MCPServerDocument",
        "OAuthProviderConfig",
        "ToolDiscoveryMode",
    ] + _generated_all
except ImportError:
    # _generated doesn't exist yet - will be created by import-schemas
    __all__ = [
        "A2AAgent",
        "AgentCoreGateway",
        "ExtendedMCPServer",
        "MCPServerDocument",
        "OAuthProviderConfig",
        "ToolDiscoveryMode",
    ]
