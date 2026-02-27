import logging
from pathlib import Path

import yaml

from .config import settings

logger = logging.getLogger(__name__)


def load_scopes_config() -> dict:
    """Load the scopes configuration from the configured scopes.yml file.

    The file path is determined by the SCOPES_CONFIG_PATH environment variable
    (default: ``config/scopes.yml`` relative to the current working directory).

    Returns:
        Parsed YAML as dict, or empty dict on error.
    """
    try:
        scopes_file = Path(settings.scopes_config_path)
        if not scopes_file.exists():
            logger.warning(f"Scopes config file not found at {scopes_file}")
            return {}

        with open(scopes_file) as f:
            config = yaml.safe_load(f)
            if not isinstance(config, dict):
                return {}
            return config
    except Exception as e:
        logger.error(f"Failed to load scopes configuration: {e}", exc_info=True)
        return {}


def map_groups_to_scopes(groups: list[str]) -> list[str]:
    """Map user groups to OAuth2 scopes based on the scopes configuration.

    Configuration is loaded from the file specified by the SCOPES_CONFIG_PATH
    environment variable (default: config/scopes.yml).

    Args:
        groups: List of group names to map.

    Returns:
        Deduplicated list of scope strings (order-preserving).
    """
    scopes_config = load_scopes_config()
    group_mappings = scopes_config.get("group_mappings", {})
    scopes: list[str] = []

    for group in groups:
        if group in group_mappings:
            group_scopes = group_mappings[group]
            scopes.extend(group_scopes)
            logger.debug(f"Mapped group '{group}' to scopes: {group_scopes}")
        else:
            logger.debug(f"No scope mapping found for group: {group}")

    seen: set[str] = set()
    unique_scopes: list[str] = []
    for scope in scopes:
        if scope not in seen:
            seen.add(scope)
            unique_scopes.append(scope)

    logger.info(f"Final mapped scopes: {unique_scopes}")
    return unique_scopes
