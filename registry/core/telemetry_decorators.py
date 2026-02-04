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
    record_tool_execution as _record_tool_execution,
    record_tool_discovery as _record_tool_discovery,
    record_resource_access as _record_resource_access,
    record_prompt_execution as _record_prompt_execution,
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


class ResourceAccessMetricsContext:
    """
    Context manager for tracking resource access.

    Example:
        async with ResourceAccessMetricsContext(resource_uri=uri) as ctx:
            server = await get_server(id)
            ctx.set_server_name(server.name)
            ...
            ctx.set_success(True)
    """

    def __init__(
        self,
        resource_uri: str,
        server_name: str = "unknown",
    ):
        self._start_time: float = 0
        self._resource_uri: str = resource_uri
        self._server_name: str = server_name
        self._success: bool = False

    def set_server_name(self, server_name: str) -> None:
        """Set the server name."""
        self._server_name = server_name

    def set_success(self, success: bool) -> None:
        """Set the success status."""
        self._success = success

    async def __aenter__(self) -> "ResourceAccessMetricsContext":
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
            _record_resource_access(
                resource_uri=self._resource_uri,
                server_name=self._server_name,
                success=self._success,
                duration_seconds=duration,
            )
        except Exception as e:
            logger.warning(f"Failed to record resource access metric: {e}")


class PromptExecutionMetricsContext:
    """
    Context manager for tracking prompt execution.

    Example:
        async with PromptExecutionMetricsContext(prompt_name=name) as ctx:
            server = await get_server(id)
            ctx.set_server_name(server.name)
            ...
            ctx.set_success(True)
    """

    def __init__(
        self,
        prompt_name: str,
        server_name: str = "unknown",
    ):
        self._start_time: float = 0
        self._prompt_name: str = prompt_name
        self._server_name: str = server_name
        self._success: bool = False

    def set_server_name(self, server_name: str) -> None:
        """Set the server name."""
        self._server_name = server_name

    def set_success(self, success: bool) -> None:
        """Set the success status."""
        self._success = success

    async def __aenter__(self) -> "PromptExecutionMetricsContext":
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
            _record_prompt_execution(
                prompt_name=self._prompt_name,
                server_name=self._server_name,
                success=self._success,
                duration_seconds=duration,
            )
        except Exception as e:
            logger.warning(f"Failed to record prompt execution metric: {e}")


class ToolDiscoveryMetricsContext:
    """
    Context manager for tracking tool discovery operations.

    Used when fetching/discovering tools from MCP servers, such as during:
    - Server registration
    - Server health refresh
    - Server enable (toggle)

    Example:
        async with ToolDiscoveryMetricsContext(server_name=server.serverName) as ctx:
            ctx.set_transport_type(config.get("type", "streamable-http"))

            tool_list, resources, prompts, caps, error = await retrieve_from_server(...)

            if tool_list:
                ctx.set_tools_count(len(tool_list))
                ctx.set_success(True)
            else:
                ctx.set_success(False)
    """

    def __init__(
        self,
        server_name: str = "unknown",
        transport_type: str = "unknown",
    ):
        self._start_time: float = 0
        self._server_name: str = server_name
        self._transport_type: str = transport_type
        self._tools_count: int = 0
        self._success: bool = False

    def set_server_name(self, server_name: str) -> None:
        """Set the server name."""
        self._server_name = server_name

    def set_transport_type(self, transport_type: str) -> None:
        """Set the transport type."""
        self._transport_type = transport_type

    def set_tools_count(self, tools_count: int) -> None:
        """Set the number of tools discovered."""
        self._tools_count = tools_count

    def set_success(self, success: bool) -> None:
        """Set the success status."""
        self._success = success

    async def __aenter__(self) -> "ToolDiscoveryMetricsContext":
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
            _record_tool_discovery(
                server_name=self._server_name,
                success=self._success,
                duration_seconds=duration,
                transport_type=self._transport_type,
                tools_count=self._tools_count,
            )
        except Exception as e:
            logger.warning(f"Failed to record tool discovery metric: {e}")
