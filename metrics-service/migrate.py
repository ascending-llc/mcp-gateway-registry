#!/usr/bin/env python3
"""Migration management CLI for metrics service."""
import asyncio
import sys
import argparse
import json
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.storage.migrations import migration_manager
from app.storage.database import wait_for_database


async def cmd_status():
    """Show migration status."""
    print("Checking migration status...")
    
    try:
        await wait_for_database()
        status = await migration_manager.get_migration_status()
        
        print(f"\nDatabase Migration Status:")
        print(f"  Current Version: {status['current_version']}")
        print(f"  Latest Version:  {status['latest_version']}")
        print(f"  Applied:         {status['applied_count']} migrations")
        print(f"  Pending:         {status['pending_count']} migrations")
        
        if status['applied_migrations']:
            print(f"\nApplied Migrations:")
            for migration in status['applied_migrations']:
                print(f"  {migration['version']:04d}: {migration['name']} (applied {migration['applied_at']})")
        
        if status['pending_migrations']:
            print(f"\nPending Migrations:")
            for migration in status['pending_migrations']:
                print(f"  {migration['version']:04d}: {migration['name']}")
        else:
            print("\n✅ Database schema is up to date!")
            
    except Exception as e:
        print(f"❌ Error checking migration status: {e}")
        sys.exit(1)


async def cmd_up(target_version: int = None):
    """Apply pending migrations."""
    print("Applying migrations...")
    
    try:
        await wait_for_database()
        
        if target_version:
            print(f"Migrating to version {target_version}")
        else:
            print("Migrating to latest version")
        
        success = await migration_manager.migrate_up(target_version)
        
        if success:
            print("✅ Migrations applied successfully!")
        else:
            print("❌ Migration failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error applying migrations: {e}")
        sys.exit(1)


async def cmd_down(target_version: int):
    """Rollback migrations."""
    print(f"Rolling back to version {target_version}...")
    
    try:
        await wait_for_database()
        
        # Confirm dangerous operation
        current_version = await migration_manager.get_current_version()
        if target_version >= current_version:
            print(f"Target version {target_version} is not lower than current version {current_version}")
            return
        
        response = input(f"⚠️  This will rollback {current_version - target_version} migration(s). Continue? (y/N): ")
        if response.lower() != 'y':
            print("Rollback cancelled")
            return
        
        success = await migration_manager.migrate_down(target_version)
        
        if success:
            print("✅ Rollback completed successfully!")
        else:
            print("❌ Rollback failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error rolling back migrations: {e}")
        sys.exit(1)


async def cmd_list():
    """List all available migrations."""
    print("Available migrations:")
    
    try:
        await wait_for_database()
        applied_migrations = {m['version'] for m in await migration_manager.get_applied_migrations()}
        
        for migration in migration_manager.list_migrations():
            status = "✅" if migration.version in applied_migrations else "⏳"
            print(f"  {status} {migration.version:04d}: {migration.name}")
            
    except Exception as e:
        print(f"❌ Error listing migrations: {e}")
        sys.exit(1)


async def cmd_create(name: str):
    """Create a new migration template."""
    print(f"Creating migration: {name}")
    
    try:
        # Get current max version
        migrations = migration_manager.list_migrations()
        next_version = max(m.version for m in migrations) + 1 if migrations else 1
        
        # Create migration template
        template = f'''"""Migration {next_version:04d}: {name}"""
from app.storage.migrations import Migration

# Define your migration
migration = Migration(
    version={next_version},
    name="{name}",
    up_sql="""
        -- Migration {next_version:04d}: {name}
        -- Add your schema changes here
        
    """,
    down_sql="""
        -- Rollback for migration {next_version:04d}: {name}
        -- Add rollback statements here
        
    """
)
'''
        
        # Save to migrations directory
        migrations_dir = Path(__file__).parent / "migrations"
        migrations_dir.mkdir(exist_ok=True)
        
        migration_file = migrations_dir / f"{next_version:04d}_{name.replace(' ', '_').replace('-', '_')}.py"
        
        with open(migration_file, 'w') as f:
            f.write(template)
        
        print(f"✅ Created migration: {migration_file}")
        print(f"   Edit the file and then register it in migrations.py")
        
    except Exception as e:
        print(f"❌ Error creating migration: {e}")
        sys.exit(1)


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Database migration manager for metrics service")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show migration status')
    
    # Up command
    up_parser = subparsers.add_parser('up', help='Apply pending migrations')
    up_parser.add_argument('--to', type=int, help='Target version (default: latest)')
    
    # Down command
    down_parser = subparsers.add_parser('down', help='Rollback migrations')
    down_parser.add_argument('to', type=int, help='Target version')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all migrations')
    
    # Create command  
    create_parser = subparsers.add_parser('create', help='Create new migration')
    create_parser.add_argument('name', help='Migration name')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'status':
            await cmd_status()
        elif args.command == 'up':
            await cmd_up(args.to)
        elif args.command == 'down':
            await cmd_down(args.to)
        elif args.command == 'list':
            await cmd_list()
        elif args.command == 'create':
            await cmd_create(args.name)
        else:
            parser.print_help()
            
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())