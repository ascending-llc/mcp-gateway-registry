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
from bson import ObjectId
from beanie import PydanticObjectId
from beanie.operators import In, RegEx, Or

from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument
from packages.models._generated.user import IUser

from registry.schemas.server_api_schemas import (
    ServerCreateRequest,
    ServerUpdateRequest,
)
from registry.utils.crypto_utils import encrypt_auth_fields
from registry.core.mcp_client import get_tools_from_server_with_server_info

logger = logging.getLogger(__name__)


def _extract_config_field(server: MCPServerDocument, field: str, default: Any = None) -> Any:
    """Extract a field from server.config with fallback to default"""
    if not server or not server.config:
        return default
    return server.config.get(field, default)


def _build_server_info_for_mcp_client(config: Dict[str, Any], tags: List[str]) -> Dict[str, Any]:
    """
    Build server_info dictionary for MCP client operations.
    
    This helper eliminates duplicate code in create_server, retrieve_tools_from_server,
    and retrieve_tools_and_capabilities_from_server.
    
    Args:
        config: Server config dictionary
        tags: Server tags list
        
    Returns:
        server_info dictionary with type, tags, headers, and apiKey (if present)
    """
    server_info = {
        "type": config.get("type", "streamable-http"),
        "tags": tags or [],
    }
    
    # Add optional fields if present
    if "headers" in config:
        server_info["headers"] = config["headers"]
    
    if "apiKey" in config:
        server_info["apiKey"] = config["apiKey"]
    
    return server_info


def _detect_oauth_requirement(oauth_field: Optional[Any]) -> bool:
    """
    Detect if OAuth is required based on oauth field.
    
    This helper eliminates duplicate OAuth detection logic in _build_config_from_request
    and _update_config_from_request.
    
    Args:
        oauth_field: OAuth configuration object (if present)
        
    Returns:
        True if OAuth is required, False otherwise
    """
    return oauth_field is not None


def _get_current_utc_time() -> datetime:
    """Get current UTC time. Centralizes datetime.now(timezone.utc) calls."""
    return datetime.now(timezone.utc)


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
    # Determine if OAuth is required based on oauth field
    # If oauth field is provided, set requiresOAuth to True
    requires_oauth = _detect_oauth_requirement(getattr(data, 'oauth', None))
    # If user explicitly sets requires_oauth, respect that (for backward compatibility)
    if getattr(data, 'requires_oauth', False):
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

    # Handle mutually exclusive authentication fields: oauth and apiKey
    # Only store one of them, with oauth taking priority
    if data.oauth is not None:
        # oauth is already added above, just ensure apiKey is not added
        pass
    elif data.apiKey is not None:
        # When only apiKey is provided, store it
        config["apiKey"] = data.apiKey
    
    # Always set enabled to False during registration (regardless of frontend input)
    config["enabled"] = False
    
    return config


def _update_config_from_request(config: Dict[str, Any], data: ServerUpdateRequest, server_name: str = None) -> Dict[str, Any]:
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
    
    # Handle mutually exclusive authentication fields: oauth and apiKey
    # If one is being updated, remove the other from config
    if 'oauth' in update_dict:
        # When oauth is provided, remove apiKey field and store oauth
        if 'apiKey' in config:
            del config['apiKey']
        # Store oauth with all its fields
        config['oauth'] = update_dict['oauth']
        # Remove from update_dict to avoid duplicate processing
        del update_dict['oauth']
    elif 'apiKey' in update_dict:
        # When apiKey is provided, remove oauth field and store apiKey
        if 'oauth' in config:
            del config['oauth']
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
    
    # Update requiresOAuth based on oauth field
    # If oauth is being updated, recalculate requiresOAuth
    if 'oauth' in update_dict:
        requires_oauth = _detect_oauth_requirement(config.get('oauth'))
        config['requiresOAuth'] = requires_oauth
        logger.info(f"Updated requiresOAuth to {requires_oauth} based on oauth field")
    
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
    
    async def list_servers(
        self,
        query: Optional[str] = None,
        scope: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        user_id: Optional[str] = None,
        accessible_server_ids: List[PydanticObjectId] = [],
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
            accessible_server_ids: List of server IDs the user has access to based on ACL permissions
        Returns:
            Tuple of (servers list, total count)
        """
        # Validate and sanitize pagination
        page = max(1, page)
        per_page = max(1, min(100, per_page))
        skip = (page - 1) * per_page
        
        # Build filter conditions
        filters = []

        # Scope filter
        if scope:
            filters.append({"config.scope": scope})

        # Status filter
        if status:
            filters.append({"config.status": status})

        # Text search across multiple fields
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

        # Access control filter
        if accessible_server_ids:
            filters.append({"_id": {"$in": accessible_server_ids}})

        # Combine all filters
        if filters:
            query_filter = {"$and": filters} if len(filters) > 1 else filters[0]
        else:
            query_filter = {}

        # Execute query with pagination
        total = await MCPServerDocument.find(query_filter).count()
        servers = await MCPServerDocument.find(query_filter)\
            .sort([("createdAt", -1)])\
            .skip(skip)\
            .limit(per_page)\
            .to_list()
        return servers, total
    
    async def get_server_by_id(
        self,
        server_id: PydanticObjectId,
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
        server = await MCPServerDocument.get(server_id)        
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
        author = await IUser.find_one({"id": user_id})
        if not author:
            # Create a minimal user record if not exists
            now = _get_current_utc_time()
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
        now = _get_current_utc_time()
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
                logger.info(f"Health check result for {server.serverName}: {status_msg} (response_time: {response_time_ms}ms)")
                
                if not is_healthy:
                    # Health check failed - delete the server and reject registration
                    logger.error(f"Health check failed for {server.serverName}: {status_msg}")
                    await server.delete()
                    raise ValueError(f"Server registration rejected: Health check failed - {status_msg}")
                
                # Update server with health check results (root-level field)
                server.lastConnected = _get_current_utc_time()
                server.status = "active"
                
                # 2. Retrieve capabilities (but skip tools - they will be fetched on-demand)
                logger.info(f"Retrieving capabilities for {server.serverName} (skipping tools)")
                
                # Initialize empty toolFunctions and tools (will be populated on first use)
                config["toolFunctions"] = {}
                config["tools"] = ""
                
                # Try to get capabilities only
                try:
                    # Build server_info dict for mcp_client
                    server_info = _build_server_info_for_mcp_client(config, server.tags)
                    
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
                
                # 3. OAuth metadata retrieval - OPTIONAL (only if oauth is configured)
                # Check if server has OAuth configuration
                has_oauth = data.oauth is not None
                
                if has_oauth:
                    logger.info(f"OAuth configuration detected for {server.serverName}, retrieving OAuth metadata...")
                    
                    from registry.core.mcp_client import get_oauth_metadata_from_server
                    
                    # Build server_info dict for oauth metadata retrieval (no auth needed)
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
                        # Save empty oauthMetadata if retrieval failed
                        config["oauthMetadata"] = {}
                        logger.info(f"No OAuth metadata available for {server.serverName} (server may not support OAuth autodiscovery), saved empty oauthMetadata")
                
                # Update numTools at root level (0 since tools not fetched yet)
                server.numTools = 0
                
                # Save updated server
                server.config = config
                server.updatedAt = _get_current_utc_time()
                await server.save()
                
            except ValueError:
                # Re-raise ValueError (our validation errors)
                raise
            except Exception as e:
                # Unexpected error during health check or tool retrieval
                logger.error(f"Unexpected error during post-registration checks for {server.serverName}: {e}", exc_info=True)
                await server.delete()
                raise ValueError(f"Server registration rejected: Unexpected error during validation - {type(e).__name__}: {str(e)}")
        
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
        if data.oauth is not None or data.apiKey is not None:
            updated_config = encrypt_auth_fields(updated_config)
        
        # If toolFunctions was updated, recalculate numTools
        if "toolFunctions" in updated_config:
            tool_functions = updated_config.get("toolFunctions", {})
            server.numTools = len(tool_functions) if tool_functions else 0
        
        server.config = updated_config
        
        # Update the updatedAt timestamp
        server.updatedAt = _get_current_utc_time()
        
        await server.save()
        logger.info(f"Updated server: {server.serverName} (ID: {server.id})")
        
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
        
        await server.delete()
        logger.info(f"Deleted server: {server.serverName} (ID: {server.id})")
        
        return True
    
    async def _fetch_and_update_tools(
        self,
        server: MCPServerDocument,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Fetch tools from server and update toolFunctions in config.
        
        Args:
            server: Server document
            user_id: User ID (required for OAuth servers)
            
        Returns:
            True if tools were successfully fetched and updated, False otherwise
        """
        config = server.config or {}
        
        # Check authentication type
        has_oauth = config.get("oauth") is not None
        
        tool_list = None
        error_msg = None
        
        if has_oauth:
            # OAuth authentication
            if not user_id:
                logger.warning(f"Cannot fetch tools for OAuth server {server.serverName}: user_id is required")
                return False
            
            logger.info(f"Fetching tools for OAuth server {server.serverName} with user {user_id}")
            tool_list, error_msg = await self.retrieve_tools_with_oauth(server, user_id)
        else:
            # No auth or API Key authentication
            logger.info(f"Fetching tools for server {server.serverName}")
            tool_list, error_msg = await self.retrieve_tools_from_server(server)
        
        if tool_list:
            # Convert tool_list to toolFunctions format
            tool_functions = _convert_tool_list_to_functions(tool_list, server.serverName)
            
            # Update config with toolFunctions (full replacement)
            server.config['toolFunctions'] = tool_functions
            
            # Update tools string (comma-separated tool names)
            tool_names = [tool.get("name", "") for tool in tool_list if tool.get("name")]
            server.config['tools'] = ", ".join(tool_names) if tool_names else ""
            
            # Update numTools at root level
            server.numTools = len(tool_functions)
            
            logger.info(f"Successfully fetched and updated {len(tool_functions)} tools for {server.serverName}")
            return True
        else:
            logger.warning(f"Failed to fetch tools for {server.serverName}: {error_msg}")
            return False
    
    async def toggle_server_status(
        self,
        server_id: str,
        enabled: bool,
        user_id: Optional[str] = None,
    ) -> MCPServerDocument:
        """
        Toggle server enabled/disabled status.
        When enabling, fetch tools and update toolFunctions.
        
        Args:
            server_id: Server document ID
            enabled: Enable (True) or disable (False)
            user_id: Current user's ID (required for OAuth servers)
            
        Returns:
            Updated server document
            
        Raises:
            ValueError: If server not found or user_id missing for OAuth server
        """
        server = await self.get_server_by_id(server_id, user_id)
        
        if not server:
            raise ValueError("Server not found")
        
        # Update enabled field in config only (do not update status field)
        if server.config is None:
            server.config = {}
        server.config['enabled'] = enabled
        
        # If enabling the server, fetch tools and update toolFunctions
        if enabled:
            success = await self._fetch_and_update_tools(server, user_id)
            if not success:
                # Rollback enabled status
                server.config['enabled'] = False
                await server.save()
                raise ValueError("Failed to fetch tools from server. Server remains disabled.")
        
        # Update the updatedAt timestamp
        server.updatedAt = _get_current_utc_time()
        
        await server.save()
        logger.info(f"Toggled server {server.serverName} (ID: {server.id}) enabled to {enabled}")
        
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
        from registry.core.mcp_config import mcp_config
        
        config = server.config or {}
        url = config.get("url")
        
        if not url:
            return False, "No URL configured", None
        
        transport_type = config.get("type", mcp_config.TRANSPORT_HTTP)
        
        # Skip health checks for stdio transport
        if transport_type == mcp_config.TRANSPORT_STDIO:
            logger.info(f"Skipping health check for stdio transport: {url}")
            return True, "healthy (stdio transport skipped)", None
        
        try:
            # Perform simple HTTP health check
            start_time = _get_current_utc_time()
            
            async with httpx.AsyncClient(timeout=mcp_config.HEALTH_CHECK_TIMEOUT) as client:
                # Try to access the MCP endpoint
                base_url = url.rstrip('/')
                
                # Try streamable-http transport first (most common)
                if transport_type in [mcp_config.TRANSPORT_HTTP, "http"]:
                    endpoint = f"{base_url}{mcp_config.ENDPOINT_MCP}" if not base_url.endswith(mcp_config.ENDPOINT_MCP) else base_url
                    
                    try:
                        # Try a simple GET request first
                        response = await client.get(endpoint, follow_redirects=True)
                        
                        # Calculate response time
                        end_time = _get_current_utc_time()
                        response_time_ms = int((end_time - start_time).total_seconds() * 1000)
                        
                        # Check if response indicates a healthy server
                        if response.status_code in mcp_config.HEALTHY_STATUS_CODES:
                            return True, "healthy", response_time_ms
                        elif response.status_code in mcp_config.AUTH_REQUIRED_STATUS_CODES:
                            # Auth required but server is responding
                            return True, "healthy (auth required)", response_time_ms
                        else:
                            return False, f"unhealthy: status {response.status_code}", response_time_ms
                    except Exception as e:
                        logger.warning(f"Health check failed for {endpoint}: {e}")
                        return False, f"unhealthy: {type(e).__name__}", None
                
                # Try SSE transport if configured
                elif transport_type == mcp_config.TRANSPORT_SSE:
                    endpoint = f"{base_url}{mcp_config.ENDPOINT_SSE}" if not base_url.endswith(mcp_config.ENDPOINT_SSE) else base_url
                    
                    try:
                        response = await client.get(endpoint, follow_redirects=True)
                        end_time = _get_current_utc_time()
                        response_time_ms = int((end_time - start_time).total_seconds() * 1000)
                        
                        if response.status_code in mcp_config.HEALTHY_STATUS_CODES:
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
    
    async def retrieve_from_server(
        self,
        server: MCPServerDocument,
        include_capabilities: bool = True,
        user_id: Optional[str] = None,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]], Optional[str]]:
        """
        Consolidated method to retrieve tools and optionally capabilities from a server.
        
        This replaces both retrieve_tools_from_server() and retrieve_tools_and_capabilities_from_server().
        Handles both apiKey and OAuth authentication automatically.
        
        Args:
            server: Server document
            include_capabilities: Whether to retrieve capabilities (default: True)
            user_id: User ID for OAuth token retrieval (required for OAuth servers)
            
        Returns:
            Tuple of (tool_list, capabilities_dict, error_message)
            - If successful: (tool_list, capabilities_dict, None)
            - If failed: (None, None, error_message)
            - If include_capabilities=False: (tool_list, None, None) or (None, None, error_message)
        """
        config = server.config or {}
        url = config.get("url")
        
        if not url:
            return None, None, "No URL configured"
        
        # Check if server requires OAuth
        has_oauth = config.get("oauth") is not None
        
        if has_oauth and not user_id:
            return None, None, "OAuth server requires user_id for token retrieval"
        
        try:
            # Decrypt apiKey if present (key field is encrypted in MongoDB)
            from registry.utils.crypto_utils import decrypt_auth_fields
            decrypted_config = decrypt_auth_fields(config)
            
            # Build server_info using helper function with decrypted config
            server_info = _build_server_info_for_mcp_client(decrypted_config, server.tags)
            
            # Add OAuth token to headers if server requires OAuth
            if has_oauth and user_id:
                from registry.services.v1.token_service import token_service
                
                oauth_tokens = await token_service.get_oauth_tokens(user_id, server.serverName)
                
                if not oauth_tokens or not oauth_tokens.access_token:
                    return None, None, f"No OAuth tokens found for user {user_id}"
                
                # Add OAuth Authorization header to server_info
                if "headers" not in server_info:
                    server_info["headers"] = []
                
                server_info["headers"].append(
                    {"Authorization": f"Bearer {oauth_tokens.access_token}"}
                )
                
                logger.info(f"Added OAuth token to request for {server.serverName}")
            
            logger.info(f"Retrieving {'tools and capabilities' if include_capabilities else 'tools only'} from {url} for server {server.serverName}")
            
            # Use the appropriate MCP client function
            if include_capabilities:
                from registry.core.mcp_client import get_tools_and_capabilities_from_server
                tool_list, capabilities = await get_tools_and_capabilities_from_server(url, server_info)
                
                if tool_list is None or capabilities is None:
                    error_msg = "Failed to retrieve tools and capabilities from MCP server"
                    logger.warning(f"{error_msg} for {server.serverName}")
                    return None, None, error_msg
                
                logger.info(f"Retrieved {len(tool_list)} tools and capabilities from {server.serverName}")
                return tool_list, capabilities, None
            else:
                from registry.core.mcp_client import get_tools_from_server_with_server_info
                tool_list = await get_tools_from_server_with_server_info(url, server_info)
                
                if tool_list is None:
                    error_msg = "Failed to retrieve tools from MCP server"
                    logger.warning(f"{error_msg} for {server.serverName}")
                    return None, None, error_msg
                
                logger.info(f"Retrieved {len(tool_list)} tools from {server.serverName}")
                return tool_list, None, None
            
        except Exception as e:
            error_msg = f"Error: {type(e).__name__} - {str(e)}"
            logger.error(f"Retrieval error for server {server.serverName}: {e}")
            return None, None, error_msg
    
    async def retrieve_tools_from_server(
        self,
        server: MCPServerDocument,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Retrieve tools from a server using MCP client (legacy method).
        
        Wraps retrieve_from_server() for backward compatibility.
        
        Args:
            server: Server document
            
        Returns:
            Tuple of (tool_list, error_message)
            If successful, returns (tool_list, None)
            If failed, returns (None, error_message)
        """
        tool_list, _, error_msg = await self.retrieve_from_server(server, include_capabilities=False)
        return tool_list, error_msg
    
    async def retrieve_tools_with_oauth(
        self,
        server: MCPServerDocument,
        user_id: str,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Retrieve tools from a server using OAuth authentication.
        
        Args:
            server: Server document
            user_id: User ID for OAuth token retrieval
            
        Returns:
            Tuple of (tool_list, error_message)
            If successful, returns (tool_list, None)
            If failed, returns (None, error_message)
        """
        from registry.services.v1.token_service import token_service
        from registry.services.oauth.oauth_service import MCPOAuthService
        from registry.auth.oauth import OAuthHttpClient
        
        config = server.config or {}
        url = config.get("url")
        
        if not url:
            return None, "No URL configured"
        
        try:
            # Get OAuth tokens for the user
            oauth_tokens = await token_service.get_oauth_tokens(user_id, server.serverName)
            
            if not oauth_tokens or not oauth_tokens.access_token:
                return None, f"No OAuth tokens found for user {user_id}"
            
            # Build server_info dict with OAuth token
            server_info = {
                "type": config.get("type", "streamable-http"),
                "tags": server.tags or [],
                "headers": [
                    {"Authorization": f"Bearer {oauth_tokens.access_token}"}
                ]
            }
            
            logger.info(f"Retrieving tools from {url} for server {server.serverName} with OAuth token")
            
            # Try to get tools with current token
            tool_list = await get_tools_from_server_with_server_info(url, server_info)
            
            # If failed with 401-like error, try refreshing token
            if tool_list is None:
                logger.info(f"Failed to retrieve tools, attempting token refresh for {server.serverName}")
                
                # Get OAuth config
                oauth_config = config.get("oauth")
                if not oauth_config:
                    return None, "No OAuth configuration found"
                
                # Get refresh token
                refresh_token_doc = await token_service.get_oauth_refresh_token(user_id, server.serverName)
                if not refresh_token_doc or not refresh_token_doc.token:
                    return None, "No refresh token available"
                
                # Refresh tokens
                http_client = OAuthHttpClient()
                new_tokens = await http_client.refresh_tokens(
                    oauth_config=oauth_config,
                    refresh_token=refresh_token_doc.token
                )
                
                if not new_tokens:
                    return None, "Failed to refresh OAuth tokens"
                
                # Store refreshed tokens
                metadata = {
                    "authorization_endpoint": oauth_config.get("authorization_url"),
                    "token_endpoint": oauth_config.get("token_url"),
                    "issuer": oauth_config.get("issuer"),
                    "scopes_supported": oauth_config.get("scope", "").split() if oauth_config.get("scope") else [],
                    "grant_types_supported": ["authorization_code", "refresh_token"],
                    "response_types_supported": ["code"],
                }
                await token_service.store_oauth_tokens(
                    user_id=user_id,
                    service_name=server.serverName,
                    tokens=new_tokens,
                    metadata=metadata
                )
                logger.info(f"Refreshed and stored new OAuth tokens for {user_id}/{server.serverName}")
                
                # Retry with new token
                server_info["headers"] = [
                    {"Authorization": f"Bearer {new_tokens.access_token}"}
                ]
                tool_list = await get_tools_from_server_with_server_info(url, server_info)
            
            if tool_list is None:
                return None, "Failed to retrieve tools from MCP server even after token refresh"
            
            logger.info(f"Retrieved {len(tool_list)} tools from {server.serverName} with OAuth")
            return tool_list, None
            
        except Exception as e:
            error_msg = f"Error retrieving tools with OAuth: {type(e).__name__} - {str(e)}"
            logger.error(f"OAuth tool retrieval error for server {server.serverName}: {e}", exc_info=True)
            return None, error_msg
    
    async def retrieve_tools_and_capabilities_from_server(
        self,
        server: MCPServerDocument,
        user_id: Optional[str] = None,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]], Optional[str]]:
        """
        Retrieve tools and capabilities from a server using MCP client (legacy method).
        
        Wraps retrieve_from_server() for backward compatibility.
        
        This is a best-effort attempt - failures are logged but don't prevent registration.
        Tools can be fetched on-demand later.
        
        Args:
            server: Server document
            user_id: User ID for OAuth token retrieval (required for OAuth servers)
            
        Returns:
            Tuple of (tool_list, capabilities_dict, error_message)
            - If successful, returns (tool_list, capabilities_dict, None)
            - If failed, returns (None, None, error_message)
            - Empty results are acceptable for registration
        """
        return await self.retrieve_from_server(server, include_capabilities=True, user_id=user_id)
    
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
        
        now = _get_current_utc_time()
        
        # Use the same validation as registration: retrieve tools and capabilities
        # This is a more comprehensive health check than just HTTP GET
        tool_list, capabilities, tool_error = await self.retrieve_tools_and_capabilities_from_server(server, user_id)
        
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
        
        # Update capabilities and tools in config
        import json
        config = server.config or {}
        if capabilities:
            config["capabilities"] = json.dumps(capabilities)
        
        # Update toolFunctions if tools were retrieved
        if tool_list:
            # Convert tool_list to toolFunctions format
            tool_functions = _convert_tool_list_to_functions(tool_list, server.serverName)
            config['toolFunctions'] = tool_functions
            
            # Update tools string (comma-separated tool names)
            tool_names = [tool.get("name", "") for tool in tool_list if tool.get("name")]
            config['tools'] = ", ".join(tool_names) if tool_names else ""
            
            # Update numTools at root level
            server.numTools = len(tool_functions)
            logger.info(f"Updated {len(tool_functions)} tools for {server.serverName} during health refresh")
        
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
            now = _get_current_utc_time()

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
            now = _get_current_utc_time()

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

        logger.info(f"Generated system statistics: {stats['total_servers']} servers, {stats['total_tokens']} tokens, {stats['active_users']} active users")

        return stats

# Singleton instance
server_service_v1 = ServerServiceV1()