import secrets
import hashlib
import base64
from pathlib import Path
from typing import Dict
from registry.utils.log import logger


# PKCE utility functions
def generate_code_verifier() -> str:
    """
    Generate PKCE code_verifier
    
    Python implementation: Use secrets.token_urlsafe to generate secure random string
    """
    return secrets.token_urlsafe(32)


def generate_code_challenge(code_verifier: str) -> str:
    """
    Generate PKCE code_challenge
    """
    sha256_hash = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(sha256_hash).decode('utf-8').replace('=', '')
    return code_challenge


# Template directory - go up two levels from utils.py to registry/, then to templates/oauth/
TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "oauth"


def load_template(template_name: str, context: Dict[str, str]) -> str:
    """Load and render HTML template"""
    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        logger.error(f"Template not found: {template_path}")
        return f"<h1>Template Error</h1><p>Template {template_name} not found</p>"
    try:
        content = None
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Simple template rendering - handle both {{ key }} and {{ {key} }} formats
        for key, value in context.items():
            content = content.replace(f"{{{{ {key} }}}}", str(value))
            content = content.replace(f"{{{{{key}}}}}", str(value))
        return content
    except Exception as e:
        logger.error(f"Failed to load template {template_name}: {e}")
        return f"<h1>Template Error</h1><p>Failed to load template: {e}</p>"
