from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import OAuthProviderType


class BaseOAuthConfig(BaseModel):
    """Base OAuth provider configuration for AgentCore gateways."""

    providerType: OAuthProviderType
    clientId: str
    grantType: str = "client_credentials"
    scope: str = "invoke:gateway"
    authMethod: str = "client_secret_post"

    model_config = ConfigDict(extra="allow", use_enum_values=True)


class CognitoConfig(BaseOAuthConfig):
    providerType: Literal[OAuthProviderType.COGNITO] = OAuthProviderType.COGNITO
    userPoolId: str
    region: str
    domain: str | None = None

    @property
    def token_url(self) -> str:
        if self.domain:
            domain_host = f"{self.domain}.auth.{self.region}.amazoncognito.com"
        else:
            pool_id_clean = self.userPoolId.replace("_", "")
            domain_host = f"{pool_id_clean}.auth.{self.region}.amazoncognito.com"
        return f"https://{domain_host}/oauth2/token"


class Auth0Config(BaseOAuthConfig):
    providerType: Literal[OAuthProviderType.AUTH0] = OAuthProviderType.AUTH0
    domain: str
    audience: str | None = None

    @property
    def token_url(self) -> str:
        return f"https://{self.domain}/oauth/token"


class OktaConfig(BaseOAuthConfig):
    providerType: Literal[OAuthProviderType.OKTA] = OAuthProviderType.OKTA
    domain: str
    authorizationServerId: str = "default"

    @property
    def token_url(self) -> str:
        return f"https://{self.domain}/oauth2/{self.authorizationServerId}/v1/token"


class EntraIDConfig(BaseOAuthConfig):
    providerType: Literal[OAuthProviderType.ENTRA_ID] = OAuthProviderType.ENTRA_ID
    tenantId: str

    @property
    def token_url(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenantId}/oauth2/v2.0/token"


class CustomOAuth2Config(BaseOAuthConfig):
    providerType: Literal[OAuthProviderType.CUSTOM_OAUTH2] = OAuthProviderType.CUSTOM_OAUTH2
    tokenUrl: str
    extraParams: dict[str, Any] | None = None

    @property
    def token_url(self) -> str:
        return self.tokenUrl


OAuthProviderConfig = Annotated[
    CognitoConfig | Auth0Config | OktaConfig | EntraIDConfig | CustomOAuth2Config,
    Field(discriminator="providerType"),
]
