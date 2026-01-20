"""
MCP Tool Model

⚠️  DEPRECATION NOTICE:
This file will be deprecated and replaced by auto-generated models in _generated/
specifically the mcpServers model generated from JSON schemas.

This legacy model is kept for backward compatibility during migration.
New code should use the generated models from _generated/ folder.
"""

import json
import uuid
from typing import List, Dict, Any
from langchain_core.documents import Document
from packages.models.extended_mcp_server import ExtendedMCPServer as MCPServerDocument

import logging

logger = logging.getLogger(__name__)


class McpTool:
    COLLECTION_NAME = "MCP_GATEWAY"

    def __init__(
            self,
            tool_name: str,
            server_path: str,
            server_name: str,
            entity_type: List[str] = None,
            description_main: str = "",
            description_args: str = "",
            description_returns: str = "",
            description_raises: str = "",
            schema_json: str = "{}",
            tags: List[str] = None,
            is_enabled: bool = True,
            content: str = "",
            id: str = "",
            relevance_score: float = float("inf"),
    ):
        """
        Initialize MCP Tool instance.

        Args:
            tool_name: Tool name
            server_path: Server path (e.g., /weather)
            server_name: Server display name
            entity_type: Entity types for search filtering
            description_main: Main tool description
            description_args: Tool arguments description
            description_returns: Tool returns description
            description_raises: Tool raises description
            schema_json: Tool JSON schema as string
            tags: Server tags
            is_enabled: Whether the service is enabled
            content: Combined searchable text for semantic search
            id: Unique identifier (auto-generated if not provided)
        """
        self.id = id or str(uuid.uuid4())
        self.tool_name = tool_name
        self.server_path = server_path
        self.server_name = server_name
        self.entity_type = entity_type or ["all"]
        self.description_main = description_main
        self.description_args = description_args
        self.description_returns = description_returns
        self.description_raises = description_raises
        self.schema_json = schema_json
        # Normalize tags to lowercase for case-insensitive filtering
        self.tags = [tag.lower().strip() if isinstance(tag, str) else str(tag).lower().strip() for tag in (tags or [])]
        self.is_enabled = is_enabled
        self.content = content
        self.relevance_score = relevance_score

    def to_document(self) -> Document:
        """
        Convert the MCP Tool instance to a LangChain Document for vector storage.

        Returns:
            Document: LangChain Document object
        """
        # Create content for vectorization (combined searchable text)
        if not self.content:
            self._generate_content()

        metadata = {
            'tool_name': self.tool_name,
            'server_path': self.server_path,
            'server_name': self.server_name,
            'entity_type': self.entity_type,
            'description_main': self.description_main,
            'description_args': self.description_args,
            'description_returns': self.description_returns,
            'description_raises': self.description_raises,
            'schema_json': self.schema_json,
            'tags': self.tags,
            'is_enabled': self.is_enabled,
            'collection': self.COLLECTION_NAME
        }
        return Document(
            page_content=self.content,
            metadata=metadata,
            id=self.id
        )

    def _generate_content(self) -> None:
        """
        Generate combined searchable text for semantic search.

        Note: combined text
        """
        combined_parts = [
            f"Tool: {self.tool_name}",
            f"Server: {self.server_name} ({self.server_path})",
            f"Description: {self.description_main}",
        ]
        if self.description_args:
            combined_parts.append(f"Arguments: {self.description_args}")
        if self.description_returns:
            combined_parts.append(f"Returns: {self.description_returns}")
        if self.tags:
            combined_parts.append(f"Tags: {', '.join(self.tags)}")

        self.content = " | ".join(combined_parts)

    @classmethod
    def from_document(cls, document: Document) -> 'McpTool':
        """
        Create MCP Tool instance from LangChain Document.

        Args:
            document: LangChain Document object

        Returns:
            McpTool: MCP Tool instance
        """
        metadata = document.metadata

        # 从 Document.id 属性读取 id，而不是从 metadata 中读取
        return cls(
            id=document.id if hasattr(document, 'id') and document.id else metadata.get('id'),
            tool_name=metadata.get('tool_name', ''),
            server_path=metadata.get('server_path', ''),
            server_name=metadata.get('server_name', ''),
            entity_type=metadata.get('entity_type', ['all']),
            # metadata 中使用的是 'content' 键，而不是 'description_main'
            description_main=metadata.get('description_main', ''),
            description_args=metadata.get('description_args', ''),
            description_returns=metadata.get('description_returns', ''),
            description_raises=metadata.get('description_raises', ''),
            schema_json=metadata.get('schema_json', '{}'),
            tags=metadata.get('tags', []),
            is_enabled=metadata.get('is_enabled', True),
            content=document.page_content,
            relevance_score=metadata.get('relevance_score')
        )

    @classmethod
    def create_from_tool_dict(
            cls,
            tool: dict,
            service_path: str,
            server_name: str,
            server_tags: list,
            is_enabled: bool = False,
            entity_type: List[str] = None
    ) -> 'McpTool':
        """
        Create MCPTool instance from raw tool dictionary.

        Args:
            tool: Tool dictionary from server info
            service_path: Service path (e.g., /weather)
            server_name: Server display name
            server_tags: List of server tags
            is_enabled: Whether the service is enabled
            entity_type: Entity types for search filtering (default: ["all"])

        Returns:
            MCPTool instance
        """
        if entity_type is None:
            entity_type = ["all"]

        tool_name = tool.get("name", "")
        if not tool_name:
            raise ValueError("Tool must have a name")

        # Extract parsed description
        parsed_desc = tool.get("parsed_description", {}) or {}
        desc_main = parsed_desc.get("main", "No description available.")
        desc_args = parsed_desc.get("args") or ""
        desc_returns = parsed_desc.get("returns") or ""
        desc_raises = parsed_desc.get("raises") or ""

        # Get schema
        schema = tool.get("schema", {})
        schema_json = json.dumps(schema) if schema else "{}"

        # Create MCP Tool instance
        mcp_tool = cls(
            tool_name=tool_name,
            server_path=service_path,
            server_name=server_name,
            entity_type=entity_type,
            description_main=desc_main,
            description_args=desc_args,
            description_returns=desc_returns,
            description_raises=desc_raises,
            schema_json=schema_json,
            tags=server_tags,
            is_enabled=is_enabled
        )
        mcp_tool._generate_content()
        return mcp_tool

    @classmethod
    def create_tools_from_server_info(
            cls,
            service_path: str,
            server_info: dict,
            is_enabled: bool = False
    ) -> List['McpTool']:
        """
        Create list of McpTool instances from server info.

        Args:
            service_path: Service path (e.g., /weather)
            server_info: Server information dictionary containing tool_list
            is_enabled: Whether the service is enabled

        Returns:
            List of McpTool instances

        Raises:
            ValueError: If conversion fails for any tool
        """
        tool_list = server_info.get("tool_list", [])
        server_name = server_info.get("server_name", "")
        server_tags = server_info.get("tags", [])
        entity_type = server_info.get("entity_type", "mcp_server")

        # Handle agents without tools - create virtual tool
        if not tool_list and entity_type == "a2a_agent":
            agent_description = server_info.get("description", "")
            skills = server_info.get("skills", [])
            skills_text = ""
            if skills:
                if isinstance(skills[0], dict):
                    skills_text = ", ".join([skill.get("name", "") for skill in skills])
                else:
                    skills_text = ", ".join([str(skill) for skill in skills])

            tool_list = [{
                "name": server_name or service_path.strip("/"),
                "description": agent_description,
                "parsed_description": {
                    "main": f"{agent_description}. Skills: {skills_text}" if skills_text else agent_description
                },
                "schema": {}
            }]

        if not tool_list:
            return []

        # Determine entity_type list
        if entity_type == "mcp_server":
            entity_type_list = ["mcp_server", "tool"]
        elif entity_type == "a2a_agent":
            entity_type_list = ["a2a_agent", "tool"]
        else:
            entity_type_list = ["all"]

        # Convert to McpTool instances
        tools = []
        for tool_dict in tool_list:
            try:
                mcp_tool = cls.create_from_tool_dict(
                    tool=tool_dict,
                    service_path=service_path,
                    server_name=server_name,
                    server_tags=server_tags,
                    is_enabled=is_enabled,
                    entity_type=entity_type_list
                )
                tools.append(mcp_tool)
            except Exception as e:
                logger.error(f"Failed to convert tool {tool_dict.get('name', 'unknown')}: {e}")
                raise

        return tools

    @classmethod
    def compare_tools(
            cls,
            old_tools: List['McpTool'],
            new_tool_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compare old and new tools to determine changes for incremental updates.
        
        This is the core logic for efficient incremental indexing.
        
        Args:
            old_tools: Existing McpTool instances
            new_tool_list: New tool definitions from server
            
        Returns:
            Dictionary with:
            - to_delete: List of tool names to delete
            - to_add: List of tool dicts to add
            - to_update: List of tool dicts to update (description changed)
        """
        old_map = {t.tool_name: t for t in old_tools}
        new_map: Dict[str, Dict[str, Any]] = {}
        
        for tool_def in new_tool_list:
            name = tool_def.get("name")
            if not name:
                logger.warning("Skipping tool definition without 'name': %s", tool_def)
                continue
            new_map[name] = tool_def

        # Find tools to delete (exist in old but not in new)
        to_delete = [name for name in old_map if name not in new_map]
        
        # Find tools to add (exist in new but not in old)
        to_add = [t for name, t in new_map.items() if name not in old_map]

        # Find tools to update (description changed - triggers re-vectorization)
        to_update = []
        for name, new_tool in new_map.items():
            if name in old_map:
                old_tool = old_map[name]
                new_desc = new_tool.get("description", "")
                if old_tool.description_main != new_desc:
                    to_update.append(new_tool)

        return {
            "to_delete": to_delete,
            "to_add": to_add,
            "to_update": to_update
        }

    @staticmethod
    def get_safe_metadata_fields() -> set:
        """
        Get safe metadata fields that can be updated without re-vectorization.
        
        Returns:
            Set of safe field names
        """
        return {'is_enabled', 'tags', 'entity_type', 'server_name'}

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert MCP Tool instance to dictionary.

        Returns:
            Dict[str, Any]: Dictionary representation
        """
        return {
            'id': self.id,
            'tool_name': self.tool_name,
            'server_path': self.server_path,
            'server_name': self.server_name,
            'entity_type': self.entity_type,
            'description_main': self.description_main,
            'description_args': self.description_args,
            'description_returns': self.description_returns,
            'description_raises': self.description_raises,
            'schema_json': self.schema_json,
            'tags': self.tags,
            'is_enabled': self.is_enabled,
            'content': self.content
        }

    @staticmethod
    def from_server_document(server: MCPServerDocument) -> Dict[str, Any]:
        """
        Convert MCPServerDocument to server_info format for search indexing.
        """
        config = server.config or {}

        # Extract tool_list from toolFunctions or use empty list
        tool_functions = config.get("toolFunctions", {})
        tool_list = []

        # Convert toolFunctions back to tool_list format
        for func_key, func_data in tool_functions.items():
            if isinstance(func_data, dict) and "function" in func_data:
                func = func_data["function"]
                tool_list.append({
                    "name": func.get("name", func_key),
                    "description": func.get("description", ""),
                    "inputSchema": func.get("parameters", {})
                })

        return {
            "server_name": server.serverName,
            "description": config.get("description", ""),
            "path": server.path,
            "tags": server.tags or [],
            "entity_type": "mcp_server",
            "tool_list": tool_list,
            "is_enabled": config.get("enabled", True),
        }

    def __str__(self):
        return f"<McpTool: {self.tool_name} ({self.server_path})>"

    def __repr__(self):
        return self.__str__()
