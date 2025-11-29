import json
from typing import List
from packages.db import TextField, TextArrayField, BooleanField, Model
from weaviate.classes.config import VectorDistances
import logging

logger = logging.getLogger(__name__)


class McpTool(Model):
    """
    mcp Tool model for vector search.
    """

    # Tool identification
    tool_name = TextField(
        description="Tool name",
        index_filterable=True,
        index_searchable=True
    )

    server_path = TextField(
        description="Server path (e.g., /weather)",
        index_filterable=True,
        index_searchable=True
    )

    server_name = TextField(
        description="Server display name",
        index_filterable=True,
        index_searchable=True
    )

    # Tool descriptions
    description_main = TextField(
        description="Main tool description",
        index_filterable=False,
        index_searchable=True
    )

    description_args = TextField(
        description="Tool arguments description",
        index_filterable=False,
        index_searchable=True
    )

    description_returns = TextField(
        description="Tool returns description",
        index_filterable=False,
        index_searchable=True
    )

    description_raises = TextField(
        description="Tool raises description",
        index_filterable=False,
        index_searchable=True
    )

    # Schema and metadata
    schema_json = TextField(
        description="Tool JSON schema as string",
        index_filterable=False,
        index_searchable=False,
        skip_vectorization=True
    )

    tags = TextArrayField(
        description="Server tags",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True
    )

    is_enabled = BooleanField(
        description="Whether the service is enabled",
        index_filterable=True,
    )

    # Combined searchable text for better semantic search
    combined_text = TextField(
        description="Combined searchable text for semantic search",
        index_filterable=False,
        index_searchable=True
    )

    class Meta:
        """
        Model metadata configuration.
        
        Configures the collection to use AWS Bedrock (text2vec-aws) for embeddings.
        The vectorizer will be automatically configured based on the EMBEDDINGS_PROVIDER
        environment variable (should be set to 'bedrock').
        """
        collection_name = "MCP_GATEWAY"
        vectorizer = "text2vec-aws"  # AWS Bedrock embeddings
        vector_index_config = type('VectorIndexConfig', (), {
            'distance': VectorDistances.COSINE
        })()

    @classmethod
    def create_from_tool_dict(
            cls,
            tool: dict,
            service_path: str,
            server_name: str,
            server_tags: list,
            is_enabled: bool = False
    ) -> 'McpTool':
        """
        Create MCPTool instance from raw tool dictionary.
        
        Args:
            tool: Tool dictionary from server info
            service_path: Service path (e.g., /weather)
            server_name: Server display name
            server_tags: List of server tags
            is_enabled: Whether the service is enabled
            
        Returns:
            MCPTool instance
        """

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

        # Create combined text for better semantic search
        combined_parts = [
            f"Tool: {tool_name}",
            f"Server: {server_name} ({service_path})",
            f"Description: {desc_main}",
        ]
        if desc_args:
            combined_parts.append(f"Arguments: {desc_args}")
        if desc_returns:
            combined_parts.append(f"Returns: {desc_returns}")
        if server_tags:
            combined_parts.append(f"Tags: {', '.join(server_tags)}")

        combined_text = " | ".join(combined_parts)

        return cls(
            tool_name=tool_name,
            server_path=service_path,
            server_name=server_name,
            description_main=desc_main,
            description_args=desc_args,
            description_returns=desc_returns,
            description_raises=desc_raises,
            schema_json=schema_json,
            tags=server_tags,
            is_enabled=is_enabled,
            combined_text=combined_text
        )

    @classmethod
    def bulk_create_from_server_info(
        cls,
        service_path: str,
        server_info: dict,
        is_enabled: bool = False
    ):
        """
        Bulk create tools from server info dictionary.
        
        Returns BatchResult with complete error reporting (new in v2.0).
        
        Args:
            service_path: Service path identifier
            server_info: Server info with tool_list
            is_enabled: Whether the service is enabled
            
        Returns:
            BatchResult with success/failure statistics
            
        Raises:
            Exception: If bulk creation fails catastrophically
        """
        tool_list = server_info.get("tool_list", [])
        if not tool_list:
            logger.warning(f"No tools in server_info for '{service_path}'")
            from packages.db import BatchResult
            return BatchResult(total=0, successful=0, failed=0, errors=[])

        server_name = server_info.get("server_name", "")
        server_tags = server_info.get("tags", [])

        logger.info(f"Converting {len(tool_list)} tools to MCPTool instances for '{service_path}'")

        # Convert all tools to MCPTool instances
        instances = []
        conversion_errors = []
        
        for i, tool in enumerate(tool_list):
            try:
                mcp_tool = cls.create_from_tool_dict(
                    tool=tool,
                    service_path=service_path,
                    server_name=server_name,
                    server_tags=server_tags,
                    is_enabled=is_enabled
                )
                instances.append(mcp_tool)
                logger.debug(f"  Converted tool {i + 1}/{len(tool_list)}: {tool.get('name', 'unnamed')}")
            except ValueError as e:
                logger.error(f"Skipping invalid tool in '{service_path}': {e}")
                conversion_errors.append({
                    'uuid': None,
                    'message': f"Conversion failed: {e}"
                })
            except Exception as e:
                logger.error(f"Unexpected error converting tool in '{service_path}': {e}")
                conversion_errors.append({
                    'uuid': None,
                    'message': f"Unexpected error: {e}"
                })

        # Batch create with error reporting
        if instances:
            logger.info(f"Bulk creating {len(instances)} MCPTool instances for '{service_path}'")
            try:
                # Returns BatchResult (new in v2.0)
                result = cls.objects.bulk_create(instances, batch_size=100)
                
                logger.info(
                    f"Bulk create result: {result.successful}/{result.total} successful "
                    f"({result.success_rate:.1f}%)"
                )
                
                if result.has_errors:
                    logger.warning(f"⚠️  {result.failed} tools failed:")
                    for error in result.errors[:5]:
                        logger.warning(f"   - {error}")
                
                # Combine conversion errors with creation errors
                all_errors = conversion_errors + result.errors
                
                from packages.db import BatchResult
                return BatchResult(
                    total=len(tool_list),
                    successful=result.successful,
                    failed=len(all_errors),
                    errors=all_errors
                )
                
            except Exception as e:
                logger.error(f"Bulk create failed for '{service_path}': {e}", exc_info=True)
                raise
        else:
            logger.warning(f"No valid tool instances to create for '{service_path}'")
            from packages.db import BatchResult
            return BatchResult(
                total=len(tool_list),
                successful=0,
                failed=len(conversion_errors),
                errors=conversion_errors
            )

    def __str__(self):
        return f"<MCPTool: {self.tool_name} ({self.server_path})>"

    def __repr__(self):
        return self.__str__()
