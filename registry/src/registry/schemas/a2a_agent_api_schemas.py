"""
Pydantic Schemas for A2A Agent Management API v1

These schemas define the request and response models for the
A2A Agent Management endpoints based on the API documentation.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from registry.schemas.acl_schema import ResourcePermissions

# ==================== Nested Models ====================


class AgentSkillInput(BaseModel):
    """Input schema for agent skill"""

    id: str = Field(description="Unique skill identifier")
    name: str = Field(description="Human-readable skill name")
    description: str = Field(description="Detailed skill description")
    tags: list[str] = Field(default_factory=list, description="Skill categorization tags")
    examples: list[str] | None = Field(None, description="Usage examples")
    input_modes: list[str] | None = Field(None, alias="inputModes", description="Skill-specific input MIME types")
    output_modes: list[str] | None = Field(None, alias="outputModes", description="Skill-specific output MIME types")
    security: list[dict[str, list[str]]] | None = Field(None, description="Skill-level security requirements")

    class Config:
        populate_by_name = True


class AgentSkillOutput(BaseModel):
    """Output schema for agent skill"""

    id: str
    name: str
    description: str
    tags: list[str] = []
    input_modes: list[str] | None = Field(None, alias="inputModes")
    output_modes: list[str] | None = Field(None, alias="outputModes")

    class Config:
        populate_by_name = True


class AgentProviderInput(BaseModel):
    """Input schema for agent provider"""

    organization: str = Field(description="Provider organization name")
    url: str = Field(description="Provider website or documentation URL")


class AgentProviderOutput(BaseModel):
    """Output schema for agent provider"""

    organization: str
    url: str


class WellKnownInfo(BaseModel):
    """Well-known configuration info"""

    enabled: bool
    url: str | None = None
    last_sync_at: datetime | None = Field(None, alias="lastSyncAt")
    last_sync_status: str | None = Field(None, alias="lastSyncStatus")
    last_sync_version: str | None = Field(None, alias="lastSyncVersion")

    class Config:
        populate_by_name = True


# ==================== Request Schemas ====================


class AgentCreateRequest(BaseModel):
    """Request schema for creating a new agent"""

    path: str = Field(description="Registry path (e.g., /code-reviewer)")
    name: str = Field(description="Agent name")
    description: str = Field(default="", description="Agent description")
    url: HttpUrl | str = Field(description="Agent endpoint URL")
    version: str = Field(description="Agent version")
    protocol_version: str = Field(default="1.0", alias="protocolVersion", description="A2A protocol version")
    capabilities: dict[str, Any] = Field(
        default_factory=dict, description="Feature declarations (e.g., {'streaming': true})"
    )
    skills: list[AgentSkillInput] = Field(default_factory=list, description="Agent capabilities (skills)")
    security_schemes: dict[str, Any] = Field(
        default_factory=dict, alias="securitySchemes", description="Supported authentication methods"
    )
    preferred_transport: str = Field(
        default="HTTP+JSON", alias="preferredTransport", description="Preferred transport protocol"
    )
    default_input_modes: list[str] = Field(
        default_factory=lambda: ["text/plain"], alias="defaultInputModes", description="Supported input MIME types"
    )
    default_output_modes: list[str] = Field(
        default_factory=lambda: ["application/json"],
        alias="defaultOutputModes",
        description="Supported output MIME types",
    )
    provider: AgentProviderInput | None = Field(None, description="Agent provider information")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    enabled: bool = Field(default=False, description="Whether agent is enabled in registry")

    class Config:
        populate_by_name = True


class AgentUpdateRequest(BaseModel):
    """Request schema for updating an agent (partial update)"""

    name: str | None = None
    description: str | None = None
    version: str | None = None
    skills: list[AgentSkillInput] | None = None
    tags: list[str] | None = None
    enabled: bool | None = None
    capabilities: dict[str, Any] | None = None
    security_schemes: dict[str, Any] | None = Field(None, alias="securitySchemes")
    preferred_transport: str | None = Field(None, alias="preferredTransport")
    default_input_modes: list[str] | None = Field(None, alias="defaultInputModes")
    default_output_modes: list[str] | None = Field(None, alias="defaultOutputModes")
    provider: AgentProviderInput | None = None

    class Config:
        populate_by_name = True


class AgentToggleRequest(BaseModel):
    """Request schema for toggling agent status"""

    enabled: bool = Field(description="New enabled state")


# ==================== Response Schemas ====================


class PaginationMetadata(BaseModel):
    """Pagination metadata"""

    total: int
    page: int
    per_page: int = Field(alias="perPage")
    total_pages: int = Field(alias="totalPages")

    class Config:
        populate_by_name = True


class AgentListItem(BaseModel):
    """Agent item in list response"""

    id: str
    path: str
    name: str
    description: str
    url: str
    version: str
    protocol_version: str = Field(alias="protocolVersion")
    tags: list[str]
    num_skills: int = Field(alias="numSkills")
    enabled: bool
    status: str
    permissions: ResourcePermissions
    author: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    class Config:
        populate_by_name = True


class AgentListResponse(BaseModel):
    """Response schema for listing agents"""

    agents: list[AgentListItem]
    pagination: PaginationMetadata


class AgentStatsResponse(BaseModel):
    """Response schema for agent statistics"""

    total_agents: int = Field(alias="totalAgents")
    enabled_agents: int = Field(alias="enabledAgents")
    disabled_agents: int = Field(alias="disabledAgents")
    by_status: dict[str, int] = Field(alias="byStatus")
    by_transport: dict[str, int] = Field(alias="byTransport")
    total_skills: int = Field(alias="totalSkills")
    average_skills_per_agent: float = Field(alias="averageSkillsPerAgent")

    class Config:
        populate_by_name = True


class AgentDetailResponse(BaseModel):
    """Response schema for agent detail"""

    id: str
    path: str
    name: str
    description: str
    url: str
    version: str
    protocol_version: str = Field(alias="protocolVersion")
    capabilities: dict[str, Any]
    skills: list[AgentSkillOutput]
    security_schemes: dict[str, Any] = Field(alias="securitySchemes")
    preferred_transport: str = Field(alias="preferredTransport")
    default_input_modes: list[str] = Field(alias="defaultInputModes")
    default_output_modes: list[str] = Field(alias="defaultOutputModes")
    provider: AgentProviderOutput | None = None
    tags: list[str]
    status: str
    enabled: bool
    permissions: ResourcePermissions
    author: str
    well_known: WellKnownInfo | None = Field(None, alias="wellKnown")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    class Config:
        populate_by_name = True


class AgentCreateResponse(BaseModel):
    """Response schema for creating an agent"""

    message: str
    agent: AgentDetailResponse


class AgentUpdateResponse(BaseModel):
    """Response schema for updating an agent"""

    message: str
    agent: AgentDetailResponse


class AgentToggleResponse(BaseModel):
    """Response schema for toggling agent"""

    message: str
    agent: AgentDetailResponse


class AgentSkillsResponse(BaseModel):
    """Response schema for agent skills"""

    agent_id: str = Field(alias="agentId")
    agent_name: str = Field(alias="agentName")
    skills: list[AgentSkillOutput]
    total_skills: int = Field(alias="totalSkills")

    class Config:
        populate_by_name = True


class WellKnownSyncResponse(BaseModel):
    """Response schema for well-known sync"""

    message: str
    sync_status: str = Field(alias="syncStatus")
    synced_at: datetime = Field(alias="syncedAt")
    version: str
    changes: list[str]

    class Config:
        populate_by_name = True


# ==================== Converter Functions ====================


def convert_to_list_item(agent: Any, acl_permission: int | ResourcePermissions) -> AgentListItem:
    """Convert A2AAgent document to list item"""
    from registry_pkgs.models.enums import PermissionBits

    # Handle both int (permission bits) and ResourcePermissions object
    if isinstance(acl_permission, ResourcePermissions):
        permissions = acl_permission
    else:
        permissions = ResourcePermissions(
            VIEW=bool(acl_permission & PermissionBits.VIEW),
            EDIT=bool(acl_permission & PermissionBits.EDIT),
            DELETE=bool(acl_permission & PermissionBits.DELETE),
            SHARE=bool(acl_permission & PermissionBits.SHARE),
        )

    return AgentListItem(
        id=str(agent.id),
        path=agent.path,
        name=agent.card.name,
        description=agent.card.description,
        url=str(agent.card.url),
        version=agent.card.version,
        protocolVersion=agent.card.protocol_version,
        tags=agent.tags,
        numSkills=len(agent.card.skills or []),
        enabled=agent.isEnabled,
        status=agent.status,
        permissions=permissions,
        author=str(agent.author),
        createdAt=agent.createdAt,
        updatedAt=agent.updatedAt,
    )


def convert_to_detail(agent: Any, acl_permission: int | ResourcePermissions) -> AgentDetailResponse:
    """Convert A2AAgent document to detail response"""
    from registry_pkgs.models.enums import PermissionBits

    # Handle both int (permission bits) and ResourcePermissions object
    if isinstance(acl_permission, ResourcePermissions):
        permissions = acl_permission
    else:
        permissions = ResourcePermissions(
            VIEW=bool(acl_permission & PermissionBits.VIEW),
            EDIT=bool(acl_permission & PermissionBits.EDIT),
            DELETE=bool(acl_permission & PermissionBits.DELETE),
            SHARE=bool(acl_permission & PermissionBits.SHARE),
        )

    skills_output = [
        AgentSkillOutput(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            tags=skill.tags or [],
            inputModes=skill.input_modes if hasattr(skill, "input_modes") else None,
            outputModes=skill.output_modes if hasattr(skill, "output_modes") else None,
        )
        for skill in (agent.card.skills or [])
    ]

    provider_output = None
    if agent.card.provider:
        provider_output = AgentProviderOutput(
            organization=agent.card.provider.organization, url=agent.card.provider.url
        )

    well_known_info = None
    if agent.wellKnown:
        well_known_info = WellKnownInfo(
            enabled=agent.wellKnown.enabled,
            url=str(agent.wellKnown.url) if agent.wellKnown.url else None,
            lastSyncAt=agent.wellKnown.lastSyncAt,
            lastSyncStatus=agent.wellKnown.lastSyncStatus,
            lastSyncVersion=agent.wellKnown.lastSyncVersion,
        )

    # Convert capabilities to dict if it's a Pydantic model
    capabilities_dict = {}
    if agent.card.capabilities:
        if hasattr(agent.card.capabilities, "model_dump"):
            capabilities_dict = agent.card.capabilities.model_dump(exclude_none=True)
        elif isinstance(agent.card.capabilities, dict):
            capabilities_dict = agent.card.capabilities
        else:
            capabilities_dict = dict(agent.card.capabilities)

    # Convert security_schemes to dict if needed
    security_schemes_dict = {}
    if agent.card.security_schemes:
        if hasattr(agent.card.security_schemes, "model_dump"):
            security_schemes_dict = agent.card.security_schemes.model_dump(exclude_none=True)
        elif isinstance(agent.card.security_schemes, dict):
            security_schemes_dict = agent.card.security_schemes
        else:
            security_schemes_dict = dict(agent.card.security_schemes)

    return AgentDetailResponse(
        id=str(agent.id),
        path=agent.path,
        name=agent.card.name,
        description=agent.card.description,
        url=str(agent.card.url),
        version=agent.card.version,
        protocolVersion=agent.card.protocol_version,
        capabilities=capabilities_dict,
        skills=skills_output,
        securitySchemes=security_schemes_dict,
        preferredTransport=agent.card.preferred_transport,
        defaultInputModes=agent.card.default_input_modes or [],
        defaultOutputModes=agent.card.default_output_modes or [],
        provider=provider_output,
        tags=agent.tags,
        status=agent.status,
        enabled=agent.isEnabled,
        permissions=permissions,
        author=str(agent.author),
        wellKnown=well_known_info,
        createdAt=agent.createdAt,
        updatedAt=agent.updatedAt,
    )


def convert_to_create_response(agent: Any, acl_permission: int | ResourcePermissions) -> AgentCreateResponse:
    """Convert A2AAgent document to create response with full details"""
    return AgentCreateResponse(
        message="Agent registered successfully",
        agent=convert_to_detail(agent, acl_permission),
    )


def convert_to_update_response(agent: Any, acl_permission: int | ResourcePermissions) -> AgentUpdateResponse:
    """Convert A2AAgent document to update response with full details"""
    return AgentUpdateResponse(
        message="Agent updated successfully",
        agent=convert_to_detail(agent, acl_permission),
    )


def convert_to_toggle_response(agent: Any, acl_permission: int | ResourcePermissions) -> AgentToggleResponse:
    """Convert A2AAgent document to toggle response with full details"""
    message = f"Agent {'enabled' if agent.isEnabled else 'disabled'} successfully"
    return AgentToggleResponse(
        message=message,
        agent=convert_to_detail(agent, acl_permission),
    )


def convert_to_skills_response(agent: Any) -> AgentSkillsResponse:
    """Convert A2AAgent document to skills response"""
    skills_output = [
        AgentSkillOutput(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            tags=skill.tags or [],
            inputModes=skill.input_modes if hasattr(skill, "input_modes") else None,
            outputModes=skill.output_modes if hasattr(skill, "output_modes") else None,
        )
        for skill in (agent.card.skills or [])
    ]

    return AgentSkillsResponse(
        agentId=str(agent.id), agentName=agent.card.name, skills=skills_output, totalSkills=len(agent.card.skills or [])
    )
