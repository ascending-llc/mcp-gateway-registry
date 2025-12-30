from enum import Enum


class OAuthFlowStatus(str, Enum):
    """OAuth flow status"""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class ConnectionState(str, Enum):
    """Connection state enumeration"""
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    PENDING_OAUTH = "PENDING_OAUTH"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"
