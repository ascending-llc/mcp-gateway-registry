"""
Beanie ODM Models

Exports auto-generated models from _generated/ and static models
"""

# Export static models (legacy - will be deprecated)
from .enums import ToolDiscoveryMode

# Export extended models (registry-specific extensions)
from .extended_mcp_server import ExtendedMCPServer, MCPServerDocument

# Export auto-generated models from _generated/
try:
    from ._generated import *  # noqa: F403, F401
    from ._generated import __all__ as _generated_all

    __all__ = ['ToolDiscoveryMode', 'ExtendedMCPServer', 'MCPServerDocument'] + _generated_all
except ImportError:
    # _generated doesn't exist yet - will be created by import-schemas
    __all__ = ['ToolDiscoveryMode', 'ExtendedMCPServer', 'MCPServerDocument']
