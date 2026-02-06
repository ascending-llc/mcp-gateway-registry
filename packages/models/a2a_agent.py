"""
MongoDB ODM Schema for A2A (Agent-to-Agent) Agents

This module defines the MongoDB Document schema for A2A agents following
the A2A protocol specification (v0.3.0 / v1.0).

Key Features:
- Beanie ODM for MongoDB integration
- A2A protocol compliance (protocolVersion, capabilities, skills, securitySchemes)
- Registry metadata (scope, status, tags, visibility, trust_level)
- Well-known configuration for manual .well-known sync
- Access control (visibility, allowed_groups)
- Audit trail (author, registered_by, timestamps)

Storage Structure:
{
  "_id": ObjectId("..."),
  
  # A2A Protocol Fields
  "path": "/deep-intel",
  "name": "Deep Intel Agent",
  "description": "Orchestrates AWS research and BI into full report",
  "url": "https://strandsagents.com/agents/deep-intel",
  "version": "0.1.0",
  "protocolVersion": "0.3.0",
  "capabilities": {"streaming": true, "pushNotifications": false},
  "skills": [{"id": "...", "name": "...", "description": "...", "tags": [...]}],
  "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
  "preferredTransport": "HTTP+JSON",
  "defaultInputModes": ["text/plain", "application/json"],
  "defaultOutputModes": ["application/json", "text/plain"],
  "provider": {"organization": "...", "url": "..."},
  
  # Registry Metadata
  "tags": ["aws", "research", "intelligence"],
  "scope": "private_user",
  "status": "active",
  "visibility": "public",
  "trustLevel": "verified",
  "isEnabled": true,
  
  # Ratings & Stats
  "numStars": 142,
  "numRatings": 87,
  "avgRating": 4.7,
  "ratingDetails": [{"username": "...", "rating": 5, "timestamp": "..."}],
  "accessCount": 1543,
  "lastAccessed": ISODate("..."),
  
  # Well-known Configuration
  "wellKnown": {
    "enabled": true,
    "url": "https://strandsagents.com/.well-known/agent-card.json",
    "lastSyncAt": ISODate("..."),
    "lastSyncStatus": "success",
    "lastSyncVersion": "0.1.0",
    "syncError": null
  },
  
  # Audit Trail
  "author": ObjectId("..."),
  "registeredBy": "service-account-mcp-gateway-m2m",
  "registeredAt": ISODate("..."),
  "createdAt": ISODate("..."),
  "updatedAt": ISODate("...")
}
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional, Set

from beanie import Document, PydanticObjectId, before_event, Insert, Replace, Save
from pydantic import BaseModel, Field, HttpUrl, ConfigDict, field_validator, model_validator
from pymongo import IndexModel, ASCENDING

logger = logging.getLogger(__name__)


# ========== Constants ==========

# A2A Protocol Transport Types
TRANSPORT_JSONRPC = "JSONRPC"
TRANSPORT_GRPC = "GRPC"
TRANSPORT_HTTP_JSON = "HTTP+JSON"
VALID_TRANSPORTS: Set[str] = {TRANSPORT_JSONRPC, TRANSPORT_GRPC, TRANSPORT_HTTP_JSON}

# Registry Visibility Levels
VISIBILITY_PUBLIC = "public"
VISIBILITY_PRIVATE = "private"
VISIBILITY_GROUP_RESTRICTED = "group-restricted"
VALID_VISIBILITY_VALUES: Set[str] = {VISIBILITY_PUBLIC, VISIBILITY_PRIVATE, VISIBILITY_GROUP_RESTRICTED}

# Registry Trust Levels
TRUST_LEVEL_UNVERIFIED = "unverified"
TRUST_LEVEL_COMMUNITY = "community"
TRUST_LEVEL_VERIFIED = "verified"
TRUST_LEVEL_TRUSTED = "trusted"
VALID_TRUST_LEVELS: Set[str] = {TRUST_LEVEL_UNVERIFIED, TRUST_LEVEL_COMMUNITY, TRUST_LEVEL_VERIFIED, TRUST_LEVEL_TRUSTED}

# Registry Scope Levels
SCOPE_SHARED_APP = "shared_app"
SCOPE_SHARED_USER = "shared_user"
SCOPE_PRIVATE_USER = "private_user"
VALID_SCOPES: Set[str] = {SCOPE_SHARED_APP, SCOPE_SHARED_USER, SCOPE_PRIVATE_USER}

# Registry Status Values
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_ERROR = "error"
VALID_STATUSES: Set[str] = {STATUS_ACTIVE, STATUS_INACTIVE, STATUS_ERROR}

# MIME Type Validation Pattern
MIME_TYPE_PATTERN = re.compile(r'^[\w\-]+/[\w\-+.]+$')


# ========== Nested Models ==========

class AgentSkill(BaseModel):
    """A2A protocol skill definition."""
    id: str = Field(..., description="Unique skill identifier")
    name: str = Field(..., description="Human-readable skill name")
    description: str = Field(..., description="Detailed skill description")
    tags: List[str] = Field(default_factory=list, description="Skill categorization tags")
    examples: Optional[List[str]] = Field(None, description="Usage examples")
    inputModes: Optional[List[str]] = Field(None, description="Skill-specific input MIME types")
    outputModes: Optional[List[str]] = Field(None, description="Skill-specific output MIME types")
    security: Optional[List[Dict[str, List[str]]]] = Field(
        None,
        description="Skill-level security requirements"
    )
    
    model_config = ConfigDict(populate_by_name=True)


class AgentProvider(BaseModel):
    """A2A protocol provider information."""
    organization: str = Field(..., description="Provider organization name")
    url: str = Field(..., description="Provider website or documentation URL")
    
    model_config = ConfigDict(populate_by_name=True)


class WellKnownConfig(BaseModel):
    """Manual .well-known sync configuration."""
    enabled: bool = Field(False, description="Whether well-known sync is enabled")
    url: Optional[HttpUrl] = Field(None, description="URL to .well-known/agent-card.json")
    
    # Sync metadata (manual refresh only)
    lastSyncAt: Optional[datetime] = Field(None, description="Last successful sync timestamp")
    lastSyncStatus: Optional[str] = Field(None, description="success | failed | unreachable")
    lastSyncVersion: Optional[str] = Field(None, description="Agent version from last sync")
    syncError: Optional[str] = Field(None, description="Error message from last sync attempt")
    
    model_config = ConfigDict(populate_by_name=True)


class RatingDetail(BaseModel):
    """Individual user rating detail."""
    username: str = Field(..., description="User who submitted the rating")
    rating: int = Field(..., ge=1, le=5, description="Rating value (1-5)")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When rating was submitted"
    )
    comment: Optional[str] = Field(None, description="Optional rating comment")
    
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
    """
    
    # ========== A2A Protocol Fields (Core) ==========
    path: str = Field(..., description="Registry path (e.g., /deep-intel)")
    name: str = Field(..., description="Agent name")
    description: str = Field(default="", description="Agent description")
    url: HttpUrl = Field(..., description="Agent endpoint URL")
    version: str = Field(..., description="Agent version")
    protocolVersion: str = Field(default="1.0", description="A2A protocol version")
    
    # A2A Capabilities
    capabilities: Dict[str, Any] = Field(
        default_factory=dict,
        description="Feature declarations (e.g., {'streaming': true, 'pushNotifications': false})"
    )
    skills: List[AgentSkill] = Field(
        default_factory=list,
        description="Agent capabilities (skills)"
    )
    securitySchemes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Supported authentication methods"
    )
    security: Optional[List[Dict[str, List[str]]]] = Field(
        None,
        description="Security requirements array"
    )
    
    # A2A Transport & I/O
    preferredTransport: str = Field(
        default="JSONRPC",
        description="Preferred transport protocol: JSONRPC, GRPC, HTTP+JSON"
    )
    defaultInputModes: List[str] = Field(
        default_factory=lambda: ["text/plain"],
        description="Supported input MIME types"
    )
    defaultOutputModes: List[str] = Field(
        default_factory=lambda: ["text/plain"],
        description="Supported output MIME types"
    )
    
    # A2A Provider Info
    provider: Optional[AgentProvider] = Field(None, description="Agent provider information")
    
    # A2A Additional Fields
    iconUrl: Optional[str] = Field(None, description="Agent icon URL")
    documentationUrl: Optional[str] = Field(None, description="Documentation URL")
    additionalInterfaces: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Additional transport interfaces"
    )
    supportsAuthenticatedExtendedCard: Optional[bool] = Field(
        None,
        description="Supports extended card with authentication"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom metadata"
    )
    
    # ========== Registry Metadata ==========
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    scope: str = Field(
        default="private_user",
        description="Access level: shared_app, shared_user, private_user"
    )
    status: str = Field(
        default="active",
        description="Operational state: active, inactive, error"
    )
    visibility: str = Field(
        default="public",
        description="Visibility: public, private, group-restricted"
    )
    allowedGroups: List[str] = Field(
        default_factory=list,
        description="Groups with access (for group-restricted visibility)"
    )
    trustLevel: str = Field(
        default="unverified",
        description="Verification status: unverified, community, verified, trusted"
    )
    isEnabled: bool = Field(default=False, description="Whether agent is enabled in registry")
    license: str = Field(default="N/A", description="License information")
    signature: Optional[str] = Field(None, description="JWS signature for card integrity")
    
    # ========== Ratings & Statistics ==========
    numStars: float = Field(default=0.0, ge=0.0, le=5.0, description="Average community rating")
    numRatings: int = Field(default=0, ge=0, description="Total number of ratings")
    avgRating: float = Field(default=0.0, ge=0.0, le=5.0, description="Average rating (same as numStars)")
    ratingDetails: List[RatingDetail] = Field(
        default_factory=list,
        description="Individual user ratings"
    )
    accessCount: int = Field(default=0, ge=0, description="Number of times agent was accessed")
    lastAccessed: Optional[datetime] = Field(None, description="Last access timestamp")
    
    # ========== Well-known Configuration ==========
    wellKnown: Optional[WellKnownConfig] = Field(
        None,
        description="Manual .well-known sync configuration"
    )
    
    # ========== Audit Trail ==========
    author: Optional[PydanticObjectId] = Field(None, description="User who created this agent")
    registeredBy: Optional[str] = Field(None, description="Username or service account who registered")
    registeredAt: Optional[datetime] = Field(None, description="Registration timestamp")
    createdAt: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp"
    )
    updatedAt: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp"
    )
    
    # ========== Settings ==========
    class Settings:
        name = "a2a_agents"
        use_state_management = True
        keep_nulls = False
        
        # Indexes for efficient queries
        indexes = [
            IndexModel([("path", ASCENDING)], unique=True),  # Unique index on path
            "tags",                                          # Tag-based filtering
            "visibility",                                    # Visibility filtering
            "isEnabled",                                     # Enabled/disabled filtering
            [("registeredAt", -1)],                          # Chronological ordering (newest first)
            "trustLevel",                                    # Trust level filtering
            [("name", "text")],                              # Text search on name
            [("isEnabled", 1), ("visibility", 1)],           # Compound: enabled + visibility
            [("registeredBy", 1)],                           # Filter by user
            [("tags", 1), ("isEnabled", 1)],                 # Compound: tags + enabled
            [("trustLevel", 1), ("isEnabled", 1)],           # Compound: trust + enabled
            [("scope", 1)],                                  # Scope filtering
            [("status", 1)],                                 # Status filtering
        ]
    
    # ========== Lifecycle Hooks ==========
    @before_event(Insert, Replace, Save)
    async def update_timestamps(self):
        """Update timestamps before saving."""
        self.updatedAt = datetime.now(timezone.utc)
        if not self.createdAt:
            self.createdAt = datetime.now(timezone.utc)
    
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
            skills_text = "\n".join([
                f"Skill {i+1}: {skill.name} - {skill.description} (Tags: {', '.join(skill.tags)})"
                for i, skill in enumerate(self.skills)
            ])
            parts.append(f"Skills:\n{skills_text}")
        
        # Add tags
        if self.tags:
            parts.append(f"Tags: {', '.join(self.tags)}")
        
        # Add provider info
        if self.provider:
            parts.append(f"Provider: {self.provider.organization}")
        
        return "\n".join(parts)
    
    def calculate_average_rating(self) -> float:
        """
        Calculate average rating from rating details.
        
        Returns:
            Average rating (0.0 if no ratings)
        """
        if not self.ratingDetails:
            return 0.0
        
        total = sum(r.rating for r in self.ratingDetails)
        return round(total / len(self.ratingDetails), 2)
    
    def update_rating_stats(self):
        """
        Update rating statistics (numStars, numRatings, avgRating).
        
        Call this method after modifying ratingDetails.
        """
        self.numRatings = len(self.ratingDetails)
        self.avgRating = self.calculate_average_rating()
        self.numStars = self.avgRating  # Keep in sync
    
    def increment_access_count(self):
        """Increment access count and update last accessed timestamp."""
        self.accessCount += 1
        self.lastAccessed = datetime.now(timezone.utc)
    
    def is_accessible_by_user(self, username: str, user_groups: List[str], is_admin: bool = False) -> bool:
        """
        Check if user can access this agent.
        
        Args:
            username: Username
            user_groups: User's group memberships
            is_admin: Whether user is admin
        
        Returns:
            True if user can access agent
        """
        # Admins can access everything
        if is_admin:
            return True
        
        # Check visibility
        if self.visibility == "public":
            return True
        
        if self.visibility == "private":
            return self.registeredBy == username
        
        if self.visibility == "group-restricted":
            return bool(set(user_groups) & set(self.allowedGroups))
        
        return False
    
    def to_a2a_agent_card(self) -> Dict[str, Any]:
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
    def from_a2a_agent_card(
        cls,
        card: Dict[str, Any],
        path: Optional[str] = None,
        **registry_fields
    ) -> "A2AAgent":
        """
        Create A2AAgent from standard A2A agent card.
        
        This method imports a standard A2A agent card (e.g., from .well-known endpoint)
        and creates a registry entry with additional registry metadata.
        
        Args:
            card: A2A agent card dictionary
            path: Registry path (auto-generated from name if not provided)
            **registry_fields: Additional registry metadata such as:
                - scope: Access level (default: "private_user")
                - visibility: Visibility (default: "public")
                - trustLevel: Trust level (default: "unverified")
                - isEnabled: Enabled state (default: False)
                - registeredBy: Username
                - tags: List of tags
        
        Returns:
            A2AAgent instance
        
        Raises:
            ValueError: If required A2A fields are missing
        """
        # Validate required fields
        required_fields = ["name", "version", "url"]
        missing_fields = [f for f in required_fields if f not in card]
        if missing_fields:
            raise ValueError(f"Missing required A2A fields: {', '.join(missing_fields)}")
        
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
            scope=registry_fields.get("scope", SCOPE_PRIVATE_USER),
            visibility=registry_fields.get("visibility", VISIBILITY_PUBLIC),
            trustLevel=registry_fields.get("trustLevel", TRUST_LEVEL_UNVERIFIED),
            isEnabled=registry_fields.get("isEnabled", False),
            tags=registry_fields.get("tags", []),
            registeredBy=registry_fields.get("registeredBy"),
            registeredAt=registry_fields.get("registeredAt"),
        )
    
    # ========== Pydantic Configuration ==========
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None,
            HttpUrl: lambda v: str(v),
        },
        populate_by_name=True,
        use_enum_values=True,
    )
    
    # ========== Special Methods ==========
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"A2AAgent(id={self.id}, path='{self.path}', name='{self.name}', "
            f"version='{self.version}', isEnabled={self.isEnabled}, "
            f"trustLevel='{self.trustLevel}')"
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
    
    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: str) -> str:
        """Validate visibility value."""
        if v not in VALID_VISIBILITY_VALUES:
            raise ValueError(f"Visibility must be one of: {', '.join(sorted(VALID_VISIBILITY_VALUES))}")
        return v
    
    @field_validator("trustLevel")
    @classmethod
    def validate_trust_level(cls, v: str) -> str:
        """Validate trust level value."""
        if v not in VALID_TRUST_LEVELS:
            raise ValueError(f"Trust level must be one of: {', '.join(sorted(VALID_TRUST_LEVELS))}")
        return v
    
    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        """Validate scope value."""
        if v not in VALID_SCOPES:
            raise ValueError(f"Scope must be one of: {', '.join(sorted(VALID_SCOPES))}")
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
    def validate_mime_types(cls, v: List[str]) -> List[str]:
        """Validate MIME type format (A2A Protocol compliance)."""
        for mime in v:
            if not MIME_TYPE_PATTERN.match(mime):
                raise ValueError(f"Invalid MIME type format: {mime}")
        return v
    
    @field_validator("skills")
    @classmethod
    def validate_skills_unique_ids(cls, v: List[AgentSkill]) -> List[AgentSkill]:
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
    def validate_group_restricted_access(self) -> "A2AAgent":
        """Validate group-restricted visibility has allowed groups."""
        if self.visibility == "group-restricted" and not self.allowedGroups:
            raise ValueError(
                "Group-restricted visibility requires at least one allowed group"
            )
        return self
    
    @model_validator(mode="after")
    def validate_security_references(self) -> "A2AAgent":
        """Validate security requirements reference existing schemes."""
        if self.security:
            for requirement in self.security:
                for scheme_name in requirement.keys():
                    if scheme_name not in self.securitySchemes:
                        raise ValueError(
                            f"Security requirement references undefined scheme: {scheme_name}"
                        )
        return self
