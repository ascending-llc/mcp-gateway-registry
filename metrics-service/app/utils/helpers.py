import hashlib
import secrets


def generate_api_key() -> str:
    """Generate a new API key."""
    return f"mcp_metrics_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    """Hash API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return f"req_{secrets.token_hex(8)}"
