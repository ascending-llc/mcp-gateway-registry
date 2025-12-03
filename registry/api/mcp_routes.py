import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from ..auth.dependencies import enhanced_auth
from ..services.server_service import server_service
from ..mcp_management.mcp_manager import MCPManager, get_mcp_manager
from ..mcp_management.mcp_connection import ConnectionState

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_server_configs() -> Dict[str, Dict[str, Any]]:
    """
    Get MCP server configurations from server service.
    
    Returns:
        Dictionary mapping server_name -> MCP connection configuration
    """
    all_servers = server_service.get_all_servers(include_federated=True)
    configs = {}
    
    for path, server_info in all_servers.items():
        server_name = server_info.get("server_name", path.strip('/'))
        
        # Skip disabled servers
        if not server_service.is_service_enabled(path):
            logger.debug(f"Skipping disabled server: {server_name}")
            continue
        
        # Build MCP connection configuration from server info
        config = {
            "server_name": server_name,
            "enabled": True,
            "description": server_info.get("description", ""),
            "tags": server_info.get("tags", []),
            "num_tools": server_info.get("num_tools", 0),
        }
        
        # Determine transport type and URL from proxy_pass_url
        proxy_pass_url = server_info.get("proxy_pass_url")
        if proxy_pass_url:
            # Clean up the URL - remove any trailing slashes
            url = proxy_pass_url.rstrip('/')
            
            # Determine transport type based on URL pattern
            # This is a simplified heuristic - in production you might want more sophisticated detection
            if url.endswith('/sse'):
                config["type"] = "sse"
                config["url"] = url
            elif url.endswith('/mcp') or '/mcp/' in url:
                config["type"] = "streamable-http"
                config["url"] = url
            elif url.startswith('ws://') or url.startswith('wss://'):
                config["type"] = "websocket"
                config["url"] = url
            else:
                # Default to streamable-http for HTTP URLs
                config["type"] = "streamable-http"
                config["url"] = url
            
            # Add headers if present in server info
            headers = server_info.get("headers", [])
            if headers and isinstance(headers, list):
                # Convert list of dicts to single dict
                header_dict = {}
                for header_item in headers:
                    if isinstance(header_item, dict):
                        header_dict.update(header_item)
                if header_dict:
                    config["headers"] = header_dict
            
            # Add timeout if specified
            timeout = server_info.get("timeout")
            if timeout:
                config["timeout"] = timeout
            
            # Check if server requires authentication
            requires_auth = server_info.get("requires_auth", False)
            tags = server_info.get("tags", [])
            has_oauth_tag = any("oauth" in tag.lower() for tag in tags)
            config["requires_auth"] = requires_auth or has_oauth_tag
            
            # Add supported transports if specified
            supported_transports = server_info.get("supported_transports", [])
            if supported_transports:
                config["supported_transports"] = supported_transports
            
            configs[server_name] = config
        else:
            logger.warning(f"Server {server_name} has no proxy_pass_url, skipping MCP connection")
    
    logger.info(f"Found {len(configs)} MCP server configurations")
    return configs


async def initialize_mcp_manager() -> MCPManager:
    """
    Initialize the MCP manager with server configurations.
    
    Returns:
        Initialized MCPManager instance
    """
    try:
        # Get server configurations
        server_configs = await get_server_configs()
        
        # Initialize MCP manager
        mcp_manager = await MCPManager.initialize_instance(server_configs)
        logger.info("MCP manager initialized successfully")
        return mcp_manager
    except Exception as e:
        logger.error(f"Failed to initialize MCP manager: {e}")
        # Return existing instance if already initialized
        return MCPManager.get_instance()


@router.get("/connection/status")
async def get_connection_status(
    user_context: Dict[str, Any] = Depends(enhanced_auth)
):
    """
    Get connection status for all MCP servers.
    
    Returns real connection status from MCP manager, not simulated data.
    """
    try:
        user = user_context
        if not user.get("id"):
            raise HTTPException(status_code=401, detail="User not authenticated")
        user_id = user["id"]
        
        # Get or initialize MCP manager
        mcp_manager = await initialize_mcp_manager()
        
        # Get connection status for all servers
        connection_status = await mcp_manager.get_all_connection_status(user_id)
        
        # Also get server information for additional context
        server_configs = await get_server_configs()
        
        # Enrich status with server information
        enriched_status = {}
        for server_name, status in connection_status.items():
            server_config = server_configs.get(server_name, {})
            
            enriched_status[server_name] = {
                "connection_state": status["connection_state"],
                "requires_oauth": status["requires_oauth"],
                "server_name": server_name,
                "enabled": server_config.get("enabled", True),
                "description": server_config.get("description", ""),
                "tags": server_config.get("tags", []),
                "num_tools": server_config.get("num_tools", 0),
                "transport_type": status.get("transport_type", "unknown"),
                "url": status.get("url"),
                "is_app_connection": status.get("is_app_connection", False),
                "user_id": status.get("user_id"),
                "error": status.get("error")
            }
        
        # Add servers that are in config but not in connection status (e.g., disabled)
        for server_name, server_config in server_configs.items():
            if server_name not in enriched_status:
                enriched_status[server_name] = {
                    "connection_state": ConnectionState.DISCONNECTED.value,
                    "requires_oauth": server_config.get("requires_auth", False),
                    "server_name": server_name,
                    "enabled": server_config.get("enabled", True),
                    "description": server_config.get("description", ""),
                    "tags": server_config.get("tags", []),
                    "num_tools": server_config.get("num_tools", 0),
                    "transport_type": server_config.get("type", "unknown"),
                    "url": server_config.get("url"),
                    "is_app_connection": True,
                    "user_id": None,
                    "error": "Server not connected"
                }
        return JSONResponse({
            "success": True,
            "connection_status": enriched_status
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MCP Connection Status] Failed to get connection status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get connection status: {str(e)}")


@router.get("/connection/status/{server_name}")
async def get_server_connection_status_endpoint(
    server_name: str,
    user_context: Dict[str, Any] = Depends(enhanced_auth)
):
    """
    Get connection status for a specific MCP server.
    
    Returns real connection status from MCP manager, not simulated data.
    """
    try:
        user = user_context
        
        if not user.get("id"):
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        user_id = user["id"]
        
        # Get or initialize MCP manager
        mcp_manager = await initialize_mcp_manager()
        
        # Get connection status for specific server
        status = await mcp_manager.get_server_connection_status(server_name, user_id)
        
        # Get server information for additional context
        server_configs = await get_server_configs()
        server_config = server_configs.get(server_name, {})
        
        # Enrich status with server information
        enriched_status = {
            "connection_state": status["connection_state"],
            "requires_oauth": status["requires_oauth"],
            "server_name": server_name,
            "enabled": server_config.get("enabled", True),
            "description": server_config.get("description", ""),
            "tags": server_config.get("tags", []),
            "num_tools": server_config.get("num_tools", 0),
            "transport_type": status.get("transport_type", "unknown"),
            "url": status.get("url"),
            "is_app_connection": status.get("is_app_connection", False),
            "user_id": status.get("user_id"),
            "error": status.get("error")
        }
        
        # If server not found in config, add error info
        if server_name not in server_configs:
            enriched_status["error"] = "Server not found in configuration"
            enriched_status["connection_state"] = ConnectionState.DISCONNECTED.value
        
        return JSONResponse({
            "success": True,
            "server_name": server_name,
            "connection_status": enriched_status["connection_state"],
            "requires_oauth": enriched_status["requires_oauth"],
            "status": enriched_status
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MCP Server Status] Failed to get connection status for {server_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get connection status: {str(e)}")


@router.get("/tools/{server_name}")
async def get_server_tools(
    server_name: str,
    user_context: Dict[str, Any] = Depends(enhanced_auth)
):
    """Get tools available from a specific MCP server."""
    try:
        user = user_context
        
        if not user.get("id"):
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        user_id = user["id"]
        
        # Get or initialize MCP manager
        mcp_manager = await initialize_mcp_manager()
        
        # List tools from server
        tools = await mcp_manager.list_tools_for_server(server_name, user_id)
        
        return JSONResponse({
            "success": True,
            "server_name": server_name,
            "tools": tools,
            "count": len(tools)
        })
        
    except Exception as e:
        logger.error(f"Failed to get tools from server {server_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get tools: {str(e)}")


@router.get("/resources/{server_name}")
async def get_server_resources(
    server_name: str,
    user_context: Dict[str, Any] = Depends(enhanced_auth)
):
    """Get resources available from a specific MCP server."""
    try:
        user = user_context
        
        if not user.get("id"):
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        user_id = user["id"]
        
        # Get or initialize MCP manager
        mcp_manager = await initialize_mcp_manager()
        
        # List resources from server
        resources = await mcp_manager.list_resources_for_server(server_name, user_id)
        
        return JSONResponse({
            "success": True,
            "server_name": server_name,
            "resources": resources,
            "count": len(resources)
        })
        
    except Exception as e:
        logger.error(f"Failed to get resources from server {server_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get resources: {str(e)}")


@router.get("/prompts/{server_name}")
async def get_server_prompts(
    server_name: str,
    user_context: Dict[str, Any] = Depends(enhanced_auth)
):
    """Get prompts available from a specific MCP server."""
    try:
        user = user_context
        
        if not user.get("id"):
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        user_id = user["id"]
        
        # Get or initialize MCP manager
        mcp_manager = await initialize_mcp_manager()
        
        # List prompts from server
        prompts = await mcp_manager.list_prompts_for_server(server_name, user_id)
        
        return JSONResponse({
            "success": True,
            "server_name": server_name,
            "prompts": prompts,
            "count": len(prompts)
        })
        
    except Exception as e:
        logger.error(f"Failed to get prompts from server {server_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get prompts: {str(e)}")


@router.post("/tools/{server_name}/{tool_name}")
async def call_server_tool(
    server_name: str,
    tool_name: str,
    arguments: Dict[str, Any],
    user_context: Dict[str, Any] = Depends(enhanced_auth)
):
    """Call a tool on a specific MCP server."""
    try:
        user = user_context
        
        if not user.get("id"):
            raise HTTPException(status_code=401, detail="User not authenticated")
        
        user_id = user["id"]
        
        # Get or initialize MCP manager
        mcp_manager = await initialize_mcp_manager()
        
        # Call tool on server
        result = await mcp_manager.call_tool(server_name, tool_name, arguments, user_id)
        
        return JSONResponse({
            "success": True,
            "server_name": server_name,
            "tool_name": tool_name,
            "result": result
        })
        
    except Exception as e:
        logger.error(f"Failed to call tool {tool_name} on server {server_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to call tool: {str(e)}")
