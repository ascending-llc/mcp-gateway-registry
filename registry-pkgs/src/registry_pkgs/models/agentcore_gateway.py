from datetime import UTC, datetime
from typing import Any, Literal

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

from .oauth_provider_config import OAuthProviderConfig


class AgentCoreGateway(Document):
    """Persisted AgentCore gateway registration and sync metadata."""

    name: str
    arn: str
    region: str
    gatewayId: str | None = None
    gatewayUrl: str | None = None

    oauthProvider: OAuthProviderConfig | None = None

    status: Literal["active", "disabled", "auth_required"] = "active"
    lastSyncAt: datetime | None = None
    lastSyncStatus: Literal["success", "partial", "failed"] | None = None
    lastSyncStats: dict[str, Any] | None = None
    errorMessage: str | None = None

    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    createdBy: PydanticObjectId | None = None
    createdAt: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "agentcore_gateways"
        keep_nulls = False
        use_state_management = True
        indexes = [
            IndexModel([("arn", 1)], unique=True),
            IndexModel([("name", 1)], unique=True),
            IndexModel([("status", 1)]),
            IndexModel([("oauthProvider.providerType", 1)]),
        ]

    def get_oauth_service_name(self) -> str:
        return f"agentcore-gateway-{self.name}"

    def get_provider_display_name(self) -> str:
        provider_type = None
        if self.oauthProvider:
            provider_type = str(self.oauthProvider.providerType)
        provider_names = {
            "cognito": "AWS Cognito",
            "auth0": "Auth0",
            "okta": "Okta",
            "entra_id": "Microsoft EntraID",
            "custom": "Custom OAuth2",
        }
        return provider_names.get(provider_type, "Unknown")
