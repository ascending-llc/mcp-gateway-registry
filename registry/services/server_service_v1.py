"""
Server Service V1 - Business logic for Server Management API

This service handles all server-related operations using MongoDB and Beanie ODM.

ODM Schema:
- serverName: str (required)
- config: Dict[str, Any] (required) - stores all server configuration
- author: Link[IUser] (required) - references user who created the server
- createdAt: datetime (auto-generated)
- updatedAt: datetime (auto-generated)
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from bson import ObjectId
from beanie import PydanticObjectId
from beanie.operators import In, RegEx, Or

from packages.models._generated.mcpServer import MCPServerDocument
from packages.models._generated.user import IUser

from registry.schemas.server_schemas_v1 import (
    ServerCreateRequest,
    ServerUpdateRequest,
)

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
    if data.proxy_pass_url is not None:
        config["proxy_pass_url"] = data.proxy_pass_url
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
    
    return config


def _update_config_from_request(config: Dict[str, Any], data: ServerUpdateRequest) -> Dict[str, Any]:
    """Update config dictionary from ServerUpdateRequest"""
    update_dict = data.model_dump(exclude_unset=True, exclude={'version'})
    
    # Normalize tags if present
    if 'tags' in update_dict and update_dict['tags']:
        update_dict['tags'] = [tag.lower() for tag in update_dict['tags']]
    
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
        is_admin: bool = False,
    ) -> Tuple[List[MCPServerDocument], int]:
        """
        List servers with filtering and pagination.
        
        Args:
            query: Free-text search across server_name, description, tags
            scope: Filter by access level (shared_app, shared_user, private_user)
            status: Filter by operational state (active, inactive, error)
            page: Page number (min: 1)
            per_page: Items per page (min: 1, max: 100)
            user_id: Current user's ID for permission filtering
            is_admin: Whether the current user is an admin
            
        Returns:
            Tuple of (servers list, total count)
        """
        # Validate and sanitize pagination
        page = max(1, page)
        per_page = max(1, min(100, per_page))
        skip = (page - 1) * per_page
        
        # Build filter conditions
        filters = []
        
        # Access control: admins see all, users see their private servers + shared servers
        if not is_admin and user_id:
            # Match servers where:
            # 1. config.scope is shared_app or shared_user, OR
            # 2. config.scope is private_user AND config.user_id matches current user
            access_filter = {
                "$or": [
                    {"config.scope": {"$in": ["shared_app", "shared_user"]}},
                    {"$and": [
                        {"config.scope": "private_user"},
                        {"config.user_id": user_id}
                    ]}
                ]
            }
            filters.append(access_filter)
        
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
        is_admin: bool = False,
    ) -> Optional[MCPServerDocument]:
        """
        Get a server by its ID with permission check.
        
        Args:
            server_id: Server document ID
            user_id: Current user's ID
            is_admin: Whether the current user is an admin
            
        Returns:
            Server document or None if not found or no permission
        """
        try:
            # Convert string ID to ObjectId
            obj_id = PydanticObjectId(server_id)
        except Exception as e:
            logger.warning(f"Invalid server ID format: {server_id}")
            return None
        
        server = await MCPServerDocument.get(obj_id)
        
        if not server:
            return None
        
        # Permission check
        if not is_admin:
            # Users can only access shared servers or their own private servers
            scope = _extract_config_field(server, "scope", "private_user")
            server_user_id = _extract_config_field(server, "user_id")
            
            if scope == "private_user" and server_user_id != user_id:
                logger.warning(f"User {user_id} attempted to access private server {server_id}")
                return None
        
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
        
        # Set user_id for private servers
        if data.scope == "private_user":
            config["user_id"] = user_id
        
        # Get or create author user reference
        author = await IUser.find_one({"username": user_id})
        if not author:
            # Create a minimal user record if not exists
            now = datetime.now(timezone.utc)
            author = IUser(
                username=user_id,
                email=f"{user_id}@gmail.com",
                emailVerified=False,
                role="USER",
                createdAt=now,
                updatedAt=now
            )
            await author.insert()
        
        # Create server document with timestamps
        now = datetime.now(timezone.utc)
        server = MCPServerDocument(
            serverName=data.server_name,
            config=config,
            author=author,
            createdAt=now,
            updatedAt=now
        )
        
        await server.insert()
        logger.info(f"Created server: {server.serverName} (ID: {server.id}, Path: {data.path})")
        
        return server
    
    async def update_server(
        self,
        server_id: str,
        data: ServerUpdateRequest,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> MCPServerDocument:
        """
        Update a server with optimistic locking.
        
        Args:
            server_id: Server document ID
            data: Update data (partial)
            user_id: Current user's ID
            is_admin: Whether the current user is an admin
            
        Returns:
            Updated server document
            
        Raises:
            ValueError: If server not found, no permission, or version conflict
        """
        server = await self.get_server_by_id(server_id, user_id, is_admin)
        
        if not server:
            raise ValueError("Server not found or access denied")
        
        # Get current config
        config = server.config or {}
        scope = config.get("scope", "private_user")
        server_user_id = config.get("user_id")
        current_version = config.get("version", 1)
        
        # Permission check: only admins or server owners can update
        if not is_admin:
            if scope == "private_user" and server_user_id != user_id:
                raise ValueError("Cannot update another user's private server")
            if scope in ["shared_app", "shared_user"]:
                raise ValueError("Only admins can update shared servers")
        
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
        server.config = _update_config_from_request(config, data)
        
        # Update the updatedAt timestamp
        server.updatedAt = datetime.now(timezone.utc)
        
        await server.save()
        logger.info(f"Updated server: {server.serverName} (ID: {server.id}, Version: {server.config.get('version')})")
        
        return server
    
    async def delete_server(
        self,
        server_id: str,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> bool:
        """
        Delete a server.
        
        Args:
            server_id: Server document ID
            user_id: Current user's ID
            is_admin: Whether the current user is an admin
            
        Returns:
            True if deleted successfully
            
        Raises:
            ValueError: If server not found or no permission
        """
        # First check if server exists (without permission check)
        try:
            obj_id = PydanticObjectId(server_id)
        except Exception as e:
            raise ValueError("Server not found")
        
        server = await MCPServerDocument.get(obj_id)
        
        if not server:
            raise ValueError("Server not found")
        
        # Get current config
        config = server.config or {}
        scope = config.get("scope", "private_user")
        server_user_id = config.get("user_id")
        
        # Permission check: only admins or server owners can delete
        if not is_admin:
            if scope == "private_user" and server_user_id != user_id:
                raise ValueError("Access denied: cannot delete another user's private server")
            if scope in ["shared_app", "shared_user"]:
                raise ValueError("Access denied: only admins can delete shared servers")
        
        await server.delete()
        logger.info(f"Deleted server: {server.serverName} (ID: {server.id})")
        
        return True
    
    async def toggle_server_status(
        self,
        server_id: str,
        enabled: bool,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> MCPServerDocument:
        """
        Toggle server enabled/disabled status.
        
        Args:
            server_id: Server document ID
            enabled: Enable (True) or disable (False)
            user_id: Current user's ID
            is_admin: Whether the current user is an admin
            
        Returns:
            Updated server document
            
        Raises:
            ValueError: If server not found or no permission
        """
        server = await self.get_server_by_id(server_id, user_id, is_admin)
        
        if not server:
            raise ValueError("Server not found or access denied")
        
        # Get current config
        config = server.config or {}
        scope = config.get("scope", "private_user")
        server_user_id = config.get("user_id")
        
        # Permission check
        if not is_admin:
            if scope == "private_user" and server_user_id != user_id:
                raise ValueError("Cannot toggle another user's private server")
            if scope in ["shared_app", "shared_user"]:
                raise ValueError("Only admins can toggle shared servers")
        
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
        is_admin: bool = False,
    ) -> Tuple[MCPServerDocument, List[Dict[str, Any]]]:
        """
        Get server tools.
        
        Args:
            server_id: Server document ID
            user_id: Current user's ID
            is_admin: Whether the current user is an admin
            
        Returns:
            Tuple of (server, tools list)
            
        Raises:
            ValueError: If server not found or no permission
        """
        server = await self.get_server_by_id(server_id, user_id, is_admin)
        
        if not server:
            raise ValueError("Server not found or access denied")
        
        tool_list = _extract_config_field(server, "tool_list", [])
        return server, tool_list
    
    async def refresh_server_health(
        self,
        server_id: str,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """
        Refresh server health status.
        
        This is a placeholder that returns basic health info.
        In a real implementation, this would ping the actual server.
        
        Args:
            server_id: Server document ID
            user_id: Current user's ID
            is_admin: Whether the current user is an admin
            
        Returns:
            Health information dictionary
            
        Raises:
            ValueError: If server not found or no permission
        """
        server = await self.get_server_by_id(server_id, user_id, is_admin)
        
        if not server:
            raise ValueError("Server not found or access denied")
        
        # Update last_connected timestamp in config
        config = server.config or {}
        now = datetime.now(timezone.utc)
        config["last_connected"] = now.isoformat()
        server.config = config
        
        # Update the updatedAt timestamp
        server.updatedAt = now
        
        await server.save()
        
        # Return health info
        # In real implementation, would ping the server and measure response time
        status = config.get("status", "active")
        return {
            "server": server,
            "status": "healthy" if status == "active" else "unhealthy",
            "last_checked": datetime.now(timezone.utc),
            "response_time_ms": 125,  # Mock value
        }


# Singleton instance
server_service_v1 = ServerServiceV1()
