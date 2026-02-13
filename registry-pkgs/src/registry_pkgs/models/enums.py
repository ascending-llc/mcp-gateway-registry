from enum import StrEnum


class ToolDiscoveryMode(StrEnum):
    """Tool discovery mode enumeration"""

    EXTERNAL = "external"
    EMBEDDED = "embedded"


class ServerEntityType(StrEnum):
    """Entity type enumeration for vector documents"""

    SERVER = "server"
    TOOL = "tool"
    RESOURCE = "resource"
    PROMPT = "prompt"
