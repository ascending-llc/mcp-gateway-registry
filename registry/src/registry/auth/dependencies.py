import logging
import os
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import Depends, HTTPException, Request, status
from itsdangerous import URLSafeTimedSerializer

from registry.core.config import settings

logger = logging.getLogger(__name__)

signer = URLSafeTimedSerializer(settings.secret_key)


def get_current_user(request: Request) -> dict[str, Any]:
    """
        Get current authenticated user from request state
        This function replaces the need for Depends(enhanced_auth) or
    Depends(nginx_proxied_auth) in route handlers.

    Args:
        request: FastAPI request object

    Returns:
        User context dictionary with all authentication details

    Raises:
        HTTPException: If user is not authenticated
    """
    if not hasattr(request.state, "user") or not request.state.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Is not authenticated")
    return request.state.user


# Use this type to annotate a parameter of a path operation function or its dependency function so that
# FastAPI extracts the `user` attribute (typed as dict[str, Any]) of the current request and pass it to the parameter.
# Since it's Python 3.12, we use the new type statement instead of typing.TypeAlias
type CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


def user_has_wildcard_access(user_scopes: list[str]) -> bool:
    """
    Check if user should be treated as admin.
    """
    return "registry-admin" in user_scopes


def load_scopes_config() -> dict[str, Any]:
    """Load the scopes configuration from auth_server/scopes.yml"""
    try:
        # Check for SCOPES_CONFIG_PATH environment variable first
        scopes_path = os.getenv("SCOPES_CONFIG_PATH")

        # Print to stderr for immediate visibility before logging is configured
        print(f"[SCOPES_INIT] SCOPES_CONFIG_PATH env var: {scopes_path}", flush=True)

        # Fall back to default location if env var not set
        if not scopes_path:
            # IMPORTANT, TODO: Currently in the mcpgateway-registry container, the following `scope_file` path happens to work,
            # because it starts from this file, goes up three levels to reach the `/usr/local/lib/python3.12/site-packages/` folder,
            # and then reaches down to the `auth_server` package, which does have the `scopes.yml` file at its project root.
            # However, we normally should not assume all 3rd party dependencies are installed to the same folder,
            # so we should not rely on this coincidence for things to work.
            # There is a refactoring ticket where we want to stop `registry` from depending on `auth_server`.
            # In that ticket we will find a good way for registry to get scopes, and that is the right time to change this piece of code.
            # This comment is left for that ticket.
            scopes_file = Path(__file__).parent.parent.parent / "auth_server" / "scopes.yml"
        else:
            scopes_file = Path(scopes_path)

        # If file doesn't exist, try the EFS mounted location (auth_config subdirectory)
        if not scopes_file.exists():
            alt_scopes_file = Path(__file__).parent.parent.parent / "auth_server" / "auth_config" / "scopes.yml"
            if alt_scopes_file.exists():
                scopes_file = alt_scopes_file
                print(
                    f"[SCOPES_INIT] File not found at primary location, using EFS mount location: {scopes_file}",
                    flush=True,
                )

        print(f"[SCOPES_INIT] Looking for scopes config at: {scopes_file}", flush=True)
        print(f"[SCOPES_INIT] Scopes file exists: {scopes_file.exists()}", flush=True)

        if not scopes_file.exists():
            print(f"[SCOPES_INIT] ERROR: Scopes config file not found at {scopes_file}", flush=True)
            auth_server_dir = scopes_file.parent
            print(f"[SCOPES_INIT] Auth server directory exists: {auth_server_dir.exists()}", flush=True)
            if auth_server_dir.exists():
                print(f"[SCOPES_INIT] Auth server directory contents: {list(auth_server_dir.iterdir())}", flush=True)
            logger.warning(f"Scopes config file not found at {scopes_file}")
            return {}

        with open(scopes_file) as f:
            config = yaml.safe_load(f)
            logger.info(f"Loaded scopes configuration with {len(config.get('group_mappings', {}))} group mappings")
            return config
    except Exception as e:
        logger.error(f"Failed to load scopes configuration: {e}", exc_info=True)
        return {}


# Global scopes configuration
SCOPES_CONFIG = load_scopes_config()


def map_cognito_groups_to_scopes(groups: list[str]) -> list[str]:
    """
    Map Cognito groups to MCP scopes using the scopes.yml configuration.

    Args:
        groups: List of Cognito group names

    Returns:
        List of MCP scopes
    """
    scopes = []
    group_mappings = SCOPES_CONFIG.get("group_mappings", {})

    for group in groups:
        if group in group_mappings:
            group_scopes = group_mappings[group]
            scopes.extend(group_scopes)
            logger.debug(f"Mapped group '{group}' to scopes: {group_scopes}")
        else:
            logger.debug(f"No scope mapping found for group: {group}")

    # Remove duplicates while preserving order
    seen = set()
    unique_scopes = []
    for scope in scopes:
        if scope not in seen:
            seen.add(scope)
            unique_scopes.append(scope)

    logger.info(f"Final mapped scopes: {unique_scopes}")
    return unique_scopes
