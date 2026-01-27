"""Models for the registry service."""

from .anthropic_schema import (
    Repository,
    StdioTransport,
    StreamableHttpTransport,
    SseTransport,
    Package,
    ServerDetail,
    ServerResponse,
    ServerList,
    PaginationMetadata,
    ErrorResponse,
)
from .agent_models import (
    SecurityScheme,
    Skill,
    AgentCard,
    AgentInfo,
    AgentRegistrationRequest,
)
from .errors import (
    APIErrorDetail,
    APIErrorResponse,
    ErrorCode,
    create_error_detail,
)

__all__ = [
    "Repository",
    "StdioTransport",
    "StreamableHttpTransport",
    "SseTransport",
    "Package",
    "ServerDetail",
    "ServerResponse",
    "ServerList",
    "PaginationMetadata",
    "ErrorResponse",
    "SecurityScheme",
    "Skill",
    "AgentCard",
    "AgentInfo",
    "AgentRegistrationRequest",
    # Error handling
    "APIErrorDetail",
    "APIErrorResponse",
    "ErrorCode",
    "create_error_detail",
]
