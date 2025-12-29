"""
Version management for MCP Gateway Registry.

Version can be set via BUILD_VERSION environment variable (for Docker builds)
or determined from git tags at runtime (for local development).
"""

import os
import subprocess
import logging
from pathlib import Path


logger = logging.getLogger(__name__)

DEFAULT_VERSION = "1.0.0"


def _get_git_version() -> str:
    """
    Get version from git describe.

    Returns version in format: v1.0.7 or v1.0.7-3-g1234abc (if commits after tag)

    Returns:
        Version string from git, or None if not in a git repository
    """
    try:
        # Get the repository root
        repo_root = Path(__file__).parent.parent

        # Run git describe to get version
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )

        if result.returncode == 0:
            version_str = result.stdout.strip()

            # Remove 'v' prefix if present
            if version_str.startswith('v'):
                version_str = version_str[1:]

            logger.info(f"Version from git: {version_str}")
            return version_str
        else:
            logger.debug(f"Git describe failed: {result.stderr.strip()}")
            return None

    except FileNotFoundError:
        logger.debug("Git command not found")
        return None
    except subprocess.TimeoutExpired:
        logger.debug("Git describe timed out")
        return None
    except Exception as e:
        logger.debug(f"Error getting git version: {e}")
        return None


def get_version() -> str:
    """
    Get application version.

    Priority order:
    1. BUILD_VERSION environment variable (set at Docker build time)
    2. Git tags (for local development)
    3. DEFAULT_VERSION fallback

    Returns:
        Version string (e.g., "1.0.7" or "1.0.0")
    """
    # First check for build-time version (Docker builds)
    build_version = os.getenv("BUILD_VERSION")
    if build_version:
        logger.info(f"Using build version: {build_version}")
        return build_version

    # Try git for local development
    git_version = _get_git_version()
    if git_version:
        return git_version

    # Fall back to default
    logger.info(f"Using default version: {DEFAULT_VERSION}")
    return DEFAULT_VERSION


# Module-level version constant
__version__ = get_version()
