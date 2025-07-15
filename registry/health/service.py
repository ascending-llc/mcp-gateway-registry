import json
import asyncio
import logging
import httpx
from datetime import datetime, timezone
from typing import Dict, Set, Optional, Tuple
from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict, deque
from time import time

from ..core.config import settings

logger = logging.getLogger(__name__)


class HighPerformanceWebSocketManager:
    """High-performance WebSocket manager for 400-1000+ concurrent connections."""
    
    def __init__(self):
        self.connections: Set[WebSocket] = set()
        self.connection_metadata: Dict[WebSocket, Dict] = {}
        
        # Rate limiting and batching
        self.pending_updates: Dict[str, Dict] = {}  # service_path -> latest_data
        self.last_broadcast_time = 0
        self.min_broadcast_interval = settings.websocket_broadcast_interval_ms / 1000.0
        self.max_batch_size = settings.websocket_max_batch_size
        
        # Connection health tracking
        self.failed_connections: Set[WebSocket] = set()
        self.cleanup_task: Optional[asyncio.Task] = None
        
        # Performance metrics
        self.broadcast_count = 0
        self.failed_send_count = 0
        
    async def add_connection(self, websocket: WebSocket) -> bool:
        """Add a new WebSocket connection with connection limits."""
        try:
            # Connection limit for memory management
            if len(self.connections) >= settings.max_websocket_connections:
                logger.warning(f"Connection limit reached: {len(self.connections)}")
                await websocket.close(code=1008, reason="Server at capacity")
                return False
                
            await websocket.accept()
            self.connections.add(websocket)
            self.connection_metadata[websocket] = {
                "connected_at": time(),
                "last_ping": time(),
                "client_ip": getattr(websocket.client, 'host', 'unknown') if websocket.client else 'unknown'
            }
            
            logger.debug(f"WebSocket connected: {len(self.connections)} total connections")
            
            # Send initial status efficiently
            await self._send_initial_status_optimized(websocket)
            return True
            
        except Exception as e:
            logger.error(f"Error adding WebSocket connection: {e}")
            return False
    
    async def remove_connection(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.connections.discard(websocket)
        self.connection_metadata.pop(websocket, None)
        self.failed_connections.discard(websocket)
        
        logger.debug(f"WebSocket disconnected: {len(self.connections)} total connections")
    
    async def _send_initial_status_optimized(self, websocket: WebSocket):
        """Send initial status using cached data to avoid blocking."""
        try:
            # Use cached health data to avoid blocking on service calls
            cached_data = health_service._get_cached_health_data()
            if cached_data:
                await websocket.send_text(json.dumps(cached_data))
        except Exception as e:
            logger.warning(f"Failed to send initial status: {e}")
            await self.remove_connection(websocket)
    
    async def broadcast_update(self, service_path: Optional[str] = None, health_data: Optional[Dict] = None):
        """High-performance broadcasting with batching and rate limiting."""
        if not self.connections:
            return
            
        current_time = time()
        
        # Rate limiting: prevent too frequent broadcasts
        if current_time - self.last_broadcast_time < self.min_broadcast_interval:
            # Queue the update for later batch processing
            if service_path and health_data:
                self.pending_updates[service_path] = health_data
            return
        
        # Prepare broadcast data
        if service_path and health_data:
            # Single service update
            broadcast_data = {service_path: health_data}
        else:
            # Batch updates or full status
            if self.pending_updates:
                # Send pending updates in batches
                batch_data = dict(list(self.pending_updates.items())[:self.max_batch_size])
                broadcast_data = batch_data
                # Remove sent items from pending
                for key in batch_data.keys():
                    self.pending_updates.pop(key, None)
            else:
                # Full status update (avoid this when possible)
                broadcast_data = health_service._get_cached_health_data()
        
        if broadcast_data:
            await self._send_to_connections_optimized(broadcast_data)
            self.last_broadcast_time = current_time
    
    async def _send_to_connections_optimized(self, data: Dict):
        """Optimized concurrent sending with automatic cleanup."""
        if not self.connections:
            return
            
        message = json.dumps(data)
        connections_list = list(self.connections)  # Snapshot for safe iteration
        
        # Split into chunks for better memory management with many connections
        chunk_size = 100  # Process 100 connections at a time
        
        for i in range(0, len(connections_list), chunk_size):
            chunk = connections_list[i:i + chunk_size]
            
            # Send to chunk concurrently
            tasks = [self._safe_send_message(conn, message) for conn in chunk]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Track failed connections
            for conn, result in zip(chunk, results):
                if isinstance(result, Exception):
                    self.failed_connections.add(conn)
                    self.failed_send_count += 1
        
        # Cleanup failed connections in batch (non-blocking)
        if self.failed_connections:
            asyncio.create_task(self._cleanup_failed_connections())
            
        self.broadcast_count += 1
    
    async def _safe_send_message(self, connection: WebSocket, message: str):
        """Send message with timeout and error handling."""
        try:
            # Use timeout to prevent hanging on slow connections
            await asyncio.wait_for(connection.send_text(message), timeout=settings.websocket_send_timeout_seconds)
            return True
        except asyncio.TimeoutError:
            return TimeoutError("Send timeout")
        except Exception as e:
            return e
    
    async def _cleanup_failed_connections(self):
        """Cleanup failed connections without blocking main operations."""
        failed_count = len(self.failed_connections)
        if failed_count == 0:
            return
            
        for conn in list(self.failed_connections):
            await self.remove_connection(conn)
            
        logger.info(f"Cleaned up {failed_count} failed WebSocket connections")
    
    def get_stats(self) -> Dict:
        """Get performance statistics."""
        return {
            "active_connections": len(self.connections),
            "pending_updates": len(self.pending_updates),
            "total_broadcasts": self.broadcast_count,
            "failed_sends": self.failed_send_count,
            "failed_connections": len(self.failed_connections)
        }


class HealthMonitoringService:
    """Optimized health monitoring service for high-scale WebSocket operations."""
    
    def __init__(self):
        self.server_health_status: Dict[str, str] = {}
        self.server_last_check_time: Dict[str, datetime] = {}
        
        # High-performance WebSocket manager
        self.websocket_manager = HighPerformanceWebSocketManager()
        
        # Background task management
        self.health_check_task: Optional[asyncio.Task] = None
        
        # Performance optimizations
        self._cached_health_data: Dict = {}
        self._cache_timestamp = 0
        self._cache_ttl = settings.websocket_cache_ttl_seconds
        
    async def initialize(self):
        """Initialize the health monitoring service."""
        logger.info("Initializing health monitoring service...")
        
        # Start background health checks
        self.health_check_task = asyncio.create_task(self._run_health_checks())
        
        logger.info("Health monitoring service initialized!")
        
    async def shutdown(self):
        """Shutdown the health monitoring service."""
        # Cancel background tasks
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
        
        # Close all WebSocket connections
        connections = list(self.websocket_manager.connections)
        close_tasks = []
        for conn in connections:
            try:
                close_tasks.append(conn.close())
            except Exception:
                pass
                
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
            
        logger.info("Health monitoring service shutdown complete")
        
    async def add_websocket_connection(self, websocket: WebSocket):
        """Add a new WebSocket connection and send initial health status."""
        success = await self.websocket_manager.add_connection(websocket)
        if success:
            logger.info(f"WebSocket client connected: {websocket.client}")
        return success
        
    async def remove_websocket_connection(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        await self.websocket_manager.remove_connection(websocket)
        logger.info(f"WebSocket connection removed: {websocket.client}")
        
    async def _send_initial_status(self, websocket: WebSocket):
        """Send initial health status to a newly connected WebSocket client."""
        # This method is kept for compatibility but delegates to the optimized manager
        await self.websocket_manager._send_initial_status_optimized(websocket)
            
    async def broadcast_health_update(self, service_path: Optional[str] = None):
        """Broadcast health status updates to all connected WebSocket clients."""
        if not self.websocket_manager.connections:
            return
            
        from ..services.server_service import server_service
        
        if service_path:
            # Single service update - get data efficiently
            server_info = server_service.get_server_info(service_path)
            if server_info:
                health_data = self._get_service_health_data_fast(service_path, server_info)
                await self.websocket_manager.broadcast_update(service_path, health_data)
        else:
            # Full update - use cached data
            await self.websocket_manager.broadcast_update()
            
    def _get_cached_health_data(self) -> Dict:
        """Get cached health data to avoid expensive operations during WebSocket sends."""
        current_time = time()
        
        # Return cached data if still valid
        if (current_time - self._cache_timestamp) < self._cache_ttl and self._cached_health_data:
            return self._cached_health_data
            
        # Rebuild cache
        from ..services.server_service import server_service
        all_servers = server_service.get_all_servers()
        
        data = {}
        for path, server_info in all_servers.items():
            data[path] = self._get_service_health_data_fast(path, server_info)
        
        self._cached_health_data = data
        self._cache_timestamp = current_time
        return data
        
    def get_websocket_stats(self) -> Dict:
        """Get WebSocket performance statistics."""
        return self.websocket_manager.get_stats()

    async def _run_health_checks(self):
        """Background task to run periodic health checks."""
        logger.info("Starting periodic health checks...")
        
        while True:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(settings.health_check_interval_seconds)
            except asyncio.CancelledError:
                logger.info("Health check task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a minute before retrying
                
    async def _perform_health_checks(self):
        """Perform health checks on all enabled services."""
        from ..services.server_service import server_service
        import httpx
        
        enabled_services = server_service.get_enabled_services()
        if not enabled_services:
            return
            
        # Only log if there are many services to avoid spam
        if len(enabled_services) > 1:
            logger.debug(f"Performing health checks on {len(enabled_services)} enabled services")
        
        # Track if any status changed to minimize broadcasts
        status_changed = False
        
        # Perform actual health checks concurrently for better performance
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.health_check_timeout_seconds)) as client:
            # Batch process enabled services
            check_tasks = []
            for service_path in enabled_services:
                server_info = server_service.get_server_info(service_path)
                if server_info and server_info.get("proxy_pass_url"):
                    check_tasks.append(self._check_single_service(client, service_path, server_info))
            
            # Execute all health checks concurrently
            if check_tasks:
                results = await asyncio.gather(*check_tasks, return_exceptions=True)
                
                # Check if any status changed
                for result in results:
                    if isinstance(result, bool) and result:  # True indicates status changed
                        status_changed = True
                        break
            
        # Only broadcast if something actually changed
        if status_changed:
            await self.broadcast_health_update()
            
            # Regenerate nginx configuration when health status changes
            try:
                from ..core.nginx_service import nginx_service
                enabled_servers = {
                    path: server_service.get_server_info(path) 
                    for path in server_service.get_enabled_services()
                }
                await nginx_service.generate_config_async(enabled_servers)
                logger.info("Nginx configuration regenerated due to health status changes")
            except Exception as e:
                logger.error(f"Failed to regenerate nginx configuration after health status change: {e}")
            
    async def _check_single_service(self, client: httpx.AsyncClient, service_path: str, server_info: Dict) -> bool:
        """Check a single service and return True if status changed."""
        from ..services.server_service import server_service
        
        proxy_pass_url = server_info.get("proxy_pass_url")
        previous_status = self.server_health_status.get(service_path, "unknown")
        new_status = previous_status
        
        try:
            # Try to reach the service endpoint using transport-aware checking
            success = await self._check_server_endpoint_transport_aware(client, proxy_pass_url, server_info)
            
            if success:
                new_status = "healthy"
                
                # If service transitioned to healthy, fetch tool list (but don't block)
                if previous_status != "healthy":
                    asyncio.create_task(self._update_tools_background(service_path, proxy_pass_url))
            else:
                new_status = "unhealthy: endpoint check failed"
                
        except httpx.TimeoutException:
            new_status = "unhealthy: timeout"
        except httpx.ConnectError:
            new_status = "unhealthy: connection failed"
        except Exception as e:
            new_status = f"error: {type(e).__name__}"
        
        # Update status and timestamp
        self.server_health_status[service_path] = new_status
        self.server_last_check_time[service_path] = datetime.now(timezone.utc)
        
        # Return True if status changed
        return previous_status != new_status


    async def _check_server_endpoint_transport_aware(self, client: httpx.AsyncClient, proxy_pass_url: str, server_info: Dict) -> bool:
        """Check server endpoint using transport-aware logic."""
        if not proxy_pass_url:
            return False
            
        # Get transport information from server_info
        supported_transports = server_info.get("supported_transports", ["streamable-http"])
        
        # If URL already has transport endpoint, use it directly
        if proxy_pass_url.endswith('/mcp') or proxy_pass_url.endswith('/sse') or '/mcp/' in proxy_pass_url or '/sse/' in proxy_pass_url:
            logger.info(f"[TRACE] Found transport endpoint in URL: {proxy_pass_url}")
            logger.info(f"[TRACE] URL contains /mcp: {'/mcp' in proxy_pass_url}, URL contains /sse: {'/sse' in proxy_pass_url}")
            try:
                # Use GET with proper headers for MCP endpoints
                headers = {
                    'Accept': 'text/event-stream',
                    'Content-Type': 'application/json'
                }
                # For SSE endpoints, use a shorter timeout since they start streaming immediately
                if proxy_pass_url.endswith('/sse') or '/sse/' in proxy_pass_url:
                    logger.info(f"[TRACE] Detected SSE endpoint in URL, using SSE-specific handling")
                    timeout = httpx.Timeout(connect=5.0, read=2.0, write=5.0, pool=5.0)
                    try:
                        response = await client.get(proxy_pass_url, headers=headers, follow_redirects=True, timeout=timeout)
                        return self._is_mcp_endpoint_healthy(response)
                    except (httpx.TimeoutException, asyncio.TimeoutError) as e:
                        # For SSE endpoints, timeout while reading streaming response is normal after getting 200 OK
                        logger.debug(f"SSE endpoint {proxy_pass_url} timed out while streaming (expected): {e}")
                        # If we can extract status code from response, check if it was 200
                        if hasattr(e, 'response') and e.response and e.response.status_code == 200:
                            logger.debug(f"SSE endpoint {proxy_pass_url} returned 200 OK before timeout - considering healthy")
                            return True
                        # For SSE, timeout after initial connection usually means server is responding
                        return True
                    except Exception as e:
                        logger.warning(f"SSE endpoint {proxy_pass_url} failed with exception: {type(e).__name__} - {e}")
                        return False
                else:
                    logger.info(f"[TRACE] Detected MCP endpoint in URL, using standard HTTP handling")
                    response = await client.get(proxy_pass_url, headers=headers, follow_redirects=True)
                    return self._is_mcp_endpoint_healthy(response)
            except Exception as e:
                logger.warning(f"Health check failed for {proxy_pass_url}: {type(e).__name__} - {e}")
                return False
        
        # Try endpoints based on supported transports, prioritizing streamable-http
        logger.info(f"[TRACE] No transport endpoint in URL: {proxy_pass_url}")
        logger.info(f"[TRACE] Supported transports: {supported_transports}")
        base_url = proxy_pass_url.rstrip('/')
        
        # Try streamable-http first (default preference)
        if "streamable-http" in supported_transports:
            logger.info(f"[TRACE] Trying streamable-http transport")
            try:
                mcp_endpoint = f"{base_url}/mcp"
                # Use GET with proper headers for MCP endpoints
                headers = {
                    'Accept': 'text/event-stream',
                    'Content-Type': 'application/json'
                }
                response = await client.get(mcp_endpoint, headers=headers, follow_redirects=True)
                if self._is_mcp_endpoint_healthy(response):
                    return True
            except Exception:
                pass
        
        # Fallback to SSE
        if "sse" in supported_transports:
            logger.info(f"[TRACE] Trying SSE transport")
            try:
                sse_endpoint = f"{base_url}/sse"
                # Use GET with proper headers for MCP endpoints
                headers = {
                    'Accept': 'text/event-stream',
                    'Content-Type': 'application/json'
                }
                # Use shorter timeout for SSE since it starts streaming immediately
                timeout = httpx.Timeout(connect=5.0, read=2.0, write=5.0, pool=5.0)
                response = await client.get(sse_endpoint, headers=headers, follow_redirects=True, timeout=timeout)
                if self._is_mcp_endpoint_healthy(response):
                    return True
            except (httpx.TimeoutException, asyncio.TimeoutError) as e:
                # For SSE endpoints, timeout while reading streaming response is normal after getting 200 OK
                logger.info(f"SSE endpoint {sse_endpoint} timed out while streaming (expected): {e}")
                # If we can extract status code from response, check if it was 200
                if hasattr(e, 'response') and e.response and e.response.status_code == 200:
                    logger.info(f"SSE endpoint {sse_endpoint} returned 200 OK before timeout - considering healthy")
                    return True
                # For SSE, timeout after initial connection usually means server is responding
                return True
            except Exception as e:
                logger.error(f"SSE endpoint {sse_endpoint} failed with exception: {type(e).__name__} - {e}")
                pass
        
        # If no specific transports, try default streamable-http then sse
        if not supported_transports or supported_transports == []:
            logger.info(f"[TRACE] No specific transports defined, trying defaults")
            try:
                mcp_endpoint = f"{base_url}/mcp"
                # Use GET with proper headers for MCP endpoints
                headers = {
                    'Accept': 'text/event-stream',
                    'Content-Type': 'application/json'
                }
                response = await client.get(mcp_endpoint, headers=headers, follow_redirects=True)
                if self._is_mcp_endpoint_healthy(response):
                    return True
            except Exception:
                pass
                
            try:
                sse_endpoint = f"{base_url}/sse"
                # Use GET with proper headers for MCP endpoints
                headers = {
                    'Accept': 'text/event-stream',
                    'Content-Type': 'application/json'
                }
                # Use shorter timeout for SSE since it starts streaming immediately
                timeout = httpx.Timeout(connect=5.0, read=2.0, write=5.0, pool=5.0)
                response = await client.get(sse_endpoint, headers=headers, follow_redirects=True, timeout=timeout)
                if self._is_mcp_endpoint_healthy(response):
                    return True
            except (httpx.TimeoutException, asyncio.TimeoutError) as e:
                # For SSE endpoints, timeout while reading streaming response is normal after getting 200 OK
                logger.info(f"SSE endpoint {sse_endpoint} timed out while streaming (expected): {e}")
                # If we can extract status code from response, check if it was 200
                if hasattr(e, 'response') and e.response and e.response.status_code == 200:
                    logger.info(f"SSE endpoint {sse_endpoint} returned 200 OK before timeout - considering healthy")
                    return True
                # For SSE, timeout after initial connection usually means server is responding
                return True
            except Exception as e:
                logger.error(f"SSE endpoint {sse_endpoint} failed with exception: {type(e).__name__} - {e}")
                pass
        
        return False


    def _is_mcp_endpoint_healthy(self, response) -> bool:
        """
        Determine if an MCP endpoint is healthy based on HTTP response.
        
        For MCP endpoints, we consider them healthy if:
        1. HTTP 200 OK - Normal successful response
        2. HTTP 400 Bad Request with specific JSON-RPC error indicating missing session ID
        
        The 400 status with "Missing session ID" error is considered healthy because:
        - It proves the MCP endpoint is reachable and functioning
        - The server is properly validating requests according to MCP protocol
        - It's rejecting our basic GET request because we're not providing a session ID
        - This is expected behavior for a working MCP server when accessed without proper session
        
        Args:
            response: httpx.Response object from the health check request
            
        Returns:
            bool: True if the endpoint is considered healthy, False otherwise
        """
        # HTTP 200 is always healthy
        if response.status_code == 200:
            return True
            
        # HTTP 400 is healthy only if it's the expected MCP session error
        if response.status_code == 400:
            try:
                # Parse the JSON response
                response_data = response.json()
                
                # Check for the specific JSON-RPC error indicating missing session ID
                # This is the expected response from a healthy MCP endpoint when accessed without session
                if (response_data.get("jsonrpc") == "2.0" and 
                    response_data.get("id") == "server-error" and 
                    isinstance(response_data.get("error"), dict)):
                    
                    error = response_data["error"]
                    if (error.get("code") == -32600 and 
                        "Missing session ID" in error.get("message", "")):
                        return True
                        
            except (ValueError, KeyError, TypeError):
                # If we can't parse JSON or the structure is wrong, treat as unhealthy
                pass
                
        # All other status codes (404, 500, etc.) are considered unhealthy
        return False

        
    async def _update_tools_background(self, service_path: str, proxy_pass_url: str):
        """Update tool list in the background without blocking health checks."""
        try:
            from ..core.mcp_client import mcp_client_service
            from ..services.server_service import server_service
            
            # Get server info to pass transport configuration
            server_info = server_service.get_server_info(service_path)
            tool_list = await mcp_client_service.get_tools_from_server_with_server_info(proxy_pass_url, server_info)
            
            if tool_list is not None:
                new_tool_count = len(tool_list)
                current_server_info = server_service.get_server_info(service_path)
                if current_server_info:
                    current_tool_count = current_server_info.get("num_tools", 0)
                    
                    if current_tool_count != new_tool_count:
                        updated_server_info = current_server_info.copy()
                        updated_server_info["tool_list"] = tool_list
                        updated_server_info["num_tools"] = new_tool_count
                        
                        server_service.update_server(service_path, updated_server_info)
                        
                        # Broadcast only this specific service update
                        await self.broadcast_health_update(service_path)
                        
        except Exception as e:
            logger.warning(f"Failed to fetch tools for {service_path}: {e}")
        
    def get_all_health_status(self) -> Dict:
        """Get health status for all services."""
        from ..services.server_service import server_service
        
        all_servers = server_service.get_all_servers()
        
        data = {}
        for path, server_info in all_servers.items():
            data[path] = self._get_service_health_data_fast(path, server_info)
        
        return data

    async def perform_immediate_health_check(self, service_path: str) -> tuple[str, datetime | None]:
        """Perform an immediate health check for a single service."""
        from ..services.server_service import server_service
        import httpx
        
        server_info = server_service.get_server_info(service_path)
        if not server_info:
            return "error: server not registered", None

        proxy_pass_url = server_info.get("proxy_pass_url")
        
        # Record check time
        last_checked_time = datetime.now(timezone.utc)
        self.server_last_check_time[service_path] = last_checked_time

        if not proxy_pass_url:
            current_status = "error: missing proxy URL"
            self.server_health_status[service_path] = current_status
            logger.info(f"Health check skipped for {service_path}: Missing URL.")
            return current_status, last_checked_time

        # Set status to 'checking' before performing the check
        logger.info(f"Setting status to 'checking' for {service_path} ({proxy_pass_url})...")
        previous_status = self.server_health_status.get(service_path, "unknown")
        self.server_health_status[service_path] = "checking"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(settings.health_check_timeout_seconds)) as client:
                # Use transport-aware endpoint checking
                success = await self._check_server_endpoint_transport_aware(client, proxy_pass_url, server_info)
                
                if success:
                    current_status = "healthy"
                    logger.info(f"Health check successful for {service_path} ({proxy_pass_url}).")
                    
                    # Schedule tool list fetch in background (don't block the response)
                    asyncio.create_task(self._update_tools_background(service_path, proxy_pass_url))
                        
                else:
                    current_status = "unhealthy: endpoint check failed"
                    logger.info(f"Health check failed for {service_path} ({proxy_pass_url}).")
                    
        except httpx.TimeoutException:
            current_status = "unhealthy: timeout"
            logger.info(f"Health check timeout for {service_path}")
        except httpx.ConnectError:
            current_status = "error: connection failed"
            logger.info(f"Health check connection failed for {service_path}")
        except Exception as e:
            current_status = f"error: {type(e).__name__}"
            logger.error(f"ERROR: Unexpected error during health check for {service_path}: {e}")

        # Update the status
        self.server_health_status[service_path] = current_status
        logger.info(f"Final health status for {service_path}: {current_status}")

        # Regenerate nginx configuration if status changed
        if previous_status != current_status:
            try:
                from ..core.nginx_service import nginx_service
                enabled_servers = {
                    path: server_service.get_server_info(path) 
                    for path in server_service.get_enabled_services()
                }
                await nginx_service.generate_config_async(enabled_servers)
                logger.info(f"Nginx configuration regenerated due to status change for {service_path}: {previous_status} -> {current_status}")
            except Exception as e:
                logger.error(f"Failed to regenerate nginx configuration after immediate health check: {e}")

        return current_status, last_checked_time

    def _get_service_health_data(self, service_path: str) -> Dict:
        """Get health data for a specific service - legacy method, use _get_service_health_data_fast for better performance."""
        from ..services.server_service import server_service
        server_info = server_service.get_server_info(service_path)
        return self._get_service_health_data_fast(service_path, server_info or {})
        
    def _get_service_health_data_fast(self, service_path: str, server_info: Dict) -> Dict:
        """Get health data for a specific service - optimized version."""
        from ..services.server_service import server_service
        
        # Quick enabled check using cached server_info if possible
        is_enabled = server_service.is_service_enabled(service_path)
        
        if not is_enabled:
            status = "disabled"
            self.server_health_status[service_path] = "disabled"
        else:
            # Use cached status, only update if transitioning from disabled
            cached_status = self.server_health_status.get(service_path, "unknown")
            if cached_status == "disabled":
                status = "checking"
                self.server_health_status[service_path] = "checking"
            else:
                status = cached_status
        
        # Use pre-fetched server_info instead of calling get_server_info again
        last_checked_dt = self.server_last_check_time.get(service_path)
        last_checked_iso = last_checked_dt.isoformat() if last_checked_dt else None
        num_tools = server_info.get("num_tools", 0) if server_info else 0
        
        return {
            "status": status,
            "last_checked_iso": last_checked_iso,
            "num_tools": num_tools
        }


# Global health monitoring service instance
health_service = HealthMonitoringService() 