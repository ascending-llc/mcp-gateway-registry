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
    path: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
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
    oauthMetadata: Optional[Dict[str, Any]] = Field(None, alias="oauthMetadata", description="OAuth metadata from autodiscovery")
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
    connectionState: Optional[str] = Field(default=None, description="Connection state")
    error: Optional[str] = Field(default=None, description="Error message if connection failed")
    
    class ConfigDict:
        from_attributes = True
        populate_by_name = True
    
    @model_serializer(mode='wrap')
    def _serialize(self, serializer, info):
        data = serializer(self)
        # Handle mutually exclusive authentication fields
        has_authentication = data.get('authentication') is not None
        has_api_key = data.get('apiKey') is not None
        
        if has_authentication:
            # If authentication exists, remove apiKey from response
            data.pop('apiKey', None)
        elif has_api_key:
            # If only apiKey exists, remove authentication from response
            data.pop('authentication', None)
        else:
            # If both are None/empty, remove both fields
            data.pop('apiKey', None)
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
    oauthMetadata: Optional[Dict[str, Any]] = Field(None, alias="oauthMetadata", description="OAuth metadata from autodiscovery")
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

    connectionState: Optional[str] = Field(default=None, description="Connection state")
    error: Optional[str] = Field(default=None, description="Error message if connection failed")
    
    class ConfigDict:
        from_attributes = True
        populate_by_name = True
    
    @model_serializer(mode='wrap')
    def _serialize(self, serializer, info):
        data = serializer(self)
        # Handle mutually exclusive authentication fields
        has_authentication = data.get('authentication') is not None
        has_api_key = data.get('apiKey') is not None
        
        if has_authentication:
            # If authentication exists, remove apiKey from response
            data.pop('apiKey', None)
        elif has_api_key:
            # If only apiKey exists, remove authentication from response
            data.pop('authentication', None)
        else:
            # If both are None/empty, remove both fields
            data.pop('apiKey', None)
            data.pop('authentication', None)
        return data


class ServerCreateResponse(BaseModel):
    """Response schema for server creation - flattened structure matching API doc"""
    serverName: str = Field(..., alias="serverName")
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None
    apiKey: Optional[Dict[str, Any]] = None
    oauth: Optional[Dict[str, Any]] = None
    authentication: Optional[Dict[str, Any]] = None
    requiresOAuth: bool = Field(False, alias="requiresOAuth")
    capabilities: Optional[str] = None
    oauthMetadata: Optional[Dict[str, Any]] = Field(None, alias="oauthMetadata", description="OAuth metadata from autodiscovery")
    tools: Optional[str] = None
    toolFunctions: Optional[Dict[str, Any]] = Field(None, alias="toolFunctions")
    initDuration: Optional[int] = Field(None, alias="initDuration")
    author: Optional[str] = None
    scope: str
    status: str
    path: str
    tags: List[str] = Field(default_factory=list)
    numTools: int = Field(0, alias="numTools")
    numStars: int = Field(0, alias="numStars")
    enabled: bool = Field(default=True, description="Whether the server is enabled")
    lastConnected: Optional[datetime] = Field(None, alias="lastConnected")
    lastError: Optional[datetime] = Field(None, alias="lastError")
    errorMessage: Optional[str] = Field(None, alias="errorMessage")
    createdAt: datetime
    updatedAt: datetime
    
    class ConfigDict:
        from_attributes = True
        populate_by_name = True
    
    @model_serializer(mode='wrap')
    def _serialize(self, serializer, info):
        data = serializer(self)
        
        # Handle mutually exclusive auth fields
        # Priority: authentication > oauth > apiKey
        # If all are None/empty, remove all auth fields
        has_authentication = data.get('authentication') is not None
        has_oauth = data.get('oauth') is not None
        has_api_key = data.get('apiKey') is not None
        
        if has_authentication:
            # Keep authentication, remove others
            data.pop('oauth', None)
            data.pop('apiKey', None)
        elif has_oauth:
            # Keep oauth, remove others
            data.pop('authentication', None)
            data.pop('apiKey', None)
        elif has_api_key:
            # Keep apiKey, remove others
            data.pop('authentication', None)
            data.pop('oauth', None)
        else:
            # No auth required, remove all auth fields
            data.pop('authentication', None)
            data.pop('oauth', None)
            data.pop('apiKey', None)
        
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
    status: str
    lastConnected: Optional[datetime] = None
    lastError: Optional[datetime] = None
    errorMessage: Optional[str] = None
    numTools: int
    capabilities: Optional[str] = None  # JSON string
    tools: Optional[str] = None  # Comma-separated tool names
    initDuration: Optional[int] = None  # Initialization duration in ms
    message: str
    updatedAt: datetime
    
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
    """Convert ExtendedMCPServer to ServerListItemResponse matching API documentation"""
    config = server.config or {}
    
    # Decrypt sensitive authentication fields before returning
    config = decrypt_auth_fields(config)
    
    # Extract author_id from server.author PydanticObjectId
    author_id = str(server.author) if server.author else None
    
    # Get transport type from config.type
    transport_type = config.get("type", "streamable-http")
    
    # Generate title from config.title or serverName
    title = config.get("title") or server.serverName
    
    # Get tools string from config (already comma-separated)
    tools_str = config.get("tools", "")
    
    # Get capabilities from config (already JSON string)
    capabilities_str = config.get("capabilities", "{}")
    
    # Get numTools from root level (already calculated)
    num_tools = server.numTools if hasattr(server, 'numTools') else 0
    
    return ServerListItemResponse(
        id=str(server.id),
        serverName=server.serverName,
        title=title,
        description=config.get("description"),
        type=transport_type,
        url=config.get("url"),
        apiKey=config.get("apiKey"),
        authentication=config.get("authentication"),
        requiresOAuth=config.get("requiresOAuth", False),
        capabilities=capabilities_str,
        oauthMetadata=config.get("oauthMetadata"),
        tools=tools_str,
        author=author_id,
        # Registry fields from root level
        scope=server.scope,
        status=server.status,
        path=server.path,
        tags=server.tags,
        numTools=num_tools,
        numStars=server.numStars,
        enabled=config.get("enabled", True),  # Read enabled from config, default to True for backward compatibility
        lastConnected=server.lastConnected,
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_detail(server) -> ServerDetailResponse:
    """Convert ExtendedMCPServer to ServerDetailResponse matching API documentation"""
    config = server.config or {}
    
    # Decrypt sensitive authentication fields before returning
    config = decrypt_auth_fields(config)
    
    # Extract author_id from server.author PydanticObjectId
    author_id = str(server.author) if server.author else None
    
    # Get transport type from config.type
    transport_type = config.get("type", "streamable-http")
    
    # Generate title from config.title or serverName
    title = config.get("title") or server.serverName
    
    # Get tools string from config (already comma-separated)
    tools_str = config.get("tools", "")
    
    # Get toolFunctions directly from config (already in OpenAI format)
    tool_functions = config.get("toolFunctions")
    
    # Get capabilities from config (already JSON string)
    capabilities_str = config.get("capabilities", "{}")
    
    # Get numTools from root level (already calculated)
    num_tools = server.numTools if hasattr(server, 'numTools') else 0
    
    # Format lastError as ISO string if present
    last_error_str = None
    if server.lastError:
        last_error_str = server.lastError.isoformat() if isinstance(server.lastError, datetime) else str(server.lastError)
    
    return ServerDetailResponse(
        id=str(server.id),
        serverName=server.serverName,
        title=title,
        description=config.get("description"),
        type=transport_type,
        url=config.get("url"),
        apiKey=config.get("apiKey"),
        authentication=config.get("authentication"),
        requiresOAuth=config.get("requiresOAuth", False),
        capabilities=capabilities_str,
        oauthMetadata=config.get("oauthMetadata"),
        tools=tools_str,
        toolFunctions=tool_functions,
        initDuration=config.get("initDuration"),
        author=author_id,
        # Registry fields from root level
        scope=server.scope,
        status=server.status,
        path=server.path,
        tags=server.tags,
        numTools=num_tools,
        numStars=server.numStars,
        enabled=config.get("enabled", True),  # Read enabled from config, default to True for backward compatibility
        lastConnected=server.lastConnected,
        lastError=last_error_str,
        errorMessage=server.errorMessage if hasattr(server, 'errorMessage') else None,
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_create_response(server) -> ServerCreateResponse:
    """Convert ExtendedMCPServer to ServerCreateResponse - flattened structure"""
    config = server.config or {}
    
    # Decrypt sensitive authentication fields before returning
    config = decrypt_auth_fields(config)
    
    # Extract author_id from server.author PydanticObjectId
    author_id = str(server.author) if server.author else None
    
    # Get numTools from root level
    num_tools = server.numTools if hasattr(server, 'numTools') else 0
    
    # Format lastError as ISO string if present
    last_error = None
    if server.lastError:
        last_error = server.lastError if isinstance(server.lastError, datetime) else None
    
    return ServerCreateResponse(
        serverName=server.serverName,
        title=config.get("title", server.serverName),
        description=config.get("description"),
        type=config.get("type", "streamable-http"),
        url=config.get("url"),
        apiKey=config.get("apiKey"),
        oauth=config.get("oauth"),
        authentication=config.get("authentication"),
        requiresOAuth=config.get("requiresOAuth", False),
        capabilities=config.get("capabilities", "{}"),
        oauthMetadata=config.get("oauthMetadata"),
        tools=config.get("tools", ""),
        toolFunctions=config.get("toolFunctions", {}),
        initDuration=config.get("initDuration"),
        author=author_id,
        scope=server.scope,
        status=server.status,
        path=server.path,
        tags=server.tags,
        numTools=num_tools,
        numStars=server.numStars,
        enabled=config.get("enabled", True),  # Read enabled from config, default to True for backward compatibility
        lastConnected=server.lastConnected,
        lastError=last_error,
        errorMessage=server.errorMessage if hasattr(server, 'errorMessage') else None,
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_update_response(server) -> ServerUpdateResponse:
    """Convert ExtendedMCPServer to ServerUpdateResponse matching API documentation"""
    config = server.config or {}
    
    # Get numTools from root level
    num_tools = server.numTools if hasattr(server, 'numTools') else 0
    
    return ServerUpdateResponse(
        id=str(server.id),
        serverName=server.serverName,
        path=server.path,
        description=config.get("description"),
        tags=server.tags,
        num_tools=num_tools,
        num_stars=server.numStars,
        status=server.status,
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_toggle_response(server, enabled: bool) -> ServerToggleResponse:
    """Convert ExtendedMCPServer to ServerToggleResponse matching API documentation"""
    return ServerToggleResponse(
        id=str(server.id),
        serverName=server.serverName,
        path=server.path,
        enabled=enabled,
        status=server.status,
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_tools_response(server, tool_functions: Dict[str, Any]) -> ServerToolsResponse:
    """Convert ExtendedMCPServer to ServerToolsResponse matching API documentation"""
    # Convert toolFunctions dict to list format for response
    tools_list = []
    if tool_functions:
        for func_key, func_def in tool_functions.items():
            if isinstance(func_def, dict) and "function" in func_def:
                func = func_def["function"]
                tools_list.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "inputSchema": func.get("parameters", {})
                })
    
    return ServerToolsResponse(
        id=str(server.id),
        serverName=server.serverName,
        path=server.path,
        tools=tools_list,
        num_tools=len(tools_list),
        cached=False,
    )


def convert_to_health_response(server, health_data: Dict[str, Any]) -> ServerHealthResponse:
    """Convert ExtendedMCPServer to ServerHealthResponse matching API documentation"""
    # Get config fields
    config = server.config or {}
    
    # Get numTools from root level
    num_tools = server.numTools if hasattr(server, 'numTools') else 0
    
    # Get capabilities and tools from config
    capabilities = config.get("capabilities", "{}")
    tools = config.get("tools", "")
    
    # Get initDuration from config
    init_duration = config.get("initDuration")
    
    # Build message based on status
    status = health_data.get("status", "healthy")
    if status == "healthy":
        message = "Server health check successful"
    else:
        message = health_data.get("status_message", "Server health check failed")
    
    return ServerHealthResponse(
        id=str(server.id),
        serverName=server.serverName,
        status=server.status,  # Use server.status (active/error) from database
        lastConnected=server.lastConnected,
        lastError=server.lastError,
        errorMessage=server.errorMessage,
        numTools=num_tools,
        capabilities=capabilities,
        tools=tools,
        initDuration=init_duration,
        message=message,
        updatedAt=server.updatedAt,
    )
