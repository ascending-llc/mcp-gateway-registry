import json
import logging
from collections.abc import Callable
from typing import Any

from registry_pkgs.database.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class ScopesConfigCache:
    """
    Cache for scopes.yml configuration.

    Uses Redis when available, with in-memory fallback.
    """

    def __init__(self, redis_key: str = "registry:scopes_config", ttl_seconds: int | None = 300) -> None:
        self._redis_key = redis_key
        self._ttl_seconds = ttl_seconds
        self._memory_cache: dict[str, Any] | None = None

    def clear_memory(self) -> None:
        """Clear only in-memory cache (Redis is left intact)."""
        logger.debug("ScopesConfigCache: clearing in-memory cache for key=%s", self._redis_key)
        self._memory_cache = None

    def cache_source(self) -> str:
        """
        Return current cache source availability.
        - "memory": in-memory cache already populated
        - "redis": redis client available
        """
        if self._memory_cache is not None:
            return "memory"
        if get_redis_client() is not None:
            return "redis"
        return "none"

    def refresh(self) -> None:
        """
        Clear both in-memory and Redis cache.
        """
        logger.debug("ScopesConfigCache: refreshing cache (memory + redis) for key=%s", self._redis_key)
        self._memory_cache = None
        redis_client = get_redis_client()
        if redis_client is not None:
            try:
                redis_client.delete(self._redis_key)
                logger.debug("ScopesConfigCache: deleted redis key=%s", self._redis_key)
            except Exception as e:
                logger.warning("Failed to delete scopes cache from Redis: %s", e)

    def get_or_load(self, loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """
        Return scopes config from cache, or load via loader.
        """
        logger.debug(
            "ScopesConfigCache: get_or_load start key=%s source=%s",
            self._redis_key,
            self.cache_source(),
        )
        if self._memory_cache is not None:
            logger.debug("ScopesConfigCache: memory hit for key=%s", self._redis_key)
            return self._memory_cache

        redis_client = get_redis_client()
        logger.debug("ScopesConfigCache: loading from cache key=%s", self._redis_key)
        if redis_client is not None:
            try:
                cached = redis_client.get(self._redis_key)
                if cached:
                    self._memory_cache = json.loads(cached)
                    logger.debug("ScopesConfigCache: redis hit for key=%s", self._redis_key)
                    return self._memory_cache
                logger.debug("ScopesConfigCache: redis miss for key=%s", self._redis_key)
            except Exception as e:
                logger.warning("Failed to read scopes cache from Redis: %s", e)

        config = loader() or {}
        self._memory_cache = config
        logger.debug("ScopesConfigCache: loaded config via loader for key=%s", self._redis_key)

        if redis_client is not None:
            try:
                if self._ttl_seconds is None:
                    redis_client.set(self._redis_key, json.dumps(config))
                else:
                    redis_client.set(self._redis_key, json.dumps(config), ex=self._ttl_seconds)
            except Exception as e:
                logger.warning("Failed to write scopes cache to Redis: %s", e)
        return config
