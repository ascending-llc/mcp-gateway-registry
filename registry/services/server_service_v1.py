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

from packages.models._generated.mcpServer import MCPServerDocument
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


def _build_config_from_request(data: ServerCreateRequest) -> Dict[str, Any]:
    """Build config dictionary from ServerCreateRequest"""
    config = {
        "path": data.path,
        "description": data.description or "",
        "scope": data.scope,
        "tags": [tag.lower() for tag in data.tags],
        "num_tools": data.num_tools,
        "num_stars": data.num_stars,
        "is_python": data.is_python,
        "supported_transports": data.supported_transports,
        "startup": data.startup,
        "chat_menu": data.chat_menu,
        "tool_list": data.tool_list,
        "status": "active",
        "version": 1,
    }
    
    # Add optional fields only if they are provided (not None)
    if data.url is not None:
        config["url"] = data.url
    if data.license is not None:
        config["license"] = data.license
    if data.auth_type is not None:
        config["auth_type"] = data.auth_type
    if data.auth_provider is not None:
        config["auth_provider"] = data.auth_provider
    if data.transport is not None:
        config["transport"] = data.transport
    if data.icon_path is not None:
        config["icon_path"] = data.icon_path
    if data.timeout is not None:
        config["timeout"] = data.timeout
    if data.init_timeout is not None:
        config["init_timeout"] = data.init_timeout
    if data.server_instructions is not None:
        config["server_instructions"] = data.server_instructions
    if data.requires_oauth:
        config["requires_oauth"] = data.requires_oauth
    if data.oauth is not None:
        config["oauth"] = data.oauth
    if data.custom_user_vars is not None:
        config["custom_user_vars"] = data.custom_user_vars
    if data.authentication is not None:
        config["authentication"] = data.authentication
    if data.apiKey is not None:
        config["apiKey"] = data.apiKey
    
    return config


def _update_config_from_request(config: Dict[str, Any], data: ServerUpdateRequest) -> Dict[str, Any]:
    """Update config dictionary from ServerUpdateRequest"""
    update_dict = data.model_dump(exclude_unset=True, exclude={'version'})
    
    # Normalize tags if present
    if 'tags' in update_dict and update_dict['tags']:
        update_dict['tags'] = [tag.lower() for tag in update_dict['tags']]
    
    # Handle mutually exclusive authentication fields: apiKey and authentication
    # If one is being updated, remove the other from config
    if 'apiKey' in update_dict:
        # When apiKey is provided, remove authentication field
        if 'authentication' in config:
            del config['authentication']
    elif 'authentication' in update_dict:
        # When authentication is provided, remove apiKey field
        if 'apiKey' in config:
            del config['apiKey']
    
    # Update config with new values (only fields that were explicitly set)
    for key, value in update_dict.items():
        if value is not None:
            config[key] = value
    
    # Increment version
    config['version'] = config.get('version', 1) + 1
    
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
                    {"config.tags": query_lower}
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
        servers = await MCPServerDocument.find(query_filter)\
            .sort([("createdAt", -1)])\
            .skip(skip)\
            .limit(per_page)\
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
        return await MCPServerDocument.find_one({"config.path": path})
    
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
            ValueError: If path already exists, server_name already exists, or tags contain duplicates (case-insensitive)
        """
        # Check if path already exists
        existing = await self.get_server_by_path(data.path)
        if existing:
            raise ValueError(f"Server with path '{data.path}' already exists")
        
        # Check if server_name already exists
        existing_name = await MCPServerDocument.find_one({"serverName": data.server_name})
        if existing_name:
            raise ValueError(f"Server with name '{data.server_name}' already exists")
        
        # Check for duplicate tags (case-insensitive)
        normalized_tags = [tag.lower() for tag in data.tags]
        if len(normalized_tags) != len(set(normalized_tags)):
            raise ValueError("Duplicate tags are not allowed (case-insensitive)")
        
        # Build config dictionary
        config = _build_config_from_request(data)
        
        # Encrypt sensitive authentication fields before storing
        config = encrypt_auth_fields(config)
        
        # Set user_id for private servers
        if data.scope == "private_user":
            config["user_id"] = user_id
        
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
        
        # Create server document with timestamps
        now = datetime.now(timezone.utc)
        server = MCPServerDocument(
            serverName=data.server_name,
            config=config,
            author=author.id,  # Use PydanticObjectId instead of Link
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
                
                # Update config with health check results
                config["last_connected"] = datetime.now(timezone.utc).isoformat()
                config["status"] = "active"
                
                # 2. Tool retrieval - REQUIRED
                tool_list, tool_error = await self.retrieve_tools_from_server(server)
                
                if tool_list is None:
                    # Tool retrieval failed - delete the server and reject registration
                    logger.error(f"Tool retrieval failed for {server.serverName}: {tool_error}")
                    await server.delete()
                    raise ValueError(f"Server registration rejected: Failed to retrieve tools - {tool_error}")
                
                config["tool_list"] = tool_list
                config["num_tools"] = len(tool_list)
                logger.info(f"Retrieved {len(tool_list)} tools for {server.serverName}")
                
                # Save updated config
                server.config = config
                server.updatedAt = datetime.now(timezone.utc)
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
        Update a server with optimistic locking.
        
        Args:
            server_id: Server document ID
            data: Update data (partial)
            user_id: Current user's ID (kept for compatibility but not used)
            
        Returns:
            Updated server document
            
        Raises:
            ValueError: If server not found or version conflict
        """
        server = await self.get_server_by_id(server_id, user_id)
        
        if not server:
            raise ValueError("Server not found")
        
        # Get current config
        config = server.config or {}
        current_version = config.get("version", 1)
        
        # Optimistic locking check
        if data.version is not None and current_version != data.version:
            raise ValueError(
                f"Version conflict: expected {data.version}, current is {current_version}"
            )
        
        # Check for duplicate tags if tags are being updated
        if data.tags is not None:
            normalized_tags = [tag.lower() for tag in data.tags]
            if len(normalized_tags) != len(set(normalized_tags)):
                raise ValueError("Duplicate tags are not allowed (case-insensitive)")
        
        # Update server_name if provided
        if data.server_name is not None:
            server.serverName = data.server_name
        
        # Update config with new values
        updated_config = _update_config_from_request(config, data)
        
        # Encrypt sensitive authentication fields if they were updated
        if data.authentication is not None or data.apiKey is not None:
            updated_config = encrypt_auth_fields(updated_config)
        
        server.config = updated_config
        
        # Update the updatedAt timestamp
        server.updatedAt = datetime.now(timezone.utc)
        
        await server.save()
        logger.info(f"Updated server: {server.serverName} (ID: {server.id}, Version: {server.config.get('version')})")
        
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
        
        # Get current config
        config = server.config or {}
        
        # Update status in config
        config["status"] = "active" if enabled else "inactive"
        config["version"] = config.get("version", 1) + 1
        server.config = config
        
        # Update the updatedAt timestamp
        server.updatedAt = datetime.now(timezone.utc)
        
        await server.save()
        logger.info(f"Toggled server {server.serverName} (ID: {server.id}) to {config['status']}")
        
        return server
    
    async def get_server_tools(
        self,
        server_id: str,
        user_id: Optional[str] = None,
    ) -> Tuple[MCPServerDocument, List[Dict[str, Any]]]:
        """
        Get server tools.
        
        Args:
            server_id: Server document ID
            user_id: Current user's ID (kept for compatibility but not used)
            
        Returns:
            Tuple of (server, tools list)
            
        Raises:
            ValueError: If server not found
        """
        server = await self.get_server_by_id(server_id, user_id)
        
        if not server:
            raise ValueError("Server not found")
        
        tool_list = _extract_config_field(server, "tool_list", [])
        return server, tool_list
    
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
        
        supported_transports = config.get("supported_transports", ["streamable-http"])
        
        # Skip health checks for stdio transport
        if supported_transports == ["stdio"]:
            logger.info(f"Skipping health check for stdio transport: {url}")
            return True, "healthy (stdio transport skipped)", None
        
        try:
            # Perform simple HTTP health check
            start_time = datetime.now(timezone.utc)
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try to access the MCP endpoint
                base_url = url.rstrip('/')
                
                # Try streamable-http transport first (most common)
                if "streamable-http" in supported_transports:
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
                elif "sse" in supported_transports:
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
                    return False, f"unsupported transport: {supported_transports}", None
                    
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
                "supported_transports": config.get("supported_transports", ["streamable-http"]),
                "tags": config.get("tags", []),
            }
            
            # Add headers if present
            if "headers" in config:
                server_info["headers"] = config["headers"]
            
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
    
    async def refresh_server_health(
        self,
        server_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Refresh server health status.
        
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
        
        # Perform actual health check
        is_healthy, status_msg, response_time_ms = await self.perform_health_check(server)
        
        # Update server config with health check results
        config = server.config or {}
        now = datetime.now(timezone.utc)
        config["last_connected"] = now.isoformat()
        
        if is_healthy:
            config["status"] = "active"
            config["last_error"] = None
            config["error_message"] = None
        else:
            config["status"] = "error"
            config["last_error"] = now.isoformat()
            config["error_message"] = status_msg
        
        server.config = config
        server.updatedAt = now
        
        await server.save()
        
        # Return health info
        return {
            "server": server,
            "status": "healthy" if is_healthy else "unhealthy",
            "status_message": status_msg,
            "last_checked": now,
            "response_time_ms": response_time_ms,
        }

    async def get_server_by_name(self,server_name: str) -> Optional[MCPServerDocument]:
        """
        Get server by name.
        """
        return await MCPServerDocument.find_one({"serverName": server_name})

# Singleton instance
server_service_v1 = ServerServiceV1()