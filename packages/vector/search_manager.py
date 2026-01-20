import asyncio
import logging
from typing import Dict, Any, Optional
from packages.vector import initialize_database
from packages.models.mcp_tool import McpTool
from packages.vector.repository import Repository

logger = logging.getLogger(__name__)


class SearchIndexManager:
    """
    Manager for search index operations.
    """

    def __init__(self, db_client=None):
        """
        Initialize search index manager.
        
        Args:
            db_client: Optional database client for dependency injection
        """
        self._client = db_client or initialize_database()
        self.tools = Repository(self._client, McpTool)
        logger.info("SearchIndexManager initialized")

    async def sync_full(
            self,
            entity_path: str,
            entity_info: Dict[str, Any],
            is_enabled: bool = True
    ) -> Optional[Dict[str, int]]:
        """
        Full rebuild: delete all old tools and recreate from entity_info.

        Args:
            entity_path: Entity path identifier
            entity_info: Entity info with tool_list
            is_enabled: Whether tools are enabled
            
        Returns:
            {"indexed_tools": count, "failed_tools": count}
        """
        try:
            # 1. Delete old tools
            deleted = await self.tools.adelete_by_filter({"server_path": entity_path})
            if deleted > 0:
                logger.info(f"Deleted {deleted} old tools from '{entity_path}'")

            # 2. Create new tools
            tools = await asyncio.to_thread(
                McpTool.create_tools_from_server_info,
                service_path=entity_path,
                server_info=entity_info,
                is_enabled=is_enabled
            )

            # 3. Bulk save
            result = await self.tools.abulk_save(tools)
            logger.info(
                f"Indexed {result.successful}/{result.total} tools for '{entity_path}' "
                f"(success rate: {result.success_rate:.1f}%)"
            )

            return {
                "indexed_tools": result.successful,
                "failed_tools": result.failed
            }

        except Exception as e:
            logger.error(f"Full sync failed for '{entity_path}': {e}", exc_info=True)
            return None

    async def sync_incremental(
            self,
            entity_path: str,
            entity_info: Dict[str, Any],
            is_enabled: bool = True
    ) -> Optional[Dict[str, int]]:
        """
        Incremental update: only re-vectorize changed tools (most efficient).
        
        Compares new tools with existing ones:
        - Adds new tools
        - Updates tools with changed descriptions
        - Deletes removed tools
        - Preserves unchanged tools
        
        Args:
            entity_path: Entity path identifier
            entity_info: Entity info with tool_list
            is_enabled: Whether tools are enabled
            
        Returns:
            {"added_tools": count, "updated_tools": count, "deleted_tools": count}
        """
        try:
            # 1. Get existing tools
            old_tools = await self.tools.afilter(
                filters={"server_path": entity_path},
                limit=1000
            )

            # 2. Compare changes (use McpTool's comparison logic)
            new_tool_list = entity_info.get("tool_list", [])
            changes = McpTool.compare_tools(old_tools, new_tool_list)

            added_count = 0
            updated_count = 0
            deleted_count = 0

            # 3. Delete removed tools
            if changes["to_delete"]:
                for tool_name in changes["to_delete"]:
                    old_tool = next((t for t in old_tools if t.tool_name == tool_name), None)
                    if old_tool and await self.tools.adelete(old_tool.id):
                        deleted_count += 1
                logger.info(f"Deleted {deleted_count} tools")

            # 4. Add new tools
            if changes["to_add"]:
                new_tools = await asyncio.to_thread(
                    McpTool.create_tools_from_server_info,
                    service_path=entity_path,
                    server_info={**entity_info, "tool_list": changes["to_add"]},
                    is_enabled=is_enabled
                )
                result = await self.tools.abulk_save(new_tools)
                added_count = result.successful
                logger.info(f"Added {added_count} new tools")

            # 5. Update changed tools (delete old, create new)
            if changes["to_update"]:
                for tool_dict in changes["to_update"]:
                    tool_name = tool_dict.get("name")
                    if tool_name:
                        old_tool = next((t for t in old_tools if t.tool_name == tool_name), None)
                        if old_tool:
                            await self.tools.adelete(old_tool.id)

                updated_tools = await asyncio.to_thread(
                    McpTool.create_tools_from_server_info,
                    service_path=entity_path,
                    server_info={**entity_info, "tool_list": changes["to_update"]},
                    is_enabled=is_enabled
                )
                result = await self.tools.abulk_save(updated_tools)
                updated_count = result.successful
                logger.info(f"Updated {updated_count} tools")

            logger.info(
                f"Incremental sync '{entity_path}': "
                f"+{added_count}, ~{updated_count}, -{deleted_count}"
            )

            return {
                "added_tools": added_count,
                "updated_tools": updated_count,
                "deleted_tools": deleted_count
            }

        except Exception as e:
            logger.error(f"Incremental sync failed for '{entity_path}': {e}", exc_info=True)
            logger.info(f"Falling back to full sync")
            return await self.sync_full(entity_path, entity_info, is_enabled)


_manager_instance: Optional[SearchIndexManager] = None


def get_search_index_manager() -> SearchIndexManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = SearchIndexManager()
    return _manager_instance
