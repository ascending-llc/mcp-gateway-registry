"""
Utility functions for metrics collection in the registry.
"""

import hashlib
import logging
from typing import Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def extract_server_name_from_url(url: str) -> str:
    """Extract server name from MCP server URL."""
    if not url:
        return "unknown"
    
    try:
        # URL format is typically http://host:port/server_name/
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]
        return path_parts[0] if path_parts else "unknown"
    except Exception:
        return "unknown"


def hash_user_id(user_id: str) -> str:
    """Hash user ID for privacy in metrics."""
    if not user_id:
        return ""
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


def categorize_user_agent(user_agent: str) -> str:
    """Categorize user agent for metrics analysis."""
    if not user_agent:
        return "unknown"
        
    user_agent_lower = user_agent.lower()
    
    if 'curl' in user_agent_lower:
        return 'curl'
    elif 'postman' in user_agent_lower:
        return 'postman'
    elif 'chrome' in user_agent_lower:
        return 'chrome'
    elif 'firefox' in user_agent_lower:
        return 'firefox'
    elif 'safari' in user_agent_lower:
        return 'safari'
    elif 'python' in user_agent_lower or 'requests' in user_agent_lower:
        return 'python_client'
    elif 'bot' in user_agent_lower or 'crawler' in user_agent_lower:
        return 'bot'
    else:
        return 'other'


def extract_headers_for_analysis(headers: Dict[str, str]) -> Dict[str, Any]:
    """Extract and categorize headers for nginx config analysis."""
    return {
        'user_agent_type': categorize_user_agent(headers.get('user-agent', '')),
        'accept': headers.get('accept', 'unknown'),
        'content_type': headers.get('content-type', 'unknown'),
        'authorization_present': bool(headers.get('authorization')),
        'x_forwarded_for_present': bool(headers.get('x-forwarded-for')),
        'origin': headers.get('origin', 'unknown'),
        'referer_present': bool(headers.get('referer')),
        'connection': headers.get('connection', 'unknown'),
        'upgrade': headers.get('upgrade', 'unknown')
    }