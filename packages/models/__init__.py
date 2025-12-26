"""
Beanie ODM Models

Exports auto-generated models from _generated/
"""

try:
    from ._generated import *  # noqa: F403, F401
    from ._generated import __all__
except ImportError:
    # _generated doesn't exist yet - will be created by import-schemas
    __all__ = []
