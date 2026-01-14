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
from typing import Any, Dict, List, Optional
from pydantic import Field
from beanie import Document, PydanticObjectId


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
    serverName: str = Field(..., description="Unique server identifier")
    config: Dict[str, Any] = Field(..., description="MCP server configuration (oauth, apiKey, capabilities, tools, etc.)")
    author: PydanticObjectId = Field(..., description="User who created this server")
    
    # ========== Registry-Specific Root-Level Fields ==========
    # These fields are specific to the registry and should NOT be in config
    path: str = Field(..., description="API path for this server (e.g., /mcp/github)")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    scope: str = Field(default="private_user", description="Access level: shared_app, shared_user, private_user")
    status: str = Field(default="active", description="Operational state: active, inactive, error")
    numTools: int = Field(default=0, alias="numTools", description="Number of tools (calculated from toolFunctions)")
    numStars: int = Field(default=0, alias="numStars", description="Number of stars/favorites")
    
    # Monitoring fields
    lastConnected: Optional[datetime] = Field(default=None, alias="lastConnected", description="Last successful connection timestamp")
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


# Alias for compatibility with existing code
MCPServerDocument = ExtendedMCPServer

