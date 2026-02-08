"""
Pydantic Schemas for Server Management API v1

These schemas define the request and response models for the
Server Management endpoints based on the API documentation.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_serializer

from registry.schemas.acl_schema import ResourcePermissions
from registry.utils.crypto_utils import decrypt_auth_fields

# ==================== Request Schemas ====================


class ServerCreateRequest(BaseModel):
    """Request schema for creating a new server"""

    serverName: str = Field(..., alias="serverName", description="Name of the MCP server")
    path: str = Field(..., description="Unique path/route for the server")
    description: str | None = Field(default="", description="Server description")
    url: str | None = Field(default=None, description="Backend proxy URL")
    tags: list[str] = Field(default_factory=list, description="Server tags")
    num_tools: int = Field(default=0, description="Number of tools")
    num_stars: int = Field(default=0, description="Star count")
    is_python: bool = Field(default=False, description="Is Python-based")
    license: str | None = Field(default=None, description="License type")
    auth_type: str | None = Field(default=None, description="Authentication type")
    auth_provider: str | None = Field(default=None, description="Authentication provider")
    supported_transports: list[str] = Field(default_factory=list, description="Supported transports")
    transport: str | dict[str, Any] | None = Field(default=None, description="Transport configuration (string or dict)")
    startup: bool = Field(default=False, description="Start on system startup")
    chat_menu: bool = Field(default=True, description="Show in chat menu")
    tool_list: list[dict[str, Any]] = Field(default_factory=list, description="List of tools")
    icon_path: str | None = Field(default=None, description="Icon path")
    timeout: int | None = Field(default=30000, description="Request timeout (ms)")
    init_timeout: int | None = Field(default=60000, description="Init timeout (ms)")
    server_instructions: str | None = Field(default=None, description="Usage instructions")
    requires_oauth: bool = Field(default=False, description="Requires OAuth")
    oauth: dict[str, Any] | None = Field(default=None, description="OAuth configuration")
    custom_user_vars: dict[str, Any] | None = Field(default=None, description="Custom variables")
    apiKey: dict[str, Any] | None = Field(default=None, description="API Key authentication configuration")
    enabled: bool | None = Field(
        default=None, description="Whether the server is enabled (auto-set to False during registration)"
    )

    class ConfigDict:
        populate_by_name = True  # Allow both serverName and server_name

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v):
        """Convert tags to lowercase for case-insensitive comparison"""
        if isinstance(v, list):
            return [tag.lower() if isinstance(tag, str) else tag for tag in v]
        return v


class ServerUpdateRequest(BaseModel):
    """Request schema for updating a server (partial update)"""

    serverName: str | None = Field(None, alias="serverName")
    path: str | None = None
    description: str | None = None
    url: str | None = None
    type: str | None = None
    tags: list[str] | None = None
    num_tools: int | None = None
    num_stars: int | None = None
    is_python: bool | None = None
    license: str | None = None
    auth_type: str | None = None
    auth_provider: str | None = None
    supported_transports: list[str] | None = None
    transport: str | dict[str, Any] | None = None
    startup: bool | None = None
    chat_menu: bool | None = None
    tool_list: list[dict[str, Any]] | None = None
    icon_path: str | None = None
    timeout: int | None = None
    init_timeout: int | None = None
    server_instructions: str | None = None
    requires_oauth: bool | None = None
    oauth: dict[str, Any] | None = None
    custom_user_vars: dict[str, Any] | None = None
    apiKey: dict[str, Any] | None = None
    status: str | None = None
    enabled: bool | None = None

    class ConfigDict:
        populate_by_name = True  # Allow both serverName and server_name

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, v):
        """Convert tags to lowercase"""
        if isinstance(v, list):
            return [tag.lower() if isinstance(tag, str) else tag for tag in v]
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        """Validate status values"""
        if v is not None:
            valid_statuses = ["active", "inactive", "error"]
            if v not in valid_statuses:
                raise ValueError(f"status must be one of {valid_statuses}")
        return v


class ServerToggleRequest(BaseModel):
    """Request schema for toggling server status"""

    enabled: bool = Field(..., description="Enable or disable the server")


class ServerConnectionTestRequest(BaseModel):
    """Request schema for testing connection to an MCP server URL"""

    url: str = Field(..., description="MCP server URL to test connection")
    transport: str | None = Field(default="streamable-http", description="Transport type (streamable-http, sse, stdio)")


# ==================== Response Schemas ====================


class ToolSchema(BaseModel):
    """Schema for a tool definition"""

    name: str
    description: str
    inputSchema: dict[str, Any] | None = None

    class ConfigDict:
        extra = "allow"


class ServerListItemResponse(BaseModel):
    """Response schema for a server in the list"""

    id: str = Field(..., description="Server ID")
    serverName: str = Field(..., alias="serverName")
    title: str | None = Field(None, description="Display title for the server")
    description: str | None = None
    type: str | None = Field(None, description="Transport type (e.g., streamable-http, sse, stdio)")
    url: str | None = None
    apiKey: dict[str, Any] | None = None
    oauth: dict[str, Any] | None = None
    requiresOAuth: bool = Field(False, alias="requiresOAuth", description="Whether OAuth is required")
    capabilities: str | None = Field(None, description="JSON string of server capabilities")
    oauthMetadata: dict[str, Any] | None = Field(
        None, alias="oauthMetadata", description="OAuth metadata from autodiscovery"
    )
    tools: str | None = Field(None, description="Comma-separated list of tool names")
    author: str | None = Field(None, description="Author user ID")
    status: str = "active"
    path: str | None = Field(None, description="API path for this server, option to consider jarvis model schema")
    tags: list[str] = Field(default_factory=list)
    numTools: int = Field(0, alias="numTools")
    numStars: int = Field(0, alias="numStars")
    enabled: bool = Field(default=True, description="Whether the server is enabled")
    lastConnected: datetime | None = Field(None, alias="lastConnected")
    createdAt: datetime
    updatedAt: datetime
    # Connection status fields
    connectionState: str | None = Field(default=None, description="Connection state")
    error: str | None = Field(default=None, description="Error message if connection failed")
    # ACL permissions for the requesting user
    permissions: ResourcePermissions | None = Field(
        default=None, description="Resolved ACL permissions for the current user"
    )

    class ConfigDict:
        from_attributes = True
        populate_by_name = True

    @model_serializer(mode="wrap")
    def _serialize(self, serializer, info):
        data = serializer(self)
        # Handle mutually exclusive authentication fields: oauth and apiKey
        has_oauth = data.get("oauth") is not None
        has_api_key = data.get("apiKey") is not None

        if has_oauth:
            # If oauth exists, remove apiKey from response
            data.pop("apiKey", None)
        elif has_api_key:
            # If only apiKey exists, remove oauth from response
            data.pop("oauth", None)
        else:
            # If both are None/empty, remove both fields
            data.pop("oauth", None)
            data.pop("apiKey", None)
        return data


class ServerDetailResponse(BaseModel):
    """Response schema for detailed server information"""

    id: str
    serverName: str = Field(..., alias="serverName")
    title: str | None = Field(None, description="Display title for the server")
    description: str | None = None
    type: str | None = Field(None, description="Transport type (e.g., streamable-http, sse, stdio)")
    url: str | None = None
    apiKey: dict[str, Any] | None = None
    oauth: dict[str, Any] | None = None
    requiresOAuth: bool = Field(False, alias="requiresOAuth", description="Whether OAuth is required")
    capabilities: str | None = Field(None, description="JSON string of server capabilities")
    oauthMetadata: dict[str, Any] | None = Field(
        None, alias="oauthMetadata", description="OAuth metadata from autodiscovery"
    )
    tools: str | None = Field(None, description="Comma-separated list of tool names")
    toolFunctions: dict[str, Any] | None = Field(
        None, alias="toolFunctions", description="Complete OpenAI function schemas with mcpToolName"
    )
    resources: list[dict[str, Any]] | None = Field(None, description="List of available resources")
    prompts: list[dict[str, Any]] | None = Field(None, description="List of available prompts")
    initDuration: int | None = Field(None, alias="initDuration", description="Initialization duration in ms")
    author: str | None = Field(None, description="Author user ID")
    status: str
    path: str | None = Field(None, description="API path for this server, compatible with jarvis model schema")
    tags: list[str] = Field(default_factory=list)
    numTools: int = Field(0, alias="numTools")
    numStars: int = Field(0, alias="numStars")
    enabled: bool = Field(default=True, description="Whether the server is enabled")
    lastConnected: datetime | None = Field(None, alias="lastConnected")
    lastError: str | None = Field(None, alias="lastError")
    errorMessage: str | None = Field(None, alias="errorMessage")
    createdAt: datetime
    updatedAt: datetime

    connectionState: str | None = Field(default=None, description="Connection state")
    error: str | None = Field(default=None, description="Error message if connection failed")
    # ACL permissions for the requesting user
    permissions: ResourcePermissions | None = Field(
        default=None, description="Resolved ACL permissions for the current user"
    )

    class ConfigDict:
        from_attributes = True
        populate_by_name = True

    @model_serializer(mode="wrap")
    def _serialize(self, serializer, info):
        data = serializer(self)
        # Handle mutually exclusive authentication fields: oauth and apiKey
        has_oauth = data.get("oauth") is not None
        has_api_key = data.get("apiKey") is not None

        if has_oauth:
            # If oauth exists, remove apiKey from response
            data.pop("apiKey", None)
        elif has_api_key:
            # If only apiKey exists, remove oauth from response
            data.pop("oauth", None)
        else:
            # If both are None/empty, remove both fields
            data.pop("oauth", None)
            data.pop("apiKey", None)
        return data


class ServerCreateResponse(BaseModel):
    """Response schema for server creation - flattened structure matching API doc"""

    serverName: str = Field(..., alias="serverName")
    title: str | None = None
    description: str | None = None
    type: str | None = None
    url: str | None = None
    apiKey: dict[str, Any] | None = None
    oauth: dict[str, Any] | None = None
    requiresOAuth: bool = Field(False, alias="requiresOAuth")
    capabilities: str | None = None
    oauthMetadata: dict[str, Any] | None = Field(
        None, alias="oauthMetadata", description="OAuth metadata from autodiscovery"
    )
    tools: str | None = None
    toolFunctions: dict[str, Any] | None = Field(
        None, alias="toolFunctions", description="Complete OpenAI function schemas with mcpToolName"
    )
    resources: list[dict[str, Any]] | None = Field(None, description="List of available resources")
    prompts: list[dict[str, Any]] | None = Field(None, description="List of available prompts")
    initDuration: int | None = Field(None, alias="initDuration")
    author: str | None = None
    status: str
    path: str
    tags: list[str] = Field(default_factory=list)
    numTools: int = Field(0, alias="numTools")
    numStars: int = Field(0, alias="numStars")
    enabled: bool = Field(default=True, description="Whether the server is enabled")
    lastConnected: datetime | None = Field(None, alias="lastConnected")
    lastError: datetime | None = Field(None, alias="lastError")
    errorMessage: str | None = Field(None, alias="errorMessage")
    createdAt: datetime
    updatedAt: datetime

    class ConfigDict:
        from_attributes = True
        populate_by_name = True

    @model_serializer(mode="wrap")
    def _serialize(self, serializer, info):
        data = serializer(self)

        # Handle mutually exclusive auth fields: oauth and apiKey
        # Priority: oauth > apiKey
        # If all are None/empty, remove all auth fields
        has_oauth = data.get("oauth") is not None
        has_api_key = data.get("apiKey") is not None

        if has_oauth:
            # Keep oauth, remove apiKey
            data.pop("apiKey", None)
        elif has_api_key:
            # Keep apiKey, remove oauth
            data.pop("oauth", None)
        else:
            # No auth required, remove all auth fields
            data.pop("oauth", None)
            data.pop("apiKey", None)

        return data


class ServerUpdateResponse(BaseModel):
    """Response schema for server update"""

    id: str
    serverName: str = Field(..., alias="serverName")
    path: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
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
    tools: list[dict[str, Any]]
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
    lastConnected: datetime | None = None
    lastError: datetime | None = None
    errorMessage: str | None = None
    numTools: int
    capabilities: str | None = None  # JSON string
    tools: str | None = None  # Comma-separated tool names
    initDuration: int | None = None  # Initialization duration in ms
    message: str
    updatedAt: datetime

    class ConfigDict:
        from_attributes = True
        populate_by_name = True


class ServerConnectionTestResponse(BaseModel):
    """Response schema for connection test"""

    success: bool = Field(..., description="Whether the connection test was successful")
    message: str = Field(..., description="Descriptive message about the connection result")
    serverName: str | None = Field(None, description="MCP server name from serverInfo")
    protocolVersion: str | None = Field(None, description="MCP protocol version")
    responseTimeMs: int | None = Field(None, description="Response time in milliseconds")
    capabilities: dict[str, Any] | None = Field(None, description="Server capabilities")
    error: str | None = Field(None, description="Error message if connection failed")

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

    servers: list[ServerListItemResponse]
    pagination: PaginationMetadata


class ErrorResponse(BaseModel):
    """Error response schema"""

    error: str
    message: str


class ServerStatsResponse(BaseModel):
    """Response schema for server statistics (Admin only)"""

    total_servers: int = Field(..., description="Total number of servers")
    servers_by_status: dict[str, int] = Field(..., description="Server count grouped by status")
    servers_by_transport: dict[str, int] = Field(..., description="Server count grouped by transport type")
    total_tokens: int = Field(..., description="Total number of tokens")
    tokens_by_type: dict[str, int] = Field(..., description="Token count grouped by type")
    active_tokens: int = Field(..., description="Number of active (non-expired) tokens")
    expired_tokens: int = Field(..., description="Number of expired tokens")
    active_users: int = Field(..., description="Number of users with active tokens")
    total_tools: int = Field(..., description="Total number of tools across all servers")

    class ConfigDict:
        from_attributes = True


# ==================== Helper Functions ====================


def _get_config_field(server, field: str, default=None):
    """Extract a field from server.config with fallback to default"""
    if not server or not hasattr(server, "config") or not server.config:
        return default
    return server.config.get(field, default)


def _mask_oauth_client_secret(oauth_config: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Mask OAuth client_secret to show only the last 6 characters.

    Args:
        oauth_config: OAuth configuration dictionary

    Returns:
        OAuth config with masked client_secret (only last 6 characters visible)
    """
    if not oauth_config or not isinstance(oauth_config, dict):
        return oauth_config

    # Create a copy to avoid modifying the original
    masked_oauth = oauth_config.copy()

    if "client_secret" in masked_oauth and masked_oauth["client_secret"]:
        client_secret = str(masked_oauth["client_secret"])
        # Only show last 6 characters
        if len(client_secret) > 6:
            masked_oauth["client_secret"] = "************" + client_secret[-6:]
        # If secret is 6 chars or less, just show it as is (edge case)

    return masked_oauth


def _mask_apikey(apikey_config: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Mask API Key to show only the last 6 characters.

    Args:
        apikey_config: API Key configuration dictionary

    Returns:
        API Key config with masked key (only last 6 characters visible)
    """
    if not apikey_config or not isinstance(apikey_config, dict):
        return apikey_config

    # Create a copy to avoid modifying the original
    masked_apikey = apikey_config.copy()

    if "key" in masked_apikey and masked_apikey["key"]:
        key_value = str(masked_apikey["key"])
        # Only show last 6 characters
        if len(key_value) > 6:
            masked_apikey["key"] = "************" + key_value[-6:]
        # If key is 6 chars or less, just show it as is (edge case)

    return masked_apikey


def convert_to_list_item(
    server,
    acl_permission: ResourcePermissions | None = None,
) -> ServerListItemResponse:
    """Convert ExtendedMCPServer to ServerListItemResponse matching API documentation.

    Args:
        server: The ExtendedMCPServer document.
        acl_permission: Optional resolved permissions for the requesting user.
    """
    config = server.config or {}

    # Decrypt sensitive authentication fields before returning
    config = decrypt_auth_fields(config)

    # Mask OAuth client_secret to only show last 6 characters
    oauth_config = _mask_oauth_client_secret(config.get("oauth"))

    # Mask API Key to only show last 6 characters
    apikey_config = _mask_apikey(config.get("apiKey"))

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
    num_tools = server.numTools if hasattr(server, "numTools") else 0

    return ServerListItemResponse(
        id=str(server.id),
        serverName=server.serverName,
        title=title,
        description=config.get("description"),
        type=transport_type,
        url=config.get("url"),
        apiKey=apikey_config,
        oauth=oauth_config,
        requiresOAuth=config.get("requiresOAuth", False),
        capabilities=capabilities_str,
        oauthMetadata=config.get("oauthMetadata"),
        tools=tools_str,
        author=author_id,
        # Registry fields from root level
        status=server.status,
        path=server.path,
        tags=server.tags,
        numTools=num_tools,
        numStars=server.numStars,
        enabled=config.get("enabled", True),  # Read enabled from config, default to True for backward compatibility
        lastConnected=server.lastConnected,
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
        permissions=acl_permission,
    )


def convert_to_detail(
    server,
    acl_permission: ResourcePermissions | None = None,
) -> ServerDetailResponse:
    """Convert ExtendedMCPServer to ServerDetailResponse matching API documentation.

    Args:
        server: The ExtendedMCPServer document.
        acl_permission: Optional resolved permissions for the requesting user.
    """
    config = server.config or {}

    # Decrypt sensitive authentication fields before returning
    config = decrypt_auth_fields(config)

    # Mask OAuth client_secret to only show last 6 characters
    oauth_config = _mask_oauth_client_secret(config.get("oauth"))

    # Mask API Key to only show last 6 characters
    apikey_config = _mask_apikey(config.get("apiKey"))

    # Extract author_id from server.author PydanticObjectId
    author_id = str(server.author) if server.author else None

    # Get transport type from config.type
    transport_type = config.get("type", "streamable-http")

    # Generate title from config.title or serverName
    title = config.get("title") or server.serverName

    # Get tools string from config (already comma-separated)
    tools_str = config.get("tools", "")

    # Get toolFunctions directly from config (already in OpenAI format with mcpToolName)
    tool_functions = config.get("toolFunctions")

    # Get resources and prompts from config
    resources = config.get("resources", [])
    prompts = config.get("prompts", [])

    # Get capabilities from config (already JSON string)
    capabilities_str = config.get("capabilities", "{}")

    # Get numTools from root level (already calculated)
    num_tools = server.numTools if hasattr(server, "numTools") else 0

    # Format lastError as ISO string if present
    last_error_str = None
    if server.lastError:
        last_error_str = (
            server.lastError.isoformat() if isinstance(server.lastError, datetime) else str(server.lastError)
        )

    return ServerDetailResponse(
        id=str(server.id),
        serverName=server.serverName,
        title=title,
        description=config.get("description"),
        type=transport_type,
        url=config.get("url"),
        apiKey=apikey_config,
        oauth=oauth_config,
        requiresOAuth=config.get("requiresOAuth", False),
        capabilities=capabilities_str,
        oauthMetadata=config.get("oauthMetadata"),
        tools=tools_str,
        toolFunctions=tool_functions,
        resources=resources,
        prompts=prompts,
        initDuration=config.get("initDuration"),
        author=author_id,
        # Registry fields from root level
        status=server.status,
        path=server.path,
        tags=server.tags,
        numTools=num_tools,
        numStars=server.numStars,
        enabled=config.get("enabled", True),  # Read enabled from config, default to True for backward compatibility
        lastConnected=server.lastConnected,
        lastError=last_error_str,
        errorMessage=server.errorMessage if hasattr(server, "errorMessage") else None,
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
        permissions=acl_permission,
    )


def convert_to_create_response(server) -> ServerCreateResponse:
    """Convert ExtendedMCPServer to ServerCreateResponse - flattened structure"""
    config = server.config or {}

    # Decrypt sensitive authentication fields before returning
    config = decrypt_auth_fields(config)

    # Mask OAuth client_secret to only show last 6 characters
    oauth_config = _mask_oauth_client_secret(config.get("oauth"))

    # Mask API Key to only show last 6 characters
    apikey_config = _mask_apikey(config.get("apiKey"))

    # Extract author_id from server.author PydanticObjectId
    author_id = str(server.author) if server.author else None

    # Get numTools from root level
    num_tools = server.numTools if hasattr(server, "numTools") else 0

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
        apiKey=apikey_config,
        oauth=oauth_config,
        requiresOAuth=config.get("requiresOAuth", False),
        capabilities=config.get("capabilities", "{}"),
        oauthMetadata=config.get("oauthMetadata"),
        tools=config.get("tools", ""),
        toolFunctions=config.get("toolFunctions", {}),
        resources=config.get("resources", []),
        prompts=config.get("prompts", []),
        initDuration=config.get("initDuration"),
        author=author_id,
        status=server.status,
        path=server.path,
        tags=server.tags,
        numTools=num_tools,
        numStars=server.numStars,
        enabled=config.get("enabled", True),  # Read enabled from config, default to True for backward compatibility
        lastConnected=server.lastConnected,
        lastError=last_error,
        errorMessage=server.errorMessage if hasattr(server, "errorMessage") else None,
        createdAt=server.createdAt or datetime.now(),
        updatedAt=server.updatedAt or datetime.now(),
    )


def convert_to_update_response(server) -> ServerUpdateResponse:
    """Convert ExtendedMCPServer to ServerUpdateResponse matching API documentation"""
    config = server.config or {}

    # Get numTools from root level
    num_tools = server.numTools if hasattr(server, "numTools") else 0

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


def convert_to_tools_response(server, tool_functions: dict[str, Any]) -> ServerToolsResponse:
    """Convert ExtendedMCPServer to ServerToolsResponse matching API documentation"""
    # Convert toolFunctions dict to list format for response
    tools_list = []
    if tool_functions:
        for _func_key, func_def in tool_functions.items():
            if isinstance(func_def, dict) and "function" in func_def:
                func = func_def["function"]
                tools_list.append(
                    {
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "inputSchema": func.get("parameters", {}),
                    }
                )

    return ServerToolsResponse(
        id=str(server.id),
        serverName=server.serverName,
        path=server.path,
        tools=tools_list,
        num_tools=len(tools_list),
        cached=False,
    )


def convert_to_health_response(server, health_data: dict[str, Any]) -> ServerHealthResponse:
    """Convert ExtendedMCPServer to ServerHealthResponse matching API documentation"""
    # Get config fields
    config = server.config or {}

    # Get numTools from root level
    num_tools = server.numTools if hasattr(server, "numTools") else 0

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
