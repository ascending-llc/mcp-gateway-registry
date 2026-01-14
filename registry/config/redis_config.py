from redis import Redis
from registry.constants import REGISTRY_CONSTANTS
from registry.utils.log import logger

def init_redis_connection() -> Redis:
    """
    Initialize Redis connection
    """
    redis_url =  REGISTRY_CONSTANTS.REDIS_URI
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

