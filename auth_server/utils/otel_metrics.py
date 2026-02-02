"""
Metrics client and domain functions for the Auth service.

This module exports a pre-configured metrics client and domain-specific
helper functions for recording auth metrics.

Usage:
    from auth_server.utils.otel_metrics import (
        metrics,
        record_auth_request,
        record_token_operation,
        record_oauth_operation,
        record_session_operation,
    )

    # Using domain functions (recommended)
    record_auth_request("jwt", success=True, duration_seconds=0.05)

    # Using generic client directly
    metrics.record_counter("custom_metric", 1, {"label": "value"})
"""

import logging
from typing import Optional

from packages.telemetry.metrics_client import create_metrics_client, load_metrics_config

logger = logging.getLogger(__name__)


# Load configuration and create service-specific metrics client
_config = load_metrics_config("auth_server")
metrics = create_metrics_client("auth_server", config=_config)


# =============================================================================
# Domain-Specific Recording Functions
# =============================================================================


def record_auth_request(
    mechanism: str,
    success: bool,
    duration_seconds: Optional[float] = None,
) -> None:
    """
    Record an authentication attempt with optional duration for latency percentiles.

    Requires these metrics in config:
    - counter: auth_requests_total
    - histogram: auth_request_duration_seconds

    Args:
        mechanism: Authentication mechanism (e.g., "jwt", "api_key", "basic")
        success: Whether the auth attempt was successful
        duration_seconds: Request duration in seconds for p50/p95/p99 calculation
    """
    attributes = {
        "mechanism": mechanism,
        "status": "success" if success else "failure",
    }

    metrics.record_counter("auth_requests_total", 1, attributes)

    if duration_seconds is not None:
        metrics.record_histogram("auth_request_duration_seconds", duration_seconds, attributes)


def record_token_operation(
    operation: str,
    success: bool,
    duration_seconds: Optional[float] = None,
) -> None:
    """
    Record a token operation (refresh, generate, revoke).

    Requires these metrics in config:
    - counter: token_refreshes_total, token_generations_total, or token_revocations_total
    - histogram: token_generation_duration_seconds (for generate operations)

    Args:
        operation: Type of operation ("refresh", "generate", "revoke")
        success: Whether the operation was successful
        duration_seconds: Operation duration in seconds
    """
    attributes = {"status": "success" if success else "failure"}

    # Map operation to counter name
    counter_map = {
        "refresh": "token_refreshes_total",
        "generate": "token_generations_total",
        "revoke": "token_revocations_total",
    }

    counter_name = counter_map.get(operation)
    if counter_name:
        metrics.record_counter(counter_name, 1, attributes)

    # Record duration for token generation
    if duration_seconds is not None and operation == "generate":
        metrics.record_histogram("token_generation_duration_seconds", duration_seconds, attributes)


def record_oauth_operation(
    operation: str,
    success: bool,
    duration_seconds: Optional[float] = None,
) -> None:
    """
    Record an OAuth operation (callback, authorization).

    Requires these metrics in config:
    - counter: oauth_callbacks_total, oauth_authorizations_total
    - histogram: oauth_flow_duration_seconds

    Args:
        operation: Type of operation ("callback", "authorization")
        success: Whether the operation was successful
        duration_seconds: Operation duration in seconds
    """
    attributes = {"status": "success" if success else "failure"}

    # Map operation to counter name
    counter_map = {
        "callback": "oauth_callbacks_total",
        "authorization": "oauth_authorizations_total",
    }

    counter_name = counter_map.get(operation)
    if counter_name:
        metrics.record_counter(counter_name, 1, attributes)

    if duration_seconds is not None:
        metrics.record_histogram("oauth_flow_duration_seconds", duration_seconds, attributes)


def record_session_operation(
    operation: str,
    success: bool,
    duration_seconds: Optional[float] = None,
) -> None:
    """
    Record a session operation (create, validate).

    Requires these metrics in config:
    - counter: session_creations_total, session_validations_total
    - histogram: session_validation_duration_seconds

    Args:
        operation: Type of operation ("create", "validate")
        success: Whether the operation was successful
        duration_seconds: Operation duration in seconds
    """
    attributes = {"status": "success" if success else "failure"}

    # Map operation to counter name
    counter_map = {
        "create": "session_creations_total",
        "validate": "session_validations_total",
    }

    counter_name = counter_map.get(operation)
    if counter_name:
        metrics.record_counter(counter_name, 1, attributes)

    if duration_seconds is not None and operation == "validate":
        metrics.record_histogram("session_validation_duration_seconds", duration_seconds, attributes)
