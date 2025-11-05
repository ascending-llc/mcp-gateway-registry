#!/usr/bin/env python3
"""Transform Anthropic MCP Registry server format to Gateway Registry format.

This module provides utilities to convert server definitions from the
Anthropic MCP Registry API format into the format expected by the
MCP Gateway Registry.
"""
import json
import logging
from typing import (
    Any,
    Dict,
    List,
    Optional,
)


# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


# Constants
DEFAULT_BASE_PORT: int = 8100
DEFAULT_TRANSPORT: str = "stdio"
DEFAULT_DESCRIPTION: str = "MCP server imported from Anthropic Registry"
DEFAULT_LICENSE: str = "MIT"
DEFAULT_AUTH_PROVIDER: str = "keycloak"
DEFAULT_AUTH_TYPE: str = "oauth"


def _extract_package_info(
    packages: Any
) -> bool:
    """Extract Python detection from packages field.

    Args:
        packages: Package information (dict or list)

    Returns:
        True if this is a Python package, False otherwise
    """
    is_python = False

    if isinstance(packages, dict):
        is_python = "pypi" in packages or "python" in packages
    elif isinstance(packages, list):
        is_python = any(pkg.get("registryType") == "pypi" for pkg in packages)

    return is_python


def _substitute_env_vars_in_headers(
    headers: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    """Substitute environment variables in header values.

    Replaces ${VAR_NAME} or $VAR_NAME with actual environment variable values.
    If the environment variable is not set, keeps the placeholder.

    Args:
        headers: List of header dictionaries

    Returns:
        List of headers with environment variables substituted
    """
    import os
    import re

    substituted_headers = []

    for header_dict in headers:
        substituted_header = {}
        for header_name, header_value in header_dict.items():
            # Match ${VAR_NAME} or $VAR_NAME pattern
            def replace_env_var(match):
                var_name = match.group(1)
                env_value = os.getenv(var_name)
                if env_value:
                    logger.info(f"Substituted {var_name} in header {header_name}")
                    return env_value
                else:
                    logger.warning(f"Environment variable {var_name} not found, keeping placeholder")
                    return match.group(0)  # Keep original placeholder

            # Replace ${VAR} pattern first
            substituted_value = re.sub(r'\$\{([^}]+)\}', replace_env_var, header_value)
            # Then replace $VAR pattern (only for uppercase variables)
            substituted_value = re.sub(r'\$([A-Z_][A-Z0-9_]*)', replace_env_var, substituted_value)

            substituted_header[header_name] = substituted_value

        substituted_headers.append(substituted_header)

    return substituted_headers


def _extract_remote_info(
    remotes: List[Dict[str, Any]]
) -> tuple[Optional[str], str, str, List[Dict[str, str]]]:
    """Extract remote URL, transport type, auth type, and headers from remotes field.

    Args:
        remotes: List of remote server configurations

    Returns:
        Tuple of (remote_url, transport_type, auth_type, headers)
    """
    import re

    remote_url = None
    transport_type = DEFAULT_TRANSPORT
    auth_type = "none"
    output_headers = []

    if remotes:
        remote = remotes[0]
        remote_url = remote.get("url")
        transport_type = remote.get("type", "streamable-http")

        # Check if remote has authentication headers
        headers = remote.get("headers", [])
        if headers:
            for header in headers:
                header_name = header.get("name", "")
                header_value = header.get("value", "")

                # Check for auth-related headers
                if header_name.lower() in ["authorization", "x-api-key", "api-key"]:
                    # Extract variable name from the placeholder (e.g., {smithery_api_key})
                    match = re.search(r'\{([^}]+)\}', header_value)
                    if match:
                        var_name = match.group(1)
                        # Convert to uppercase with underscores (e.g., smithery_api_key -> SMITHERY_API_KEY)
                        env_var_name = var_name.upper()

                        # Determine auth type and create header value
                        if "bearer" in header_value.lower():
                            auth_type = "oauth"
                            output_headers.append({
                                header_name: f"Bearer ${{{env_var_name}}}"
                            })
                        elif "api" in header_value.lower() or "key" in header_value.lower():
                            auth_type = "api-key"
                            output_headers.append({
                                header_name: f"${{{env_var_name}}}"
                            })
                        else:
                            auth_type = "custom"
                            output_headers.append({
                                header_name: f"${{{env_var_name}}}"
                            })
                    break

    return remote_url, transport_type, auth_type, output_headers


def _generate_tags(
    name: str
) -> List[str]:
    """Generate tags from server name.

    Args:
        name: Server name (may contain slashes)

    Returns:
        List of tags including name parts and 'anthropic-registry'
    """
    name_parts = name.replace("/", "-").split("-")
    tags = name_parts + ["anthropic-registry"]
    return tags


def transform_anthropic_to_gateway(
    anthropic_response: Dict[str, Any],
    base_port: int = DEFAULT_BASE_PORT
) -> Dict[str, Any]:
    """Transform Anthropic ServerResponse to Gateway Registry Config format.

    Args:
        anthropic_response: Server data from Anthropic Registry API
        base_port: Base port number for local proxy URLs

    Returns:
        Dictionary in Gateway Registry configuration format

    Example:
        >>> response = {"server": {"name": "brave-search", ...}}
        >>> config = transform_anthropic_to_gateway(response)
        >>> print(config["server_name"])
        brave-search
    """
    server = anthropic_response.get("server", anthropic_response)
    name = server["name"]

    tags = _generate_tags(name)

    packages = server.get("packages", {})
    is_python = _extract_package_info(packages)

    remotes = server.get("remotes", [])
    remote_url, transport_type, auth_type, auth_headers = _extract_remote_info(remotes)

    # Substitute environment variables in headers
    if auth_headers:
        auth_headers = _substitute_env_vars_in_headers(auth_headers)

    safe_path = name.replace("/", "-")

    proxy_url = remote_url if remote_url else f"http://localhost:{base_port}/"

    return {
        "server_name": name,
        "description": server.get("description", DEFAULT_DESCRIPTION),
        "path": f"/{safe_path}",
        "proxy_pass_url": proxy_url,
        "auth_provider": DEFAULT_AUTH_PROVIDER if auth_type != "none" else None,
        "auth_type": auth_type,
        "supported_transports": [transport_type],
        "tags": tags,
        "headers": auth_headers if auth_headers else [],
        "num_tools": 0,
        "num_stars": 0,
        "is_python": is_python,
        "license": DEFAULT_LICENSE,
        "remote_url": remote_url,
        "tool_list": []
    }


def _run_example() -> None:
    """Run example transformation and print result."""
    example_input = {
        "name": "brave-search",
        "description": "MCP server for Brave Search API",
        "version": "0.1.0",
        "repository": {
            "type": "github",
            "url": "https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search"
        },
        "websiteUrl": "https://brave.com/search/api/",
        "packages": {
            "npm": "@modelcontextprotocol/server-brave-search"
        }
    }

    result = transform_anthropic_to_gateway(example_input)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _run_example()
