import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .service import health_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/health_status")
async def websocket_endpoint(websocket: WebSocket):
    """High-performance WebSocket endpoint for real-time health status updates."""
    connection_added = False
    try:
        connection_added = await health_service.add_websocket_connection(websocket)
        if not connection_added:
            return  # Connection rejected (server at capacity)
        
        # Keep connection open and handle client messages
        while True:
            # We don't expect messages from client, but keep alive
            # Add timeout to prevent hanging on slow clients
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.ping()
            
    except WebSocketDisconnect:
        logger.debug(f"WebSocket client disconnected: {websocket.client}")
    except Exception as e:
        logger.warning(f"WebSocket error for {websocket.client}: {e}")
    finally:
        if connection_added:
            await health_service.remove_websocket_connection(websocket)


@router.get("/ws/health_status")
async def health_status_http():
    """HTTP endpoint that returns the same health status data as the WebSocket endpoint.
    
    This handles cases where health checks are done via HTTP GET instead of WebSocket.
    """
    return health_service.get_all_health_status()


@router.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket performance statistics for monitoring."""
    return health_service.get_websocket_stats() 