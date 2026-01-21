"""
Abstract base classes for connection management.
Defines interfaces for connection lifecycle and state management.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
import time
from registry.schemas.enums import ConnectionState


@dataclass
class Connection(ABC):
    """Basic connection interface"""
    server_id: str
    connection_state: ConnectionState
    last_activity: float = field(default_factory=time.time)
    error_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    @abstractmethod
    def is_stale(self, max_idle_time: Optional[float] = None) -> bool:
        """Return True if the connection is stale based on idle time and optional max_idle_time."""
        pass

    def update_activity(self) -> None:
        """Update last activity time"""
        self.last_activity = time.time()

    def increment_error(self) -> None:
        """Increase the error count."""
        self.error_count += 1

    def reset_errors(self) -> None:
        """Reset the error count."""
        self.error_count = 0


class ConnectionManager(ABC):
    """Connection Manager Abstract Interface"""

    @abstractmethod
    async def get_connection(
            self,
            user_id: str,
            server_id: str
    ) -> Optional[Connection]:
        pass

    @abstractmethod
    async def update_connection_state(
            self,
            user_id: str,
            server_id: str,
            state: ConnectionState,
            details: Optional[Dict[str, Any]] = None
    ) -> None:
        """update user connection state"""
        pass

    @abstractmethod
    async def create_user_connection(
            self,
            user_id: str,
            server_id: str,
            initial_state: ConnectionState = ConnectionState.CONNECTING,
            details: Optional[Dict[str, Any]] = None
    ) -> Connection:
        """Create new user-level connection"""
        pass

    @abstractmethod
    async def disconnect_user_connection(
            self,
            user_id: str,
            server_id: str
    ) -> bool:
        """Disconnect user connection"""
        pass

    @abstractmethod
    def get_user_connections(self, user_id: str) -> Dict[str, Connection]:
        """Get all connections for the user"""
        pass


@dataclass
class ConnectionStateContext:
    """Connection status context - used for status parsing"""
    user_id: str
    server_name: str
    server_id: str
    server_config: Dict[str, Any]
    connection: Optional[Connection] = None
    is_oauth_server: bool = False
    idle_timeout: Optional[float] = None  # idle_timeout value provided from server_config
