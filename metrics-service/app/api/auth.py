from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging
from ..storage.database import MetricsStorage
from ..utils.helpers import hash_api_key
from ..core.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)
security = HTTPBearer()


async def verify_api_key(request: Request) -> str:
    """Verify API key from X-API-Key header and check rate limits."""
    api_key = request.headers.get("X-API-Key")
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required in X-API-Key header"
        )
    
    # Hash the provided API key
    key_hash = hash_api_key(api_key)
    
    # Verify against database
    storage = MetricsStorage()
    key_info = await storage.get_api_key(key_hash)
    
    if not key_info:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    if not key_info['is_active']:
        raise HTTPException(
            status_code=401,
            detail="API key is inactive"
        )
    
    # Check rate limit
    rate_limit = key_info.get('rate_limit', 1000)
    allowed, remaining = await rate_limiter.check_rate_limit(key_hash, rate_limit)
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Limit: {rate_limit} requests/minute",
            headers={
                "X-RateLimit-Limit": str(rate_limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After": "60"
            }
        )
    
    # Update last used timestamp
    await storage.update_api_key_usage(key_hash)
    
    # Add rate limit headers
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_limit = rate_limit
    
    logger.debug(f"API key verified for service: {key_info['service_name']}, remaining: {remaining}")
    return key_info['service_name']


async def get_rate_limit_status(api_key: str) -> dict:
    """Get current rate limit status for an API key."""
    key_hash = hash_api_key(api_key)
    
    # Get key info from database
    storage = MetricsStorage()
    key_info = await storage.get_api_key(key_hash)
    
    if not key_info:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    rate_limit = key_info.get('rate_limit', 1000)
    status = await rate_limiter.get_bucket_status(key_hash, rate_limit)
    
    return {
        "service": key_info['service_name'],
        "rate_limit": status["rate_limit"],
        "available_tokens": status["available_tokens"],
        "reset_time_seconds": status["reset_time_seconds"]
    }