import time
from typing import Dict, Set


class OAuthReconnectionTracker:
    """OAuth Reconnection Tracker"""

    def __init__(self):
        # user_id -> set of server names with failed reconnections
        self._failed: Dict[str, Set[str]] = {}
        # user_id -> set of server names currently reconnecting
        self._active: Dict[str, Set[str]] = {}
        # user_id:server_name -> reconnection start timestamp
        self._active_timestamps: Dict[str, float] = {}
        # reconnection timeout in seconds
        self._reconnection_timeout_seconds = 3 * 60  # 3 minutes

    def is_failed(self, user_id: str, server_name: str) -> bool:
        """Check if server reconnection failed"""
        user_servers = self._failed.get(user_id)
        return user_servers is not None and server_name in user_servers

    def is_active(self, user_id: str, server_name: str) -> bool:
        """Check if server is reconnecting (basic check)"""
        user_servers = self._active.get(user_id)
        return user_servers is not None and server_name in user_servers

    def is_still_reconnecting(self, user_id: str, server_name: str) -> bool:
        """Check if server is still reconnecting (considering timeout)"""
        if not self.is_active(user_id, server_name):
            return False

        key = f"{user_id}:{server_name}"
        start_time = self._active_timestamps.get(key)

        # If timestamp exists and has timed out, no longer reconnecting
        if start_time and time.time() - start_time > self._reconnection_timeout_seconds:
            return False

        return True

    def cleanup_if_timed_out(self, user_id: str, server_name: str) -> bool:
        """Clean up server if timed out - returns True if cleanup was performed"""
        key = f"{user_id}:{server_name}"
        start_time = self._active_timestamps.get(key)

        if start_time and time.time() - start_time > self._reconnection_timeout_seconds:
            self.remove_active(user_id, server_name)
            return True

        return False

    def set_failed(self, user_id: str, server_name: str) -> None:
        """Mark server reconnection as failed"""
        if user_id not in self._failed:
            self._failed[user_id] = set()

        self._failed[user_id].add(server_name)

    def set_active(self, user_id: str, server_name: str) -> None:
        """Mark server as reconnecting"""
        if user_id not in self._active:
            self._active[user_id] = set()

        self._active[user_id].add(server_name)

        # Track reconnection start time
        key = f"{user_id}:{server_name}"
        self._active_timestamps[key] = time.time()

    def remove_failed(self, user_id: str, server_name: str) -> None:
        """Remove failed server"""
        user_servers = self._failed.get(user_id)
        if user_servers:
            user_servers.discard(server_name)
            if not user_servers:
                del self._failed[user_id]

    def remove_active(self, user_id: str, server_name: str) -> None:
        """Remove reconnecting server"""
        user_servers = self._active.get(user_id)
        if user_servers:
            user_servers.discard(server_name)
            if not user_servers:
                del self._active[user_id]

        # Clean up timestamp tracking
        key = f"{user_id}:{server_name}"
        self._active_timestamps.pop(key, None)
