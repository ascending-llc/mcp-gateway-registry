from enum import Enum


class ToolDiscoveryMode(str, Enum):
    """Tool discovery mode enumeration"""
    EXTERNAL = "external"
    EMBEDDED = "embedded"