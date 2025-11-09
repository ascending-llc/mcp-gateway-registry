"""
Pydantic models for A2A (Agent-to-Agent) protocol support.

This module defines Agent Cards and related models following the A2A specification
for agent discovery and registration in the MCP Gateway Registry.

Based on: docs/design/a2a-protocol-integration.md
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


def _validate_path_format(
    path: str,
) -> str:
    """
    Validate agent path format.

    Args:
        path: Agent path to validate

    Returns:
        Validated path string

    Raises:
        ValueError: If path format is invalid
    """
    if not path.startswith("/"):
        raise ValueError("Path must start with '/'")

    if "//" in path:
        raise ValueError("Path cannot contain consecutive slashes")

    if path.endswith("/") and len(path) > 1:
        raise ValueError("Path cannot end with '/' unless it is the root path")

    return path


def _validate_protocol_version(
    version: str,
) -> str:
    """
    Validate A2A protocol version format.

    Args:
        version: Protocol version string

    Returns:
        Validated version string

    Raises:
        ValueError: If version format is invalid
    """
    if not version:
        raise ValueError("Protocol version cannot be empty")

    parts = version.split(".")
    if len(parts) < 2:
        raise ValueError("Protocol version must be in format 'X.Y' or 'X.Y.Z'")

    for part in parts:
        if not part.isdigit():
            raise ValueError("Protocol version parts must be numeric")

    return version


def _validate_skill_ids_unique(
    skills: List["Skill"],
) -> List["Skill"]:
    """
    Validate that skill IDs are unique within the agent.

    Args:
        skills: List of skill objects

    Returns:
        Validated skills list

    Raises:
        ValueError: If duplicate skill IDs are found
    """
    if not skills:
        return skills

    skill_ids = [skill.id for skill in skills]
    duplicates = [sid for sid in skill_ids if skill_ids.count(sid) > 1]

    if duplicates:
        unique_duplicates = list(set(duplicates))
        raise ValueError(f"Duplicate skill IDs found: {', '.join(unique_duplicates)}")

    return skills


def _validate_security_references(
    security: Optional[List[Dict[str, List[str]]]],
    security_schemes: Dict[str, "SecurityScheme"],
) -> Optional[List[Dict[str, List[str]]]]:
    """
    Validate that security references exist in security_schemes.

    Args:
        security: Security requirements array
        security_schemes: Available security schemes

    Returns:
        Validated security array

    Raises:
        ValueError: If referenced security scheme does not exist
    """
    if not security:
        return security

    for requirement in security:
        for scheme_name in requirement.keys():
            if scheme_name not in security_schemes:
                raise ValueError(
                    f"Security requirement references undefined scheme: {scheme_name}"
                )

    return security


class SecurityScheme(BaseModel):
    """
    Security scheme for agent authentication.

    Supports various authentication methods including OAuth2, bearer tokens,
    API keys, and OpenID Connect.
    """

    type: str = Field(
        ...,
        description="Security type: apiKey, http, oauth2, openIdConnect",
    )
    scheme: Optional[str] = Field(
        None,
        description="HTTP auth scheme: basic, bearer, digest",
    )
    in_: Optional[str] = Field(
        None,
        alias="in",
        description="API key location: header, query, cookie",
    )
    name: Optional[str] = Field(
        None,
        description="Name of header/query/cookie for API key",
    )
    bearer_format: Optional[str] = Field(
        None,
        description="Bearer token format hint (e.g., JWT)",
    )
    flows: Optional[Dict[str, Any]] = Field(
        None,
        description="OAuth2 flows configuration",
    )
    openid_connect_url: Optional[HttpUrl] = Field(
        None,
        description="OpenID Connect discovery URL",
    )

    @field_validator("type")
    @classmethod
    def _validate_security_type(
        cls,
        v: str,
    ) -> str:
        """Validate security type is one of the supported types."""
        valid_types = ["apiKey", "http", "oauth2", "openIdConnect"]
        if v not in valid_types:
            raise ValueError(
                f"Security type must be one of: {', '.join(valid_types)}"
            )
        return v

    @field_validator("in_")
    @classmethod
    def _validate_api_key_location(
        cls,
        v: Optional[str],
    ) -> Optional[str]:
        """Validate API key location."""
        if v is not None:
            valid_locations = ["header", "query", "cookie"]
            if v not in valid_locations:
                raise ValueError(
                    f"API key location must be one of: {', '.join(valid_locations)}"
                )
        return v


class Skill(BaseModel):
    """
    Agent skill definition.

    A skill represents a discrete capability that an agent can perform.
    Each skill has a unique ID, name, description, and optional parameters
    defined using JSON Schema.
    """

    id: str = Field(
        ...,
        description="Unique skill identifier",
    )
    name: str = Field(
        ...,
        description="Human-readable skill name",
    )
    description: str = Field(
        ...,
        description="Detailed skill description",
    )
    parameters: Optional[Dict[str, Any]] = Field(
        None,
        description="JSON Schema for skill parameters",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Skill categorization tags",
    )

    @field_validator("id")
    @classmethod
    def _validate_skill_id(
        cls,
        v: str,
    ) -> str:
        """Validate skill ID format."""
        if not v:
            raise ValueError("Skill ID cannot be empty")
        if " " in v:
            raise ValueError("Skill ID cannot contain spaces")
        return v

    @field_validator("name")
    @classmethod
    def _validate_skill_name(
        cls,
        v: str,
    ) -> str:
        """Validate skill name."""
        if not v or not v.strip():
            raise ValueError("Skill name cannot be empty")
        return v.strip()


class AgentCard(BaseModel):
    """
    A2A Agent Card - machine-readable agent profile.

    This model represents a complete agent card following the A2A protocol
    specification, with extensions for MCP Gateway Registry integration.

    The agent card includes:
    - Required A2A fields (protocol_version, name, description, url)
    - Optional A2A fields (version, provider, skills, security, etc.)
    - MCP Gateway Registry extensions (path, tags, visibility, trust_level)
    """

    # Required A2A fields
    protocol_version: str = Field(
        ...,
        description="A2A protocol version (e.g., '1.0')",
    )
    name: str = Field(
        ...,
        description="Agent name",
    )
    description: str = Field(
        ...,
        description="Agent description",
    )
    url: HttpUrl = Field(
        ...,
        description="Agent endpoint URL",
    )

    # Optional A2A fields
    version: Optional[str] = Field(
        None,
        description="Agent version",
    )
    provider: Optional[str] = Field(
        None,
        description="Agent provider/author",
    )
    security_schemes: Dict[str, SecurityScheme] = Field(
        default_factory=dict,
        description="Supported authentication methods",
    )
    security: Optional[List[Dict[str, List[str]]]] = Field(
        None,
        description="Security requirements array",
    )
    skills: List[Skill] = Field(
        default_factory=list,
        description="Agent capabilities",
    )
    streaming: bool = Field(
        False,
        description="Supports streaming responses",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )

    # MCP Gateway Registry extensions
    path: str = Field(
        ...,
        description="Registry path (e.g., /agents/my-agent)",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Categorization tags",
    )
    is_enabled: bool = Field(
        False,
        description="Whether agent is enabled in registry",
    )
    num_stars: int = Field(
        0,
        ge=0,
        description="Community rating",
    )
    license: str = Field(
        "N/A",
        description="License information",
    )

    # Registry metadata
    registered_at: Optional[datetime] = Field(
        None,
        description="Registration timestamp",
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="Last update timestamp",
    )
    registered_by: Optional[str] = Field(
        None,
        description="Username who registered agent",
    )

    # Access control
    visibility: str = Field(
        "public",
        description="public, private, or group-restricted",
    )
    allowed_groups: List[str] = Field(
        default_factory=list,
        description="Groups with access",
    )

    # Validation and trust
    signature: Optional[str] = Field(
        None,
        description="JWS signature for card integrity",
    )
    trust_level: str = Field(
        "unverified",
        description="unverified, community, verified, trusted",
    )

    @field_validator("protocol_version")
    @classmethod
    def _validate_protocol_version_field(
        cls,
        v: str,
    ) -> str:
        """Validate protocol version format."""
        return _validate_protocol_version(v)

    @field_validator("path")
    @classmethod
    def _validate_path_field(
        cls,
        v: str,
    ) -> str:
        """Validate path format."""
        return _validate_path_format(v)

    @field_validator("visibility")
    @classmethod
    def _validate_visibility_field(
        cls,
        v: str,
    ) -> str:
        """Validate visibility value."""
        valid_values = ["public", "private", "group-restricted"]
        if v not in valid_values:
            raise ValueError(
                f"Visibility must be one of: {', '.join(valid_values)}"
            )
        return v

    @field_validator("trust_level")
    @classmethod
    def _validate_trust_level_field(
        cls,
        v: str,
    ) -> str:
        """Validate trust level value."""
        valid_levels = ["unverified", "community", "verified", "trusted"]
        if v not in valid_levels:
            raise ValueError(
                f"Trust level must be one of: {', '.join(valid_levels)}"
            )
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def _convert_tags_field(
        cls,
        v: Any,
    ) -> List[str]:
        """Convert tags from string or list format to list of strings.

        Supports both:
        - String format: "tag1,tag2,tag3"
        - List format: ["tag1", "tag2", "tag3"]
        """
        if isinstance(v, str):
            return [tag.strip() for tag in v.split(",") if tag.strip()]
        if isinstance(v, list):
            return [str(tag).strip() for tag in v if str(tag).strip()]
        return []

    @field_validator("skills")
    @classmethod
    def _validate_skills_field(
        cls,
        v: List[Skill],
    ) -> List[Skill]:
        """Validate skills have unique IDs."""
        return _validate_skill_ids_unique(v)

    @model_validator(mode="after")
    def _validate_security_requirements(
        self,
    ) -> "AgentCard":
        """Validate security requirements reference existing schemes."""
        if self.security is not None:
            _validate_security_references(self.security, self.security_schemes)
        return self

    @model_validator(mode="after")
    def _validate_group_restricted_access(
        self,
    ) -> "AgentCard":
        """Validate group-restricted visibility has allowed groups."""
        if self.visibility == "group-restricted" and not self.allowed_groups:
            raise ValueError(
                "Group-restricted visibility requires at least one allowed group"
            )
        return self


class AgentInfo(BaseModel):
    """
    Simplified agent information for listing and search.

    This lightweight model is used for agent discovery results and listings,
    containing only the essential information needed for agent selection.
    """

    name: str = Field(
        ...,
        description="Agent name",
    )
    description: str = Field(
        default="",
        description="Agent description",
    )
    path: str = Field(
        ...,
        description="Registry path",
    )
    url: str = Field(
        ...,
        description="Agent endpoint URL",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Categorization tags",
    )
    skills: List[str] = Field(
        default_factory=list,
        description="Skill names only",
    )
    num_skills: int = Field(
        0,
        ge=0,
        description="Number of skills",
    )
    num_stars: int = Field(
        0,
        ge=0,
        description="Community rating",
    )
    is_enabled: bool = Field(
        False,
        description="Whether agent is enabled",
    )
    provider: Optional[str] = Field(
        None,
        description="Agent provider/author",
    )
    streaming: bool = Field(
        False,
        description="Supports streaming responses",
    )
    trust_level: str = Field(
        "unverified",
        description="unverified, community, verified, trusted",
    )


class AgentRegistrationRequest(BaseModel):
    """
    API request model for agent registration.

    This model is used for the agent registration API endpoint and converts
    form-style inputs (e.g., comma-separated tags) into the proper types.
    """

    name: str = Field(
        ...,
        min_length=1,
        description="Agent name",
    )
    description: str = Field(
        default="",
        description="Agent description",
    )
    url: str = Field(
        ...,
        min_length=1,
        description="Agent endpoint URL",
    )
    path: str = Field(
        ...,
        min_length=1,
        description="Registry path",
    )
    protocol_version: str = Field(
        default="1.0",
        description="A2A protocol version",
    )
    version: Optional[str] = Field(
        None,
        description="Agent version",
    )
    provider: Optional[str] = Field(
        None,
        description="Agent provider/author",
    )
    security_schemes: Optional[Dict[str, Dict[str, Any]]] = Field(
        None,
        description="Security schemes configuration",
    )
    skills: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Agent skills",
    )
    streaming: bool = Field(
        False,
        description="Supports streaming responses",
    )
    tags: str = Field(
        default="",
        description="Comma-separated tags",
    )
    license: str = Field(
        default="N/A",
        description="License information",
    )
    visibility: str = Field(
        default="public",
        description="Visibility: public, private, or group-restricted",
    )

    @field_validator("path")
    @classmethod
    def _validate_path_request(
        cls,
        v: str,
    ) -> str:
        """Validate path format."""
        return _validate_path_format(v)

    @field_validator("protocol_version")
    @classmethod
    def _validate_protocol_version_request(
        cls,
        v: str,
    ) -> str:
        """Validate protocol version format."""
        return _validate_protocol_version(v)
