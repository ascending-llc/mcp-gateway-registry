"""
Pydantic models for Server Management API V1
Based on MongoDB Schema definitions, contains only fields defined in the schema
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


# ================= Transport Related Models =================
class TransportConfig(BaseModel):
    """Transport configuration"""
    type: str = Field(..., description="Transport type, such as stdio, streamable-http, etc.")
    command: Optional[str] = Field(None, description="Command for stdio type")
    args: Optional[List[str]] = Field(None, description="Command arguments")
    env: Optional[Dict[str, str]] = Field(None, description="Environment variables")


# ================= OAuth Related Models =================
class OAuthConfig(BaseModel):
    """OAuth configuration"""
    authorization_url: str = Field(..., description="Authorization URL")
    token_url: str = Field(..., description="Token URL")
    client_id: str = Field(..., description="Client ID")
    scope: Optional[str] = Field(None, description="OAuth scope")


# ================= Tool Related Models =================
class ToolSchema(BaseModel):
    """Tool schema definition"""
    name: str = Field(..., description="Tool name")
    description: Optional[str] = Field(None, description="Tool description")
    inputSchema: Optional[Dict[str, Any]] = Field(None, description="Input schema")


# ================= Server Related Models =================
class ServerRegisterRequest(BaseModel):
    """Server registration request"""
    server_name: str = Field(..., description="Server name")
    path: str = Field(..., description="Server path")
    description: Optional[str] = Field(None, description="Server description")
    proxy_pass_url: Optional[str] = Field(None, description="Proxy URL")
    supported_transports: Optional[List[str]] = Field(default=None, description="Supported transport methods")
    auth_type: Optional[str] = Field(None, description="Authentication type")
    auth_provider: Optional[str] = Field(None, description="Authentication provider")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tag list")
    num_tools: Optional[int] = Field(0, description="Number of tools")
    num_stars: Optional[int] = Field(0, description="Number of stars")
    is_python: Optional[bool] = Field(False, description="Whether it is a Python service")
    license: Optional[str] = Field(None, description="License")
    tool_list: Optional[List[ToolSchema]] = Field(default_factory=list, description="Tool list")
    scope: Optional[str] = Field("shared_app", description="Access scope: shared_app, shared_user, private_user")
    user_id: Optional[str] = Field(None, description="User ID (for private service)")
    organization_id: Optional[str] = Field(None, description="Organization ID")
    startup: Optional[bool] = Field(False, description="Whether to run automatically at startup")
    icon_path: Optional[str] = Field(None, description="Icon path")
    timeout: Optional[int] = Field(30000, description="Timeout (milliseconds)")
    init_timeout: Optional[int] = Field(60000, description="Initialization timeout (milliseconds)")
    chat_menu: Optional[bool] = Field(True, description="Whether to display in chat menu")
    server_instructions: Optional[str] = Field(None, description="Server instructions")
    transport: Optional[TransportConfig] = Field(None, description="Transport configuration")
    requires_oauth: Optional[bool] = Field(False, description="Whether OAuth is required")
    oauth: Optional[OAuthConfig] = Field(None, description="OAuth configuration")
    custom_user_vars: Optional[Dict[str, Any]] = Field(None, description="Custom user variables")

    @field_validator('tags')
    @classmethod
    def validate_tags_case_insensitive(cls, v: Optional[List[str]]) -> List[str]:
        """Validate tags case-insensitively, convert all tags to lowercase, and check for duplicates"""
        if not v:
            return []

        # Convert to lowercase
        lowercase_tags = [tag.lower() for tag in v]

        # Check for duplicates (case-insensitive)
        if len(lowercase_tags) != len(set(lowercase_tags)):
            raise ValueError("Duplicate tags found (case-insensitive)")

        return lowercase_tags


class ServerUpdateRequest(BaseModel):
    """Server update request"""
    description: Optional[str] = Field(None, description="Server description")
    proxy_pass_url: Optional[str] = Field(None, description="Proxy URL")
    supported_transports: Optional[List[str]] = Field(None, description="Supported transport methods")
    auth_type: Optional[str] = Field(None, description="Authentication type")
    auth_provider: Optional[str] = Field(None, description="Authentication provider")
    tags: Optional[List[str]] = Field(None, description="Tag list")
    num_tools: Optional[int] = Field(None, description="Number of tools")
    num_stars: Optional[int] = Field(None, description="Number of stars")
    is_python: Optional[bool] = Field(None, description="Whether it is a Python service")
    license: Optional[str] = Field(None, description="License")
    tool_list: Optional[List[ToolSchema]] = Field(None, description="Tool list")
    status: Optional[str] = Field(None, description="Status: active, inactive, error")
    startup: Optional[bool] = Field(None, description="Whether to run automatically at startup")
    icon_path: Optional[str] = Field(None, description="Icon path")
    timeout: Optional[int] = Field(None, description="Timeout (milliseconds)")
    init_timeout: Optional[int] = Field(None, description="Initialization timeout (milliseconds)")
    chat_menu: Optional[bool] = Field(None, description="Whether to display in chat menu")
    server_instructions: Optional[str] = Field(None, description="Server instructions")
    transport: Optional[TransportConfig] = Field(None, description="Transport configuration")
    requires_oauth: Optional[bool] = Field(None, description="Whether OAuth is required")
    oauth: Optional[OAuthConfig] = Field(None, description="OAuth configuration")
    custom_user_vars: Optional[Dict[str, Any]] = Field(None, description="Custom user variables")
    version: int = Field(..., description="Version number (for optimistic locking)")

    @field_validator('tags')
    @classmethod
    def validate_tags_case_insensitive(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate tags case-insensitively"""
        if v is None:
            return None

        # Convert to lowercase
        lowercase_tags = [tag.lower() for tag in v]

        # Check for duplicates (case-insensitive)
        if len(lowercase_tags) != len(set(lowercase_tags)):
            raise ValueError("Duplicate tags found (case-insensitive)")

        return lowercase_tags


class ServerToggleRequest(BaseModel):
    """Server toggle status request"""
    enabled: bool = Field(..., description="Whether to enable")


class ServerResponse(BaseModel):
    """Server response"""
    id: str = Field(..., description="Server ID")
    server_name: str = Field(..., description="Server name")
    path: str = Field(..., description="Server path")
    description: Optional[str] = Field(None, description="Server description")
    proxy_pass_url: Optional[str] = Field(None, description="Proxy URL")
    supported_transports: Optional[List[str]] = Field(None, description="Supported transport methods")
    auth_type: Optional[str] = Field(None, description="Authentication type")
    auth_provider: Optional[str] = Field(None, description="Authentication provider")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tag list")
    num_tools: Optional[int] = Field(0, description="Number of tools")
    num_stars: Optional[int] = Field(0, description="Number of stars")
    is_python: Optional[bool] = Field(False, description="Whether it is a Python service")
    license: Optional[str] = Field(None, description="License")
    tool_list: Optional[List[ToolSchema]] = Field(default_factory=list, description="Tool list")
    scope: Optional[str] = Field("shared_app", description="Access scope")
    user_id: Optional[str] = Field(None, description="User ID")
    organization_id: Optional[str] = Field(None, description="Organization ID")
    startup: Optional[bool] = Field(False, description="Whether to run automatically at startup")
    icon_path: Optional[str] = Field(None, description="Icon path")
    timeout: Optional[int] = Field(None, description="Timeout (milliseconds)")
    init_timeout: Optional[int] = Field(None, description="Initialization timeout (milliseconds)")
    chat_menu: Optional[bool] = Field(None, description="Whether to display in chat menu")
    server_instructions: Optional[str] = Field(None, description="Server instructions")
    transport: Optional[TransportConfig] = Field(None, description="Transport configuration")
    requires_oauth: Optional[bool] = Field(False, description="Whether OAuth is required")
    oauth: Optional[OAuthConfig] = Field(None, description="OAuth configuration")
    custom_user_vars: Optional[Dict[str, Any]] = Field(None, description="Custom user variables")
    status: Optional[str] = Field("active", description="Status")
    last_connected: Optional[datetime] = Field(None, description="Last connection time")
    last_error: Optional[str] = Field(None, description="Last error")
    error_message: Optional[str] = Field(None, description="Error message")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Update time")
    version: int = Field(..., description="Version number")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ServerListResponse(BaseModel):
    """Server list response"""
    servers: List[ServerResponse] = Field(..., description="Server list")
    pagination: Dict[str, int] = Field(..., description="Pagination information")


class ServerToggleResponse(BaseModel):
    """Server toggle status response"""
    id: str = Field(..., description="Server ID")
    server_name: str = Field(..., description="Server name")
    path: str = Field(..., description="Server path")
    enabled: bool = Field(..., description="Whether enabled")
    status: str = Field(..., description="Status")
    updated_at: datetime = Field(..., description="Update time")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ServerToolsResponse(BaseModel):
    """Server tools list response"""
    id: str = Field(..., description="Server ID")
    server_name: str = Field(..., description="Server name")
    path: str = Field(..., description="Server path")
    tools: List[ToolSchema] = Field(..., description="Tool list")
    num_tools: int = Field(..., description="Number of tools")
    cached: bool = Field(False, description="Whether from cache")


class ServerHealthResponse(BaseModel):
    """Server health status response"""
    id: str = Field(..., description="Server ID")
    server_name: str = Field(..., description="Server name")
    path: str = Field(..., description="Server path")
    status: str = Field(..., description="Health status")
    last_checked: datetime = Field(..., description="Last check time")
    response_time_ms: Optional[int] = Field(None, description="Response time (milliseconds)")
    num_tools: int = Field(..., description="Number of tools")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ErrorResponse(BaseModel):
    """Error response"""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    current_version: Optional[int] = Field(None, description="Current version number (on conflict)")
    provided_version: Optional[int] = Field(None, description="Provided version number (on conflict)")