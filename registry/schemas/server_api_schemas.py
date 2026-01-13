"""
Pydantic Schemas for Server Management API v1

These schemas define the request and response models for the
Server Management endpoints based on the API documentation.
"""

import json
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_serializer
from registry.utils.crypto_utils import decrypt_auth_fields


# ==================== Request Schemas ====================

class ServerCreateRequest(BaseModel):
    """Request schema for creating a new server"""
    serverName: str = Field(..., alias="serverName", description="Name of the MCP server")
    path: str = Field(..., description="Unique path/route for the server")
    description: Optional[str] = Field(default="", description="Server description")
    url: Optional[str] = Field(default=None, description="Backend proxy URL")
    scope: str = Field(default="private_user", description="Access scope: shared_app, shared_user, or private_user")
    tags: List[str] = Field(default_factory=list, description="Server tags")
    num_tools: int = Field(default=0, description="Number of tools")
    num_stars: int = Field(default=0, description="Star count")
    is_python: bool = Field(default=False, description="Is Python-based")
    license: Optional[str] = Field(default=None, description="License type")
    auth_type: Optional[str] = Field(default=None, description="Authentication type")
    auth_provider: Optional[str] = Field(default=None, description="Authentication provider")
    supported_transports: List[str] = Field(default_factory=list, description="Supported transports")
    transport: Optional[Union[str, Dict[str, Any]]] = Field(default=None, description="Transport configuration (string or dict)")
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
    authentication: Optional[Dict[str, Any]] = Field(default=None, description="Authentication configuration (type, provider, scopes, etc.)")
    apiKey: Optional[Dict[str, Any]] = Field(default=None, description="API Key authentication configuration")
    enabled: bool = Field(default=True, description="Whether the server is enabled")
    
    class ConfigDict:
        populate_by_name = True  # Allow both serverName and server_name
    
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
    serverName: Optional[str] = Field(None, alias="serverName")
    description: Optional[str] = None
    url: Optional[str] = None
    tags: Optional[List[str]] = None
    num_tools: Optional[int] = None
    num_stars: Optional[int] = None
    is_python: Optional[bool] = None
    license: Optional[str] = None
    auth_type: Optional[str] = None
    auth_provider: Optional[str] = None
    supported_transports: Optional[List[str]] = None
    transport: Optional[Union[str, Dict[str, Any]]] = None
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
    authentication: Optional[Dict[str, Any]] = None
    apiKey: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    scope: Optional[str] = None
    enabled: Optional[bool] = None
    
    class ConfigDict:
        populate_by_name = True  # Allow both serverName and server_name
    
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
    
    class ConfigDict:
        extra = "allow"


class ServerListItemResponse(BaseModel):
    """Response schema for a server in the list"""
    id: str = Field(..., description="Server ID")
    serverName: str = Field(..., alias="serverName")
    title: Optional[str] = Field(None, description="Display title for the server")
    description: Optional[str] = None
    type: Optional[str] = Field(None, description="Transport type (e.g., streamable-http, sse, stdio)")
    url: Optional[str] = None
    apiKey: Optional[Dict[str, Any]] = None
    authentication: Optional[Dict[str, Any]] = None
    requiresOAuth: bool = Field(False, alias="requiresOAuth", description="Whether OAuth is required")
    capabilities: Optional[str] = Field(None, description="JSON string of server capabilities")
    tools: Optional[str] = Field(None, description="Comma-separated list of tool names")
    author: Optional[str] = Field(None, description="Author user ID")
    scope: str
    status: str = "active"
    path: str
    tags: List[str] = Field(default_factory=list)
    numTools: int = Field(0, alias="numTools")
    numStars: int = Field(0, alias="numStars")
    enabled: bool = Field(default=True, description="Whether the server is enabled")
    lastConnected: Optional[datetime] = Field(None, alias="lastConnected")
    createdAt: datetime
    updatedAt: datetime
    # Connection status fields
    connection_state: Optional[str] = Field(default=None, description="Connection state")
    requires_oauth: Optional[bool] = Field(default=None, description="Whether server requires OAuth")
    error: Optional[str] = Field(default=None, description="Error message if connection failed")
    
    class ConfigDict:
        from_attributes = True
        populate_by_name = True
    
    @model_serializer(mode='wrap')
    def _serialize(self, serializer, info):
        data = serializer(self)
        # If authentication exists, remove apiKey from response
        if data.get('authentication'):
            data.pop('apiKey', None)
        # If authentication doesn't exist, remove authentication from response
        else:
            data.pop('authentication', None)
        return data


class ServerDetailResponse(BaseModel):
    """Response schema for detailed server information"""
    id: str
    serverName: str = Field(..., alias="serverName")
    title: Optional[str] = Field(None, description="Display title for the server")
    description: Optional[str] = None
    type: Optional[str] = Field(None, description="Transport type (e.g., streamable-http, sse, stdio)")
    url: Optional[str] = None
    apiKey: Optional[Dict[str, Any]] = None
    authentication: Optional[Dict[str, Any]] = None
    requiresOAuth: bool = Field(False, alias="requiresOAuth", description="Whether OAuth is required")
    capabilities: Optional[str] = Field(None, description="JSON string of server capabilities")
    tools: Optional[str] = Field(None, description="Comma-separated list of tool names")
    toolFunctions: Optional[Dict[str, Any]] = Field(None, alias="toolFunctions", description="Complete OpenAI function schemas")
    initDuration: Optional[int] = Field(None, alias="initDuration", description="Initialization duration in ms")
    author: Optional[str] = Field(None, description="Author user ID")
    scope: str
    status: str
    path: str
    tags: List[str] = Field(default_factory=list)
    numTools: int = Field(0, alias="numTools")
    numStars: int = Field(0, alias="numStars")
    enabled: bool = Field(default=True, description="Whether the server is enabled")
    lastConnected: Optional[datetime] = Field(None, alias="lastConnected")
    lastError: Optional[str] = Field(None, alias="lastError")
    errorMessage: Optional[str] = Field(None, alias="errorMessage")
    createdAt: datetime
    updatedAt: datetime
    
    class ConfigDict:
        from_attributes = True
        populate_by_name = True
    
    @model_serializer(mode='wrap')
    def _serialize(self, serializer, info):
        data = serializer(self)
        # If authentication exists, remove apiKey from response
        if data.get('authentication'):
            data.pop('apiKey', None)
        # If authentication doesn't exist, remove authentication from response
        else:
            data.pop('authentication', None)
        return data


class ServerCreateResponse(BaseModel):
    """Response schema for server creation"""
    id: str
    serverName: str = Field(..., alias="serverName")
    path: str
    description: Optional[str] = None
    url: Optional[str] = None
    supported_transports: List[str] = Field(default_factory=list)
    auth_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    num_tools: int = 0
    num_stars: int = 0
    is_python: bool = False
    license: Optional[str] = None
    tool_list: List[Dict[str, Any]] = Field(default_factory=list)
    scope: str
    status: str
    enabled: bool = Field(default=True, description="Whether the server is enabled")
    author_id: Optional[str] = None
    authentication: Optional[Dict[str, Any]] = None
    apiKey: Optional[Dict[str, Any]] = None
    requires_oauth: bool = False
    last_connected: Optional[datetime] = None
    init_duration: Optional[int] = None
    createdAt: datetime
    updatedAt: datetime
    
    class ConfigDict:
        from_attributes = True
        populate_by_name = True
    
    @model_serializer(mode='wrap')
    def _serialize(self, serializer, info):
        data = serializer(self)
        # If authentication exists, remove apiKey from response
        if data.get('authentication'):
            data.pop('apiKey', None)
        # If authentication doesn't exist, remove authentication from response
        else:
            data.pop('authentication', None)
        return data


class ServerUpdateResponse(BaseModel):
    """Response schema for server update"""
    id: str
    serverName: str = Field(..., alias="serverName")
    path: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    num_tools: int = 0
    num_stars: int = 0
    status: str
    updatedAt: datetime
    
    class ConfigDict:
        from_attributes = True
        populate_by_name = True


class ServerToggleResponse(BaseModel):
    """Response schema for server toggle"""
    id: str
    serverName: str = Field(..., alias="serverName")
    path: str
    enabled: bool
    status: str
    updatedAt: datetime
    
    class ConfigDict:
        from_attributes = True
        populate_by_name = True


class ServerToolsResponse(BaseModel):
    """Response schema for server tools"""
    id: str
    serverName: str = Field(..., alias="serverName")
    path: str
    tools: List[Dict[str, Any]]
    num_tools: int
    cached: bool = False
    
    class ConfigDict:
        from_attributes = True
        populate_by_name = True


class ServerHealthResponse(BaseModel):
    """Response schema for server health refresh"""
    id: str
    serverName: str = Field(..., alias="serverName")
    path: str
    status: str
    last_checked: datetime
    response_time_ms: Optional[int] = None
    num_tools: int
    
    class ConfigDict:
        from_attributes = True
        populate_by_name = True


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


class ServerStatsResponse(BaseModel):
    """Response schema for server statistics (Admin only)"""
    total_servers: int = Field(..., description="Total number of servers")
    servers_by_scope: Dict[str, int] = Field(..., description="Server count grouped by scope")
    servers_by_status: Dict[str, int] = Field(..., description="Server count grouped by status")
    servers_by_transport: Dict[str, int] = Field(..., description="Server count grouped by transport type")
    total_tokens: int = Field(..., description="Total number of tokens")
    tokens_by_type: Dict[str, int] = Field(..., description="Token count grouped by type")
    active_tokens: int = Field(..., description="Number of active (non-expired) tokens")
    expired_tokens: int = Field(..., description="Number of expired tokens")
    active_users: int = Field(..., description="Number of users with active tokens")
    total_tools: int = Field(..., description="Total number of tools across all servers")
    
    class ConfigDict:
        from_attributes = True


# ==================== Helper Functions ====================

def _get_config_field(server, field: str, default=None):
    """Extract a field from server.config with fallback to default"""
    if not server or not hasattr(server, 'config') or not server.config:
        return default
    return server.config.get(field, default)


def convert_to_list_item(server) -> ServerListItemResponse:
    """Convert MCPServerDocument to ServerListItemResponse"""
    config = server.config or {}
    
    # Decrypt sensitive authentication fields before returning
    config = decrypt_auth_fields(config)
    
    # Extract author_id from server.author PydanticObjectId
    author_id = str(server.author) if server.author else None
    
    # Get transport type (first supported transport or default)
    supported_transports = config.get("supported_transports", [])
    transport_type = supported_transports[0] if supported_transports else "streamable-http"
    
    # Generate title from serverName if not provided
    title = config.get("title") or server.serverName
    
    # Build tools string from tool_list (comma-separated tool names)
    tool_list = config.get("tool_list", [])
    tools_str = None
    if tool_list:
        tool_names = [tool.get("name", "") for tool in tool_list if tool.get("name")]
        tools_str = ", ".join(tool_names) if tool_names else None
    
    # Convert capabilities dict to JSON string if present
    capabilities = config.get("capabilities")
    capabilities_str = None
    if capabilities:
        capabilities_str = json.dumps(capabilities) if isinstance(capabilities, dict) else str(capabilities)
    
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
    
    return ServerListItemResponse(
        id=str(server.id),
        serverName=server.serverName,
        title=title,
        description=config.get("description"),
        type=transport_type,
        url=config.get("url"),
        apiKey=config.get("apiKey"),
        authentication=config.get("authentication"),
        requiresOAuth=config.get("requires_oauth", False),
        capabilities=capabilities_str,
        tools=tools_str,
        author=author_id,
        scope=config.get("scope", "private_user"),
        status=config.get("status", "active"),
        path=config.get("path", ""),
        tags=config.get("tags", []),
        numTools=config.get("num_tools", 0),
        numStars=config.get("num_stars", 0),
        enabled=config.get("enabled", True),
        lastConnected=last_connected,
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_detail(server) -> ServerDetailResponse:
    """Convert MCPServerDocument to ServerDetailResponse"""
    config = server.config or {}
    
    # Decrypt sensitive authentication fields before returning
    config = decrypt_auth_fields(config)
    
    # Extract author_id from server.author PydanticObjectId
    author_id = str(server.author) if server.author else None
    
    # Get transport type (first supported transport or default)
    supported_transports = config.get("supported_transports", [])
    transport_type = supported_transports[0] if supported_transports else "streamable-http"
    
    # Generate title from serverName if not provided
    title = config.get("title") or server.serverName
    
    # Build tools string from tool_list (comma-separated tool names)
    tool_list = config.get("tool_list", [])
    tools_str = None
    if tool_list:
        tool_names = [tool.get("name", "") for tool in tool_list if tool.get("name")]
        tools_str = ", ".join(tool_names) if tool_names else None
    
    # Build toolFunctions dict with OpenAI function schema format
    tool_functions = None
    if tool_list:
        tool_functions = {}
        for tool in tool_list:
            tool_name = tool.get("name")
            if tool_name:
                # Create function name with server suffix
                function_key = f"{tool_name}_{server.serverName}".lower().replace(" ", "_")
                
                tool_functions[function_key] = {
                    "type": "function",
                    "function": {
                        "name": function_key,
                        "description": tool.get("description", ""),
                        "parameters": tool.get("inputSchema", {
                            "type": "object",
                            "properties": {},
                            "required": []
                        })
                    }
                }
    
    # Convert capabilities dict to JSON string if present
    capabilities = config.get("capabilities")
    capabilities_str = None
    if capabilities:
        capabilities_str = json.dumps(capabilities) if isinstance(capabilities, dict) else str(capabilities)
    
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
    
    # Parse last_error if stored as ISO string
    last_error = None
    if config.get("last_error"):
        try:
            if isinstance(config["last_error"], str):
                last_error = datetime.fromisoformat(config["last_error"].replace('Z', '+00:00'))
            elif isinstance(config["last_error"], datetime):
                last_error = config["last_error"]
        except (ValueError, AttributeError):
            pass
    
    return ServerDetailResponse(
        id=str(server.id),
        serverName=server.serverName,
        title=title,
        description=config.get("description"),
        type=transport_type,
        url=config.get("url"),
        apiKey=config.get("apiKey"),
        authentication=config.get("authentication"),
        requiresOAuth=config.get("requires_oauth", False),
        capabilities=capabilities_str,
        tools=tools_str,
        toolFunctions=tool_functions,
        initDuration=config.get("init_timeout"),
        author=author_id,
        scope=config.get("scope", "private_user"),
        status=config.get("status", "active"),
        path=config.get("path", ""),
        tags=config.get("tags", []),
        numTools=config.get("num_tools", 0),
        numStars=config.get("num_stars", 0),
        enabled=config.get("enabled", True),
        lastConnected=last_connected,
        lastError=str(last_error.isoformat()) if last_error else None,
        errorMessage=config.get("error_message"),
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_create_response(server) -> ServerCreateResponse:
    """Convert MCPServerDocument to ServerCreateResponse"""
    config = server.config or {}
    
    # Decrypt sensitive authentication fields before returning
    config = decrypt_auth_fields(config)
    
    # Extract author_id from server.author PydanticObjectId
    author_id = str(server.author) if server.author else None
    
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
    
    return ServerCreateResponse(
        id=str(server.id),
        serverName=server.serverName,
        path=config.get("path", ""),
        description=config.get("description"),
        url=config.get("url"),
        supported_transports=config.get("supported_transports", []),
        auth_type=config.get("auth_type"),
        tags=config.get("tags", []),
        num_tools=config.get("num_tools", 0),
        num_stars=config.get("num_stars", 0),
        is_python=config.get("is_python", False),
        license=config.get("license"),
        tool_list=config.get("tool_list", []),
        scope=config.get("scope", "private_user"),
        status=config.get("status", "active"),
        enabled=config.get("enabled", True),
        author_id=author_id,
        authentication=config.get("authentication"),
        apiKey=config.get("apiKey"),
        requires_oauth=config.get("requires_oauth", False),
        last_connected=last_connected,
        init_duration=config.get("init_timeout"),
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_update_response(server) -> ServerUpdateResponse:
    """Convert MCPServerDocument to ServerUpdateResponse"""
    config = server.config or {}
    
    return ServerUpdateResponse(
        id=str(server.id),
        serverName=server.serverName,
        path=config.get("path", ""),
        description=config.get("description"),
        tags=config.get("tags", []),
        num_tools=config.get("num_tools", 0),
        num_stars=config.get("num_stars", 0),
        status=config.get("status", "active"),
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_toggle_response(server, enabled: bool) -> ServerToggleResponse:
    """Convert MCPServerDocument to ServerToggleResponse"""
    config = server.config or {}
    return ServerToggleResponse(
        id=str(server.id),
        serverName=server.serverName,
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
        serverName=server.serverName,
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
        serverName=server.serverName,
        path=config.get("path", ""),
        status=health_data.get("status", "healthy"),
        last_checked=health_data.get("last_checked", datetime.now()),
        response_time_ms=health_data.get("response_time_ms"),
        num_tools=config.get("num_tools", 0),
    )
