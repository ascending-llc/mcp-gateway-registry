"""
Beanie ODM Models

Exports auto-generated models from _generated/ and static models
"""

# Export static models (legacy - will be deprecated)
from .mcp_tool import McpTool
from .enums import ToolDiscoveryMode

# Export auto-generated models from _generated/
try:
    from ._generated import *  # noqa: F403, F401
    from ._generated import __all__ as _generated_all
    __all__ = ['McpTool', 'ToolDiscoveryMode'] + _generated_all
except ImportError:
    # _generated doesn't exist yet - will be created by import-schemas
    __all__ = ['McpTool', 'ToolDiscoveryMode']
