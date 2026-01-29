"""
Metrics client for the Auth service.

This module exports a pre-configured metrics client for the Auth service.
Import this module wherever you need to record metrics in the Auth service.
"""
from packages.telemetry.metrics_client import create_metrics_client

# Create service-specific metrics client
metrics = create_metrics_client("auth_server")
