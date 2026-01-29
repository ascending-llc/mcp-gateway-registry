"""
Extended MCP Server Model for Registry-Specific Fields

This module extends the auto-generated MCPServerDocument with registry-specific fields.
The base model (_generated/mcpServer.py) should NOT be modified as it's auto-generated.

Storage Structure (following API documentation specifications):

Configuration Fields (stored in config object):
- title: string - Display name
- description: string - Server description
- type: string - Transport type (streamable-http, sse, stdio, websocket)
- url: string - Server endpoint URL
- apiKey: object (optional) - API key configuration
- requiresOAuth: boolean - Whether OAuth is required
- oauth: object (optional) - OAuth configuration
- capabilities: string - JSON string of server capabilities
- tools: string - Comma-separated list of tool names (e.g., "tool1, tool2, tool3")
- toolFunctions: object - Tool function definitions in OpenAI format
- initDuration: number - Server initialization time in ms

Identity & Metadata Fields (stored at root level):
- _id (id): ObjectId - MongoDB document ID
- serverName: string - Unique server identifier
- author: ObjectId - User who created this server
- scope: string - Access level (shared_app, shared_user, private_user)
- status: string - Server status (active, inactive, error)
- createdAt: datetime - Creation timestamp
- updatedAt: datetime - Last update timestamp

Additional Fields (stored at root level):
- path: string - API path for this server (e.g., "/mcp/github")
- tags: array[string] - Array of tags for categorization
- numTools: number - Number of tools (calculated from toolFunctions object size)
- numStars: number - Number of stars/favorites
- lastConnected: datetime (nullable) - Last successful connection timestamp
- lastError: datetime (nullable) - Last error timestamp
- errorMessage: string (nullable) - Last error message details

Key Principle: 
- Configuration Fields are stored in the config object
- Identity & Metadata and Additional Fields are stored at root level
- numTools is a calculated field, not stored in the database
"""

from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional, Set, Literal
from pydantic import Field
from beanie import Document, PydanticObjectId
from langchain_core.documents import Document as LangChainDocument


class ExtendedMCPServer(Document):
    """
    Extended MCP Server Document with Registry-Specific Fields
    
    This model extends the base MCPServerDocument with registry-specific fields
    that are stored at root level in MongoDB, not in the config object.
    
    Storage Structure (MongoDB):
    {
      "_id": ObjectId("..."),
      "serverName": "github",
      "config": {  # MCP-specific configuration
        "title": "GitHub MCP Server",
        "description": "...",
        "type": "streamable-http",
        "url": "http://github-server:8011",
        "apiKey": {...} or "oauth": {...} or "authentication": {...},
        "requiresOAuth": false,
        "capabilities": "{}",  # JSON string
        "toolFunctions": {     # OpenAI function format
          "tool1_mcp_github": {
            "type": "function",
            "function": {
              "name": "tool1_mcp_github",
              "description": "...",
              "parameters": {...}
            }
          }
        },
        "tools": "tool1, tool2",
        "initDuration": 170
      },
      "scope": "shared_app",  # Registry field (root level)
      "status": "active",     # Registry field (root level)
      "path": "/mcp/github",  # Registry field (root level)
      "tags": ["github"],     # Registry field (root level)
      "numTools": 2,          # Registry field (root level)
      "numStars": 0,          # Registry field (root level)
      "lastConnected": ISODate("..."),  # Registry field (root level)
      "lastError": ISODate("..."),      # Registry field (root level)
      "errorMessage": "...",   # Registry field (root level)
      "author": ObjectId("..."),
      "createdAt": ISODate("..."),
      "updatedAt": ISODate("...")
    }
    """

    # ========== Base Fields (from MCPServerDocument) ==========
    serverName: str = Field(..., description="Server name for display",
                            json_schema_extra={"vector_role": "content"})  # Vectorized for search
    config: Dict[str, Any] = Field(...,
                                   description="MCP server configuration (oauth, apiKey, capabilities, tools, etc.)")
    author: PydanticObjectId = Field(..., description="User who created this server")

    # ========== Registry-Specific Root-Level Fields ==========
    # These fields are specific to the registry and should NOT be in config
    path: str = Field(..., description="API path for this server (e.g., /mcp/github)",
                      json_schema_extra={"vector_role": "content"})  # Vectorized for search
    tags: List[str] = Field(default_factory=list, description="Tags for categorization",
                            json_schema_extra={"vector_role": "metadata"})
    scope: str = Field(default="private_user", description="Access level: shared_app, shared_user, private_user",
                       json_schema_extra={"vector_role": "metadata"})
    status: str = Field(default="active", description="Operational state: active, inactive, error",
                        json_schema_extra={"vector_role": "metadata"})
    numTools: int = Field(default=0, alias="numTools", description="Number of tools (calculated from toolFunctions)")
    numStars: int = Field(default=0, alias="numStars", description="Number of stars/favorites")

    # Monitoring fields
    lastConnected: Optional[datetime] = Field(default=None, alias="lastConnected",
                                              description="Last successful connection timestamp")
    lastError: Optional[datetime] = Field(default=None, alias="lastError", description="Last error timestamp")
    errorMessage: Optional[str] = Field(default=None, alias="errorMessage", description="Last error message details")

    # Timestamps (auto-generated by Beanie)
    createdAt: Optional[datetime] = Field(default=None, alias="createdAt")
    updatedAt: Optional[datetime] = Field(default=None, alias="updatedAt")

    class Settings:
        name = "mcpservers"
        keep_nulls = False
        use_state_management = True
        # Note: No indexes defined here - this file only defines field structure
        # Indexes should be managed separately via database migrations

    # ========== Vector Search Integration (Weaviate) ==========
    COLLECTION_NAME: ClassVar[str] = "Jarvis_Registry"

    def to_document(self) -> LangChainDocument:
        """
        Convert ExtendedMCPServer to LangChain Document for vector storage.
        
        Storage format:
        - content: Vectorized text (serverName | path | title | description | tools | resources | prompts)
        - metadata: Non-vectorized fields (serverName, path, scope, status)

        """
        content = self.generate_content()

        # Auto-discover metadata fields using annotations
        metadata = {'collection': self.COLLECTION_NAME}

        for field_name in self._get_fields_by_role("metadata"):
            value = getattr(self, field_name, None)
            metadata_key = self._camel_to_snake(field_name)
            metadata[metadata_key] = value

        # Always include server_id for lookups (MongoDB _id)
        metadata['server_id'] = str(self.id) if self.id else None

        return LangChainDocument(
            page_content=content,
            metadata=metadata,
        )

    def generate_content(self) -> str:
        """
        Generate combined searchable text for semantic search.
        
        Format: serverName | path | config.title | config.description | 
                toolFunctions (name + description) | 
                resources (name + description) | 
                prompts (name + description)
        
        Returns:
            Combined text string separated by |
        """
        parts = [self.serverName, self.path]
        # Config fields
        if self.config:
            parts.append(self.config.get('title', ''))
            parts.append(self.config.get('description', ''))

            # Tool functions
            tool_functions = self.config.get('toolFunctions', {})
            for func_data in tool_functions.values():
                if isinstance(func_data, dict) and 'function' in func_data:
                    func = func_data['function']
                    parts.append(func.get('name', ''))
                    parts.append(func.get('description', ''))

            # Resources
            resources = self.config.get('resources', [])
            for res in resources:
                if isinstance(res, dict):
                    parts.append(res.get('name', ''))
                    parts.append(res.get('description', ''))

            # Prompts
            prompts = self.config.get('prompts', [])
            for prompt in prompts:
                if isinstance(prompt, dict):
                    parts.append(prompt.get('name', ''))
                    parts.append(prompt.get('description', ''))

        # Filter out empty strings and join with |
        return ' | '.join(filter(None, parts))

    @classmethod
    def from_document(cls, document: LangChainDocument) -> dict:
        """
        Create ExtendedMCPServer instance from LangChain Document.
        
        Note: This creates a minimal instance from metadata.
        Full server data should be fetched from MongoDB.

        """
        metadata = document.metadata
        return {
            "server_id": metadata.get('server_id'),
            "path": metadata.get('path'),
            "scope": metadata.get('scope'),
            "server_name": metadata.get('server_name'),
            "status": metadata.get('status'),
            "content": metadata.get('content'),
        }

    @classmethod
    def from_server_info(
            cls,
            server_info: Dict[str, Any],
            is_enabled: bool = False
    ) -> 'ExtendedMCPServer':
        """
        Create ExtendedMCPServer instance from server info dictionary.

        Args:
            server_info: Server information dictionary (must contain 'path' and 'server_name')
            is_enabled: Whether the service is enabled (maps to status)

        Returns:
            ExtendedMCPServer instance

        Raises:
            ValueError: If required fields are missing
        """
        # Extract required fields
        path = server_info.get('path')
        if not path:
            raise ValueError("server_info must contain 'path' field")

        server_name = server_info.get('server_name', path.strip('/'))
        config = server_info.get('config', {})

        # If config is not provided, build it from server_info
        if not config:
            config = {
                'title': server_info.get('title', server_name),
                'description': server_info.get('description', ''),
                'toolFunctions': server_info.get('toolFunctions', {}),
                'resources': server_info.get('resources', []),
                'prompts': server_info.get('prompts', []),
            }

        # Map is_enabled to status
        status = 'active' if is_enabled else 'inactive'

        # Extract server_id if available (for updates)
        server_id = server_info.get('id') or server_info.get('_id')

        # Create server instance
        return cls(
            id=PydanticObjectId(server_id) if server_id else None,
            serverName=server_name,
            path=path,
            config=config,
            scope=server_info.get('scope', 'private_user'),
            status=status,
            tags=server_info.get('tags', []),
            author=server_info.get('author') or PydanticObjectId(),
        )

    @staticmethod
    def get_safe_metadata_fields() -> Set[str]:
        """
        Get safe metadata fields that can be updated without re-vectorization.

        Auto-discovers fields marked with vector_role="metadata".

        Returns:
            Set of safe field names (matching Weaviate metadata field names in snake_case)
        """
        metadata_fields = ExtendedMCPServer._get_fields_by_role("metadata")
        return {ExtendedMCPServer._camel_to_snake(f) for f in metadata_fields}

    @staticmethod
    def _camel_to_snake(name: str) -> str:
        """Convert camelCase to snake_case"""
        return ''.join(['_' + c.lower() if c.isupper() else c for c in name]).lstrip('_')

    @classmethod
    def _get_fields_by_role(cls, role: Literal["content", "metadata"]) -> Set[str]:
        """
        Automatically discover fields marked with specific vector_role.

        This eliminates manual maintenance of field lists and ensures
        consistency between field definitions and vector storage logic.
        """
        fields = set()
        for field_name, field_info in cls.model_fields.items():
            extra = field_info.json_schema_extra
            if extra and extra.get("vector_role") == role:
                fields.add(field_name)
        return fields


MCPServerDocument = ExtendedMCPServer
