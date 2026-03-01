"""Centralized scopes configuration loader for MCP Gateway Registry.

This module provides a consistent way to load and access the scopes.yml configuration
across all services (registry, auth-server, mcpgw).

The loader follows this priority:
1. SCOPES_CONFIG_PATH environment variable (for local development)
2. Package-bundled scopes.yml (for production containers)

The configuration is loaded once at module import and cached for the lifetime of the process.
Changes to scopes.yml require a service restart.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from .config import settings

logger = logging.getLogger(__name__)

# Module-level cache - loaded once at import
_SCOPES_CONFIG: dict[str, Any] | None = None


def get_scopes_file_path() -> Path:
    """Get the path to the scopes.yml file.

    Priority:
    1. SCOPES_CONFIG_PATH environment variable (absolute or relative path)
    2. Package-bundled scopes.yml file

    Returns:
        Path object pointing to scopes.yml

    Raises:
        FileNotFoundError: If scopes.yml cannot be found in any location
    """
    # Check environment variable first (for local development)
    if settings.SCOPES_CONFIG_PATH:
        scopes_path = Path(settings.SCOPES_CONFIG_PATH)
        if scopes_path.exists():
            logger.info(f"Using scopes config from SCOPES_CONFIG_PATH: {scopes_path}")
            return scopes_path
        else:
            logger.warning(f"SCOPES_CONFIG_PATH set to {settings.SCOPES_CONFIG_PATH} but file not found")

    # Fallback to package-bundled file (production)
    package_path = Path(__file__).parent.parent / "scopes.yml"
    if package_path.exists():
        logger.info(f"Using package-bundled scopes config: {package_path}")
        return package_path

    # If nothing found, raise error (fail fast)
    raise FileNotFoundError(
        "scopes.yml not found. Set SCOPES_CONFIG_PATH environment variable "
        "or ensure scopes.yml is packaged with registry-pkgs."
    )


def load_scopes_config() -> dict[str, Any]:
    """Load scopes configuration from YAML file.

    This function uses module-level caching - the config is loaded once at first call
    and reused for subsequent calls. Changes require a service restart.

    Returns:
        Dictionary containing scopes configuration with structure:
        {
            "group_mappings": {
                "group-name": ["scope1", "scope2", ...],
                ...
            },
            "scope-name": [
                {"action": "...", "method": "...", "endpoint": "..."},
                ...
            ],
            ...
        }

    Raises:
        FileNotFoundError: If scopes.yml cannot be found
        yaml.YAMLError: If scopes.yml is not valid YAML
        RuntimeError: If loaded config is empty or invalid
    """
    global _SCOPES_CONFIG

    # Return cached config if already loaded
    if _SCOPES_CONFIG is not None:
        return _SCOPES_CONFIG

    # Load configuration
    scopes_file = get_scopes_file_path()

    try:
        with open(scopes_file) as f:
            config = yaml.safe_load(f)

        if not config or not isinstance(config, dict):
            raise RuntimeError(f"Invalid scopes configuration: expected dict, got {type(config)}")

        # Validate structure
        if "group_mappings" not in config:
            raise RuntimeError("scopes.yml missing required 'group_mappings' section")

        logger.info(f"Loaded scopes config with {len(config.get('group_mappings', {}))} group mappings")

        # Cache the configuration
        _SCOPES_CONFIG = config
        return config

    except yaml.YAMLError as e:
        logger.error(f"Failed to parse scopes.yml: {e}")
        raise RuntimeError(f"Invalid YAML in scopes.yml: {e}") from e
    except Exception as e:
        logger.error(f"Failed to load scopes config from {scopes_file}: {e}")
        raise


def get_scopes_config() -> dict[str, Any]:
    """Get the cached scopes configuration.

    This is a convenience function that calls load_scopes_config().
    Use this when you want to be explicit about retrieving cached config.

    Returns:
        Dictionary containing scopes configuration

    Raises:
        Same exceptions as load_scopes_config()
    """
    return load_scopes_config()


# Pre-load configuration at module import for fail-fast behavior
# If this fails, the service won't start - which is desired behavior
try:
    load_scopes_config()
    logger.info("Scopes configuration pre-loaded successfully")
except Exception as e:
    logger.error(f"Failed to pre-load scopes configuration: {e}")
    # Don't suppress the exception - let the service fail to start
    raise
