"""
Beanie ODM Models

Exports auto-generated models from _generated/ and static models
"""

# Export static models (legacy - will be deprecated)
from .enums import ToolDiscoveryMode

# Export extended models (registry-specific extensions)
from .extended_mcp_server import ExtendedMCPServer, MCPServerDocument

# Export A2A Agent model (main ODM class only)
from .a2a_agent import A2AAgent

# Export auto-generated models from _generated/
try:
    from ._generated import *  # noqa: F403, F401
    from ._generated import __all__ as _generated_all

    __all__ = [
        # Static models
        'ToolDiscoveryMode',
        'ExtendedMCPServer',
        'MCPServerDocument',
        # A2A Agent (main model only)
        'A2AAgent',
    ] + _generated_all
except ImportError:
    # _generated doesn't exist yet - will be created by import-schemas
    __all__ = [
        'ToolDiscoveryMode',
        'ExtendedMCPServer',
        'MCPServerDocument',
        'A2AAgent',
    ]
