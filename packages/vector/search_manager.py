import asyncio
import logging
from typing import Dict, Any, Optional, List
from packages.vector import initialize_database
from packages.models.mcp_tool import McpTool

logger = logging.getLogger(__name__)


class SearchIndexManager:
    """
    Manager for search index operations.
    
    Provides intelligent update strategies to minimize vectorization costs.
    """

    _instance: Optional['SearchIndexManager'] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize search index manager (only once for singleton)."""
        if not self._initialized:
            try:
                self._client = initialize_database()
                self._mcp_tools = self._client.for_model(McpTool)
                self._initialized = True
                logger.info("SearchIndexManager initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize SearchIndexManager: {e}")
                self._client = None
                self._mcp_tools = None
                self._initialized = False

    def is_available(self) -> bool:
        """Check if search index manager is available."""
        return self._initialized and self._client is not None

    async def toggle_entity_status(
            self,
            entity_path: str,
            is_enabled: bool
    ) -> Optional[Dict[str, int]]:
        """
        Toggle entity enabled status (field update only, no vectorization).
        
        Args:
            entity_path: Entity path identifier
            is_enabled: New enabled status
            
        Returns:
            {"updated_tools": count} or None if unavailable
            
        """
        if not self.is_available():
            logger.warning(f"Search index unavailable, skipping toggle for '{entity_path}'")
            return None

        try:
            filters = {"server_path": entity_path}
            update_data = {"is_enabled": is_enabled}

            updated_count = await asyncio.to_thread(
                self._mcp_tools.batch_update_by_filter,
                filters=filters,
                update_data=update_data
            )

            logger.info(f"Toggled {updated_count} tools for '{entity_path}' to enabled={is_enabled}")
            return {"updated_tools": updated_count}

        except Exception as e:
            logger.error(f"Toggle failed for '{entity_path}': {e}", exc_info=True)
            return None

    async def update_entity_metadata(
            self,
            entity_path: str,
            metadata: Dict[str, Any]
    ) -> Optional[Dict[str, int]]:
        """
        Update entity metadata fields (no vectorization).

        Args:
            entity_path: Entity path identifier
            metadata: Dictionary of metadata fields to update
                Valid fields: is_enabled, tags, entity_type, server_name
                Invalid fields (will cause re-vectorization): content, description_*
            
        Returns:
            {"updated_tools": count} or None if unavailable
        """
        if not self.is_available():
            logger.warning(f"Search index unavailable, skipping metadata update for '{entity_path}'")
            return None

        try:
            # Only allow metadata fields (no vector fields)
            safe_fields = {'is_enabled', 'tags', 'entity_type', 'server_name'}
            update_data = {k: v for k, v in metadata.items() if k in safe_fields}

            if not update_data:
                logger.warning(f"No valid metadata fields to update for '{entity_path}'")
                return {"updated_tools": 0}

            filters = {"server_path": entity_path}

            updated_count = await asyncio.to_thread(
                self._mcp_tools.batch_update_by_filter,
                filters=filters,
                update_data=update_data
            )
            logger.info(f"Updated metadata for {updated_count} tools in '{entity_path}': {update_data}")
            return {"updated_tools": updated_count}

        except Exception as e:
            logger.error(f"Metadata update failed for '{entity_path}': {e}", exc_info=True)
            return None

    async def add_or_update_entity(
            self,
            entity_path: str,
            entity_info: Dict[str, Any],
            entity_type: str = "mcp_server",
            is_enabled: bool = True
    ) -> Optional[Dict[str, int]]:
        """
        Add or update entity with full rebuild (delete + recreate all tools).
        
        This is the least efficient method but necessary when:
        - Creating a new entity
        - Tools list changed significantly
        - Tool descriptions changed
        
        Args:
            entity_path: Entity path identifier
            entity_info: Complete entity information with tool_list
            entity_type: Entity type (mcp_server, a2a_agent)
            is_enabled: Enabled status
            
        Returns:
            {"indexed_tools": count, "failed_tools": count} or None if unavailable

        """
        if not self.is_available():
            logger.warning(f"Search index unavailable, skipping full update for '{entity_path}'")
            return None

        tool_count = len(entity_info.get("tool_list", []))
        logger.info(f"Full rebuild for '{entity_path}': {tool_count} tools, enabled={is_enabled}")

        try:
            # 1. Remove existing tools
            deleted_count = await self.remove_entity(entity_path)
            if deleted_count and deleted_count.get('deleted_tools', 0) > 0:
                logger.info(f"Removed {deleted_count['deleted_tools']} old tools")

            # 2. Create new tools from entity info
            tools = await asyncio.to_thread(
                McpTool.create_tools_from_server_info,
                service_path=entity_path,
                server_info=entity_info,
                is_enabled=is_enabled
            )

            # 3. Bulk save
            result = await asyncio.to_thread(
                self._mcp_tools.bulk_save,
                tools
            )

            logger.info(f"Indexed {result.successful}/{result.total} tools for '{entity_path}' "
                        f"(success rate: {result.success_rate:.1f}%)")

            if result.has_errors:
                logger.warning(f"{result.failed} tools failed to index:")
                for error in result.errors[:3]:
                    logger.warning(f"   - {error.get('message', 'unknown')}")

            return {
                "indexed_tools": result.successful,
                "failed_tools": result.failed
            }

        except Exception as e:
            logger.error(f"Full update failed for '{entity_path}': {e}", exc_info=True)
            return None

    async def remove_entity(
            self,
            entity_path: str
    ) -> Optional[Dict[str, int]]:
        """
        Remove all tools for an entity.
        
        Args:
            entity_path: Entity path identifier
            
        Returns:
            {"deleted_tools": count} or None if unavailable
        """
        if not self.is_available():
            logger.warning(f"Search index unavailable, skipping removal for '{entity_path}'")
            return None

        try:
            filters = {"server_path": entity_path}
            deleted_count = await asyncio.to_thread(
                self._mcp_tools.delete_by_filter,
                filters
            )
            logger.info(f"Removed {deleted_count} tools for '{entity_path}'")
            return {"deleted_tools": deleted_count}

        except Exception as e:
            logger.error(f"Removal failed for '{entity_path}': {e}", exc_info=True)
            return None

    def _compare_tools(
            self,
            old_tools: List[McpTool],
            new_tool_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compare old and new tools to determine changes.
        
        Args:
            old_tools: Existing McpTool instances
            new_tool_list: New tool definitions
            
        Returns:
            Dictionary with:
            - to_delete: List of tool names to delete
            - to_add: List of tool dicts to add
            - to_update: List of tool dicts to update (description changed)
        """
        old_map = {t.tool_name: t for t in old_tools}
        # Safe extraction of tool names, with logging for skipped tools
        new_map: Dict[str, Dict[str, Any]] = {}
        for tool_def in new_tool_list:
            name = tool_def.get("name")
            if not name:
                logger.warning("Skipping tool definition without a 'name' field: %s", tool_def)
                continue
            new_map[name] = tool_def

        # Find differences
        to_delete = [name for name in old_map if name not in new_map]
        to_add = [t for name, t in new_map.items() if name not in old_map]

        # Check if descriptions changed
        to_update = []
        for name, new_tool in new_map.items():
            if name in old_map:
                old_tool = old_map[name]
                new_desc = new_tool.get("description", "")
                # Check if description changed (this triggers re-vectorization)
                if old_tool.description_main != new_desc:
                    to_update.append(new_tool)

        return {
            "to_delete": to_delete,
            "to_add": to_add,
            "to_update": to_update
        }

    async def update_entity_incremental(
            self,
            entity_path: str,
            entity_info: Dict[str, Any],
            entity_type: str = "mcp_server",
            is_enabled: bool = True
    ) -> Optional[Dict[str, int]]:
        """
        Incrementally update entity (only process changed tools).
        
        Most efficient method for partial updates:
        - Only vectorizes new or changed tools
        - Deletes removed tools
        - Preserves unchanged tools
        
        Args:
            entity_path: Entity path identifier
            entity_info: Complete entity information with tool_list
            entity_type: Entity type
            is_enabled: Enabled status
            
        Returns:
            {"added": count, "updated": count, "deleted": count} or None
        """
        if not self.is_available():
            logger.warning(f"Search index unavailable, skipping incremental update for '{entity_path}'")
            return None

        try:
            # 1. Get existing tools (sync operation in thread pool)
            old_tools = await asyncio.to_thread(
                self._mcp_tools.filter,
                filters={"server_path": entity_path},
                limit=1000
            )

            # 2. Compare with new tool list
            new_tool_list = entity_info.get("tool_list", [])
            changes = self._compare_tools(old_tools, new_tool_list)

            added_count = 0
            updated_count = 0
            deleted_count = 0

            # 3. Delete removed tools
            if changes["to_delete"]:
                tool_ids_to_delete = []
                for tool_name in changes["to_delete"]:
                    old_tool = next((t for t in old_tools if t.tool_name == tool_name), None)
                    if old_tool:
                        tool_ids_to_delete.append(old_tool.id)

                # Batch delete in thread pool
                for tool_id in tool_ids_to_delete:
                    deleted = await asyncio.to_thread(self._mcp_tools.delete, tool_id)
                    if deleted:
                        deleted_count += 1
                logger.info(f"Deleted {deleted_count} tools from '{entity_path}'")

            # 4. Add new tools
            if changes["to_add"]:
                # Create temporary entity info with only new tools
                temp_info = {**entity_info, "tool_list": changes["to_add"]}

                # Create tools in thread pool
                new_tools = await asyncio.to_thread(
                    McpTool.create_tools_from_server_info,
                    service_path=entity_path,
                    server_info=temp_info,
                    is_enabled=is_enabled
                )

                # Bulk save in thread pool
                result = await asyncio.to_thread(self._mcp_tools.bulk_save, new_tools)
                added_count = result.successful
                logger.info(f"Added {added_count} new tools to '{entity_path}'")

            # 5. Update changed tools (re-vectorize)
            if changes["to_update"]:
                # Delete old versions
                for tool_dict in changes["to_update"]:
                    tool_name = tool_dict.get("name")
                    if not tool_name:
                        continue
                    old_tool = next((t for t in old_tools if t.tool_name == tool_name), None)
                    if old_tool:
                        await asyncio.to_thread(self._mcp_tools.delete, old_tool.id)

                # Create new versions with updated descriptions
                temp_info = {**entity_info, "tool_list": changes["to_update"]}

                # Create tools in thread pool
                updated_tools = await asyncio.to_thread(
                    McpTool.create_tools_from_server_info,
                    service_path=entity_path,
                    server_info=temp_info,
                    is_enabled=is_enabled
                )

                # Bulk save in thread pool
                result = await asyncio.to_thread(self._mcp_tools.bulk_save, updated_tools)
                updated_count = result.successful
                logger.info(f"Updated {updated_count} tools in '{entity_path}'")

            logger.info(f"Incremental update for '{entity_path}': "
                        f"+{added_count}, ~{updated_count}, -{deleted_count}")

            return {
                "added_tools": added_count,
                "updated_tools": updated_count,
                "deleted_tools": deleted_count
            }

        except Exception as e:
            logger.error(f"Incremental update failed for '{entity_path}': {e}", exc_info=True)
            # Fallback to full update on error
            logger.info(f"Falling back to full update for '{entity_path}'")
            return await self.add_or_update_entity(entity_path, entity_info, entity_type, is_enabled)

    async def cleanup(self):
        """Cleanup resources and close database connection."""
        logger.info("Cleaning up SearchIndexManager")

        if self._initialized and self._client:
            try:
                await asyncio.to_thread(self._client.close)
                logger.info("Database connection closed")
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

        self._client = None
        self._mcp_tools = None
        self._initialized = False
        logger.info("SearchIndexManager cleanup complete")


_manager_instance: Optional[SearchIndexManager] = None


def get_search_index_manager() -> SearchIndexManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = SearchIndexManager()
    return _manager_instance
