"""Simplified federation configuration schemas."""


from pydantic import BaseModel, Field


class AnthropicServerConfig(BaseModel):
    """Anthropic server configuration."""
    name: str


class AnthropicFederationConfig(BaseModel):
    """Anthropic federation configuration."""
    enabled: bool = False
    endpoint: str = "https://registry.modelcontextprotocol.io"
    sync_on_startup: bool = False
    servers: list[AnthropicServerConfig] = Field(default_factory=list)


class AsorAgentConfig(BaseModel):
    """ASOR agent configuration."""
    id: str


class AsorFederationConfig(BaseModel):
    """ASOR federation configuration."""
    enabled: bool = False
    endpoint: str = "https://wcpdev-services1.wd103.myworkday.com/ccx/api/asor/v1/awsasor_wcpdev1"
    auth_env_var: str | None = None
    sync_on_startup: bool = False
    agents: list[AsorAgentConfig] = Field(default_factory=list)


class FederationConfig(BaseModel):
    """Root federation configuration."""
    anthropic: AnthropicFederationConfig = Field(default_factory=AnthropicFederationConfig)
    asor: AsorFederationConfig = Field(default_factory=AsorFederationConfig)

    def is_any_federation_enabled(self) -> bool:
        """Check if any federation is enabled."""
        return self.anthropic.enabled or self.asor.enabled

    def get_enabled_federations(self) -> list[str]:
        """Get list of enabled federation names."""
        enabled = []
        if self.anthropic.enabled:
            enabled.append("anthropic")
        if self.asor.enabled:
            enabled.append("asor")
        return enabled


# Add missing FederatedServer class for compatibility
class FederatedServer(BaseModel):
    """Federated server configuration."""
    name: str
    endpoint: str
    enabled: bool = True
