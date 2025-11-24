"""
External vector search service for MCPGW.

This implementation delegates vector search to the registry's semantic search API,
avoiding the need for heavy FAISS dependencies in the MCPGW server.
"""

import logging
import httpx
from typing import List, Dict, Any, Optional

from .base import VectorSearchService

logger = logging.getLogger(__name__)


class ExternalVectorSearchService(VectorSearchService):
    """External vector search using registry's semantic search API."""
    
    def __init__(
        self,
        registry_base_url: str,
        registry_username: Optional[str] = None,
        registry_password: Optional[str] = None,
        timeout: float = 30.0
    ):
        """
        Initialize the external vector search service.
        
        Args:
            registry_base_url: Base URL of the registry service
            registry_username: Optional username for registry authentication
            registry_password: Optional password for registry authentication
            timeout: Request timeout in seconds
        """
        self.registry_base_url = registry_base_url.rstrip('/')
        self.registry_username = registry_username
        self.registry_password = registry_password
        self.timeout = timeout
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize the external vector search service."""
        # Check connectivity to registry
        try:
            auth = None
            if self.registry_username and self.registry_password:
                auth = httpx.BasicAuth(self.registry_username, self.registry_password)
            
            async with httpx.AsyncClient(timeout=self.timeout, auth=auth) as client:
                # Try to reach the registry health endpoint
                response = await client.get(f"{self.registry_base_url}/health")
                if response.status_code == 200:
                    self._initialized = True
                    logger.info(f"External vector search service initialized - registry available at {self.registry_base_url}")
                else:
                    logger.warning(f"Registry returned status {response.status_code}, but continuing")
                    self._initialized = True
        except Exception as e:
            logger.error(f"Failed to connect to registry at {self.registry_base_url}: {e}")
            self._initialized = False
            raise Exception(f"Cannot connect to registry: {e}")
    
    async def search_tools(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_scopes: Optional[List[str]] = None,
        top_k_services: int = 3,
        top_n_tools: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Search for tools by calling the registry's unified semantic search API.
        
        The registry's /api/search/semantic endpoint handles:
        - Semantic search across servers, tools, and agents
        - Tag filtering
        - Scope-based access control
        - Result ranking and filtering
        """
        if not self._initialized:
            raise Exception("External vector search service not initialized")
        
        # Input validation
        if not query and not tags:
            raise Exception("At least one of 'query' or 'tags' must be provided")
        
        # Prepare request payload
        search_request = {
            "top_n": top_n_tools,
            "entity_types": ["tool"]  # Only search for tools
        }
        
        if query:
            search_request["query"] = query
        
        if tags:
            search_request["tags"] = tags
        
        if user_scopes:
            # Pass scopes as a header or in payload depending on registry API design
            # For now, we'll include in payload
            search_request["user_scopes"] = user_scopes
        
        # Additional parameters
        if query:
            # Only use top_k_services if doing semantic search
            search_request["top_k_services"] = top_k_services
        
        try:
            auth = None
            if self.registry_username and self.registry_password:
                auth = httpx.BasicAuth(self.registry_username, self.registry_password)
            
            headers = {}
            # If user_scopes provided, also pass as header for registry auth
            if user_scopes:
                headers["X-Scopes"] = " ".join(user_scopes)
            
            async with httpx.AsyncClient(timeout=self.timeout, auth=auth) as client:
                logger.info(f"Calling registry semantic search: {self.registry_base_url}/api/search/semantic")
                logger.debug(f"Search request: {search_request}")
                
                response = await client.post(
                    f"{self.registry_base_url}/api/search/semantic",
                    json=search_request,
                    headers=headers
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Extract tools from the unified search response
                    # The registry returns: {"tools": [...], "servers": [...], "agents": [...]}
                    tools = result.get("tools", [])
                    
                    # Convert registry response format to mcpgw format
                    formatted_tools = []
                    for tool in tools:
                        formatted_tool = {
                            "tool_name": tool.get("name", "Unknown"),
                            "tool_parsed_description": tool.get("parsed_description", {}),
                            "tool_schema": tool.get("schema", {}),
                            "service_path": tool.get("server_path", ""),
                            "service_name": tool.get("server_name", "Unknown"),
                            "supported_transports": tool.get("supported_transports", ["streamable-http"]),
                            "auth_provider": tool.get("auth_provider"),
                        }
                        
                        # Add similarity score if present
                        if "score" in tool:
                            formatted_tool["overall_similarity_score"] = tool["score"]
                        
                        formatted_tools.append(formatted_tool)
                    
                    logger.info(f"External search returned {len(formatted_tools)} tools")
                    return formatted_tools
                    
                elif response.status_code == 404:
                    logger.error("Registry semantic search endpoint not found")
                    raise Exception("Registry does not support semantic search API")
                else:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = error_json.get("detail", error_detail)
                    except:
                        pass
                    logger.error(f"Registry search failed with status {response.status_code}: {error_detail}")
                    raise Exception(f"Registry search failed: {error_detail}")
                    
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to registry: {e}")
            raise Exception(f"Registry connection error: {e}")
        except Exception as e:
            logger.error(f"External search failed: {e}", exc_info=True)
            raise
    
    async def check_availability(self) -> bool:
        """Check if the external vector search service is available."""
        if not self._initialized:
            return False
        
        try:
            auth = None
            if self.registry_username and self.registry_password:
                auth = httpx.BasicAuth(self.registry_username, self.registry_password)
            
            async with httpx.AsyncClient(timeout=5.0, auth=auth) as client:
                response = await client.get(f"{self.registry_base_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.debug(f"Registry availability check failed: {e}")
            return False
