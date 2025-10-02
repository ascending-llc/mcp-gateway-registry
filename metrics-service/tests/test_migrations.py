"""Tests for database migration system."""
import pytest
import tempfile
import os
import aiosqlite
from unittest.mock import patch, AsyncMock
from pathlib import Path

from app.storage.migrations import Migration, MigrationManager


class TestMigration:
    """Test Migration class."""
    
    def test_migration_creation(self):
        """Test creating a Migration object."""
        migration = Migration(
            version=1,
            name="test_migration",
            up_sql="CREATE TABLE test (id INTEGER);",
            down_sql="DROP TABLE test;"
        )
        
        assert migration.version == 1
        assert migration.name == "test_migration"
        assert migration.up_sql == "CREATE TABLE test (id INTEGER);"
        assert migration.down_sql == "DROP TABLE test;"
        assert str(migration) == "Migration 0001: test_migration"
    
    def test_migration_with_python_functions(self):
        """Test migration with Python functions."""
        async def python_up(db):
            pass
        
        async def python_down(db):
            pass
        
        migration = Migration(
            version=2,
            name="python_migration",
            up_sql="",
            python_up=python_up,
            python_down=python_down
        )
        
        assert migration.python_up is not None
        assert migration.python_down is not None


class TestMigrationManager:
    """Test MigrationManager class."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        os.unlink(path)
    
    @pytest.fixture
    def migration_manager(self, temp_db):
        """Create a migration manager with temp database."""
        return MigrationManager(db_path=temp_db)
    
    @pytest.mark.asyncio
    async def test_get_current_version_no_table(self, migration_manager):
        """Test getting version when migrations table doesn't exist."""
        version = await migration_manager.get_current_version()
        assert version == 0
    
    @pytest.mark.asyncio
    async def test_get_current_version_empty_table(self, migration_manager, temp_db):
        """Test getting version from empty migrations table."""
        # Create empty migrations table
        async with aiosqlite.connect(temp_db) as db:
            await db.execute("""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
            """)
            await db.commit()
        
        version = await migration_manager.get_current_version()
        assert version == 0
    
    @pytest.mark.asyncio
    async def test_get_current_version_with_data(self, migration_manager, temp_db):
        """Test getting version with existing migrations."""
        # Setup migrations table with data
        async with aiosqlite.connect(temp_db) as db:
            await db.execute("""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (1, 'initial', '2024-01-01T00:00:00')
            """)
            await db.execute("""
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (2, 'second', '2024-01-01T00:00:01')
            """)
            await db.commit()
        
        version = await migration_manager.get_current_version()
        assert version == 2
    
    @pytest.mark.asyncio
    async def test_get_applied_migrations(self, migration_manager, temp_db):
        """Test getting list of applied migrations."""
        # Setup migrations table with data
        async with aiosqlite.connect(temp_db) as db:
            await db.execute("""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (1, 'initial', '2024-01-01T00:00:00')
            """)
            await db.commit()
        
        migrations = await migration_manager.get_applied_migrations()
        
        assert len(migrations) == 1
        assert migrations[0]['version'] == 1
        assert migrations[0]['name'] == 'initial'
        assert migrations[0]['applied_at'] == '2024-01-01T00:00:00'
    
    @pytest.mark.asyncio
    async def test_apply_migration_sql_only(self, migration_manager, temp_db):
        """Test applying a SQL-only migration."""
        migration = Migration(
            version=1,
            name="test_migration",
            up_sql="""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE test_table (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                );
            """
        )
        
        success = await migration_manager.apply_migration(migration)
        assert success
        
        # Verify table was created
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='test_table'
            """)
            result = await cursor.fetchone()
            assert result is not None
        
        # Verify migration was recorded
        version = await migration_manager.get_current_version()
        assert version == 1
    
    @pytest.mark.asyncio
    async def test_apply_migration_with_python(self, migration_manager, temp_db):
        """Test applying migration with Python function."""
        python_executed = False
        
        async def python_migration(db):
            nonlocal python_executed
            python_executed = True
            await db.execute("INSERT INTO test_data (value) VALUES (?)", ("test_value",))
        
        migration = Migration(
            version=1,
            name="python_migration",
            up_sql="""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE test_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    value TEXT NOT NULL
                );
            """,
            python_up=python_migration
        )
        
        success = await migration_manager.apply_migration(migration)
        assert success
        assert python_executed
        
        # Verify Python function executed
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute("SELECT value FROM test_data")
            result = await cursor.fetchone()
            assert result[0] == "test_value"
    
    @pytest.mark.asyncio
    async def test_apply_migration_failure(self, migration_manager):
        """Test migration failure handling."""
        migration = Migration(
            version=1,
            name="failing_migration",
            up_sql="INVALID SQL STATEMENT;"
        )
        
        success = await migration_manager.apply_migration(migration)
        assert not success
        
        # Verify no migration was recorded
        version = await migration_manager.get_current_version()
        assert version == 0
    
    @pytest.mark.asyncio
    async def test_rollback_migration(self, migration_manager, temp_db):
        """Test rolling back a migration."""
        # First apply a migration
        up_migration = Migration(
            version=1,
            name="test_migration",
            up_sql="""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE test_table (id INTEGER);
            """,
            down_sql="DROP TABLE test_table;"
        )
        
        await migration_manager.apply_migration(up_migration)
        assert await migration_manager.get_current_version() == 1
        
        # Now rollback
        success = await migration_manager.rollback_migration(up_migration)
        assert success
        
        # Verify table was dropped
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='test_table'
            """)
            result = await cursor.fetchone()
            assert result is None
        
        # Verify migration record was removed
        version = await migration_manager.get_current_version()
        assert version == 0
    
    def test_list_migrations(self, migration_manager):
        """Test listing all migrations."""
        migrations = migration_manager.list_migrations()
        
        # Should have the registered migrations
        assert len(migrations) >= 4  # We registered 4 migrations
        assert all(isinstance(m, Migration) for m in migrations)
        
        # Should be sorted by version
        versions = [m.version for m in migrations]
        assert versions == sorted(versions)
    
    @pytest.mark.asyncio
    async def test_migrate_up_all(self, migration_manager, temp_db):
        """Test migrating up to latest version."""
        # Mock the registered migrations with simpler ones for testing
        simple_migrations = [
            Migration(1, "first", "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT);"),
            Migration(2, "second", "CREATE TABLE table2 (id INTEGER);"),
            Migration(3, "third", "CREATE TABLE table3 (id INTEGER);")
        ]
        
        migration_manager.migrations = simple_migrations
        
        success = await migration_manager.migrate_up()
        assert success
        
        version = await migration_manager.get_current_version()
        assert version == 3
        
        # Verify all tables exist
        async with aiosqlite.connect(temp_db) as db:
            for table_name in ['schema_migrations', 'table2', 'table3']:
                cursor = await db.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                """, (table_name,))
                result = await cursor.fetchone()
                assert result is not None, f"Table {table_name} should exist"
    
    @pytest.mark.asyncio
    async def test_migrate_up_to_target(self, migration_manager, temp_db):
        """Test migrating up to specific target version."""
        simple_migrations = [
            Migration(1, "first", "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT);"),
            Migration(2, "second", "CREATE TABLE table2 (id INTEGER);"),
            Migration(3, "third", "CREATE TABLE table3 (id INTEGER);")
        ]
        
        migration_manager.migrations = simple_migrations
        
        success = await migration_manager.migrate_up(target_version=2)
        assert success
        
        version = await migration_manager.get_current_version()
        assert version == 2
        
        # Verify only first two tables exist
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='table3'
            """)
            result = await cursor.fetchone()
            assert result is None  # table3 should not exist
    
    @pytest.mark.asyncio
    async def test_migrate_up_already_current(self, migration_manager, temp_db):
        """Test migrate up when already at current version."""
        # Setup database at version 1
        async with aiosqlite.connect(temp_db) as db:
            await db.execute("""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (1, 'test', '2024-01-01T00:00:00')
            """)
            await db.commit()
        
        # Try to migrate to version 1 (current)
        success = await migration_manager.migrate_up(target_version=1)
        assert success  # Should succeed but do nothing
    
    @pytest.mark.asyncio
    async def test_migrate_down(self, migration_manager, temp_db):
        """Test migrating down to target version."""
        # Setup migrations
        simple_migrations = [
            Migration(1, "first", 
                     "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT, applied_at TEXT);",
                     "SELECT 'Cannot rollback initial' as error;"),
            Migration(2, "second", 
                     "CREATE TABLE table2 (id INTEGER);",
                     "DROP TABLE table2;"),
            Migration(3, "third",
                     "CREATE TABLE table3 (id INTEGER);", 
                     "DROP TABLE table3;")
        ]
        
        migration_manager.migrations = simple_migrations
        
        # First migrate up to version 3
        await migration_manager.migrate_up()
        assert await migration_manager.get_current_version() == 3
        
        # Now migrate down to version 1
        success = await migration_manager.migrate_down(target_version=1)
        assert success
        
        version = await migration_manager.get_current_version()
        assert version == 1
        
        # Verify tables 2 and 3 were dropped
        async with aiosqlite.connect(temp_db) as db:
            for table_name in ['table2', 'table3']:
                cursor = await db.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                """, (table_name,))
                result = await cursor.fetchone()
                assert result is None, f"Table {table_name} should be dropped"
    
    @pytest.mark.asyncio
    async def test_get_migration_status(self, migration_manager, temp_db):
        """Test getting comprehensive migration status."""
        # Setup some applied migrations
        async with aiosqlite.connect(temp_db) as db:
            await db.execute("""
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (1, 'first', '2024-01-01T00:00:00')
            """)
            await db.commit()
        
        status = await migration_manager.get_migration_status()
        
        assert status['current_version'] == 1
        assert status['applied_count'] == 1
        assert status['pending_count'] > 0  # There should be pending migrations
        assert len(status['applied_migrations']) == 1
        assert status['applied_migrations'][0]['name'] == 'first'
        assert len(status['pending_migrations']) > 0