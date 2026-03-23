"""Centralized Redis connection management for the registry."""

import logging

from redis import Redis

from ..core.config import RedisConfig

logger = logging.getLogger(__name__)


def create_redis_client(config: RedisConfig) -> Redis:
    """Create a Redis client without touching module-level global state."""
    redis_url = config.redis_uri

    try:
        client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
            max_connections=50,
        )

        # Test connection
        client.ping()
        logger.info(f"✅ Successfully connected to Redis: {redis_url}")
        return client

    except Exception as e:
        logger.error(f"❌ Failed to connect to Redis at {redis_url}: {e}")
        raise RuntimeError(f"Redis connection failed: {e}")


def close_redis_client(client: Redis | None) -> None:
    """Close a Redis client created by create_redis_client()."""
    if client is None:
        return
    client.close()
