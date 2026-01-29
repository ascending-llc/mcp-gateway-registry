"""
Centralized telemetry decorators for the Registry service.

This module provides specialized decorators that use the registry-specific
domain functions to track operations with minimal code changes.

All decorators use time.perf_counter() for accurate timing and handle
exceptions gracefully without affecting business logic.
"""

import time
from functools import wraps
from typing import (
    Any,
    Callable,
    Optional,
    TypeVar,
)
import logging

from registry.utils.otel_metrics import (
    record_auth_request as _record_auth_request,
    record_registry_operation as _record_registry_operation,
    record_tool_discovery as _record_tool_discovery,
    record_tool_execution as _record_tool_execution,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def track_registry_operation(
    operation: str,
    resource_type: Optional[str] = None,
    extract_resource: Optional[Callable[..., str]] = None,
) -> Callable[[F], F]:
    """
    Universal decorator for tracking registry API operations.

    Automatically tracks operation duration, success/failure, and records
    metrics using the registry metrics client.

    Args:
        operation: Type of operation (e.g., "search", "create", "update", "delete", "read", "list")
        resource_type: Static resource type (e.g., "server", "tool", "agent")
        extract_resource: Optional function to dynamically extract resource type from args/kwargs

    Returns:
        Decorated function that tracks the operation

    Example:
        @router.get("/servers")
        @track_registry_operation("list", resource_type="server")
        async def list_servers():
            ...

        @router.post("/search")
        @track_registry_operation("search", extract_resource=lambda q, **kw: q.type)
        async def search(query: SearchQuery):
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            success = False

            # Extract resource name dynamically if function provided
            resource = resource_type
            if extract_resource:
                try:
                    resource = extract_resource(*args, **kwargs)
                except Exception:
                    resource = "unknown"

            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception:
                raise
            finally:
                duration = time.perf_counter() - start_time
                try:
                    _record_registry_operation(
                        operation=operation,
                        resource_type=resource or func.__name__,
                        success=success,
                        duration_seconds=duration,
                    )
                except Exception as e:
                    logger.warning(f"Failed to record operation metric: {e}")

        return wrapper  # type: ignore

    return decorator


def track_auth_request(
    extract_mechanism: Optional[Callable[..., str]] = None,
    default_mechanism: str = "unknown",
) -> Callable[[F], F]:
    """
    Decorator for tracking authentication requests.

    Automatically tracks auth duration and success/failure rates.

    Args:
        extract_mechanism: Optional function to extract auth mechanism from context
        default_mechanism: Default mechanism name if extraction fails

    Returns:
        Decorated function that tracks authentication

    Example:
        @track_auth_request(default_mechanism="jwt")
        async def authenticate_jwt(request: Request):
            ...

        @track_auth_request(extract_mechanism=lambda ctx: ctx.get('auth_source', 'unknown'))
        async def authenticate(request: Request):
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            success = False
            mechanism = default_mechanism

            try:
                result = await func(*args, **kwargs)
                success = True

                # Try to extract mechanism from result if it's a dict
                if extract_mechanism:
                    try:
                        mechanism = extract_mechanism(result)
                    except Exception:
                        pass
                elif isinstance(result, dict):
                    mechanism = result.get("auth_source", default_mechanism)

                return result
            except Exception:
                raise
            finally:
                duration = time.perf_counter() - start_time
                try:
                    _record_auth_request(
                        mechanism=mechanism,
                        success=success,
                        duration_seconds=duration,
                    )
                except Exception as e:
                    logger.warning(f"Failed to record auth metric: {e}")

        return wrapper  # type: ignore

    return decorator


def track_tool_execution(
    extract_tool_info: Optional[Callable[..., dict]] = None,
) -> Callable[[F], F]:
    """
    Decorator for tracking MCP tool executions.

    Automatically tracks tool execution duration and success rates.

    Args:
        extract_tool_info: Optional function to extract tool_name, server_name, method
                          from args/kwargs. Should return dict with keys:
                          'tool_name', 'server_name', 'method'

    Returns:
        Decorated function that tracks tool execution

    Example:
        def get_tool_info(request, server, **kw):
            return {
                'tool_name': extract_tool_from_body(request),
                'server_name': server.serverName,
                'method': request.method
            }

        @track_tool_execution(extract_tool_info=get_tool_info)
        async def proxy_to_mcp_server(request, server):
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            success = False

            # Extract tool info
            tool_name = "unknown"
            server_name = "unknown"
            method = "UNKNOWN"

            if extract_tool_info:
                try:
                    info = extract_tool_info(*args, **kwargs)
                    tool_name = info.get("tool_name", "unknown")
                    server_name = info.get("server_name", "unknown")
                    method = info.get("method", "UNKNOWN")
                except Exception as e:
                    logger.debug(f"Failed to extract tool info: {e}")

            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception:
                raise
            finally:
                duration = time.perf_counter() - start_time
                try:
                    _record_tool_execution(
                        tool_name=tool_name,
                        server_name=server_name,
                        success=success,
                        duration_seconds=duration,
                        method=method,
                    )
                except Exception as e:
                    logger.warning(f"Failed to record tool execution metric: {e}")

        return wrapper  # type: ignore

    return decorator


def track_tool_discovery(
    extract_query: Optional[Callable[..., str]] = None,
    source: str = "search",
) -> Callable[[F], F]:
    """
    Decorator for tracking tool discovery operations.

    Tracks overall discovery operation and optionally individual tool discoveries.

    Args:
        extract_query: Optional function to extract query string from args/kwargs
        source: Source of discovery (default: "search")

    Returns:
        Decorated function that tracks tool discovery

    Example:
        @track_tool_discovery(extract_query=lambda body, **kw: body.get('query', ''))
        async def discover_tools(body: dict):
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            success = False
            query = "unknown"

            # Extract query
            if extract_query:
                try:
                    query = extract_query(*args, **kwargs)
                except Exception:
                    pass

            try:
                result = await func(*args, **kwargs)
                success = True

                # Record discovery for each found tool (if result has matches)
                if hasattr(result, "matches"):
                    for match in result.matches:
                        try:
                            _record_tool_discovery(
                                tool_name=getattr(match, "tool_name", "unknown"),
                                source=source,
                                success=True,
                                duration_seconds=None,  # Don't duplicate duration per tool
                            )
                        except Exception:
                            pass

                return result
            except Exception:
                raise
            finally:
                duration = time.perf_counter() - start_time
                try:
                    # Record overall discovery operation with timing
                    _record_tool_discovery(
                        tool_name=query,  # Use query as identifier for overall operation
                        source=source,
                        success=success,
                        duration_seconds=duration,
                    )
                except Exception as e:
                    logger.warning(f"Failed to record tool discovery metric: {e}")

        return wrapper  # type: ignore

    return decorator


class AuthMetricsContext:
    """
    Context manager for tracking authentication with dynamic mechanism detection.

    Useful when the auth mechanism is determined during the authentication process
    rather than being known upfront.

    Example:
        async with AuthMetricsContext() as ctx:
            user_context = await try_jwt_auth(request)
            if user_context:
                ctx.set_mechanism("jwt")
                ctx.set_success(True)
                return user_context

            user_context = await try_session_auth(request)
            if user_context:
                ctx.set_mechanism("session")
                ctx.set_success(True)
                return user_context

            ctx.set_success(False)
            raise AuthenticationError("No valid auth")
    """

    def __init__(self, default_mechanism: str = "unknown"):
        self._start_time: float = 0
        self._mechanism: str = default_mechanism
        self._success: bool = False

    def set_mechanism(self, mechanism: str) -> None:
        """Set the authentication mechanism."""
        self._mechanism = mechanism

    def set_success(self, success: bool) -> None:
        """Set the success status."""
        self._success = success

    async def __aenter__(self) -> "AuthMetricsContext":
        self._start_time = time.perf_counter()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        if exc_type is not None:
            self._success = False

        duration = time.perf_counter() - self._start_time

        try:
            _record_auth_request(
                mechanism=self._mechanism,
                success=self._success,
                duration_seconds=duration,
            )
        except Exception as e:
            logger.warning(f"Failed to record auth metric: {e}")


class ToolExecutionMetricsContext:
    """
    Context manager for tracking tool execution with dynamic info.

    Useful for proxy functions where tool info may be extracted at various points.

    Example:
        async with ToolExecutionMetricsContext(method=request.method) as ctx:
            ctx.set_server_name(server.serverName)
            tool_name = extract_tool_from_body(body)
            ctx.set_tool_name(tool_name)

            response = await proxy_request(target_url)

            ctx.set_success(response.status_code < 400)
            return response
    """

    def __init__(
        self,
        tool_name: str = "unknown",
        server_name: str = "unknown",
        method: str = "UNKNOWN",
    ):
        self._start_time: float = 0
        self._tool_name: str = tool_name
        self._server_name: str = server_name
        self._method: str = method
        self._success: bool = False

    def set_tool_name(self, tool_name: str) -> None:
        """Set the tool name."""
        self._tool_name = tool_name

    def set_server_name(self, server_name: str) -> None:
        """Set the server name."""
        self._server_name = server_name

    def set_method(self, method: str) -> None:
        """Set the HTTP method."""
        self._method = method

    def set_success(self, success: bool) -> None:
        """Set the success status."""
        self._success = success

    async def __aenter__(self) -> "ToolExecutionMetricsContext":
        self._start_time = time.perf_counter()
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        if exc_type is not None:
            self._success = False

        duration = time.perf_counter() - self._start_time

        try:
            _record_tool_execution(
                tool_name=self._tool_name,
                server_name=self._server_name,
                success=self._success,
                duration_seconds=duration,
                method=self._method,
            )
        except Exception as e:
            logger.warning(f"Failed to record tool execution metric: {e}")
