"""
Agent Card validator for A2A (Agent-to-Agent) protocol.

This module validates Agent Cards according to the A2A protocol specification,
ensuring compliance with required fields, URL formats, skill definitions,
and security schemes.

Based on: docs/design/a2a-protocol-integration.md
"""

import logging
import re
from typing import (
    Dict,
    List,
    Optional,
    Tuple,
)

import httpx
from pydantic import BaseModel

from registry.schemas.agent_models import (
    AgentCard,
    SecurityScheme,
    Skill,
)


# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


class ValidationResult(BaseModel):
    """Result of agent card validation."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]


def _validate_agent_url(
    url: str,
) -> bool:
    """
    Validate agent URL format.

    Allows both HTTP and HTTPS for flexibility in local/development environments,
    though HTTPS is required for production per A2A specification.

    Args:
        url: Agent endpoint URL to validate

    Returns:
        True if URL is valid, False otherwise
    """
    if not url:
        return False

    url_str = str(url)

    if not (url_str.startswith("http://") or url_str.startswith("https://")):
        return False

    url_pattern = (
        r"^https?://([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
        r"[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
        r"(:\d+)?(/[^\s]*)?$"
    )

    return bool(re.match(url_pattern, url_str))


def _validate_skills(
    skills: List[Skill],
) -> List[str]:
    """
    Validate agent skills.

    Ensures each skill has required fields and proper format.

    Args:
        skills: List of skills to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors: List[str] = []

    if not isinstance(skills, list):
        errors.append("Skills must be a list")
        return errors

    for idx, skill in enumerate(skills):
        if not skill.id:
            errors.append(f"Skill {idx}: ID cannot be empty")

        if not skill.name:
            errors.append(f"Skill {idx}: name cannot be empty")

        if not skill.description:
            errors.append(f"Skill {idx}: description cannot be empty")

    return errors


def _validate_security_schemes(
    security_schemes: Dict[str, SecurityScheme],
) -> List[str]:
    """
    Validate security schemes configuration.

    Ensures schemes are properly configured with required fields.

    Args:
        security_schemes: Dictionary of security schemes to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors: List[str] = []

    if not isinstance(security_schemes, dict):
        errors.append("Security schemes must be a dictionary")
        return errors

    for scheme_name, scheme in security_schemes.items():
        if not scheme_name:
            errors.append("Security scheme name cannot be empty")

        if not scheme.type:
            errors.append(f"Scheme '{scheme_name}': type is required")

        valid_types = ["apiKey", "http", "oauth2", "openIdConnect"]
        if scheme.type not in valid_types:
            errors.append(
                f"Scheme '{scheme_name}': invalid type '{scheme.type}'"
            )

        if scheme.type == "apiKey":
            if not scheme.in_:
                errors.append(f"Scheme '{scheme_name}': 'in' is required for apiKey")

            if not scheme.name:
                errors.append(
                    f"Scheme '{scheme_name}': 'name' is required for apiKey"
                )

        if scheme.type == "http":
            if not scheme.scheme:
                errors.append(
                    f"Scheme '{scheme_name}': 'scheme' is required for http"
                )

        if scheme.type == "oauth2":
            if not scheme.flows:
                errors.append(
                    f"Scheme '{scheme_name}': 'flows' is required for oauth2"
                )

        if scheme.type == "openIdConnect":
            if not scheme.openid_connect_url:
                errors.append(
                    f"Scheme '{scheme_name}': openIdConnect URL required"
                )

    return errors


def _validate_tags(
    tags: List[str],
) -> List[str]:
    """
    Validate agent tags.

    Ensures tags are non-empty strings.

    Args:
        tags: List of tags to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors: List[str] = []

    if not isinstance(tags, list):
        errors.append("Tags must be a list")
        return errors

    for idx, tag in enumerate(tags):
        if not isinstance(tag, str):
            errors.append(f"Tag {idx}: must be a string, got {type(tag).__name__}")

        if isinstance(tag, str) and not tag.strip():
            errors.append(f"Tag {idx}: cannot be empty")

    return errors


def _check_endpoint_reachability(
    url: str,
) -> Tuple[bool, Optional[str]]:
    """
    Check if agent endpoint is reachable.

    Attempts HTTP GET request to the well-known endpoint.
    Does not block validation if unreachable.

    Args:
        url: Agent endpoint URL to check

    Returns:
        Tuple of (is_reachable, error_message)
    """
    try:
        well_known_url = f"{url}/.well-known/agent-card.json"

        response = httpx.get(
            well_known_url,
            timeout=5.0,
        )

        if response.status_code == 200:
            return (True, None)

        return (False, f"Endpoint returned status {response.status_code}")

    except httpx.TimeoutException:
        logger.warning(f"Endpoint timeout for {url}")
        return (False, "Endpoint request timed out")

    except Exception as e:
        logger.warning(f"Could not reach endpoint {url}: {e}")
        return (False, str(e))


def _validate_agent_card(
    agent_card: AgentCard,
) -> Tuple[bool, List[str]]:
    """
    Validate agent card structure and content.

    Performs core validation on required fields and references.

    Args:
        agent_card: AgentCard instance to validate

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors: List[str] = []

    if not agent_card.name or not agent_card.name.strip():
        errors.append("Agent name cannot be empty")

    if not agent_card.description or not agent_card.description.strip():
        errors.append("Agent description cannot be empty")

    # Path is optional - auto-generated if not provided
    if agent_card.path and not agent_card.path.strip():
        errors.append("Agent path cannot be empty if provided")

    if not _validate_agent_url(str(agent_card.url)):
        errors.append("Agent URL must be HTTP or HTTPS and properly formatted")

    if agent_card.protocol_version:
        if not re.match(r"^\d+\.\d+(\.\d+)?$", agent_card.protocol_version):
            errors.append("Protocol version must be in format X.Y or X.Y.Z")

    if agent_card.visibility not in ["public", "private", "group-restricted"]:
        errors.append(f"Invalid visibility: {agent_card.visibility}")

    if agent_card.trust_level not in [
        "unverified",
        "community",
        "verified",
        "trusted",
    ]:
        errors.append(f"Invalid trust level: {agent_card.trust_level}")

    skill_errors = _validate_skills(agent_card.skills)
    errors.extend(skill_errors)

    scheme_errors = _validate_security_schemes(agent_card.security_schemes)
    errors.extend(scheme_errors)

    tag_errors = _validate_tags(agent_card.tags)
    errors.extend(tag_errors)

    is_valid = len(errors) == 0
    return (is_valid, errors)


def validate_agent_card(
    agent_card: AgentCard,
    check_reachability: bool = False,
) -> ValidationResult:
    """
    Validate an agent card.

    Main entry point for agent card validation. Performs structure
    and content validation, with optional reachability checks.

    Args:
        agent_card: AgentCard instance to validate
        check_reachability: If True, attempt to reach agent endpoint

    Returns:
        ValidationResult with validation status and messages
    """
    is_valid, errors = _validate_agent_card(agent_card)

    warnings: List[str] = []

    if check_reachability and agent_card.url:
        reachable, error_msg = _check_endpoint_reachability(str(agent_card.url))

        if not reachable:
            warnings.append(f"Agent endpoint unreachable: {error_msg}")
            logger.warning(
                f"Agent {agent_card.name} endpoint unreachable: {error_msg}"
            )

    if errors:
        logger.error(f"Agent card validation failed: {errors}")
    else:
        logger.info(f"Agent card '{agent_card.name}' validated successfully")

    if warnings:
        logger.warning(f"Agent card '{agent_card.name}' has warnings: {warnings}")

    return ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
    )


class AgentValidator:
    """Service for validating A2A agent cards."""

    async def validate_agent_card(
        self,
        agent_card: AgentCard,
        verify_endpoint: bool = False,
    ) -> ValidationResult:
        """
        Async wrapper for validating an agent card.

        Args:
            agent_card: AgentCard instance to validate
            verify_endpoint: If True, attempt to verify endpoint

        Returns:
            ValidationResult with validation status and messages
        """
        return validate_agent_card(
            agent_card=agent_card,
            check_reachability=verify_endpoint,
        )


# Global validator instance
agent_validator = AgentValidator()
