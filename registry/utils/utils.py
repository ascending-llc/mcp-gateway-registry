import logging
from pathlib import Path

from fastapi import HTTPException
from fastapi import status as http_status

from registry.core.acl_constants import ResourceType

logger = logging.getLogger(__name__)

# Template directory - go up two levels from utils.py to registry/, then to templates/oauth/
TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "oauth"


def load_template(template_name: str, context: dict[str, str]) -> str:
    """Load and render HTML template"""
    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        logger.error(f"Template not found: {template_path}")
        return f"<h1>Template Error</h1><p>Template {template_name} not found</p>"
    try:
        content = None
        with open(template_path, encoding="utf-8") as f:
            content = f.read()

        # Simple template rendering - handle both {{ key }} and {{ {key} }} formats
        for key, value in context.items():
            content = content.replace(f"{{{{ {key} }}}}", str(value))
            content = content.replace(f"{{{{{key}}}}}", str(value))
        return content
    except Exception as e:
        logger.error(f"Failed to load template {template_name}: {e}")
        return f"<h1>Template Error</h1><p>Failed to load template: {e}</p>"


# ACL utility function
def validate_resource_type(resource_type: str) -> None:
    if resource_type not in [rt.value for rt in ResourceType]:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_resource_type", "message": f"Resource type '{resource_type}' is not valid."},
        )
