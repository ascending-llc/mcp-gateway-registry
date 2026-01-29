"""
Metrics client for the Auth service.

This module exports a pre-configured metrics client for the Auth service.
Import this module wherever you need to record metrics in the Auth service.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

from packages.telemetry.metrics_client import create_metrics_client

logger = logging.getLogger(__name__)


def _load_metrics_config() -> Optional[dict]:
    """
    Load metrics configuration from YAML file.

    Returns:
        Configuration dictionary or None if file not found/invalid
    """
    config_path = Path(__file__).parent.parent.parent / "config" / "metrics" / "auth_server.yml"

    if not config_path.exists():
        logger.debug(f"Metrics config not found at {config_path}, using defaults")
        return None

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
            logger.info(f"Loaded metrics config from {config_path}")
            return config
    except Exception as e:
        logger.warning(f"Failed to load metrics config: {e}")
        return None


# Load configuration and create service-specific metrics client
_config = _load_metrics_config()
metrics = create_metrics_client("auth_server", config=_config)
