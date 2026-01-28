#!/usr/bin/env python3
"""
MongoDB to Weaviate Sync Script for MCP Gateway Registry

This script synchronizes MCP servers from MongoDB to Weaviate.
It reads all servers from MongoDB using server_service_v1 and imports them
into Weaviate for semantic search. Already existing servers are skipped.

Usage:
    uv run python scripts/sync_mongo_to_weaviate.py [--clean] [--batch-size N]
    
Options:
    --clean: Delete all existing servers from Weaviate before syncing
    --batch-size N: Number of servers to process per batch (default: 100)
"""
import traceback
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.database.mongodb import MongoDB
from packages.models.extended_mcp_server import ExtendedMCPServer
from registry.services.server_service_v1 import server_service_v1
from packages.vector.repositories.mcp_server_repository import get_mcp_server_repo

mcp_server_repo = get_mcp_server_repo()


class SyncStats:
    """Statistics tracker for sync operation."""

    def __init__(self):
        self.total_servers = 0
        self.servers_with_tools = 0
        self.servers_without_tools = 0
        self.total_tools = 0
        self.tools_imported = 0
        self.tools_skipped = 0
        self.tools_failed = 0
        self.servers_processed: List[Dict[str, Any]] = []
        self.errors: List[str] = []

    def add_server(self, server_name: str, server_path: str, tool_count: int, imported: int, skipped: int, failed: int):
        """Record server processing stats."""
        self.servers_processed.append({
            'name': server_name,
            'path': server_path,
            'total_tools': tool_count,
            'imported': imported,
            'skipped': skipped,
            'failed': failed
        })

    def add_error(self, error: str):
        """Record an error."""
        self.errors.append(error)

    def print_summary(self):
        """Print comprehensive summary."""
        print("\n" + "=" * 80)
        print("SYNC SUMMARY")
        print("=" * 80)
        print(f"Total Servers Scanned:      {self.total_servers}")
        print(f"Servers Imported:           {self.servers_with_tools}")
        print(f"Servers Skipped:            {self.servers_without_tools}")
        print(f"\nTotal Servers:              {self.total_tools}")
        print(f"Servers Imported:           {self.tools_imported} ✓")
        print(f"Servers Skipped (existing): {self.tools_skipped}")
        print(f"Servers Failed:             {self.tools_failed} ✗")

        if self.servers_processed:
            print(f"\n{'-' * 80}")
            print("PER-SERVER BREAKDOWN:")
            print(f"{'-' * 80}")
            for server in self.servers_processed:
                status = "✓" if server['imported'] > 0 else "○"
                print(f"{status} {server['name']:<30} ({server['path']:<20})")
                print(
                    f"  Imported: {server['imported']:>3} | Skipped: {server['skipped']:>3} | Failed: {server['failed']:>3}")

        if self.errors:
            print(f"\n{'-' * 80}")
            print(f"ERRORS ({len(self.errors)}):")
            print(f"{'-' * 80}")
            for error in self.errors:
                print(f"✗ {error}")

        print("=" * 80)

        # Success summary
        success_rate = (self.tools_imported / self.total_tools * 100) if self.total_tools > 0 else 0
        if self.tools_failed == 0 and self.total_tools > 0:
            print(f"✓ SUCCESS: All {self.total_tools} servers processed successfully!")
        elif self.tools_imported > 0:
            print(f"⚠ PARTIAL SUCCESS: {self.tools_imported}/{self.total_tools} servers imported ({success_rate:.1f}%)")
        else:
            print("✗ FAILED: No servers were imported")
        print("=" * 80 + "\n")


async def check_server_exists(server_id: str) -> bool:
    """
    Check if server already exists in Weaviate.
    
    Args:
        server_id: Server document ID (MongoDB _id)
        
    Returns:
        True if server exists in Weaviate
    """
    try:
        existing = await mcp_server_repo.get_by_server_id(server_id)
        return existing is not None
    except Exception as e:
        print(f"  Warning: Failed to check existence for server {server_id}: {e}")
        return False


async def sync_server(server: Any, stats: SyncStats):
    """
    Sync a single server to Weaviate.
    """
    server_name = server.serverName
    server_path = server.path
    server_id = str(server.id)

    print(f"Processing: {server_name} ({server_path}) [ID: {server_id}]")

    try:
        # Check if server already exists (by server_id)
        exists = await check_server_exists(server_id)

        if exists:
            print(f"  ○ Server already exists, skipping...")
            stats.servers_without_tools += 1
            stats.tools_skipped += 1
            stats.add_server(server_name, server_path, 1, 0, 1, 0)
            return

        # Count tools for stats
        num_tools = server.numTools if hasattr(server, 'numTools') else 0
        print(f"  Server has {num_tools} tools")
        stats.servers_with_tools += 1
        stats.total_tools += 1  # Count servers, not individual tools

        result = await mcp_server_repo.sync_server_to_vector_db(
            server=server,
            is_delete=False  # No need to delete, we already checked existence
        )

        if result and result.get("indexed_tools", 0) > 0:
            print(f"  ✓ Successfully imported server")
            stats.tools_imported += 1
            stats.add_server(server_name, server_path, 1, 1, 0, 0)
        else:
            error_msg = f"{server_name}: Failed to import server"
            print(f"  ✗ {error_msg}")
            stats.add_error(error_msg)
            stats.tools_failed += 1
            stats.add_server(server_name, server_path, 1, 0, 0, 1)

    except Exception as e:
        error_msg = f"Unexpected error processing {server_name}: {e}"
        print(f"  ✗ {error_msg}")
        stats.add_error(error_msg)
        stats.total_tools += 1
        stats.tools_failed += 1
        stats.add_server(server_name, server_path, 1, 0, 0, 1)


async def clean_weaviate():
    """Delete all existing servers from Weaviate using specialized repository."""
    print("Deleting all existing servers...")
    try:
        # Use specialized repository
        deleted = await mcp_server_repo.adelete_by_filter(
            filters={"collection": ExtendedMCPServer.COLLECTION_NAME}
        )
        print(f"✓ Deleted {deleted} servers from Weaviate")
        print("=" * 80 + "\n")
        return deleted
    except Exception as e:
        print(f"✗ Error cleaning Weaviate: {e}")
        traceback.print_exc()
        return 0


async def sync_all_servers(batch_size: int = 100):
    stats = SyncStats()
    print("\n" + "=" * 80)
    print("MONGODB TO WEAVIATE SYNC")
    print("=" * 80)
    print(f"Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Batch size: {batch_size} servers per batch")
    print("=" * 80)

    try:
        # First, get total count
        print("\nFetching server count from MongoDB...")
        _, total = await server_service_v1.list_servers(page=1, per_page=1)

        print(f"Found {total} servers in MongoDB")

        if total == 0:
            print("\n  No servers found in MongoDB. Nothing to sync.")
            return stats

        # Calculate total pages
        total_pages = (total + batch_size - 1) // batch_size  # Ceiling division
        print(f"Will process in {total_pages} batch(es)\n")

        # Process servers in batches
        processed_count = 0

        for page in range(1, total_pages + 1):
            print(f"\n{'─' * 80}")
            print(
                f"BATCH {page}/{total_pages} (Servers {processed_count + 1}-{min(processed_count + batch_size, total)})")
            print(f"{'─' * 80}")

            # Fetch current batch
            servers, _ = await server_service_v1.list_servers(
                page=page,
                per_page=batch_size
            )

            if not servers:
                print(f"  No servers returned for page {page}, stopping...")
                break

            # Process each server in the batch
            for server in servers:
                processed_count += 1
                stats.total_servers = processed_count

                print(f"\n[{processed_count}/{total}] ", end="")
                await sync_server(server, stats)

            print(f"\n{'─' * 80}")
            print(
                f"Batch {page} completed. Progress: {processed_count}/{total} servers ({processed_count / total * 100:.1f}%)")
            print(f"{'─' * 80}")

        return stats

    except Exception as e:
        print(f"\n✗ Fatal error during sync: {e}")
        traceback.print_exc()
        stats.add_error(f"Fatal error: {e}")
        return stats


async def main():
    """Main entry point."""
    # Parse command line arguments
    clean_mode = "--clean" in sys.argv

    # Parse batch size
    batch_size = 100  # Default
    for i, arg in enumerate(sys.argv):
        if arg == "--batch-size" and i + 1 < len(sys.argv):
            try:
                batch_size = int(sys.argv[i + 1])
                if batch_size < 1:
                    print(" Error: batch-size must be at least 1")
                    sys.exit(1)
            except ValueError:
                print(f" Error: Invalid batch-size value: {sys.argv[i + 1]}")
                sys.exit(1)

    # Get MongoDB connection details from environment
    mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/jarvis")

    # Parse database name from URI
    db_name = None
    uri_without_scheme = mongo_uri.split("://")[-1]
    if '/' in uri_without_scheme:
        uri_path = uri_without_scheme
        if '/' in uri_path:
            db_name = uri_path.split('/')[-1].split('?')[0]

    if not db_name:
        db_name = "jarvis"

    print(f"Connecting to MongoDB at {mongo_uri}...")
    print(f"Database: {db_name}")
    print(f"Mode: {'CLEAN + SYNC' if clean_mode else 'SYNC ONLY'}")
    print(f"Batch size: {batch_size}\n")

    try:
        # Connect to MongoDB
        await MongoDB.connect_db(db_name=db_name)
        print(" Connected to MongoDB successfully!")

        # Initialize Weaviate (already initialized via mcp_tool_search_index_manager)
        print(" Connected to Weaviate successfully!\n")

        # Clean Weaviate if requested
        if clean_mode:
            await clean_weaviate()

        # Sync all servers
        stats = await sync_all_servers(batch_size=batch_size)

        # Print summary
        stats.print_summary()

        # Exit with appropriate code
        if stats.tools_failed > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print(f"\n Fatal Error: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Close connections
        await MongoDB.close_db()
        print("\nConnections closed.")


def cli():
    """CLI entry point for script execution."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
