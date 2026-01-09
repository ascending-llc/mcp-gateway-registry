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
        "enabled": data.enabled,
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

    # Handle mutually exclusive authentication fields: apiKey and authentication
    # Only store one of them, with authentication taking priority
    if data.authentication is not None:
        # When authentication is provided, store it and do NOT store apiKey
        config["authentication"] = data.authentication
    elif data.apiKey is not None:
        # When only apiKey is provided, store it
        config["apiKey"] = data.apiKey
    
    return config


def _update_config_from_request(config: Dict[str, Any], data: ServerUpdateRequest) -> Dict[str, Any]:
    """Update config dictionary from ServerUpdateRequest"""
    update_dict = data.model_dump(exclude_unset=True)
    
    # Normalize tags if present
    if 'tags' in update_dict and update_dict['tags']:
        update_dict['tags'] = [tag.lower() for tag in update_dict['tags']]
    
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
    
    # Update config with remaining fields (only fields that were explicitly set)
    for key, value in update_dict.items():
        if value is not None:
            config[key] = value

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
        
        # Check if serverName already exists
        existing_name = await MCPServerDocument.find_one({"serverName": data.serverName})
        if existing_name:
            raise ValueError(f"Server with name '{data.serverName}' already exists")
        
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
            serverName=data.serverName,
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
        
        # Update serverName if provided
        if data.serverName is not None:
            server.serverName = data.serverName
        
        # Update config with new values
        updated_config = _update_config_from_request(config, data)
        
        # Encrypt sensitive authentication fields if they were updated
        if data.authentication is not None or data.apiKey is not None:
            updated_config = encrypt_auth_fields(updated_config)
        
        server.config = updated_config
        
        # Update the updatedAt timestamp
        server.updatedAt = datetime.now(timezone.utc)
        
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
        
        # Update enabled field in config
        config["enabled"] = enabled
        server.config = config
        
        # Update the updatedAt timestamp
        server.updatedAt = datetime.now(timezone.utc)
        
        await server.save()
        logger.info(f"Toggled server {server.serverName} (ID: {server.id}) to {'enabled' if enabled else 'disabled'}")
        
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
            server_pipeline = [
                {
                    "$facet": {
                        "total": [
                            {"$count": "count"}
                        ],
                        "by_scope": [
                            {"$group": {"_id": "$config.scope", "count": {"$sum": 1}}}
                        ],
                        "by_status": [
                            {"$group": {"_id": "$config.status", "count": {"$sum": 1}}}
                        ],
                        "by_transport": [
                            {"$unwind": "$config.supported_transports"},
                            {"$group": {"_id": "$config.supported_transports", "count": {"$sum": 1}}}
                        ],
                        "total_tools": [
                            {"$group": {"_id": None, "total": {"$sum": "$config.num_tools"}}}
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

        logger.info(f"Generated system statistics: {stats['total_servers']} servers, {stats['total_tokens']} tokens, {stats['active_users']} active users")

        return stats

# Singleton instance
server_service_v1 = ServerServiceV1()