"""
Version management for MCP Gateway Registry.

Version is determined from Docker image tag inspection.
"""

import os
import subprocess
import logging


logger = logging.getLogger(__name__)

DEFAULT_VERSION = "1.0.0"


def _get_docker_image_version() -> str:
    """
    Get version from Docker image tag by inspecting the current container.
    
    This looks for the image tag of the running container via docker inspect.
    
    Returns:
        Version string from Docker image tag, or None if not in a container
        or unable to determine the version
    """
    try:
        # Check if we're running in a Docker container
        if not os.path.exists('/.dockerenv') and not os.path.exists('/run/.containerenv'):
            logger.debug("Not running in a container")
            return None
            
        # Try to get the hostname (container ID)
        hostname = os.getenv('HOSTNAME')
        if not hostname:
            logger.debug("Could not determine container hostname")
            return None
        
        # Try docker inspect to get the image tag
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Config.Image}}", hostname],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        
        if result.returncode == 0:
            image_tag = result.stdout.strip()
            
            # Extract version from image tag (e.g., "myimage:v1.0.7" -> "1.0.7")
            if ':' in image_tag:
                tag = image_tag.split(':')[-1]
                # Remove 'v' prefix if present
                if tag.startswith('v'):
                    tag = tag[1:]
                
                # Skip generic tags like 'latest' or 'dev'
                if tag not in ['latest', 'dev', 'main', 'master', 'develop']:
                    logger.info(f"Version from Docker image tag: {tag}")
                    return tag
            
            logger.debug(f"Could not extract version from image tag: {image_tag}")
            return None
        else:
            logger.debug(f"Docker inspect failed: {result.stderr.strip()}")
            return None
            
    except FileNotFoundError:
        logger.debug("Docker command not found")
        return None
    except subprocess.TimeoutExpired:
        logger.debug("Docker inspect timed out")
        return None
    except Exception as e:
        logger.debug(f"Error getting Docker image version: {e}")
        return None


def get_version() -> str:
    """
    Get application version from environment or Docker image tag.

    Returns:
        Version string from BUILD_VERSION env var, Docker image tag, or DEFAULT_VERSION
    """
    # First, check BUILD_VERSION environment variable
    build_version = os.getenv('BUILD_VERSION')
    if build_version:
        logger.info(f"Version from BUILD_VERSION env: {build_version}")
        return build_version
    
    # Get version from Docker image tag
    docker_version = _get_docker_image_version()
    if docker_version:
        return docker_version

    # Fall back to default
    logger.info(f"Using default version: {DEFAULT_VERSION}")
    return DEFAULT_VERSION


# Module-level version constant
__version__ = get_version()
