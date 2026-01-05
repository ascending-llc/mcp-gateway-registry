
from typing import Optional
from redis import Redis
from registry.constants import REGISTRY_CONSTANTS
from registry.utils.log import logger


def get_redis_url() -> str:
    """
    Get Redis URL from environment variables
    """
    host = REGISTRY_CONSTANTS.REDIS_HOST
    port = REGISTRY_CONSTANTS.REDIS_PORT

    # Build URL
    redis_url = f"redis://{host}:{port}/1"
    return redis_url


def init_redis_connection(redis_url: Optional[str] = None) -> Redis:
    """
    Initialize Redis connection using native redis-py
    
    Args:
        redis_url: Optional Redis URL (defaults to environment variables)
        
    Returns:
        Redis client instance
        
    Raises:
        RuntimeError: If connection fails
    """
    if redis_url is None:
        redis_url = get_redis_url()
    
    try:
        # Create Redis client with connection pooling
        redis_conn = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
            max_connections=50
        )
        
        # Test connection
        redis_conn.ping()
        logger.info(f"Successfully connected to Redis: {redis_url}")
        return redis_conn
        
    except Exception as e:
        logger.error(f"Failed to connect to Redis at {redis_url}: {e}")
        raise RuntimeError(f"Redis connection failed: {e}")


def check_redis_health(redis_url: Optional[str] = None) -> bool:
    """
    Check if Redis is healthy and reachable
    
    Args:
        redis_url: Optional Redis URL
        
    Returns:
        True if Redis is reachable, False otherwise
    """
    try:
        if redis_url is None:
            redis_url = get_redis_url()
        
        redis_conn = Redis.from_url(redis_url, decode_responses=True)
        redis_conn.ping()
        return True
        
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        return False

