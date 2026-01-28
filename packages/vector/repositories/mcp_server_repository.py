"""
MCP Server Specialized Repository

Contains MCP Server-specific vector database operations
that don't belong in the generic Repository class.
"""

import logging
from typing import Optional, Dict, Set
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
    
    def ensure_collection(self) -> bool:
        """
        Ensure the collection exists in vector database.
        """
        try:
            # Check if collection exists
            if self.adapter.collection_exists(self.collection):
                logger.info(f"Collection '{self.collection}' already exists")
                return True
            
            logger.info(f"Creating collection '{self.collection}'...")
            store = self.adapter.get_vector_store(self.collection)
            
            if store:
                logger.info(f"Collection '{self.collection}' created successfully")
                return True
            else:
                logger.error(f"Failed to create collection '{self.collection}'")
                return False
        except Exception as e:
            logger.error(f"Error ensuring collection '{self.collection}': {e}", exc_info=True)
            raise

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

    async def sync_by_enabled_status(
            self,
            server: ExtendedMCPServer,
            enabled: bool,
            fields_changed: Optional[Set[str]] = None
    ) -> bool:
        """
        Sync server to vector DB based on enabled status.
        
        This is the centralized method for all vector DB sync operations.
        
        - If enabled=True: Upsert to vector DB (create if missing, update if exists)
        - If enabled=False: Delete from vector DB

        Args:
            server: Server instance
            enabled: Whether server is enabled
            fields_changed: Set of changed field names (for optimization)

        Returns:
            True if sync successful, False otherwise
        """
        server_id = str(server.id)
        server_name = server.serverName
        
        try:
            if enabled:
                # Server enabled: Upsert to vector DB
                logger.info(f"Syncing enabled server '{server_name}' (ID: {server_id}) to vector DB")
                success = await self.aupsert(
                    instance=server,
                    fields_changed=fields_changed
                )
                if success:
                    logger.info(f"Successfully synced server '{server_name}' (ID: {server_id}) to vector DB")
                else:
                    logger.warning(f"Failed to sync server '{server_name}' (ID: {server_id}) to vector DB")
                return success
            else:
                # Server disabled: Delete from vector DB
                logger.info(f"Removing disabled server '{server_name}' (ID: {server_id}) from vector DB")
                deleted_count = await self.adelete_by_filter(
                    filters={"server_id": server_id}
                )
                if deleted_count > 0:
                    logger.info(f"Successfully removed server '{server_name}' (ID: {server_id}) from vector DB (deleted {deleted_count} records)")
                    return True
                else:
                    logger.debug(f"Server '{server_name}' (ID: {server_id}) not found in vector DB, nothing to delete")
                    return True  # Not an error if already gone
                    
        except Exception as e:
            logger.error(f"Vector DB sync failed for server '{server_name}' (ID: {server_id}): {e}", exc_info=True)
            return False

    async def delete_by_server_id(
            self,
            server_id: str,
            server_name: Optional[str] = None
    ) -> bool:
        """
        Delete server from vector DB by MongoDB server ID.
        
        This is a convenience method for delete operations.

        Args:
            server_id: MongoDB server ID
            server_name: Server name (optional, for better logging)

        Returns:
            True if deletion successful, False otherwise
        """
        log_name = f"'{server_name}' (ID: {server_id})" if server_name else f"ID: {server_id}"
        try:
            logger.info(f"Removing server {log_name} from vector DB")
            deleted_count = await self.adelete_by_filter(
                filters={"server_id": server_id}
            )
            if deleted_count > 0:
                logger.info(f"Successfully removed server {log_name} from vector DB (deleted {deleted_count} records)")
                return True
            else:
                logger.debug(f"Server {log_name} not found in vector DB")
                return True
                
        except Exception as e:
            logger.error(f"Failed to remove server {log_name} from vector DB: {e}", exc_info=True)
            return False


def create_mcp_server_repository(db_client: DatabaseClient) -> MCPServerRepository:
    """
    Factory function to create MCP Server repository.
    """
    repo = MCPServerRepository(db_client)
    repo.ensure_collection()
    return repo


_mcp_server_repo = None


def get_mcp_server_repo():
    """Lazy initialization of MCP Server repository."""
    global _mcp_server_repo
    if _mcp_server_repo is None:
        _mcp_server_repo = create_mcp_server_repository(initialize_database())
    return _mcp_server_repo
