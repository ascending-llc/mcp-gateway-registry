from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field, validator
import time

class OAuthTokens(BaseModel):
    """OAuth tokens"""
    access_token: str = Field(..., description="Access token")
    token_type: str = Field("Bearer", description="Token type")
    expires_in: Optional[int] = Field(None, description="Expiration time (seconds)")
    refresh_token: Optional[str] = Field(None, description="Refresh token")
    scope: Optional[str] = Field(None, description="Authorization scope")
    obtained_at: Optional[int] = Field(None, description="Obtained timestamp")
    expires_at: Optional[int] = Field(None, description="Expiration timestamp")

    @validator("expires_at", always=True)
    def set_expires_at(cls, v, values):
        """Calculate expires_at based on expires_in"""
        if v is None and values.get("expires_in") is not None:
            import time
            return int(time.time()) + values["expires_in"]
        return v


class OAuthClientInformation(BaseModel):
    """OAuth client information"""
    client_id: str = Field(..., description="Client ID")
    client_secret: Optional[str] = Field(None, description="Client secret")
    redirect_uris: Optional[List[str]] = Field(None, description="Redirect URI list")
    scope: Optional[str] = Field(None, description="Authorization scope")
    grant_types: Optional[List[str]] = Field(None, description="Grant type list")
    additional_params: Optional[Dict[str, Any]] = Field(
        None, description="Additional OAuth parameters")


class OAuthMetadata(BaseModel):
    """OAuth metadata"""
    issuer: Optional[str] = Field(None, description="Issuer")
    authorization_endpoint: str = Field(..., description="Authorization endpoint")
    token_endpoint: str = Field(..., description="Token endpoint")
    registration_endpoint: Optional[str] = Field(None, description="Registration endpoint")
    scopes_supported: Optional[List[str]] = Field(None, description="Supported scopes")
    response_types_supported: Optional[List[str]] = Field(
        None, description="Supported response types"
    )
    grant_types_supported: Optional[List[str]] = Field(
        None, description="Supported grant types"
    )
    token_endpoint_auth_methods_supported: Optional[List[str]] = Field(
        None, description="Supported token endpoint authentication methods"
    )
    code_challenge_methods_supported: Optional[List[str]] = Field(
        None, description="Supported code challenge methods"
    )


class OAuthProtectedResourceMetadata(BaseModel):
    """OAuth protected resource metadata"""
    resource: Optional[str] = Field(None, description="Resource identifier")
    authorization_servers: Optional[List[str]] = Field(
        None, description="Authorization server list"
    )
    scopes_supported: Optional[List[str]] = Field(None, description="Supported scopes")


class TokenTransformConfig(BaseModel):
    """Token transformation configuration"""
    provider: Optional[str] = Field(None, description="Provider name")
    access_token_path: Optional[str] = Field(
        None, description="Access token path in response"
    )
    refresh_token_path: Optional[str] = Field(
        None, description="Refresh token path in response"
    )
    expires_in_path: Optional[str] = Field(
        None, description="Expiration time path in response"
    )
    token_type_path: Optional[str] = Field(
        None, description="Token type path in response"
    )
    scope_path: Optional[str] = Field(None, description="Scope path in response")
    field_mappings: Optional[Dict[str, str]] = Field(
        None, description="Field mapping configuration"
    )
    value_transforms: Optional[Dict[str, Any]] = Field(
        None, description="Value transformation configuration"
    )


class MCPOAuthFlowMetadata(BaseModel):
    """MCP OAuth flow metadata"""
    server_name: str = Field(..., description="Server name")
    user_id: str = Field(..., description="User ID")
    authorize_url: str = Field(..., description="Authorize URL")
    state: str = Field(..., description="State parameter")
    code_verifier: str = Field(..., description="PKCE code_verifier")
    client_info: OAuthClientInformation = Field(..., description="Client information")
    metadata: OAuthMetadata = Field(..., description="OAuth metadata")
    resource_metadata: Optional[OAuthProtectedResourceMetadata] = Field(
        None, description="Resource metadata"
    )
    token_transform: Optional[TokenTransformConfig] = Field(
        None, description="Token transformation configuration"
    )


@dataclass
class OAuthFlow:
    """OAuth flow"""
    flow_id: str
    server_name: str
    user_id: str
    code_verifier: str
    state: str
    status: str = "pending"  # pending, completed, failed
    created_at: float = field(default_factory=time.time)  # Use dataclasses.field instead of Pydantic Field
    completed_at: Optional[float] = None
    tokens: Optional[OAuthTokens] = None
    error: Optional[str] = None
    metadata: Optional[MCPOAuthFlowMetadata] = None
