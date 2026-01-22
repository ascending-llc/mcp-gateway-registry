#!/usr/bin/env python3
"""
MongoDB to Weaviate Sync Script for MCP Gateway Registry

This script synchronizes MCP servers and their tools from MongoDB to Weaviate.
It reads all servers from MongoDB using server_service_v1, extracts their tools,
and bulk imports them into Weaviate. Already existing tools are skipped.

Usage:
    uv run  python scripts/sync_mongo_to_weaviate.py [--clean] [--batch-size N]
    
Options:
    --clean: Delete all existing tools from Weaviate before syncing
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
from packages.models.mcp_tool import McpTool
from packages.vector.search_manager import mcp_tool_search_index_manager
from registry.services.server_service_v1 import server_service_v1


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
        print(f"Servers With Tools:         {self.servers_with_tools}")
        print(f"Servers Without Tools:      {self.servers_without_tools} (skipped)")
        print(f"\nTotal Tools:                {self.total_tools}")
        print(f"Tools Imported:             {self.tools_imported} ")
        print(f"Tools Skipped (existing):   {self.tools_skipped}")
        print(f"Tools Failed:               {self.tools_failed} ✗")

        if self.servers_processed:
            print(f"\n{'-' * 80}")
            print("PER-SERVER BREAKDOWN:")
            print(f"{'-' * 80}")
            for server in self.servers_processed:
                status = "" if server['imported'] > 0 else "○"
                print(f"{status} {server['name']:<30} ({server['path']:<20})")
                print(f"  Total: {server['total_tools']:>3} | Imported: {server['imported']:>3} |"
                      f"  Skipped: {server['skipped']:>3} | Failed: {server['failed']:>3}")

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
            print(f" SUCCESS: All {self.total_tools} tools processed successfully!")
        elif self.tools_imported > 0:
            print(f"  PARTIAL SUCCESS: {self.tools_imported}/{self.total_tools} tools imported ({success_rate:.1f}%)")
        else:
            print(" FAILED: No tools were imported")
        print("=" * 80 + "\n")


async def check_tool_exists(tool: McpTool) -> bool:
    try:
        # Query by server_path and tool_name (unique combination)
        existing_tools = await mcp_tool_search_index_manager.repository.afilter(
            filters={
                "server_path": tool.server_path,
                "tool_name": tool.tool_name
            },
            limit=1
        )
        return len(existing_tools) > 0
    except Exception as e:
        print(f"  Warning: Failed to check existence for {tool.tool_name}: {e}")
        return False


async def sync_server_tools(server, stats: SyncStats):
    server_name = server.serverName
    server_path = server.path

    print(f"Processing: {server_name} ({server_path})")
    try:
        # Convert server document to server_info format
        server_info = McpTool.from_server_document(server)

        # Get tool_list from server_info
        tool_list = server_info.get("tool_list", [])

        if not tool_list:
            print(f"  No tools found, skipping...")
            stats.servers_without_tools += 1
            stats.add_server(server_name, server_path, 0, 0, 0, 0)
            return

        print(f"  Found {len(tool_list)} tools")
        stats.servers_with_tools += 1
        stats.total_tools += len(tool_list)

        # Create McpTool instances
        try:
            tools = McpTool.create_tools_from_server_info(
                service_path=server_path,
                server_info=server_info,
                is_enabled=server_info.get("is_enabled", True)
            )
        except Exception as e:
            error_msg = f"Failed to create tools for {server_name}: {e}"
            print(f"  ✗ {error_msg}")
            stats.add_error(error_msg)
            stats.tools_failed += len(tool_list)
            stats.add_server(server_name, server_path, len(tool_list), 0, 0, len(tool_list))
            return

        # Filter out existing tools
        tools_to_import = []
        skipped_count = 0

        for tool in tools:
            exists = await check_tool_exists(tool)
            if exists:
                skipped_count += 1
                stats.tools_skipped += 1
            else:
                tools_to_import.append(tool)

        if tools_to_import:
            print(f"  Importing {len(tools_to_import)} new tools...")

            # Bulk save to Weaviate
            result = await mcp_tool_search_index_manager.repository.abulk_save(tools_to_import)

            stats.tools_imported += result.successful
            stats.tools_failed += result.failed

            if result.failed > 0:
                error_msg = f"{server_name}: {result.failed}/{len(tools_to_import)} tools failed to import"
                print(f"   {error_msg}")
                stats.add_error(error_msg)
            else:
                print(f"   Successfully imported {result.successful} tools")
        else:
            print(f"  ○ All {skipped_count} tools already exist, skipping...")

        # Record stats for this server
        failed_count = len(tool_list) - len(tools_to_import) - skipped_count if len(tool_list) >= len(tools_to_import) + skipped_count else 0
        stats.add_server(
            server_name,
            server_path,
            len(tool_list),
            len(tools_to_import) - failed_count if tools_to_import else 0,
            skipped_count,
            failed_count
        )

    except Exception as e:
        error_msg = f"Unexpected error processing {server_name}: {e}"
        print(f"  ✗ {error_msg}")
        stats.add_error(error_msg)
        # Try to estimate tool count from config if available
        tool_count = server.numTools if hasattr(server, 'numTools') else 0
        stats.total_tools += tool_count
        stats.tools_failed += tool_count
        stats.add_server(server_name, server_path, tool_count, 0, 0, tool_count)


async def clean_weaviate():
    print("Deleting all existing tools...")
    try:
        # Delete all tools (filter by collection name)
        deleted = await mcp_tool_search_index_manager.repository.adelete_by_filter(
            filters={"collection": McpTool.COLLECTION_NAME}
        )
        print(f" Deleted {deleted} tools from Weaviate")
        print("=" * 80 + "\n")
        return deleted
    except Exception as e:
        print(f"✗ Error cleaning Weaviate: {e}")
        print("=" * 80 + "\n")
        raise


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
            print(f"BATCH {page}/{total_pages} (Servers {processed_count + 1}-{min(processed_count + batch_size, total)})")
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
                await sync_server_tools(server, stats)

            print(f"\n{'─' * 80}")
            print(f"Batch {page} completed. Progress: {processed_count}/{total} servers ({processed_count/total*100:.1f}%)")
            print(f"{'─' * 80}")

        return stats

    except Exception as e:
        print(f"\n✗ Fatal error during sync: {e}")
        import traceback
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
    if '/' in mongo_uri.split('://')[-1]:
        uri_path = mongo_uri.split('://')[-1]
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


if __name__ == "__main__":
    asyncio.run(main())
