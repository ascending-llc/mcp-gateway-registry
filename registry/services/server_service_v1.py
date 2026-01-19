"""
Server Service V1 - Business logic for Server Management API

This service handles all server-related operations using MongoDB and Beanie ODM.

ODM Schema:
- serverName: str (required)
- config: Dict[str, Any] (required) - stores all server configuration
- author: PydanticObjectId (required) - references user who created the server
- createdAt: datetime (auto-generated)
- updatedAt: datetime (auto-generated)
"""

import logging
import httpx
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from beanie import PydanticObjectId
from models import McpTool
from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument
from packages.models._generated.user import IUser
from registry.schemas.server_api_schemas import (
    ServerCreateRequest,
    ServerUpdateRequest,
)
from registry.utils.crypto_utils import encrypt_auth_fields
from registry.core.mcp_client import get_tools_from_server_with_server_info
from vector.search_manager import get_search_index_manager

logger = logging.getLogger(__name__)


def _extract_config_field(server: MCPServerDocument, field: str, default: Any = None) -> Any:
    """Extract a field from server.config with fallback to default"""
    if not server or not server.config:
        return default
    return server.config.get(field, default)


def _convert_tool_list_to_functions(tool_list: List[Dict[str, Any]], server_name: str) -> Dict[str, Any]:
    """
    Convert tool_list array to toolFunctions object in OpenAI format.
    
    Example output:
    {
      "tavily_search_mcp_tavilysearchv1": {
        "type": "function",
        "function": {
          "name": "tavily_search_mcp_tavilysearchv1",
          "description": "Search the web",
          "parameters": {
            "type": "object",
            "properties": {...},
            "required": [...]
          }
        }
      }
    }
    """
    if not tool_list:
        return {}

    tool_functions = {}
    for tool in tool_list:
        tool_name = tool.get("name")
        if not tool_name:
            continue

        # Create function name with server suffix (mcp_servername format)
        # Normalize: lowercase, replace spaces/hyphens with underscores
        normalized_server = server_name.lower().replace(" ", "_").replace("-", "_")
        function_key = f"{tool_name}_mcp_{normalized_server}"

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

    return tool_functions


def _build_config_from_request(data: ServerCreateRequest, server_name: str = None) -> Dict[str, Any]:
    """
    Build config dictionary from ServerCreateRequest
    
    Important: Registry-specific fields (path, tags, scope, status, numStars, lastConnected, etc.)
    are stored at root level in MongoDB, NOT in config.
    Config stores MCP-specific configuration only (title, description, type, url, oauth, apiKey, etc.)
    """
    # Determine if OAuth is required based on oauth/authentication fields
    # If oauth field is provided OR authentication has OAuth URLs, set requiresOAuth to True
    requires_oauth = False
    if data.oauth is not None:
        requires_oauth = True
    elif data.authentication is not None and data.authentication.get('authorize_url'):
        requires_oauth = True
    # If user explicitly sets requires_oauth, respect that (for backward compatibility)
    elif data.requires_oauth:
        requires_oauth = True

    # Build MCP-specific configuration (stored in config object)
    config = {
        "title": data.serverName,  # Use serverName as default title
        "description": data.description or "",
        "type": data.supported_transports[0] if data.supported_transports else "streamable-http",
        "url": data.url,
        "requiresOAuth": requires_oauth,  # Auto-detect based on oauth/authentication fields
        "capabilities": "{}",  # Default empty JSON string
    }

    # Add optional MCP config fields
    if data.timeout is not None:
        config["timeout"] = data.timeout
    if data.init_timeout is not None:
        config["initDuration"] = data.init_timeout  # Match API doc naming
    if data.server_instructions is not None:
        config["server_instructions"] = data.server_instructions
    if data.oauth is not None:
        config["oauth"] = data.oauth
    if data.custom_user_vars is not None:
        config["custom_user_vars"] = data.custom_user_vars

    # Convert tool_list to toolFunctions in OpenAI format
    if data.tool_list is not None:
        use_server_name = server_name or data.serverName
        config["toolFunctions"] = _convert_tool_list_to_functions(data.tool_list, use_server_name)

        # Build tools string (comma-separated tool names)
        tool_names = [tool.get("name", "") for tool in data.tool_list if tool.get("name")]
        if tool_names:
            config["tools"] = ", ".join(tool_names)
        else:
            config["tools"] = ""
    else:
        config["toolFunctions"] = {}
        config["tools"] = ""

    # Handle mutually exclusive authentication fields: apiKey and authentication
    # Only store one of them, with authentication taking priority
    if data.authentication is not None:
        # When authentication is provided, store it and do NOT store apiKey
        config["authentication"] = data.authentication
    elif data.apiKey is not None:
        # When only apiKey is provided, store it
        config["apiKey"] = data.apiKey

    # Store enabled field in config
    config["enabled"] = data.enabled

    return config


def _update_config_from_request(config: Dict[str, Any], data: ServerUpdateRequest, server_name: str = None) -> Dict[
    str, Any]:
    """
    Update config dictionary from ServerUpdateRequest
    
    Important: Only updates MCP-specific config fields.
    Registry fields (path, tags, scope, status) are updated at root level separately.
    Note: enabled field is stored in BOTH config and used to update status at root level.
    """
    update_dict = data.model_dump(exclude_unset=True)

    # Save enabled field separately before removing it (we'll update config with it)
    enabled_value = update_dict.get('enabled')

    # Remove root-level registry fields from update_dict (these are handled at root level)
    # Note: enabled is removed here but will be added to config separately
    registry_fields = ['path', 'tags', 'scope', 'status', 'serverName', 'num_stars', 'enabled']
    for field in registry_fields:
        update_dict.pop(field, None)

    # Handle mutually exclusive authentication fields: apiKey and authentication
    # If one is being updated, remove the other from config
    if 'authentication' in update_dict:
        # When authentication is provided, remove apiKey field and store authentication
        if 'apiKey' in config:
            del config['apiKey']
        # Store authentication with all its fields
        config['authentication'] = update_dict['authentication']
        # Remove from update_dict to avoid duplicate processing
        del update_dict['authentication']
    elif 'apiKey' in update_dict:
        # When apiKey is provided, remove authentication field and store apiKey
        if 'authentication' in config:
            del config['authentication']
        # Store apiKey with all its fields
        config['apiKey'] = update_dict['apiKey']
        # Remove from update_dict to avoid duplicate processing
        del update_dict['apiKey']

    # Update config with MCP-specific fields only
    mcp_config_fields = ['url', 'description', 'type', 'timeout', 'init_timeout', 'server_instructions',
                         'requires_oauth', 'oauth', 'custom_user_vars', 'tool_list']
    for key, value in update_dict.items():
        if key in mcp_config_fields and value is not None:
            # Map init_timeout to initDuration to match API doc
            if key == 'init_timeout':
                config['initDuration'] = value
            else:
                config[key] = value

    # Update enabled field in config if provided
    if enabled_value is not None:
        config['enabled'] = enabled_value

    # Update requiresOAuth based on oauth/authentication fields
    # If oauth or authentication is being updated, recalculate requiresOAuth
    if 'oauth' in update_dict or 'authentication' in update_dict:
        requires_oauth = False

        # Check if oauth field is set in config
        if config.get('oauth') is not None:
            requires_oauth = True
        # Check if authentication has OAuth URLs
        elif config.get('authentication') and config['authentication'].get('authorize_url'):
            requires_oauth = True

        config['requiresOAuth'] = requires_oauth
        logger.info(f"Updated requiresOAuth to {requires_oauth} based on oauth/authentication fields")

    # If tool_list is updated, regenerate toolFunctions and tools string
    if 'tool_list' in update_dict and update_dict['tool_list'] is not None:
        tool_list = update_dict['tool_list']

        # Convert to toolFunctions format
        if server_name:
            config["toolFunctions"] = _convert_tool_list_to_functions(tool_list, server_name)

        # Generate tools string
        tool_names = [tool.get("name", "") for tool in tool_list if tool.get("name")]
        if tool_names:
            config["tools"] = ", ".join(tool_names)
        else:
            config["tools"] = ""

    return config


class ServerServiceV1:
    """Service class for managing MCP servers with MongoDB"""

    def __init__(self):
        """Initialize server service with search index manager."""
        self.search_mgr = get_search_index_manager()
        logger.info("ServerServiceV1 initialized with search index manager")

    async def list_servers(
            self,
            query: Optional[str] = None,
            scope: Optional[str] = None,
            status: Optional[str] = None,
            page: int = 1,
            per_page: int = 20,
            user_id: Optional[str] = None,
    ) -> Tuple[List[MCPServerDocument], int]:
        """
        List servers with filtering and pagination.
        
        Args:
            query: Free-text search across server_name, description, tags
            scope: Filter by access level (shared_app, shared_user, private_user)
            status: Filter by operational state (active, inactive, error)
            page: Page number (min: 1)
            per_page: Items per page (min: 1, max: 100)
            user_id: Current user's ID (kept for compatibility but not used for filtering)
            
        Returns:
            Tuple of (servers list, total count)
        """
        # Validate and sanitize pagination
        page = max(1, page)
        per_page = max(1, min(100, per_page))
        skip = (page - 1) * per_page

        # Build filter conditions
        filters = []

        # Scope filter (now at root level)
        if scope:
            filters.append({"scope": scope})

        # Status filter (now at root level)
        if status:
            filters.append({"status": status})

        # Text search across multiple fields (tags now at root level)
        if query:
            query_lower = query.lower()
            text_filter = {
                "$or": [
                    {"serverName": {"$regex": query, "$options": "i"}},
                    {"config.description": {"$regex": query, "$options": "i"}},
                    {"tags": query_lower}
                ]
            }
            filters.append(text_filter)

        # Combine all filters
        if filters:
            query_filter = {"$and": filters} if len(filters) > 1 else filters[0]
        else:
            query_filter = {}

        # Execute query with pagination
        total = await MCPServerDocument.find(query_filter).count()
        servers = await MCPServerDocument.find(query_filter) \
            .sort([("createdAt", -1)]) \
            .skip(skip) \
            .limit(per_page) \
            .to_list()

        return servers, total

    async def get_server_by_id(
            self,
            server_id: str,
            user_id: Optional[str] = None,
    ) -> Optional[MCPServerDocument]:
        """
        Get a server by its ID.
        
        Args:
            server_id: Server document ID
            user_id: Current user's ID (kept for compatibility but not used)
            
        Returns:
            Server document or None if not found
        """
        try:
            # Convert string ID to ObjectId
            obj_id = PydanticObjectId(server_id)
        except Exception as e:
            logger.warning(f"Invalid server ID format: {server_id}")
            return None

        server = await MCPServerDocument.get(obj_id)

        return server

    async def get_server_by_path(self, path: str) -> Optional[MCPServerDocument]:
        """
        Get a server by its path.
        
        Args:
            path: Server path (e.g., /github)
            
        Returns:
            Server document or None if not found
        """
        return await MCPServerDocument.find_one({"path": path})

    async def create_server(
            self,
            data: ServerCreateRequest,
            user_id: str,
    ) -> MCPServerDocument:
        """
        Create a new server.
        
        Args:
            data: Server creation data
            user_id: ID of the user creating the server
            
        Returns:
            Created server document
            
        Raises:
            ValueError: If path+url combination already exists, server_name already exists, or tags contain duplicates (case-insensitive)
        """
        # Check if path+url combination already exists
        # Only reject if BOTH path AND url are the same (to allow same path for different services)
        existing_servers = await MCPServerDocument.find({"path": data.path}).to_list()
        for existing in existing_servers:
            existing_url = existing.config.get("url") if existing.config else None
            if existing_url == data.url:
                raise ValueError(f"Server with path '{data.path}' and URL '{data.url}' already exists")

        # Check if serverName already exists
        existing_name = await MCPServerDocument.find_one({"serverName": data.serverName})
        if existing_name:
            raise ValueError(f"Server with name '{data.serverName}' already exists")

        # Check for duplicate tags (case-insensitive)
        normalized_tags = [tag.lower() for tag in data.tags]
        if len(normalized_tags) != len(set(normalized_tags)):
            raise ValueError("Duplicate tags are not allowed (case-insensitive)")

        # Build MCP config dictionary (MCP-specific fields only)
        config = _build_config_from_request(data, server_name=data.serverName)

        # Encrypt sensitive authentication fields before storing
        config = encrypt_auth_fields(config)

        # Calculate numTools from toolFunctions
        tool_functions = config.get("toolFunctions", {})
        num_tools = len(tool_functions) if tool_functions else 0

        # Get or create author user reference
        author = await IUser.find_one({"username": user_id})
        if not author:
            # Create a minimal user record if not exists
            now = datetime.now(timezone.utc)
            # Generate unique email to avoid conflicts
            email = f"{user_id}@local.mcp-gateway.internal"

            # Check if email already exists
            existing_user = await IUser.find_one({"email": email})
            if existing_user:
                author = existing_user
            else:
                # Create user without OAuth ID fields to avoid unique index conflicts
                # Use model_dump with exclude_none to prevent OAuth fields from being included
                user_data = {
                    "username": user_id,
                    "email": email,
                    "emailVerified": False,
                    "role": "USER",
                    "provider": "local",
                    "createdAt": now,
                    "updatedAt": now
                }

                # Insert directly to avoid Pydantic adding None values for OAuth fields
                collection = IUser.get_pymongo_collection()
                result = await collection.insert_one(user_data)

                # Fetch the created user
                author = await IUser.get(result.inserted_id)

        # Create server document with registry fields at root level
        now = datetime.now(timezone.utc)
        server = MCPServerDocument(
            serverName=data.serverName,
            config=config,
            author=author.id,  # Use PydanticObjectId instead of Link
            # Registry-specific root-level fields
            path=data.path,
            tags=[tag.lower() for tag in data.tags],  # Normalize tags to lowercase
            scope=data.scope,
            status="active",  # Default status (independent of enabled field)
            numTools=num_tools,  # Store calculated numTools at root level
            numStars=data.num_stars,
            # Initialize error tracking fields as None
            lastError=None,
            errorMessage=None,
            # Timestamps
            createdAt=now,
            updatedAt=now
        )

        await server.insert()
        logger.info(f"Created server: {server.serverName} (ID: {server.id}, Path: {data.path})")

        # Perform health check and tool retrieval after registration
        if data.url:
            logger.info(f"Performing post-registration health check and tool retrieval for {server.serverName}")

            try:
                # 1. Health check - REQUIRED
                is_healthy, status_msg, response_time_ms = await self.perform_health_check(server)
                logger.info(
                    f"Health check result for {server.serverName}: {status_msg} (response_time: {response_time_ms}ms)")

                if not is_healthy:
                    # Health check failed - delete the server and reject registration
                    logger.error(f"Health check failed for {server.serverName}: {status_msg}")
                    await server.delete()
                    raise ValueError(f"Server registration rejected: Health check failed - {status_msg}")

                # Update server with health check results (root-level field)
                server.lastConnected = datetime.now(timezone.utc)
                server.status = "active"

                # 2. Retrieve capabilities (but skip tools - they will be fetched on-demand)
                logger.info(f"Retrieving capabilities for {server.serverName} (skipping tools)")

                # Initialize empty toolFunctions and tools (will be populated on first use)
                config["toolFunctions"] = {}
                config["tools"] = ""

                # Try to get capabilities only
                try:
                    # Build server_info dict for mcp_client
                    server_info = {
                        "type": config.get("type", "streamable-http"),
                        "tags": server.tags or [],
                    }

                    # Add headers if present
                    if "headers" in config:
                        server_info["headers"] = config["headers"]

                    # Add apiKey if present (for backend server authentication)
                    if "apiKey" in config:
                        server_info["apiKey"] = config["apiKey"]

                    from registry.core.mcp_client import get_tools_and_capabilities_from_server

                    # Get tools and capabilities (we'll only use capabilities)
                    tool_list, capabilities = await get_tools_and_capabilities_from_server(data.url, server_info)

                    # Save capabilities if retrieved successfully
                    if capabilities:
                        import json
                        config["capabilities"] = json.dumps(capabilities)
                        logger.info(f"Saved capabilities for {server.serverName}: {config['capabilities']}")
                    else:
                        config["capabilities"] = "{}"
                        logger.warning(f"No capabilities retrieved for {server.serverName}, using empty JSON")

                except Exception as e:
                    # If capabilities retrieval fails, just use empty capabilities
                    config["capabilities"] = "{}"
                    logger.warning(f"Failed to retrieve capabilities for {server.serverName}: {e}")

                logger.info(f"Server {server.serverName} registered successfully. Tools will be fetched on-demand.")

                # 3. OAuth metadata retrieval - OPTIONAL (only if oauth/authentication is configured)
                # Check if server has OAuth configuration
                has_oauth = (
                        data.oauth is not None or
                        (data.authentication is not None and data.authentication.get('authorize_url'))
                )

                if has_oauth:
                    logger.info(f"OAuth configuration detected for {server.serverName}, retrieving OAuth metadata...")

                    from registry.core.mcp_client import get_oauth_metadata_from_server

                    # Build server_info dict for oauth metadata retrieval
                    server_info = {
                        "type": config.get("type", "streamable-http"),
                        "tags": server.tags or [],
                    }

                    # Add headers if present
                    if "headers" in config:
                        server_info["headers"] = config["headers"]

                    oauth_metadata = await get_oauth_metadata_from_server(data.url, server_info)

                    if oauth_metadata:
                        import json
                        config["oauthMetadata"] = oauth_metadata
                        logger.info(f"Saved OAuth metadata for {server.serverName}: {json.dumps(oauth_metadata)}")
                    else:
                        logger.info(
                            f"No OAuth metadata available for {server.serverName} (server may not support OAuth autodiscovery)")

                # Update numTools at root level (0 since tools not fetched yet)
                server.numTools = 0

                # Save updated server
                server.config = config
                server.updatedAt = datetime.now(timezone.utc)
                await server.save()

                # Sync search index after successful registration and tool retrieval
                server_info = McpTool.from_server_document(server)
                await self.search_mgr.add_or_update_entity(
                    entity_path=server.path,
                    entity_info=server_info,
                    entity_type="mcp_server",
                    is_enabled=config.get("enabled", True)
                )

            except ValueError:
                # Re-raise ValueError (our validation errors)
                raise
            except Exception as e:
                # Unexpected error during health check or tool retrieval
                await server.delete()
        else:
            # No URL - sync search index immediately (for stdio or other transports)
            server_info = self._to_server_info(server)
            await self.search_mgr.add_or_update_entity(
                entity_path=server.path,
                entity_info=server_info,
                entity_type="mcp_server",
                is_enabled=config.get("enabled", True)
            )
        return server

    async def update_server(
            self,
            server_id: str,
            data: ServerUpdateRequest,
            user_id: Optional[str] = None,
    ) -> MCPServerDocument:
        """
        Update a server.
        
        Args:
            server_id: Server document ID
            data: Update data (partial)
            user_id: Current user's ID (kept for compatibility but not used)
            
        Returns:
            Updated server document
            
        Raises:
            ValueError: If server not found
        """
        server = await self.get_server_by_id(server_id, user_id)

        if not server:
            raise ValueError("Server not found")

        # Get current config
        config = server.config or {}

        # Check for duplicate tags if tags are being updated
        if data.tags is not None:
            normalized_tags = [tag.lower() for tag in data.tags]
            if len(normalized_tags) != len(set(normalized_tags)):
                raise ValueError("Duplicate tags are not allowed (case-insensitive)")

        # Update root-level registry fields
        if data.serverName is not None:
            server.serverName = data.serverName
        if data.path is not None:
            server.path = data.path
        if data.tags is not None:
            server.tags = [tag.lower() for tag in data.tags]
        if data.scope is not None:
            server.scope = data.scope
        if data.status is not None:
            server.status = data.status

        # Update config with MCP-specific values only
        updated_config = _update_config_from_request(config, data, server_name=server.serverName)

        # Encrypt sensitive authentication fields if they were updated
        if data.authentication is not None or data.apiKey is not None:
            updated_config = encrypt_auth_fields(updated_config)

        # If toolFunctions was updated, recalculate numTools
        if "toolFunctions" in updated_config:
            tool_functions = updated_config.get("toolFunctions", {})
            server.numTools = len(tool_functions) if tool_functions else 0

        server.config = updated_config

        # Update the updatedAt timestamp
        server.updatedAt = datetime.now(timezone.utc)

        await server.save()
        logger.info(f"Updated server: {server.serverName} (ID: {server.id})")

        # Smart search index update
        try:
            # Determine update strategy based on what changed
            metadata_only_fields = {'tags', 'scope', 'status', 'serverName'}
            tools_changed = data.tool_list is not None
            metadata_changed = any(getattr(data, field, None) is not None
                                   for field in metadata_only_fields)

            if tools_changed:
                # Tools changed - use incremental update
                logger.info(f"Tools changed for '{server.path}', using incremental update")
                server_info = self._to_server_info(server)
                await self.search_mgr.update_entity_incremental(
                    entity_path=server.path,
                    entity_info=server_info,
                    entity_type="mcp_server",
                    is_enabled=updated_config.get("enabled", True)
                )
            elif metadata_changed:
                # Only metadata changed - use metadata update
                logger.info(f"Metadata changed for '{server.path}', using metadata update")
                metadata_updates = {}
                if data.tags is not None:
                    metadata_updates["tags"] = server.tags
                if data.serverName is not None:
                    metadata_updates["server_name"] = server.serverName

                if metadata_updates:
                    await self.search_mgr.update_entity_metadata(
                        entity_path=server.path,
                        metadata=metadata_updates
                    )
            else:
                logger.debug(f"No index-relevant changes for '{server.path}'")

        except Exception as e:
            logger.warning(f"Failed to update search index for '{server.path}': {e}")

        return server

    async def delete_server(
            self,
            server_id: str,
            user_id: Optional[str] = None,
    ) -> bool:
        """
        Delete a server.
        
        Args:
            server_id: Server document ID
            user_id: Current user's ID (kept for compatibility but not used)
            
        Returns:
            True if deleted successfully
            
        Raises:
            ValueError: If server not found
        """
        try:
            obj_id = PydanticObjectId(server_id)
        except Exception as e:
            raise ValueError("Server not found")

        server = await MCPServerDocument.get(obj_id)

        if not server:
            raise ValueError("Server not found")

        # Remove from search index before deleting
        try:
            await self.search_mgr.remove_entity(server.path)
            logger.info(f"Removed search index for '{server.path}'")
        except Exception as e:
            logger.warning(f"Failed to remove search index for '{server.path}': {e}")

        await server.delete()
        logger.info(f"Deleted server: {server.serverName} (ID: {server.id})")

        return True

    async def toggle_server_status(
            self,
            server_id: str,
            enabled: bool,
            user_id: Optional[str] = None,
    ) -> MCPServerDocument:
        """
        Toggle server enabled/disabled status.
        
        Args:
            server_id: Server document ID
            enabled: Enable (True) or disable (False)
            user_id: Current user's ID (kept for compatibility but not used)
            
        Returns:
            Updated server document
            
        Raises:
            ValueError: If server not found
        """
        server = await self.get_server_by_id(server_id, user_id)

        if not server:
            raise ValueError("Server not found")

        # Update enabled field in config only (do not update status field)
        if server.config is None:
            server.config = {}
        server.config['enabled'] = enabled

        # Update the updatedAt timestamp
        server.updatedAt = datetime.now(timezone.utc)

        await server.save()
        logger.info(f"Toggled server {server.serverName} (ID: {server.id}) enabled to {enabled}")

        # update search index
        await self.search_mgr.toggle_entity_status(
            entity_path=server.path,
            is_enabled=enabled
        )
        return server

    async def get_server_tools(
            self,
            server_id: str,
            user_id: Optional[str] = None,
    ) -> Tuple[MCPServerDocument, Dict[str, Any]]:
        """
        Get server tools in toolFunctions format.
        
        Args:
            server_id: Server document ID
            user_id: Current user's ID (kept for compatibility but not used)
            
        Returns:
            Tuple of (server, toolFunctions dict)
            
        Raises:
            ValueError: If server not found
        """
        server = await self.get_server_by_id(server_id, user_id)

        if not server:
            raise ValueError("Server not found")

        tool_functions = _extract_config_field(server, "toolFunctions", {})
        return server, tool_functions

    async def perform_health_check(
            self,
            server: MCPServerDocument,
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Perform health check on a server.
        
        Args:
            server: Server document
            
        Returns:
            Tuple of (is_healthy, status_message, response_time_ms)
        """
        config = server.config or {}
        url = config.get("url")

        if not url:
            return False, "No URL configured", None

        transport_type = config.get("type", "streamable-http")

        # Skip health checks for stdio transport
        if transport_type == "stdio":
            logger.info(f"Skipping health check for stdio transport: {url}")
            return True, "healthy (stdio transport skipped)", None

        try:
            # Perform simple HTTP health check
            start_time = datetime.now(timezone.utc)

            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try to access the MCP endpoint
                base_url = url.rstrip('/')

                # Try streamable-http transport first (most common)
                if transport_type in ["streamable-http", "http"]:
                    endpoint = f"{base_url}/mcp" if not base_url.endswith('/mcp') else base_url

                    try:
                        # Try a simple GET request first
                        response = await client.get(endpoint, follow_redirects=True)

                        # Calculate response time
                        end_time = datetime.now(timezone.utc)
                        response_time_ms = int((end_time - start_time).total_seconds() * 1000)

                        # Check if response indicates a healthy server
                        # 200, 400 (MCP protocol errors), 405 (method not allowed) are all healthy signs
                        if response.status_code in [200, 400, 405]:
                            return True, "healthy", response_time_ms
                        elif response.status_code in [401, 403]:
                            # Auth required but server is responding
                            return True, "healthy (auth required)", response_time_ms
                        else:
                            return False, f"unhealthy: status {response.status_code}", response_time_ms
                    except Exception as e:
                        logger.warning(f"Health check failed for {endpoint}: {e}")
                        return False, f"unhealthy: {type(e).__name__}", None

                # Try SSE transport if configured
                elif transport_type == "sse":
                    endpoint = f"{base_url}/sse" if not base_url.endswith('/sse') else base_url

                    try:
                        response = await client.get(endpoint, follow_redirects=True)
                        end_time = datetime.now(timezone.utc)
                        response_time_ms = int((end_time - start_time).total_seconds() * 1000)

                        if response.status_code in [200, 400, 405]:
                            return True, "healthy", response_time_ms
                        else:
                            return False, f"unhealthy: status {response.status_code}", response_time_ms
                    except Exception as e:
                        logger.warning(f"Health check failed for {endpoint}: {e}")
                        return False, f"unhealthy: {type(e).__name__}", None

                # Unknown transport
                else:
                    return False, f"unsupported transport: {transport_type}", None

        except Exception as e:
            logger.error(f"Health check error for server {server.serverName}: {e}")
            return False, f"error: {type(e).__name__}", None

    async def retrieve_tools_from_server(
            self,
            server: MCPServerDocument,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Retrieve tools from a server using MCP client.
        
        Args:
            server: Server document
            
        Returns:
            Tuple of (tool_list, error_message)
            If successful, returns (tool_list, None)
            If failed, returns (None, error_message)
        """
        config = server.config or {}
        url = config.get("url")

        if not url:
            return None, "No URL configured"

        try:
            # Build server_info dict for mcp_client
            server_info = {
                "type": config.get("type", "streamable-http"),
                "tags": server.tags or [],
            }

            # Add headers if present
            if "headers" in config:
                server_info["headers"] = config["headers"]

            # Add apiKey if present (for backend server authentication)
            if "apiKey" in config:
                server_info["apiKey"] = config["apiKey"]

            logger.info(f"Retrieving tools from {url} for server {server.serverName}")

            # Use the MCP client to get tools
            tool_list = await get_tools_from_server_with_server_info(url, server_info)

            if tool_list is None:
                return None, "Failed to retrieve tools from MCP server"

            logger.info(f"Retrieved {len(tool_list)} tools from {server.serverName}")
            return tool_list, None

        except Exception as e:
            error_msg = f"Error retrieving tools: {type(e).__name__} - {str(e)}"
            logger.error(f"Tool retrieval error for server {server.serverName}: {e}")
            return None, error_msg

    async def retrieve_tools_and_capabilities_from_server(
            self,
            server: MCPServerDocument,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]], Optional[str]]:
        """
        Retrieve tools and capabilities from a server using MCP client.
        
        This is a best-effort attempt - failures are logged but don't prevent registration.
        Tools can be fetched on-demand later.
        
        Args:
            server: Server document
            
        Returns:
            Tuple of (tool_list, capabilities_dict, error_message)
            - If successful, returns (tool_list, capabilities_dict, None)
            - If failed, returns (None, None, error_message)
            - Empty results are acceptable for registration
        """
        config = server.config or {}
        url = config.get("url")

        if not url:
            return None, None, "No URL configured"

        try:
            # Build server_info dict for mcp_client
            server_info = {
                "type": config.get("type", "streamable-http"),
                "tags": server.tags or [],
            }

            # Add headers if present
            if "headers" in config:
                server_info["headers"] = config["headers"]

            # Add apiKey if present (for backend server authentication)
            if "apiKey" in config:
                server_info["apiKey"] = config["apiKey"]

            logger.info(f"Attempting to retrieve tools and capabilities from {url} for server {server.serverName}")

            # Import the new function
            from registry.core.mcp_client import get_tools_and_capabilities_from_server

            # Use the MCP client to get tools and capabilities
            tool_list, capabilities = await get_tools_and_capabilities_from_server(url, server_info)

            if tool_list is None and capabilities is None:
                error_msg = "Failed to retrieve tools and capabilities from MCP server"
                logger.warning(f"{error_msg} for {server.serverName} - will retry on-demand")
                return None, None, error_msg

            # Log success
            tool_count = len(tool_list) if tool_list else 0
            logger.info(f"Retrieved {tool_count} tools and capabilities from {server.serverName}")
            if capabilities:
                logger.info(f"Server capabilities: {capabilities}")

            return tool_list, capabilities, None

        except Exception as e:
            error_msg = f"Error retrieving tools and capabilities: {type(e).__name__} - {str(e)}"
            logger.warning(f"Tool/capabilities retrieval error for server "
                           f"{server.serverName}: {e} - will retry on-demand")
            return None, None, error_msg

    async def refresh_server_health(
            self,
            server_id: str,
            user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Refresh server health status.
        
        Uses the same strict validation as registration:
        - Retrieves tools and capabilities from the server
        - If capabilities cannot be retrieved, server is considered unhealthy
        - This serves as a comprehensive sanity check
        
        Args:
            server_id: Server document ID
            user_id: Current user's ID (kept for compatibility but not used)
            
        Returns:
            Health information dictionary
            
        Raises:
            ValueError: If server not found
        """
        server = await self.get_server_by_id(server_id, user_id)

        if not server:
            raise ValueError("Server not found")

        now = datetime.now(timezone.utc)

        # Use the same validation as registration: retrieve tools and capabilities
        # This is a more comprehensive health check than just HTTP GET
        tool_list, capabilities, tool_error = await self.retrieve_tools_and_capabilities_from_server(server)

        if tool_list is None or capabilities is None:
            # Health check failed - cannot retrieve capabilities
            logger.error(f"Health check failed for {server.serverName}: {tool_error}")

            server.status = "error"
            server.lastError = now
            server.errorMessage = tool_error or "Failed to retrieve capabilities"
            server.lastConnected = now
            server.updatedAt = now

            await server.save()

            return {
                "server": server,
                "status": "unhealthy",
                "status_message": tool_error or "Failed to retrieve capabilities",
                "last_checked": now,
                "response_time_ms": None,
            }

        # Health check passed - capabilities retrieved successfully
        logger.info(f"Health check passed for {server.serverName}: retrieved {len(tool_list)} tools and capabilities")

        server.status = "active"
        server.lastError = None
        server.errorMessage = None
        server.lastConnected = now
        server.updatedAt = now

        # Optionally update capabilities in config if they changed
        import json
        config = server.config or {}
        if capabilities:
            config["capabilities"] = json.dumps(capabilities)
            server.config = config

        await server.save()

        # Return health info
        return {
            "server": server,
            "status": "healthy",
            "status_message": f"healthy (retrieved {len(tool_list)} tools)",
            "last_checked": now,
            "response_time_ms": None,  # We don't track response time for MCP connections
        }

    async def get_server_by_name(self, server_name: str, status: str = "active") -> Optional[MCPServerDocument]:
        """
        Get server by name.
        """
        return await MCPServerDocument.find_one({"serverName": server_name})

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get system-wide statistics (Admin only).

        This method uses MongoDB aggregation pipelines to gather statistics about:
        - Servers (total, by scope, by status, by transport)
        - Tokens (total, by type, active/expired)
        - Active users (users with active tokens)
        - Total tools across all servers

        Returns:
            Dictionary containing all statistics
        """
        from packages.models._generated.token import Token
        from packages.models._generated.user import IUser

        stats = {}

        # 1. Server Statistics
        try:
            # Use facet to get multiple aggregations in one query
            # Note: scope and status are now at root level
            server_pipeline = [
                {
                    "$facet": {
                        "total": [
                            {"$count": "count"}
                        ],
                        "by_scope": [
                            {"$group": {"_id": "$scope", "count": {"$sum": 1}}}
                        ],
                        "by_status": [
                            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
                        ],
                        "by_transport": [
                            {"$group": {"_id": "$config.type", "count": {"$sum": 1}}}
                        ],
                        "total_tools": [
                            {
                                "$addFields": {
                                    "toolCount": {
                                        "$cond": {
                                            "if": {"$isArray": "$config.tool_list"},
                                            "then": {"$size": "$config.tool_list"},
                                            "else": 0
                                        }
                                    }
                                }
                            },
                            {"$group": {"_id": None, "total": {"$sum": "$toolCount"}}}
                        ]
                    }
                }
            ]

            # Use PyMongo collection directly for aggregation
            collection = MCPServerDocument.get_pymongo_collection()
            cursor = collection.aggregate(server_pipeline)
            server_results = await cursor.to_list(length=None)

            if server_results and len(server_results) > 0:
                result = server_results[0]

                # Total servers
                stats["total_servers"] = result["total"][0]["count"] if result["total"] else 0

                # Servers by scope
                servers_by_scope = {}
                for item in result.get("by_scope", []):
                    scope = item["_id"] or "unknown"
                    servers_by_scope[scope] = item["count"]
                stats["servers_by_scope"] = servers_by_scope

                # Servers by status
                servers_by_status = {}
                for item in result.get("by_status", []):
                    status = item["_id"] or "unknown"
                    servers_by_status[status] = item["count"]
                stats["servers_by_status"] = servers_by_status

                # Servers by transport
                servers_by_transport = {}
                for item in result.get("by_transport", []):
                    transport = item["_id"] or "unknown"
                    servers_by_transport[transport] = item["count"]
                stats["servers_by_transport"] = servers_by_transport

                # Total tools
                stats["total_tools"] = result["total_tools"][0]["total"] if result["total_tools"] else 0
            else:
                # No servers found
                stats["total_servers"] = 0
                stats["servers_by_scope"] = {}
                stats["servers_by_status"] = {}
                stats["servers_by_transport"] = {}
                stats["total_tools"] = 0

        except Exception as e:
            logger.error(f"Error gathering server statistics: {e}", exc_info=True)
            stats["total_servers"] = 0
            stats["servers_by_scope"] = {}
            stats["servers_by_status"] = {}
            stats["servers_by_transport"] = {}
            stats["total_tools"] = 0

        # 2. Token Statistics
        try:
            now = datetime.now(timezone.utc)

            token_pipeline = [
                {
                    "$facet": {
                        "total": [
                            {"$count": "count"}
                        ],
                        "by_type": [
                            {"$group": {"_id": "$type", "count": {"$sum": 1}}}
                        ],
                        "by_expiry": [
                            {
                                "$group": {
                                    "_id": {
                                        "$cond": [
                                            {"$gt": ["$expiresAt", now]},
                                            "active",
                                            "expired"
                                        ]
                                    },
                                    "count": {"$sum": 1}
                                }
                            }
                        ]
                    }
                }
            ]

            # Use PyMongo collection directly for aggregation
            token_collection = Token.get_pymongo_collection()
            token_cursor = token_collection.aggregate(token_pipeline)
            token_results = await token_cursor.to_list(length=None)

            if token_results and len(token_results) > 0:
                result = token_results[0]

                # Total tokens
                stats["total_tokens"] = result["total"][0]["count"] if result["total"] else 0

                # Tokens by type
                tokens_by_type = {}
                for item in result.get("by_type", []):
                    token_type = item["_id"] or "unknown"
                    tokens_by_type[token_type] = item["count"]
                stats["tokens_by_type"] = tokens_by_type

                # Active/Expired tokens
                active_count = 0
                expired_count = 0
                for item in result.get("by_expiry", []):
                    if item["_id"] == "active":
                        active_count = item["count"]
                    elif item["_id"] == "expired":
                        expired_count = item["count"]

                stats["active_tokens"] = active_count
                stats["expired_tokens"] = expired_count
            else:
                # No tokens found
                stats["total_tokens"] = 0
                stats["tokens_by_type"] = {}
                stats["active_tokens"] = 0
                stats["expired_tokens"] = 0

        except Exception as e:
            logger.error(f"Error gathering token statistics: {e}", exc_info=True)
            stats["total_tokens"] = 0
            stats["tokens_by_type"] = {}
            stats["active_tokens"] = 0
            stats["expired_tokens"] = 0

        # 3. Active Users Statistics
        try:
            now = datetime.now(timezone.utc)

            # Count unique users with active tokens
            active_users_pipeline = [
                {"$match": {"expiresAt": {"$gt": now}}},
                {"$group": {"_id": "$userId"}},
                {"$count": "count"}
            ]

            # Use PyMongo collection directly for aggregation
            active_users_collection = Token.get_pymongo_collection()
            active_users_cursor = active_users_collection.aggregate(active_users_pipeline)
            active_users_results = await active_users_cursor.to_list(length=None)

            stats["active_users"] = active_users_results[0]["count"] if active_users_results else 0

        except Exception as e:
            logger.error(f"Error gathering active users statistics: {e}", exc_info=True)
            stats["active_users"] = 0

        logger.info(f"Generated system statistics: {stats['total_servers']} servers,"
                    f" {stats['total_tokens']} tokens, {stats['active_users']} active users")

        return stats

# Singleton instance
server_service_v1 = ServerServiceV1()