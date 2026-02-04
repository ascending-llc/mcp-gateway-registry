"""
Generic telemetry decorators for automatic timing and metrics collection.

This module provides reusable decorators that can be used across any service
to automatically track operation duration, success/failure rates, and custom attributes.
"""

import asyncio
import functools
import logging
import time
from collections.abc import Callable
from typing import (
    Any,
    TypeVar,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _safe_extract_labels(
    extract_labels: Callable | None,
    args: tuple,
    kwargs: dict,
    result: Any = None,
    error: Exception | None = None,
) -> dict[str, str]:
    """
    Safely extract labels from function arguments.

    Args:
        extract_labels: Optional function to extract labels
        args: Function positional arguments
        kwargs: Function keyword arguments
        result: Function return value (if successful)
        error: Exception (if failed)

    Returns:
        Dictionary of label names to string values
    """
    if not extract_labels:
        return {}

    try:
        labels = extract_labels(*args, **kwargs, result=result, error=error)
        # Ensure all values are strings
        return {k: str(v) for k, v in labels.items()} if labels else {}
    except Exception as e:
        logger.debug(f"Failed to extract labels: {e}")
        return {}


def track_duration(
    record_func: Callable[[float, dict[str, str]], None],
    extract_labels: Callable[..., dict[str, str]] | None = None,
    include_success: bool = True,
) -> Callable[[F], F]:
    """
    Decorator to automatically track operation duration.

    This decorator handles both sync and async functions, automatically
    measuring execution time and recording it via the provided record_func.

    Args:
        record_func: Function to call with (duration_seconds, labels) to record the metric.
                    Signature: (duration: float, labels: Dict[str, str]) -> None
        extract_labels: Optional function to extract labels from function args/kwargs/result.
                       Signature: (*args, **kwargs, result=None, error=None) -> Dict[str, str]
        include_success: If True, automatically adds 'success' label ('true'/'false')

    Returns:
        Decorated function that tracks duration

    Example:
        def record_auth(duration: float, labels: Dict[str, str]) -> None:
            metrics.record_auth_request(
                mechanism=labels.get('mechanism', 'unknown'),
                success=labels.get('success') == 'true',
                duration_seconds=duration
            )

        @track_duration(record_auth, extract_labels=lambda req, **kw: {'mechanism': 'jwt'})
        async def authenticate_request(request: Request):
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            success = True
            result = None
            error = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error = e
                raise
            finally:
                duration = time.perf_counter() - start_time
                labels = _safe_extract_labels(
                    extract_labels, args, kwargs, result=result, error=error
                )
                if include_success:
                    labels["success"] = "true" if success else "false"

                try:
                    record_func(duration, labels)
                except Exception as record_error:
                    logger.warning(f"Failed to record metric: {record_error}")

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            success = True
            result = None
            error = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error = e
                raise
            finally:
                duration = time.perf_counter() - start_time
                labels = _safe_extract_labels(
                    extract_labels, args, kwargs, result=result, error=error
                )
                if include_success:
                    labels["success"] = "true" if success else "false"

                try:
                    record_func(duration, labels)
                except Exception as record_error:
                    logger.warning(f"Failed to record metric: {record_error}")

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def create_timed_context(
    record_func: Callable[[float, dict[str, str]], None],
    labels: dict[str, str] | None = None,
):
    """
    Create a context manager for timing code blocks.

    This is useful when you need to time a section of code rather than
    an entire function.

    Args:
        record_func: Function to call with (duration_seconds, labels)
        labels: Optional static labels to include

    Returns:
        Async context manager that records duration on exit

    Example:
        async with create_timed_context(
            lambda d, l: metrics.record_tool_execution("tool", "server", True, d),
            labels={"tool": "my_tool"}
        ):
            await execute_tool()
    """

    class TimedContext:
        def __init__(self):
            self.start_time: float = 0
            self.success: bool = True
            self.extra_labels: dict[str, str] = {}

        def set_success(self, success: bool) -> None:
            """Set the success status for this context."""
            self.success = success

        def add_label(self, key: str, value: str) -> None:
            """Add an additional label."""
            self.extra_labels[key] = value

        async def __aenter__(self) -> "TimedContext":
            self.start_time = time.perf_counter()
            return self

        async def __aexit__(
            self,
            exc_type: Any,
            exc_val: Any,
            exc_tb: Any,
        ) -> None:
            if exc_type is not None:
                self.success = False

            duration = time.perf_counter() - self.start_time
            final_labels = {**(labels or {}), **self.extra_labels}
            final_labels["success"] = "true" if self.success else "false"

            try:
                record_func(duration, final_labels)
            except Exception as e:
                logger.warning(f"Failed to record timed context metric: {e}")

        def __enter__(self) -> "TimedContext":
            self.start_time = time.perf_counter()
            return self

        def __exit__(
            self,
            exc_type: Any,
            exc_val: Any,
            exc_tb: Any,
        ) -> None:
            if exc_type is not None:
                self.success = False

            duration = time.perf_counter() - self.start_time
            final_labels = {**(labels or {}), **self.extra_labels}
            final_labels["success"] = "true" if self.success else "false"

            try:
                record_func(duration, final_labels)
            except Exception as e:
                logger.warning(f"Failed to record timed context metric: {e}")

    return TimedContext()
