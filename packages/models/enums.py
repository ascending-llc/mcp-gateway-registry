from enum import Enum


class ToolDiscoveryMode(str, Enum):
    """Tool discovery mode enumeration"""
    EXTERNAL = "external"
    EMBEDDED = "embedded"


class ServerEntityType(str, Enum):
    """Entity type enumeration for vector documents"""
    SERVER = "server"
    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"
