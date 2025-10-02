from fastapi import FastAPI, HTTPException, Depends
from contextlib import asynccontextmanager
import logging
import asyncio
from .config import settings
from .api.routes import router as api_router
from .storage.database import init_database, wait_for_database, MetricsStorage
from .core.rate_limiter import rate_limiter
from .core.retention import retention_manager
from .utils.helpers import hash_api_key
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Starting Metrics Collection Service...")
    
    # Wait for database container to be ready
    logger.info("Waiting for database container...")
    await wait_for_database()
    logger.info("Database container is ready")
    
    # Initialize database
    await init_database()
    logger.info("Database initialized")
    
    # Setup pre-shared API keys from environment variables
    await setup_preshared_api_keys()
    logger.info("Pre-shared API keys configured")
    
    # Load retention policies from database
    try:
        await retention_manager.load_policies_from_database()
        logger.info("Retention policies loaded")
    except Exception as e:
        logger.warning(f"Failed to load retention policies: {e}, using defaults")
    
    # Setup OpenTelemetry (optional, continue if it fails)
    try:
        from .otel.exporters import setup_otel
        setup_otel()
        logger.info("OpenTelemetry configured")
    except Exception as e:
        logger.warning(f"OpenTelemetry setup skipped: {e}")
    
    # Start background tasks
    cleanup_task = asyncio.create_task(rate_limit_cleanup_task())
    retention_task = asyncio.create_task(retention_cleanup_task())
    flush_task = asyncio.create_task(metrics_flush_task())
    logger.info("Background tasks started")
    
    yield
    
    # Cancel background tasks
    cleanup_task.cancel()
    retention_task.cancel()
    flush_task.cancel()
    try:
        await cleanup_task
        await retention_task
        await flush_task
    except asyncio.CancelledError:
        pass
    
    logger.info("Shutting down Metrics Collection Service")


async def rate_limit_cleanup_task():
    """Background task to clean up old rate limit buckets."""
    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            await rate_limiter.cleanup_old_buckets(max_age_hours=24)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in rate limit cleanup task: {e}")
            await asyncio.sleep(60)  # Wait a minute before retry


async def retention_cleanup_task():
    """Background task to run data retention cleanup."""
    while True:
        try:
            await asyncio.sleep(86400)  # Run once per day (24 hours)
            logger.info("Starting scheduled data retention cleanup...")
            result = await retention_manager.cleanup_all_tables(dry_run=False)
            
            total_deleted = result.get('total_records_processed', 0)
            duration = result.get('duration_seconds', 0)
            
            if total_deleted > 0:
                logger.info(f"Retention cleanup completed: {total_deleted} records deleted in {duration:.2f}s")
            else:
                logger.info("Retention cleanup completed: no records to delete")
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in retention cleanup task: {e}")
            await asyncio.sleep(3600)  # Wait an hour before retry


async def metrics_flush_task():
    """Background task to flush metrics buffer every 5 seconds."""
    # Import the shared processor instance from routes
    from .api.routes import processor

    while True:
        try:
            await asyncio.sleep(5)  # Flush every 5 seconds
            await processor.force_flush()
            logger.debug("Metrics buffer flushed to database")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in metrics flush task: {e}")
            await asyncio.sleep(5)  # Wait 5 seconds before retry


async def setup_preshared_api_keys():
    """Setup pre-shared API keys from environment variables dynamically."""
    storage = MetricsStorage()
    
    # Dynamically discover all METRICS_API_KEY_* environment variables
    api_key_count = 0
    for key, value in os.environ.items():
        if key.startswith('METRICS_API_KEY_') and value:
            # Extract service name from environment variable
            # METRICS_API_KEY_AUTH -> auth
            # METRICS_API_KEY_REGISTRY -> registry  
            # METRICS_API_KEY_CURRENTTIME_SERVER -> currenttime-server
            service_suffix = key.replace('METRICS_API_KEY_', '')
            service_name = service_suffix.lower().replace('_', '-')
            
            try:
                key_hash = hash_api_key(value)
                success = await storage.create_api_key(key_hash, service_name, rate_limit=1000)
                if success:
                    logger.info(f"Configured API key for service: {service_name}")
                    api_key_count += 1
                else:
                    logger.debug(f"API key for {service_name} already exists")
                    api_key_count += 1
            except Exception as e:
                logger.error(f"Failed to setup API key for {service_name}: {e}")
    
    if api_key_count == 0:
        logger.warning("No METRICS_API_KEY_* environment variables found")
    else:
        logger.info(f"Configured {api_key_count} API keys from environment variables")


app = FastAPI(
    title="MCP Metrics Collection Service",
    description="Centralized metrics collection for MCP Gateway Registry components",
    version="1.0.0",
    lifespan=lifespan
)

# Include API routes
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "metrics-collection"}


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "MCP Metrics Collection Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "metrics": "/metrics",
            "health": "/health",
            "flush": "/flush",
            "rate-limit": "/rate-limit"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host=settings.METRICS_SERVICE_HOST, 
        port=settings.METRICS_SERVICE_PORT
    )