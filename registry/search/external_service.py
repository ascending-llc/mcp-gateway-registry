"""
External HTTP-based vector search service.

This implementation delegates vector search operations to an external MCP server via HTTP,
allowing the main registry to avoid heavy dependencies like torch and sentence-transformers.
Uses httpx for HTTP streamable protocol communication.
"""

import json
import logging
from typing import Dict, Any, Optional, List

import httpx

from .base import VectorSearchService

logger = logging.getLogger(__name__)


class ExternalVectorSearchService(VectorSearchService):
    """Vector search service that uses an external HTTP MCP server."""
    
    def __init__(self, mcp_server_url: str):
        """
        Initialize the external vector search service.
        
        Args:
            mcp_server_url: URL of the external MCP vector search server (HTTP endpoint)
        """
        self.mcp_server_url = mcp_server_url.rstrip('/')
        self._initialized = False
        self._client: Optional[httpx.AsyncClient] = None
        
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
        
    async def initialize(self):
        """Test connection to external HTTP vector search service."""
        logger.info(f"Connecting to external vector search service at {self.mcp_server_url}")
        # TODO: 直接连接DB python client
        try:
            client = await self._get_client()
            
            # Test connection by calling list_tools
            response = await client.post(
                self.mcp_server_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {}
                },
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            result = response.json()
            tools = result.get("result", {}).get("tools", [])
            tool_names = [tool.get("name") for tool in tools]
            
            required_tools = ["index_document", "search_documents", "delete_document"]
            missing_tools = [t for t in required_tools if t not in tool_names]
            
            if missing_tools:
                logger.warning(f"External vector search service is missing tools: {missing_tools}")
            
            self._initialized = True
            logger.info(f"Successfully connected to external vector search service. Available tools: {tool_names}")
        except Exception as e:
            # Log warning but don't fail - allow app to start for local development
            logger.warning(f"⚠️  External vector search service not available at {self.mcp_server_url}: {e}")
            logger.warning("⚠️  App will continue running but vector search features will be disabled")
            logger.warning("💡 To enable vector search, ensure the external service is running or switch to embedded mode")
            self._initialized = False
    
    async def add_or_update_service(self, service_path: str, server_info: Dict[str, Any], is_enabled: bool = False):
        """Add or update a service via external HTTP vector search."""
        if not self._initialized:
            logger.debug(f"External service not available, skipping index for '{service_path}'")
            return None
            
        logger.info(f"Indexing service '{service_path}' via external HTTP MCP")
        
        # Prepare document for indexing
        document = {
            "id": service_path,
            "name": server_info.get("server_name", ""),
            "description": server_info.get("description", ""),
            "tags": server_info.get("tags", []),
            "metadata": {
                "is_enabled": is_enabled,
                "full_server_info": server_info
            }
        }
        
        try:
            client = await self._get_client()
            response = await client.post(
                self.mcp_server_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "index_document",
                        "arguments": {
                            "document": json.dumps(document)
                        }
                    }
                },
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Successfully indexed '{service_path}' via external service")
            return result.get("result")
        except Exception as e:
            logger.warning(f"Failed to index service '{service_path}' via external service: {e}")
            return None
    
    async def remove_service(self, service_path: str):
        """Remove a service via external HTTP vector search."""
        if not self._initialized:
            logger.debug(f"External service not available, skipping delete for '{service_path}'")
            return None
            
        logger.info(f"Removing service '{service_path}' via external HTTP MCP")
        
        try:
            client = await self._get_client()
            response = await client.post(
                self.mcp_server_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "delete_document",
                        "arguments": {
                            "document_id": service_path
                        }
                    }
                },
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Successfully removed '{service_path}' via external service")
            return result.get("result")
        except Exception as e:
            logger.warning(f"Failed to remove service '{service_path}' via external service: {e}")
            return None
    
    async def search(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search for services via external HTTP vector search."""
        if not self._initialized:
            logger.warning("External service not available, returning empty search results")
            return []
            
        logger.info(f"Searching via external HTTP MCP - query: '{query}', tags: {tags}, top_k={top_k}")
        
        try:
            client = await self._get_client()
            
            search_args = {
                "top_k": top_k,
            }
            
            if query:
                search_args["query"] = query
            if tags:
                search_args["tags"] = tags
            if filters:
                search_args["filters"] = json.dumps(filters)
            
            response = await client.post(
                self.mcp_server_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "search_documents",
                        "arguments": search_args
                    }
                },
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Parse result - MCP tools/call returns result with content array
            mcp_result = result.get("result", {})
            content = mcp_result.get("content", [])
            
            if content and len(content) > 0:
                # First content item should have text with JSON results
                text_content = content[0].get("text", "[]")
                results = json.loads(text_content) if isinstance(text_content, str) else text_content
            else:
                results = []
            
            logger.info(f"External search returned {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"Search via external service failed: {e}, returning empty results")
            return []
    
    async def cleanup(self):
        """Cleanup resources - close HTTP client."""
        logger.info("Cleaning up external vector search service")
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        logger.info("External vector search service cleanup complete")
