from enum import StrEnum


class OAuthFlowStatus(StrEnum):
    """OAuth flow status"""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ConnectionState(StrEnum):
    """Connection state enumeration"""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    PENDING_OAUTH = "pending_oauth"
    ERROR = "error"
    UNKNOWN = "unknown"
