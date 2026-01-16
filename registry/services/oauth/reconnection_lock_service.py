import time
from typing import Optional, List, Dict, Any
from redis import Redis
from contextlib import asynccontextmanager
from registry.config.redis_config import init_redis_connection
from registry.constants import REGISTRY_CONSTANTS
from registry.utils.log import logger


class ReconnectionLockService:
    """
    Distributed lock service for server reconnection using Redis.
    
    Uses Redis SET with NX (not exists) and EX (expiry) options to implement
    distributed locks that prevent concurrent reconnection attempts.
    """

    LOCK_KEY_PREFIX = f"{REGISTRY_CONSTANTS.REDIS_KEY_PREFIX}:reconnection:lock"

    # Redis key prefix for reconnection status tracking
    STATUS_KEY_PREFIX = f"{REGISTRY_CONSTANTS.REDIS_KEY_PREFIX}:reconnection:status"

    # Default lock timeout: 30 seconds
    # This should be longer than expected reconnection time but short enough
    # to not block too long if the process crashes
    DEFAULT_LOCK_TTL = 30

    # Default cooldown period: 60 seconds
    # Minimum time between reconnection attempts for the same server
    DEFAULT_COOLDOWN_PERIOD = 60

    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Initialize reconnection lock service.
        
        Args:
            redis_client: Redis client instance. If None, creates a new one.
        """
        self.redis = redis_client or init_redis_connection()
        logger.info("ReconnectionLockService initialized")

    def _make_lock_key(self, user_id: str, server_name: str) -> str:
        """Generate Redis lock key for user:server combination."""
        return f"{self.LOCK_KEY_PREFIX}:{user_id}:{server_name}"

    def _make_status_key(self, user_id: str, server_name: str) -> str:
        """Generate Redis status key for user:server combination."""
        return f"{self.STATUS_KEY_PREFIX}:{user_id}:{server_name}"

    def acquire_lock(
            self,
            user_id: str,
            server_name: str,
            ttl: int = DEFAULT_LOCK_TTL
    ) -> bool:
        """
        Try to acquire a distributed lock for server reconnection.
        
        Args:
            user_id: User ID
            server_name: Server name
            ttl: Lock time-to-live in seconds
            
        Returns:
            True if lock was acquired, False if already locked
        """
        lock_key = self._make_lock_key(user_id, server_name)
        lock_value = str(time.time())

        try:
            # SET key value NX EX ttl
            # NX: Only set if key doesn't exist
            # EX: Set expiry time
            acquired = self.redis.set(
                lock_key,
                lock_value,
                nx=True,  # Only set if not exists
                ex=ttl  # Expire after ttl seconds
            )

            if acquired:
                logger.debug(f"Acquired reconnection lock: {user_id}:{server_name} "
                             f"(TTL: {ttl}s)")
            else:
                logger.debug(f"Failed to acquire lock (already locked): "
                             f"{user_id}:{server_name}")

            return bool(acquired)

        except Exception as e:
            logger.error(f"Error acquiring reconnection lock for {user_id}:{server_name}: {e}",
                         exc_info=True)
            # Fail open: allow reconnection attempt on Redis error
            return True

    def release_lock(self, user_id: str, server_name: str) -> bool:
        """
        Release a reconnection lock.
        
        Args:
            user_id: User ID
            server_name: Server name
            
        Returns:
            True if lock was released, False if lock didn't exist
        """
        lock_key = self._make_lock_key(user_id, server_name)

        try:
            deleted = self.redis.delete(lock_key)

            if deleted:
                logger.debug(f"Released reconnection lock: {user_id}:{server_name}")

            return bool(deleted)

        except Exception as e:
            logger.error(f"Error releasing reconnection lock for {user_id}:{server_name}: {e}",
                         exc_info=True)
            return False

    def is_locked(self, user_id: str, server_name: str) -> bool:
        """
        Check if a server is currently locked for reconnection.
        
        Args:
            user_id: User ID
            server_name: Server name
            
        Returns:
            True if locked, False otherwise
        """
        lock_key = self._make_lock_key(user_id, server_name)

        try:
            return bool(self.redis.exists(lock_key))
        except Exception as e:
            logger.error(f"Error checking reconnection lock for {user_id}:{server_name}: {e}",
                         exc_info=True)
            return False

    def set_reconnection_status(
            self,
            user_id: str,
            server_name: str,
            status: str,
            details: Optional[Dict[str, Any]] = None,
            ttl: int = DEFAULT_COOLDOWN_PERIOD
    ) -> bool:
        """
        Set reconnection status for a server.
        
        Args:
            user_id: User ID
            server_name: Server name
            status: Status string (e.g., "success", "failed", "in_progress")
            details: Optional additional details
            ttl: Time-to-live for status in seconds
            
        Returns:
            True if status was set successfully
        """
        status_key = self._make_status_key(user_id, server_name)

        try:
            data = {
                "status": status,
                "timestamp": str(time.time()),
                "user_id": user_id,
                "server_name": server_name
            }

            if details:
                data["details"] = str(details)

            # Use pipeline for atomic operation
            pipe = self.redis.pipeline()
            pipe.hmset(status_key, data)
            pipe.expire(status_key, ttl)
            pipe.execute()

            logger.debug(
                f"Set reconnection status for {user_id}:{server_name}: "
                f"{status} (TTL: {ttl}s)"
            )
            return True

        except Exception as e:
            logger.error(f"Error setting reconnection status for {user_id}:{server_name}: {e}",
                         exc_info=True)
            return False

    def get_reconnection_status(
            self,
            user_id: str,
            server_name: str
    ) -> Optional[Dict[str, str]]:
        """
        Get reconnection status for a server.
        
        Args:
            user_id: User ID
            server_name: Server name
            
        Returns:
            Status dictionary or None if no status exists
        """
        status_key = self._make_status_key(user_id, server_name)

        try:
            data = self.redis.hgetall(status_key)
            return data if data else None

        except Exception as e:
            logger.error(f"Error getting reconnection status for {user_id}:{server_name}: {e}",
                         exc_info=True)
            return None

    def can_attempt_reconnection(
            self,
            user_id: str,
            server_name: str,
            cooldown_period: int = DEFAULT_COOLDOWN_PERIOD
    ) -> bool:
        """
        Check if reconnection can be attempted (not locked and cooldown expired).
        
        Args:
            user_id: User ID
            server_name: Server name
            cooldown_period: Minimum seconds between reconnection attempts
            
        Returns:
            True if reconnection can be attempted
        """
        # Check if currently locked
        if self.is_locked(user_id, server_name):
            logger.debug(f"Cannot attempt reconnection (locked): {user_id}:{server_name}")
            return False

        # Check cooldown period
        status = self.get_reconnection_status(user_id, server_name)
        if status:
            try:
                last_attempt = float(status.get("timestamp", 0))
                elapsed = time.time() - last_attempt

                if elapsed < cooldown_period:
                    logger.debug(f"Cannot attempt reconnection (cooldown): "
                                 f"{user_id}:{server_name} "
                                 f"(elapsed: {elapsed:.1f}s, required: {cooldown_period}s)")
                    return False
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid timestamp in reconnection status: {e}")
        return True

    @asynccontextmanager
    async def reconnection_lock(
            self,
            user_id: str,
            server_name: str,
            ttl: int = DEFAULT_LOCK_TTL
    ):
        """
        Async context manager for reconnection lock.
        
        Usage:
            async with lock_service.reconnection_lock(user_id, server_name):
                # Perform reconnection
                pass
        
        Args:
            user_id: User ID
            server_name: Server name
            ttl: Lock time-to-live in seconds
            
        Yields:
            True if lock was acquired, raises exception if not
        """
        acquired = self.acquire_lock(user_id, server_name, ttl)

        if not acquired:
            raise RuntimeError(f"Failed to acquire reconnection lock for "
                               f"{user_id}:{server_name}")

        try:
            yield True
        finally:
            self.release_lock(user_id, server_name)

    def cleanup_expired_locks(self) -> int:
        """
        Cleanup expired locks (Redis handles this automatically via TTL).
        
        This method is provided for manual cleanup if needed.
        
        Returns:
            Number of locks cleaned up (always 0 as Redis auto-expires)
        """
        # Redis automatically handles expiry, but we can scan for orphaned keys
        # This is a safety measure in case TTL wasn't set properly
        pattern = f"{self.LOCK_KEY_PREFIX}:*"
        cleaned = 0

        try:
            for key in self.redis.scan_iter(match=pattern, count=100):
                # Check if key has no TTL (should not happen)
                ttl = self.redis.ttl(key)
                if ttl == -1:  # No expiry set
                    self.redis.delete(key)
                    cleaned += 1
                    logger.warning(f"Cleaned up lock without TTL: {key}")

            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} locks without TTL")

            return cleaned

        except Exception as e:
            logger.error(f"Error during lock cleanup: {e}", exc_info=True)
            return 0

    def get_all_locked_servers(self, user_id: Optional[str] = None) -> List[str]:
        """
        Get all currently locked servers (optionally filtered by user).
        
        Args:
            user_id: Optional user ID to filter by
            
        Returns:
            List of server names currently locked
        """
        if user_id:
            pattern = f"{self.LOCK_KEY_PREFIX}:{user_id}:*"
        else:
            pattern = f"{self.LOCK_KEY_PREFIX}:*"

        locked_servers = []

        try:
            for key in self.redis.scan_iter(match=pattern, count=100):
                # Extract server name from key
                # Key format: prefix:user_id:server_name
                key_str = key if isinstance(key, str) else key.decode('utf-8')
                parts = key_str.split(":")
                if len(parts) >= 4:  # prefix has colons too
                    server_name = ":".join(parts[3:])
                    locked_servers.append(server_name)

            return locked_servers

        except Exception as e:
            logger.error(f"Error getting locked servers: {e}", exc_info=True)
            return []


_reconnection_lock_service: Optional[ReconnectionLockService] = None


def get_reconnection_lock_service() -> ReconnectionLockService:
    global _reconnection_lock_service
    if _reconnection_lock_service is None:
        _reconnection_lock_service = ReconnectionLockService()
        logger.info("Initialized global ReconnectionLockService")
    return _reconnection_lock_service
