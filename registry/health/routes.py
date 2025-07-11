import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from .service import health_service
from ..core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize session signer for WebSocket authentication
signer = URLSafeTimedSerializer(settings.secret_key)


@router.websocket("/ws/health_status")
async def websocket_endpoint(websocket: WebSocket):
    """High-performance WebSocket endpoint for real-time health status updates with authentication."""
    connection_added = False
    try:
        # WebSocket cookies are automatically included in handshake
        # Validate session before accepting connection
        session_cookie = None
        
        # Debug: Log WebSocket connection attempt
        logger.info(f"WebSocket connection attempt from {websocket.client}")
        
        # Try different ways to access cookies from WebSocket
        if hasattr(websocket, 'cookies') and websocket.cookies:
            session_cookie = websocket.cookies.get(settings.session_cookie_name)
            logger.debug(f"WebSocket cookies found via websocket.cookies: {list(websocket.cookies.keys())}")
        
        # Alternative: Try to get cookies from headers
        if not session_cookie and hasattr(websocket, 'headers'):
            cookie_header = websocket.headers.get('cookie', '')
            if cookie_header:
                logger.debug(f"WebSocket cookie header: {cookie_header}")
                # Parse cookie header manually
                cookies = {}
                for cookie_pair in cookie_header.split(';'):
                    if '=' in cookie_pair:
                        name, value = cookie_pair.strip().split('=', 1)
                        cookies[name] = value
                session_cookie = cookies.get(settings.session_cookie_name)
        
        # Alternative: Try to get from query parameters as fallback
        if not session_cookie and hasattr(websocket, 'query_params'):
            session_cookie = websocket.query_params.get(settings.session_cookie_name)
        
        logger.debug(f"WebSocket session cookie found: {bool(session_cookie)}")
        
        if session_cookie:
            try:
                # Validate session
                session_data = signer.loads(
                    session_cookie, 
                    max_age=settings.session_max_age_seconds
                )
                username = session_data.get('username')
                if username:
                    logger.info(f"WebSocket connection from authenticated user: {username}")
                else:
                    raise ValueError("No username in session")
            except (SignatureExpired, BadSignature, ValueError) as e:
                logger.warning(f"WebSocket authentication failed: {e}")
                await websocket.close(code=1008, reason="Authentication failed")
                return
            except Exception as e:
                logger.warning(f"WebSocket authentication error: {e}")
                await websocket.close(code=1008, reason="Authentication failed")
                return
        else:
            logger.warning(f"WebSocket connection without valid session cookie from {websocket.client}")
            await websocket.close(code=1008, reason="Authentication required")
            return
            
        # Accept connection after successful authentication
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