import hashlib
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def mask_sensitive_id(value: str) -> str:
    """Mask sensitive IDs showing only first and last 4 characters."""
    if not value or len(value) <= 8:
        return "***MASKED***"
    return f"{value[:4]}...{value[-4:]}"


def hash_username(username: str) -> str:
    """Hash username for privacy compliance."""
    if not username:
        return "anonymous"
    return f"user_{hashlib.sha256(username.encode()).hexdigest()[:8]}"


def anonymize_ip(ip_address: str) -> str:
    """Anonymize IP address by masking last octet for IPv4."""
    if not ip_address or ip_address == 'unknown':
        return ip_address
    if '.' in ip_address:  # IPv4
        parts = ip_address.split('.')
        if len(parts) == 4:
            return f"{'.'.join(parts[:3])}.xxx"
    elif ':' in ip_address:  # IPv6
        parts = ip_address.split(':')
        if len(parts) > 1:
            parts[-1] = 'xxxx'
            return ':'.join(parts)
    return ip_address


def mask_token(token: str) -> str:
    """Mask JWT token showing only last 4 characters."""
    if not token:
        return "***EMPTY***"
    if len(token) > 20:
        return f"...{token[-4:]}"
    return "***MASKED***"


def mask_headers(headers: dict) -> dict:
    """Mask sensitive headers for logging compliance."""
    masked = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if key_lower in ['x-authorization', 'authorization', 'cookie']:
            if 'bearer' in str(value).lower():
                parts = str(value).split(' ', 1)
                if len(parts) == 2:
                    masked[key] = f"Bearer {mask_token(parts[1])}"
                else:
                    masked[key] = mask_token(value)
            else:
                masked[key] = "***MASKED***"
        elif key_lower in ['x-user-pool-id', 'x-client-id']:
            masked[key] = mask_sensitive_id(value)
        else:
            masked[key] = value
    return masked


def map_groups_to_scopes(groups: List[str], scopes_config: Optional[Dict] = None) -> List[str]:
    """
    Map identity provider groups to MCP scopes using the provided scopes_config.

    Args:
        groups: List of group names from identity provider (Cognito, Keycloak, etc.)
        scopes_config: Optional dict of group_mappings; if None returns empty mapping

    Returns:
        List of MCP scopes
    """
    scopes: List[str] = []
    if not scopes_config:
        logger.debug("No scopes_config provided to map_groups_to_scopes; returning empty list")
        return []

    group_mappings = scopes_config.get('group_mappings', {})

    for group in groups:
        if group in group_mappings:
            group_scopes = group_mappings[group]
            scopes.extend(group_scopes)
            logger.debug(f"Mapped group '{group}' to scopes: {group_scopes}")
        else:
            logger.debug(f"No scope mapping found for group: {group}")

    seen = set()
    unique_scopes: List[str] = []
    for scope in scopes:
        if scope not in seen:
            seen.add(scope)
            unique_scopes.append(scope)

    logger.info(f"Final mapped scopes: {unique_scopes}")
    return unique_scopes


def parse_server_and_tool_from_url(original_url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse server name and tool name from the original URL and request payload.

    Args:
        original_url: The original URL from X-Original-URL header

    Returns:
        Tuple of (server_name, tool_name) or (None, None) if parsing fails
    """
    try:
        from urllib.parse import urlparse
        parsed_url = urlparse(original_url)
        path = parsed_url.path.strip('/')
        path_parts = path.split('/') if path else []
        server_name = path_parts[0] if path_parts else None
        logger.debug(f"Parsed server name '{server_name}' from URL path: {path}")
        return server_name, None
    except Exception as e:
        logger.error(f"Failed to parse server/tool from URL {original_url}: {e}")
        return None, None
