"""
MCP Server Specialized Repository

Contains MCP Server-specific vector database operations
that don't belong in the generic Repository class.
"""

import logging
from typing import Optional, Dict
from packages.models import ExtendedMCPServer
from packages.vector.repository import Repository
from packages.vector.client import DatabaseClient, initialize_database

logger = logging.getLogger(__name__)


class MCPServerRepository(Repository[ExtendedMCPServer]):
    """
    Specialized repository for MCP Server operations.

    Extends generic Repository with MCP-specific methods like
    sync_server_to_vector_db() that shouldn't be in the base class.
    """

    def __init__(self, db_client: DatabaseClient):
        """
        Initialize MCP Server repository.

        Args:
            db_client: Database client instance
        """
        super().__init__(db_client, ExtendedMCPServer)
        logger.info("MCPServerRepository initialized")

    async def sync_server_to_vector_db(
            self,
            server: ExtendedMCPServer,
            is_delete: bool = True,
    ) -> Optional[Dict[str, int]]:
        """
        Full rebuild: delete old server and recreate from server object.

        Uses server_id as primary identifier if available, falls back to path.
        This method is mainly used for initial sync from MongoDB to Weaviate.

        Args:
            server: ExtendedMCPServer object from MongoDB
            is_delete: Whether to delete old server records before saving

        Returns:
            {"indexed_tools": count, "failed_tools": count, "deleted": count}
        """
        try:
            # 1. Extract identifiers from server object
            server_id = str(server.id) if server.id else None
            server_name = server.serverName

            # 2. Delete old server records if requested
            deleted = 0
            if is_delete and server_id:
                deleted = await self.adelete_by_filter({"server_id": server_id})
                if deleted > 0:
                    logger.info(f"Deleted {deleted} old record(s) by server_id: {server_id}")

            # 3. Save server object to vector database
            doc_id = await self.asave(server)
            success = doc_id is not None

            logger.info(
                f"Indexed server '{server_name}' (server_id: {server_id}): "
                f"{'success' if success else 'failed'}"
            )

            return {
                "indexed_tools": 1 if success else 0,
                "failed_tools": 0 if success else 1,
                "deleted": deleted
            }

        except Exception as e:
            logger.error(f"Full sync failed for server {server.serverName}: {e}", exc_info=True)
            return None

    async def get_by_server_id(self, server_id: str) -> Optional[ExtendedMCPServer]:
        """
        Get server by MongoDB server_id (stored in metadata).

        Args:
            server_id: MongoDB _id as string

        Returns:
            ExtendedMCPServer instance if found, None otherwise
        """
        try:
            results = await self.afilter(
                filters={"server_id": server_id},
                limit=1
            )
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Get by server_id failed: {e}")
            return None

    async def get_by_path(self, path: str) -> Optional[ExtendedMCPServer]:
        """
        Get server by path.

        Args:
            path: Server path (e.g., /github)

        Returns:
            ExtendedMCPServer instance if found, None otherwise
        """
        try:
            results = await self.afilter(
                filters={"path": path},
                limit=1
            )
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Get by path failed: {e}")
            return None

    async def update_server_smart(
            self,
            server: ExtendedMCPServer,
            fields_changed: Optional[set] = None
    ) -> bool:
        """
        Smart update that auto-detects content vs metadata changes.

        Args:
            server: Updated server instance
            fields_changed: Set of field names that changed (optional)

        Returns:
            True if updated successfully
        """
        return await self.aupdate(server, fields_changed=fields_changed)


def create_mcp_server_repository(db_client: DatabaseClient) -> MCPServerRepository:
    """
    Factory function to create MCP Server repository.

    Args:
        db_client: Database client instance

    Returns:
        MCPServerRepository instance
    """
    return MCPServerRepository(db_client)


_mcp_server_repo = None


def get_mcp_server_repo():
    """Lazy initialization of MCP Server repository."""
    global _mcp_server_repo
    if _mcp_server_repo is None:
        _mcp_server_repo = create_mcp_server_repository(initialize_database())
    return _mcp_server_repo
