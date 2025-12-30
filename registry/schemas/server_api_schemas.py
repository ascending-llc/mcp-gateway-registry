"""
Pydantic Schemas for Server Management API v1

These schemas define the request and response models for the
Server Management endpoints based on the API documentation.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# ==================== Request Schemas ====================

class ServerCreateRequest(BaseModel):
    """Request schema for creating a new server"""
    server_name: str = Field(..., description="Name of the MCP server")
    path: str = Field(..., description="Unique path/route for the server")
    description: Optional[str] = Field(default="", description="Server description")
    proxy_pass_url: Optional[str] = Field(default=None, description="Backend proxy URL")
    scope: str = Field(default="private_user", description="Access scope: shared_app, shared_user, or private_user")
    tags: List[str] = Field(default_factory=list, description="Server tags")
    num_tools: int = Field(default=0, description="Number of tools")
    num_stars: int = Field(default=0, description="Star count")
    is_python: bool = Field(default=False, description="Is Python-based")
    license: Optional[str] = Field(default=None, description="License type")
    auth_type: Optional[str] = Field(default=None, description="Authentication type")
    auth_provider: Optional[str] = Field(default=None, description="Authentication provider")
    supported_transports: List[str] = Field(default_factory=list, description="Supported transports")
    transport: Optional[Dict[str, Any]] = Field(default=None, description="Transport configuration")
    startup: bool = Field(default=False, description="Start on system startup")
    chat_menu: bool = Field(default=True, description="Show in chat menu")
    tool_list: List[Dict[str, Any]] = Field(default_factory=list, description="List of tools")
    icon_path: Optional[str] = Field(default=None, description="Icon path")
    timeout: Optional[int] = Field(default=30000, description="Request timeout (ms)")
    init_timeout: Optional[int] = Field(default=60000, description="Init timeout (ms)")
    server_instructions: Optional[str] = Field(default=None, description="Usage instructions")
    requires_oauth: bool = Field(default=False, description="Requires OAuth")
    oauth: Optional[Dict[str, Any]] = Field(default=None, description="OAuth configuration")
    custom_user_vars: Optional[Dict[str, Any]] = Field(default=None, description="Custom variables")
    
    @field_validator('tags', mode='before')
    @classmethod
    def normalize_tags(cls, v):
        """Convert tags to lowercase for case-insensitive comparison"""
        if isinstance(v, list):
            return [tag.lower() if isinstance(tag, str) else tag for tag in v]
        return v
    
    @field_validator('scope')
    @classmethod
    def validate_scope(cls, v):
        """Validate scope values"""
        valid_scopes = ['shared_app', 'shared_user', 'private_user']
        if v not in valid_scopes:
            raise ValueError(f"scope must be one of {valid_scopes}")
        return v


class ServerUpdateRequest(BaseModel):
    """Request schema for updating a server (partial update)"""
    server_name: Optional[str] = None
    description: Optional[str] = None
    proxy_pass_url: Optional[str] = None
    tags: Optional[List[str]] = None
    num_tools: Optional[int] = None
    num_stars: Optional[int] = None
    is_python: Optional[bool] = None
    license: Optional[str] = None
    auth_type: Optional[str] = None
    auth_provider: Optional[str] = None
    supported_transports: Optional[List[str]] = None
    transport: Optional[Dict[str, Any]] = None
    startup: Optional[bool] = None
    chat_menu: Optional[bool] = None
    tool_list: Optional[List[Dict[str, Any]]] = None
    icon_path: Optional[str] = None
    timeout: Optional[int] = None
    init_timeout: Optional[int] = None
    server_instructions: Optional[str] = None
    requires_oauth: Optional[bool] = None
    oauth: Optional[Dict[str, Any]] = None
    custom_user_vars: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    scope: Optional[str] = None
    version: Optional[int] = Field(None, description="Current version for optimistic locking")
    
    @field_validator('tags', mode='before')
    @classmethod
    def normalize_tags(cls, v):
        """Convert tags to lowercase"""
        if isinstance(v, list):
            return [tag.lower() if isinstance(tag, str) else tag for tag in v]
        return v
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        """Validate status values"""
        if v is not None:
            valid_statuses = ['active', 'inactive', 'error']
            if v not in valid_statuses:
                raise ValueError(f"status must be one of {valid_statuses}")
        return v
    
    @field_validator('scope')
    @classmethod
    def validate_scope(cls, v):
        """Validate scope values"""
        if v is not None:
            valid_scopes = ['shared_app', 'shared_user', 'private_user']
            if v not in valid_scopes:
                raise ValueError(f"scope must be one of {valid_scopes}")
        return v


class ServerToggleRequest(BaseModel):
    """Request schema for toggling server status"""
    enabled: bool = Field(..., description="Enable or disable the server")


# ==================== Response Schemas ====================

class ToolSchema(BaseModel):
    """Schema for a tool definition"""
    name: str
    description: str
    inputSchema: Optional[Dict[str, Any]] = None
    
    class Config:
        extra = "allow"


class ServerListItemResponse(BaseModel):
    """Response schema for a server in the list"""
    id: str = Field(..., description="Server ID")
    server_name: str
    path: str
    description: Optional[str] = None
    proxy_pass_url: Optional[str] = None
    supported_transports: List[str] = Field(default_factory=list)
    auth_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    num_tools: int = 0
    num_stars: int = 0
    is_python: bool = False
    license: Optional[str] = None
    tool_list: List[Dict[str, Any]] = Field(default_factory=list)
    scope: str
    author_id: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime
    
    class Config:
        from_attributes = True


class ServerDetailResponse(BaseModel):
    """Response schema for detailed server information"""
    id: str
    server_name: str
    path: str
    description: Optional[str] = None
    proxy_pass_url: Optional[str] = None
    supported_transports: List[str] = Field(default_factory=list)
    auth_type: Optional[str] = None
    auth_provider: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    num_tools: int = 0
    num_stars: int = 0
    is_python: bool = False
    license: Optional[str] = None
    tool_list: List[Dict[str, Any]] = Field(default_factory=list)
    scope: str
    author_id: Optional[str] = None
    organization_id: Optional[str] = None
    startup: bool = False
    icon_path: Optional[str] = None
    timeout: Optional[int] = None
    init_timeout: Optional[int] = None
    chat_menu: bool = True
    server_instructions: Optional[str] = None
    transport: Optional[Dict[str, Any]] = None
    requires_oauth: bool = False
    oauth: Optional[Dict[str, Any]] = None
    custom_user_vars: Optional[Dict[str, Any]] = None
    status: str
    last_connected: Optional[datetime] = None
    last_error: Optional[str] = None
    error_message: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime
    version: int
    
    class Config:
        from_attributes = True


class ServerCreateResponse(BaseModel):
    """Response schema for server creation"""
    id: str
    server_name: str
    path: str
    description: Optional[str] = None
    scope: str
    status: str
    createdAt: datetime
    updatedAt: datetime
    version: int
    
    class Config:
        from_attributes = True


class ServerUpdateResponse(BaseModel):
    """Response schema for server update"""
    id: str
    server_name: str
    path: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    num_tools: int = 0
    num_stars: int = 0
    status: str
    updatedAt: datetime
    version: int
    
    class Config:
        from_attributes = True


class ServerToggleResponse(BaseModel):
    """Response schema for server toggle"""
    id: str
    server_name: str
    path: str
    enabled: bool
    status: str
    updatedAt: datetime
    
    class Config:
        from_attributes = True


class ServerToolsResponse(BaseModel):
    """Response schema for server tools"""
    id: str
    server_name: str
    path: str
    tools: List[Dict[str, Any]]
    num_tools: int
    cached: bool = False
    
    class Config:
        from_attributes = True


class ServerHealthResponse(BaseModel):
    """Response schema for server health refresh"""
    id: str
    server_name: str
    path: str
    status: str
    last_checked: datetime
    response_time_ms: Optional[int] = None
    num_tools: int
    
    class Config:
        from_attributes = True


class PaginationMetadata(BaseModel):
    """Pagination metadata"""
    total: int
    page: int
    per_page: int
    total_pages: int


class ServerListResponse(BaseModel):
    """Response schema for server list with pagination"""
    servers: List[ServerListItemResponse]
    pagination: PaginationMetadata


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str
    message: str
    current_version: Optional[int] = None
    provided_version: Optional[int] = None


# ==================== Helper Functions ====================

def _get_config_field(server, field: str, default=None):
    """Extract a field from server.config with fallback to default"""
    if not server or not hasattr(server, 'config') or not server.config:
        return default
    return server.config.get(field, default)


def convert_to_list_item(server) -> ServerListItemResponse:
    """Convert MCPServerDocument to ServerListItemResponse"""
    config = server.config or {}
    
    # Extract author_id from server.author Link object
    # Use ref.id to avoid fetching the entire user document
    author_id = str(server.author.ref.id) if server.author else None
    
    return ServerListItemResponse(
        id=str(server.id),
        server_name=server.serverName,
        path=config.get("path", ""),
        description=config.get("description"),
        proxy_pass_url=config.get("proxy_pass_url"),
        supported_transports=config.get("supported_transports", []),
        auth_type=config.get("auth_type"),
        tags=config.get("tags", []),
        num_tools=config.get("num_tools", 0),
        num_stars=config.get("num_stars", 0),
        is_python=config.get("is_python", False),
        license=config.get("license"),
        tool_list=config.get("tool_list", []),
        scope=config.get("scope", "private_user"),
        author_id=author_id,
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_detail(server) -> ServerDetailResponse:
    """Convert MCPServerDocument to ServerDetailResponse"""
    config = server.config or {}
    
    # Extract author_id from server.author Link object
    # Use ref.id to avoid fetching the entire user document
    author_id = str(server.author.ref.id) if server.author else None
    
    # Parse last_connected if stored as ISO string
    last_connected = None
    if config.get("last_connected"):
        try:
            if isinstance(config["last_connected"], str):
                last_connected = datetime.fromisoformat(config["last_connected"].replace('Z', '+00:00'))
            elif isinstance(config["last_connected"], datetime):
                last_connected = config["last_connected"]
        except (ValueError, AttributeError):
            pass
    
    return ServerDetailResponse(
        id=str(server.id),
        server_name=server.serverName,
        path=config.get("path", ""),
        description=config.get("description"),
        proxy_pass_url=config.get("proxy_pass_url"),
        supported_transports=config.get("supported_transports", []),
        auth_type=config.get("auth_type"),
        auth_provider=config.get("auth_provider"),
        tags=config.get("tags", []),
        num_tools=config.get("num_tools", 0),
        num_stars=config.get("num_stars", 0),
        is_python=config.get("is_python", False),
        license=config.get("license"),
        tool_list=config.get("tool_list", []),
        scope=config.get("scope", "private_user"),
        author_id=author_id,
        organization_id=config.get("organization_id"),
        startup=config.get("startup", False),
        icon_path=config.get("icon_path"),
        timeout=config.get("timeout"),
        init_timeout=config.get("init_timeout"),
        chat_menu=config.get("chat_menu", True),
        server_instructions=config.get("server_instructions"),
        transport=config.get("transport"),
        requires_oauth=config.get("requires_oauth", False),
        oauth=config.get("oauth"),
        custom_user_vars=config.get("custom_user_vars"),
        status=config.get("status", "active"),
        last_connected=last_connected,
        last_error=config.get("last_error"),
        error_message=config.get("error_message"),
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
        version=config.get("version", 1),
    )


def convert_to_create_response(server) -> ServerCreateResponse:
    """Convert MCPServerDocument to ServerCreateResponse"""
    config = server.config or {}
    return ServerCreateResponse(
        id=str(server.id),
        server_name=server.serverName,
        path=config.get("path", ""),
        description=config.get("description"),
        scope=config.get("scope", "private_user"),
        status=config.get("status", "active"),
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
        version=config.get("version", 1),
    )


def convert_to_update_response(server) -> ServerUpdateResponse:
    """Convert MCPServerDocument to ServerUpdateResponse"""
    config = server.config or {}
    return ServerUpdateResponse(
        id=str(server.id),
        server_name=server.serverName,
        path=config.get("path", ""),
        description=config.get("description"),
        tags=config.get("tags", []),
        num_tools=config.get("num_tools", 0),
        num_stars=config.get("num_stars", 0),
        status=config.get("status", "active"),
        updatedAt=server.updatedAt or datetime.now(),
        version=config.get("version", 1),
    )


def convert_to_toggle_response(server, enabled: bool) -> ServerToggleResponse:
    """Convert MCPServerDocument to ServerToggleResponse"""
    config = server.config or {}
    return ServerToggleResponse(
        id=str(server.id),
        server_name=server.serverName,
        path=config.get("path", ""),
        enabled=enabled,
        status=config.get("status", "active"),
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_tools_response(server, tools: List[Dict[str, Any]]) -> ServerToolsResponse:
    """Convert MCPServerDocument to ServerToolsResponse"""
    config = server.config or {}
    return ServerToolsResponse(
        id=str(server.id),
        server_name=server.serverName,
        path=config.get("path", ""),
        tools=tools,
        num_tools=len(tools),
        cached=False,
    )


def convert_to_health_response(server, health_data: Dict[str, Any]) -> ServerHealthResponse:
    """Convert MCPServerDocument to ServerHealthResponse"""
    config = server.config or {}
    return ServerHealthResponse(
        id=str(server.id),
        server_name=server.serverName,
        path=config.get("path", ""),
        status=health_data.get("status", "healthy"),
        last_checked=health_data.get("last_checked", datetime.now()),
        response_time_ms=health_data.get("response_time_ms"),
        num_tools=config.get("num_tools", 0),
    )
