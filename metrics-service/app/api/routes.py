import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..api.auth import get_rate_limit_status, verify_api_key
from ..core.models import MetricRequest, MetricResponse
from ..core.processor import MetricsProcessor
from ..core.retention import retention_manager
from ..utils.helpers import generate_request_id

router = APIRouter()
logger = logging.getLogger(__name__)
processor = MetricsProcessor()


@router.post("/metrics", response_model=MetricResponse)
async def collect_metrics(
    metric_request: MetricRequest,
    request: Request,
    response: Response,
    api_key: str = Depends(verify_api_key)
):
    """Collect metrics from MCP components."""
    request_id = generate_request_id()

    try:
        # Add rate limit headers
        if hasattr(request.state, "rate_limit_remaining") and hasattr(request.state, "rate_limit_limit"):
            response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)

        # Process metrics
        result = await processor.process_metrics(metric_request, request_id, api_key)

        logger.info(f"Processed {result.accepted} metrics from {metric_request.service} (request: {request_id})")

        return MetricResponse(
            status="success",
            accepted=result.accepted,
            rejected=result.rejected,
            errors=result.errors,
            request_id=request_id
        )

    except Exception as e:
        logger.error(f"Error processing metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {e!s}"
        )


@router.post("/flush")
async def flush_metrics(
    request: Request,
    response: Response,
    api_key: str = Depends(verify_api_key)
):
    """Force flush buffered metrics to storage."""
    try:
        # Add rate limit headers
        if hasattr(request.state, "rate_limit_remaining") and hasattr(request.state, "rate_limit_limit"):
            response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)

        await processor.force_flush()
        return {"status": "success", "message": "Metrics flushed to storage"}
    except Exception as e:
        logger.error(f"Error flushing metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to flush metrics: {e!s}"
        )


@router.get("/rate-limit")
async def get_rate_limit(request: Request):
    """Get current rate limit status for the API key."""
    api_key = request.headers.get("X-API-Key")

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required in X-API-Key header"
        )

    try:
        status = await get_rate_limit_status(api_key)
        return status
    except Exception as e:
        logger.error(f"Error getting rate limit status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get rate limit status: {e!s}"
        )


@router.get("/admin/retention/preview")
async def get_cleanup_preview(
    table_name: str | None = None,
    api_key: str = Depends(verify_api_key)
):
    """Preview what would be cleaned up by retention policies."""
    try:
        preview = await retention_manager.get_cleanup_preview(table_name)
        return preview
    except Exception as e:
        logger.error(f"Error getting cleanup preview: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cleanup preview: {e!s}"
        )


@router.post("/admin/retention/cleanup")
async def run_cleanup(
    table_name: str | None = None,
    dry_run: bool = True,
    api_key: str = Depends(verify_api_key)
):
    """Run data cleanup according to retention policies."""
    try:
        if table_name:
            result = await retention_manager.cleanup_table(table_name, dry_run)
        else:
            result = await retention_manager.cleanup_all_tables(dry_run)
        return result
    except Exception as e:
        logger.error(f"Error running cleanup: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run cleanup: {e!s}"
        )


@router.get("/admin/retention/policies")
async def get_retention_policies(api_key: str = Depends(verify_api_key)):
    """Get current retention policies."""
    try:
        policies = {}
        for name, policy in retention_manager.policies.items():
            policies[name] = {
                "table_name": policy.table_name,
                "retention_days": policy.retention_days,
                "is_active": policy.is_active,
                "timestamp_column": policy.timestamp_column
            }
        return policies
    except Exception as e:
        logger.error(f"Error getting retention policies: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get retention policies: {e!s}"
        )


@router.put("/admin/retention/policies/{table_name}")
async def update_retention_policy(
    table_name: str,
    retention_days: int,
    is_active: bool = True,
    api_key: str = Depends(verify_api_key)
):
    """Update retention policy for a table."""
    try:
        await retention_manager.update_policy(table_name, retention_days, is_active)
        return {
            "status": "success",
            "message": f"Updated retention policy for {table_name}",
            "table_name": table_name,
            "retention_days": retention_days,
            "is_active": is_active
        }
    except Exception as e:
        logger.error(f"Error updating retention policy: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update retention policy: {e!s}"
        )


@router.get("/admin/database/stats")
async def get_database_stats(api_key: str = Depends(verify_api_key)):
    """Get database table statistics."""
    try:
        stats = await retention_manager.get_table_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get database stats: {e!s}"
        )


@router.get("/admin/database/size")
async def get_database_size(api_key: str = Depends(verify_api_key)):
    """Get database size information."""
    try:
        size_info = await retention_manager.get_database_size()
        return size_info
    except Exception as e:
        logger.error(f"Error getting database size: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get database size: {e!s}"
        )
