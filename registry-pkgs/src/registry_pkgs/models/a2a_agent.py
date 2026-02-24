"""
MongoDB ODM Schema for A2A (Agent-to-Agent) Agents

This module defines the MongoDB Document schema for A2A agents following

Storage Structure:
{
  "_id": ObjectId("..."),

  # A2A Protocol Fields (Core)
  "path": "/deep-intel",
  "name": "Deep Intel Agent",
  "description": "Orchestrates AWS research and BI into full report",
  "url": "https://strandsagents.com/agents/deep-intel",
  "version": "0.1.0",
  "protocolVersion": "1.0",

  # A2A Capabilities
  "capabilities": {"streaming": true, "pushNotifications": false},
  "skills": [
    {
      "id": "research-skill",
      "name": "AWS Research",
      "description": "Deep research on AWS services",
      "tags": ["aws", "research"],
      "inputModes": ["text/plain"],
      "outputModes": ["application/json"]
    }
  ],
  "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
  "security": [{"bearer": []}],  # Optional

  # A2A Transport & I/O
  "preferredTransport": "HTTP+JSON",
  "defaultInputModes": ["text/plain", "application/json"],
  "defaultOutputModes": ["application/json", "text/plain"],

  # A2A Provider & Additional Info
  "provider": {"organization": "Strands AI", "url": "https://strandsagents.com"},
  "iconUrl": "https://strandsagents.com/icons/deep-intel.png",  # Optional
  "documentationUrl": "https://strandsagents.com/docs/deep-intel",  # Optional
  "additionalInterfaces": [],  # Optional
  "supportsAuthenticatedExtendedCard": true,  # Optional
  "metadata": {},  # Optional custom metadata

  # Registry Metadata
  "tags": ["ai", "research", "aws"],
  "status": "active",
  "isEnabled": true,
  "license": "MIT",
  "signature": "eyJhbGc...",  # Optional JWS signature

  # Well-known Configuration
  "wellKnown": {
    "enabled": true,
    "url": "https://strandsagents.com/.well-known/agent-card.json",
    "lastSyncAt": ISODate("2024-01-20T12:00:00Z"),
    "lastSyncStatus": "success",
    "lastSyncVersion": "0.1.0",
    "syncError": null
  },

  # Audit Trail & Access Control
  "author": ObjectId("507f1f77bcf86cd799439011"),  # Required: User ID for ACL
  "registeredBy": "john.doe@example.com",
  "registeredAt": ISODate("2024-01-15T10:30:00Z"),
  "createdAt": ISODate("2024-01-15T10:30:00Z"),
  "updatedAt": ISODate("2024-01-20T15:45:00Z")
}
"""

import logging
import re
from datetime import UTC, datetime
from typing import Any, ClassVar

from beanie import Document, Insert, PydanticObjectId, Replace, Save, before_event
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from pymongo import IndexModel

logger = logging.getLogger(__name__)

# ========== Constants ==========

# A2A Protocol Transport Types
TRANSPORT_JSONRPC = "JSONRPC"
TRANSPORT_GRPC = "GRPC"
TRANSPORT_HTTP_JSON = "HTTP+JSON"
VALID_TRANSPORTS: set[str] = {TRANSPORT_JSONRPC, TRANSPORT_GRPC, TRANSPORT_HTTP_JSON}

# Registry Status Values
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_ERROR = "error"
VALID_STATUSES: set[str] = {STATUS_ACTIVE, STATUS_INACTIVE, STATUS_ERROR}

# MIME Type Validation Pattern
MIME_TYPE_PATTERN = re.compile(r"^[\w\-]+/[\w\-+.]+$")


# ========== Nested Models ==========


class AgentSkill(BaseModel):
    """A2A protocol skill definition."""

    id: str = Field(..., description="Unique skill identifier")
    name: str = Field(..., description="Human-readable skill name")
    description: str = Field(..., description="Detailed skill description")
    tags: list[str] = Field(default_factory=list, description="Skill categorization tags")
    examples: list[str] | None = Field(None, description="Usage examples")
    inputModes: list[str] | None = Field(None, description="Skill-specific input MIME types")
    outputModes: list[str] | None = Field(None, description="Skill-specific output MIME types")
    security: list[dict[str, list[str]]] | None = Field(None, description="Skill-level security requirements")

    model_config = ConfigDict(populate_by_name=True)


class AgentProvider(BaseModel):
    """A2A protocol provider information."""

    organization: str = Field(..., description="Provider organization name")
    url: str = Field(..., description="Provider website or documentation URL")

    model_config = ConfigDict(populate_by_name=True)


class WellKnownConfig(BaseModel):
    """Manual .well-known sync configuration."""

    enabled: bool = Field(False, description="Whether well-known sync is enabled")
    url: HttpUrl | None = Field(None, description="URL to .well-known/agent-card.json")

    # Sync metadata (manual refresh only)
    lastSyncAt: datetime | None = Field(None, description="Last successful sync timestamp")
    lastSyncStatus: str | None = Field(None, description="success | failed | unreachable")
    lastSyncVersion: str | None = Field(None, description="Agent version from last sync")
    syncError: str | None = Field(None, description="Error message from last sync attempt")

    model_config = ConfigDict(populate_by_name=True)


# ========== Main Document ==========


class A2AAgent(Document):
    """
    MongoDB Document for A2A Agents.

    This model represents a complete A2A agent following the A2A protocol specification,
    with extensions for MCP Gateway Registry integration.

    Design Principles:
    - Self-contained: No inheritance from other models
    - A2A compliant: Follows A2A protocol v0.3.0 / v1.0
    - Registry aware: Includes registry-specific metadata
    - Well-known support: Manual sync configuration for .well-known endpoints
    - ACL integration: Uses author field for ownership and ACLService for permissions

    Access Control:
    - Agent creation automatically creates ACL entry granting creator OWNER permissions
    - Update/Delete operations require appropriate ACL permissions (EDIT/DELETE)
    - Query operations filter based on ACL visibility (VIEW permission)
    - Permissions managed via ACLService using ResourceType.A2AAGENT
    """

    # ========== A2A Protocol Fields (Core) ==========
    path: str = Field(..., description="Registry path (e.g., /deep-intel)")
    name: str = Field(..., description="Agent name")
    description: str = Field(default="", description="Agent description")
    url: HttpUrl = Field(..., description="Agent endpoint URL")
    version: str = Field(..., description="Agent version")
    protocolVersion: str = Field(default="1.0", description="A2A protocol version")

    # A2A Capabilities
    capabilities: dict[str, Any] = Field(
        default_factory=dict, description="Feature declarations (e.g., {'streaming': true, 'pushNotifications': false})"
    )
    skills: list[AgentSkill] = Field(default_factory=list, description="Agent capabilities (skills)")
    securitySchemes: dict[str, Any] = Field(default_factory=dict, description="Supported authentication methods")
    security: list[dict[str, list[str]]] | None = Field(None, description="Security requirements array")

    # A2A Transport & I/O
    preferredTransport: str = Field(
        default="JSONRPC", description="Preferred transport protocol: JSONRPC, GRPC, HTTP+JSON"
    )
    defaultInputModes: list[str] = Field(
        default_factory=lambda: ["text/plain"], description="Supported input MIME types"
    )
    defaultOutputModes: list[str] = Field(
        default_factory=lambda: ["text/plain"], description="Supported output MIME types"
    )

    # A2A Provider Info
    provider: AgentProvider | None = Field(None, description="Agent provider information")

    # A2A Additional Fields
    iconUrl: str | None = Field(None, description="Agent icon URL")
    documentationUrl: str | None = Field(None, description="Documentation URL")
    additionalInterfaces: list[dict[str, Any]] = Field(
        default_factory=list, description="Additional transport interfaces"
    )
    supportsAuthenticatedExtendedCard: bool | None = Field(
        None, description="Supports extended card with authentication"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional custom metadata")

    # ========== Registry Metadata ==========
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    status: str = Field(default="active", description="Operational state: active, inactive, error")
    isEnabled: bool = Field(default=False, description="Whether agent is enabled in registry")
    license: str = Field(default="N/A", description="License information")
    signature: str | None = Field(None, description="JWS signature for card integrity")

    # ========== Well-known Configuration ==========
    wellKnown: WellKnownConfig | None = Field(None, description="Manual .well-known sync configuration")

    # ========== Audit Trail & Access Control ==========
    author: PydanticObjectId = Field(..., description="User who created/registered this agent (for ACL)")
    registeredBy: str | None = Field(None, description="Username or service account who registered")
    registeredAt: datetime | None = Field(None, description="Registration timestamp")
    createdAt: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Creation timestamp")
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Last update timestamp")

    # ========== Settings ==========
    class Settings:
        name = "a2a_agents"
        use_state_management = True
        keep_nulls = False

        # Indexes for efficient queries
        indexes = [
            IndexModel([("path", 1)], unique=True),  # Unique index on path
            "tags",  # Tag-based filtering
            "isEnabled",  # Enabled/disabled filtering
            [("name", "text")],  # Text search on name
            [("author", 1)],  # Filter by author (for ACL and user queries)
            [("registeredBy", 1)],  # Filter by registeredBy
            [("status", 1)],  # Status filtering
        ]

    # ========== Lifecycle Hooks ==========
    @before_event(Insert, Replace, Save)
    async def update_timestamps(self):
        """Update timestamps before saving."""
        self.updatedAt = datetime.now(UTC)
        if not self.createdAt:
            self.createdAt = datetime.now(UTC)

    # ========== Vector Search Integration ==========
    COLLECTION_NAME: ClassVar[str] = "a2a_agents"

    def to_searchable_text(self) -> str:
        """
        Generate searchable text for vector embedding.

        This text is used for semantic search via FAISS/Weaviate.

        Returns:
            Combined text representation of agent for embedding
        """
        parts = [
            f"Name: {self.name}",
            f"Description: {self.description}",
            f"Path: {self.path}",
        ]

        # Add skill information
        if self.skills:
            skills_text = "\n".join(
                [
                    f"Skill {i + 1}: {skill.name} - {skill.description} (Tags: {', '.join(skill.tags)})"
                    for i, skill in enumerate(self.skills)
                ]
            )
            parts.append(f"Skills:\n{skills_text}")

        # Add tags
        if self.tags:
            parts.append(f"Tags: {', '.join(self.tags)}")

        # Add provider info
        if self.provider:
            parts.append(f"Provider: {self.provider.organization}")

        return "\n".join(parts)

    def is_accessible_by_user(self, username: str, user_groups: list[str], is_admin: bool = False) -> bool:
        """
        DEPRECATED: Access control is now handled by ACL permissions.
        Use ACLService.check_user_permission() instead.

        This method is kept for backward compatibility and always returns True.

        Args:
            username: Username (unused)
            user_groups: User's group memberships (unused)
            is_admin: Whether user is admin (unused)

        Returns:
            Always returns True (use ACL system for actual access control)
        """
        logger.warning(
            "is_accessible_by_user() is deprecated. Use ACLService.check_user_permission() for access control."
        )
        return True

    def to_a2a_agent_card(self) -> dict[str, Any]:
        """
        Export A2A-compliant agent card (without registry metadata).

        This method generates a standard A2A agent card that can be served at
        the .well-known/agent-card.json endpoint or used with A2A SDK.

        Returns:
            Standard A2A agent card as dictionary
        """
        card = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "url": str(self.url),
            "protocolVersion": self.protocolVersion,
            "capabilities": self.capabilities,
            "skills": [skill.model_dump() for skill in self.skills],
            "securitySchemes": self.securitySchemes,
            "preferredTransport": self.preferredTransport,
            "defaultInputModes": self.defaultInputModes,
            "defaultOutputModes": self.defaultOutputModes,
        }

        # Add optional fields if present
        if self.security:
            card["security"] = self.security

        if self.provider:
            card["provider"] = self.provider.model_dump()

        if self.iconUrl:
            card["iconUrl"] = self.iconUrl

        if self.documentationUrl:
            card["documentationUrl"] = self.documentationUrl

        if self.additionalInterfaces:
            card["additionalInterfaces"] = self.additionalInterfaces

        if self.supportsAuthenticatedExtendedCard is not None:
            card["supportsAuthenticatedExtendedCard"] = self.supportsAuthenticatedExtendedCard

        if self.metadata:
            card["metadata"] = self.metadata

        return card

    @classmethod
    def from_a2a_agent_card(cls, card: dict[str, Any], path: str | None = None, **registry_fields) -> "A2AAgent":
        """
        Create A2AAgent from standard A2A agent card.

        This method imports a standard A2A agent card (e.g., from .well-known endpoint)
        and creates a registry entry with additional registry metadata.

        Args:
            card: A2A agent card dictionary
            path: Registry path (auto-generated from name if not provided)
            **registry_fields: Additional registry metadata such as:
                - author: User ID who created this agent (required for ACL)
                - isEnabled: Enabled state (default: False)
                - registeredBy: Username or service account
                - tags: List of tags

        Returns:
            A2AAgent instance

        Raises:
            ValueError: If required A2A fields or author field are missing
        """
        # Validate required fields
        required_fields = ["name", "version", "url"]
        missing_fields = [f for f in required_fields if f not in card]
        if missing_fields:
            raise ValueError(f"Missing required A2A fields: {', '.join(missing_fields)}")

        # Validate required registry fields
        if "author" not in registry_fields:
            raise ValueError("'author' field is required in registry_fields for ACL integration")

        # Auto-generate path if not provided
        if not path:
            path = "/" + card["name"].lower().replace(" ", "-")

        # Parse provider if exists
        provider = None
        if card.get("provider"):
            provider = AgentProvider(**card["provider"])

        # Parse skills
        skills = [AgentSkill(**skill) for skill in card.get("skills", [])]

        # Merge A2A fields with registry fields
        return cls(
            # A2A Protocol Fields
            name=card["name"],
            description=card.get("description", ""),
            version=card["version"],
            url=card["url"],
            protocolVersion=card.get("protocolVersion", "1.0"),
            capabilities=card.get("capabilities", {}),
            skills=skills,
            securitySchemes=card.get("securitySchemes", {}),
            security=card.get("security"),
            preferredTransport=card.get("preferredTransport", TRANSPORT_JSONRPC),
            defaultInputModes=card.get("defaultInputModes", ["text/plain"]),
            defaultOutputModes=card.get("defaultOutputModes", ["text/plain"]),
            provider=provider,
            iconUrl=card.get("iconUrl"),
            documentationUrl=card.get("documentationUrl"),
            additionalInterfaces=card.get("additionalInterfaces", []),
            supportsAuthenticatedExtendedCard=card.get("supportsAuthenticatedExtendedCard"),
            metadata=card.get("metadata", {}),
            # Registry Fields (from kwargs or defaults)
            path=path,
            author=registry_fields["author"],  # Required for ACL
            isEnabled=registry_fields.get("isEnabled", False),
            tags=registry_fields.get("tags", []),
            registeredBy=registry_fields.get("registeredBy"),
            registeredAt=registry_fields.get("registeredAt"),
        )

    # ========== Pydantic Configuration ==========
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
            HttpUrl: str,
        },
        populate_by_name=True,
        use_enum_values=True,
    )

    # ========== Special Methods ==========
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"A2AAgent(id={self.id}, path='{self.path}', name='{self.name}', "
            f"version='{self.version}', isEnabled={self.isEnabled})"
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"{self.name} v{self.version} ({self.path})"

    # ========== Field Validators ==========
    @field_validator("path")
    @classmethod
    def validate_path_format(cls, v: str) -> str:
        """Validate agent path format."""
        if not v.startswith("/"):
            raise ValueError("Path must start with '/'")
        if "//" in v:
            raise ValueError("Path cannot contain consecutive slashes")
        if v.endswith("/") and len(v) > 1:
            raise ValueError("Path cannot end with '/' unless it is root")
        return v

    @field_validator("protocolVersion")
    @classmethod
    def validate_protocol_version(cls, v: str) -> str:
        """Validate A2A protocol version format."""
        if not v:
            raise ValueError("Protocol version cannot be empty")
        parts = v.split(".")
        if len(parts) < 2:
            raise ValueError("Protocol version must be in format 'X.Y' or 'X.Y.Z'")
        for part in parts:
            if not part.isdigit():
                raise ValueError("Protocol version parts must be numeric")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status value."""
        if v not in VALID_STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(sorted(VALID_STATUSES))}")
        return v

    @field_validator("preferredTransport")
    @classmethod
    def validate_preferred_transport(cls, v: str) -> str:
        """Validate preferredTransport value (A2A Protocol compliance)."""
        if v not in VALID_TRANSPORTS:
            raise ValueError(f"Transport must be one of: {', '.join(sorted(VALID_TRANSPORTS))}")
        return v

    @field_validator("defaultInputModes", "defaultOutputModes")
    @classmethod
    def validate_mime_types(cls, v: list[str]) -> list[str]:
        """Validate MIME type format (A2A Protocol compliance)."""
        for mime in v:
            if not MIME_TYPE_PATTERN.match(mime):
                raise ValueError(f"Invalid MIME type format: {mime}")
        return v

    @field_validator("skills")
    @classmethod
    def validate_skills_unique_ids(cls, v: list[AgentSkill]) -> list[AgentSkill]:
        """Validate that skill IDs are unique."""
        if not v:
            return v

        skill_ids = [skill.id for skill in v]
        duplicates = [sid for sid in skill_ids if skill_ids.count(sid) > 1]

        if duplicates:
            unique_duplicates = list(set(duplicates))
            raise ValueError(f"Duplicate skill IDs found: {', '.join(unique_duplicates)}")

        return v

    @model_validator(mode="after")
    def validate_security_references(self) -> "A2AAgent":
        """Validate security requirements reference existing schemes."""
        if self.security:
            for requirement in self.security:
                for scheme_name in requirement:
                    if scheme_name not in self.securitySchemes:
                        raise ValueError(f"Security requirement references undefined scheme: {scheme_name}")
        return self
