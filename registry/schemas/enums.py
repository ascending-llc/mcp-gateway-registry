from enum import Enum


class OAuthFlowStatus(str, Enum):
    """OAuth flow status"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ConnectionState(str, Enum):
    """Connection state enumeration"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    PENDING_OAUTH = "pending_oauth"
    ERROR = "error"
    UNKNOWN = "unknown"
