"""Tests for data retention and cleanup functionality."""
import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
from datetime import datetime, timedelta
from app.core.retention import RetentionPolicy, RetentionManager
from app.storage.database import MetricsStorage
from app.storage.migrations import MigrationManager
import aiosqlite


@pytest_asyncio.fixture
async def temp_db():
    """Create temporary database for testing."""
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    try:
        # Initialize database with schema using migrations
        migration_manager = MigrationManager(db_path)
        await migration_manager.migrate_up()
        
        # Add sample data
        async with aiosqlite.connect(db_path) as db:
            # Create test tables
            await db.execute("""
                CREATE TABLE IF NOT EXISTS test_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    value REAL NOT NULL
                )
            """)
            
            # Insert test data with various timestamps
            now = datetime.now()
            await db.execute(
                "INSERT INTO test_metrics (created_at, value) VALUES (?, ?)",
                ((now - timedelta(days=100)).isoformat(), 1.0)
            )
            await db.execute(
                "INSERT INTO test_metrics (created_at, value) VALUES (?, ?)",
                ((now - timedelta(days=50)).isoformat(), 2.0)
            )
            await db.execute(
                "INSERT INTO test_metrics (created_at, value) VALUES (?, ?)",
                ((now - timedelta(days=10)).isoformat(), 3.0)
            )
            await db.execute(
                "INSERT INTO test_metrics (created_at, value) VALUES (?, ?)",
                (now.isoformat(), 4.0)
            )
            await db.commit()
        
        yield db_path
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


class TestRetentionPolicy:
    """Test retention policy functionality."""
    
    def test_policy_creation(self):
        """Test retention policy creation."""
        policy = RetentionPolicy(
            table_name="metrics",
            retention_days=90,
            is_active=True
        )
        
        assert policy.table_name == "metrics"
        assert policy.retention_days == 90
        assert policy.is_active is True
        assert policy.timestamp_column == "created_at"
    
    def test_custom_cleanup_query(self):
        """Test custom cleanup query."""
        custom_query = "DELETE FROM metrics WHERE timestamp < datetime('now', '-30 days')"
        policy = RetentionPolicy(
            table_name="metrics",
            retention_days=30,
            cleanup_query=custom_query
        )
        
        assert policy.get_cleanup_query() == custom_query
    
    def test_default_cleanup_query(self):
        """Test default cleanup query generation."""
        policy = RetentionPolicy(
            table_name="metrics",
            retention_days=90
        )
        
        query = policy.get_cleanup_query()
        assert "DELETE FROM metrics" in query
        assert "created_at < datetime('now', '-90 days')" in query
    
    def test_count_query(self):
        """Test count query generation."""
        policy = RetentionPolicy(
            table_name="metrics",
            retention_days=30
        )
        
        query = policy.get_count_query()
        assert "SELECT COUNT(*)" in query
        assert "FROM metrics" in query
        assert "created_at < datetime('now', '-30 days')" in query


class TestRetentionManager:
    """Test retention manager functionality."""
    
    @pytest_asyncio.fixture
    async def manager(self, temp_db):
        """Create retention manager with temporary database."""
        manager = RetentionManager()
        manager.storage.db_path = temp_db
        return manager
    
    @pytest.mark.asyncio
    async def test_load_default_policies(self, manager):
        """Test loading default policies."""
        assert len(manager.policies) > 0
        assert "metrics" in manager.policies
        assert "auth_metrics" in manager.policies
        assert manager.policies["metrics"].retention_days == 90
    
    @pytest.mark.asyncio
    async def test_update_policy(self, manager):
        """Test updating retention policy."""
        await manager.update_policy("test_table", 60, True)
        
        assert "test_table" in manager.policies
        assert manager.policies["test_table"].retention_days == 60
        assert manager.policies["test_table"].is_active is True
    
    @pytest.mark.asyncio
    async def test_get_cleanup_preview(self, manager, temp_db):
        """Test cleanup preview functionality."""
        # Add test policy
        manager.policies["test_metrics"] = RetentionPolicy(
            table_name="test_metrics",
            retention_days=30
        )
        
        preview = await manager.get_cleanup_preview("test_metrics")
        
        assert "test_metrics" in preview
        preview_data = preview["test_metrics"]
        assert "retention_days" in preview_data
        assert "records_to_delete" in preview_data
        assert "total_records" in preview_data
        assert preview_data["retention_days"] == 30
        assert preview_data["total_records"] == 4  # From test data
        
        # Should have 2 records older than 30 days
        assert preview_data["records_to_delete"] == 2
    
    @pytest.mark.asyncio
    async def test_cleanup_table_dry_run(self, manager, temp_db):
        """Test table cleanup in dry run mode."""
        # Add test policy
        manager.policies["test_metrics"] = RetentionPolicy(
            table_name="test_metrics",
            retention_days=30
        )
        
        result = await manager.cleanup_table("test_metrics", dry_run=True)
        
        assert result["table"] == "test_metrics"
        assert result["status"] == "dry_run"
        assert result["records_would_delete"] == 2
        
        # Verify no records were actually deleted
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM test_metrics")
            count = (await cursor.fetchone())[0]
            assert count == 4
    
    @pytest.mark.asyncio
    async def test_cleanup_table_actual(self, manager, temp_db):
        """Test actual table cleanup."""
        # Add test policy
        manager.policies["test_metrics"] = RetentionPolicy(
            table_name="test_metrics",
            retention_days=30
        )
        
        result = await manager.cleanup_table("test_metrics", dry_run=False)
        
        assert result["table"] == "test_metrics"
        assert result["status"] == "completed"
        assert result["records_deleted"] == 2
        
        # Verify records were actually deleted
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM test_metrics")
            count = (await cursor.fetchone())[0]
            assert count == 2
    
    @pytest.mark.asyncio
    async def test_cleanup_inactive_policy(self, manager):
        """Test cleanup with inactive policy."""
        manager.policies["test_table"] = RetentionPolicy(
            table_name="test_table",
            retention_days=30,
            is_active=False
        )
        
        result = await manager.cleanup_table("test_table", dry_run=False)
        
        assert result["status"] == "skipped"
        assert result["reason"] == "policy_inactive"
    
    @pytest.mark.asyncio
    async def test_cleanup_no_policy(self, manager):
        """Test cleanup for table without policy."""
        with pytest.raises(ValueError, match="No retention policy found"):
            await manager.cleanup_table("nonexistent_table")
    
    @pytest.mark.asyncio
    async def test_cleanup_all_tables(self, manager, temp_db):
        """Test cleanup of all tables."""
        # Add test policy
        manager.policies["test_metrics"] = RetentionPolicy(
            table_name="test_metrics",
            retention_days=30
        )
        
        result = await manager.cleanup_all_tables(dry_run=True)
        
        assert result["operation"] == "dry_run"
        assert "test_metrics" in result["table_results"]
        assert result["table_results"]["test_metrics"]["status"] == "dry_run"
    
    @pytest.mark.asyncio
    async def test_get_table_stats(self, manager, temp_db):
        """Test getting table statistics."""
        stats = await manager.get_table_stats()
        
        # Check that we get stats for some tables
        assert len(stats) > 0
        
        # Check that real metrics tables have proper stats
        if "metrics" in stats and "error" not in stats["metrics"]:
            assert "record_count" in stats["metrics"]
            assert "has_retention_policy" in stats["metrics"]
        
        # For test table that might have errors, just verify it exists
        assert "test_metrics" in stats
    
    @pytest.mark.asyncio
    async def test_get_database_size(self, manager):
        """Test getting database size information."""
        size_info = await manager.get_database_size()
        
        assert "main_db_bytes" in size_info
        assert "main_db_mb" in size_info
        assert "total_bytes" in size_info
        assert "page_count" in size_info
        assert "page_size" in size_info
        assert size_info["main_db_bytes"] > 0
    
    @pytest.mark.asyncio
    async def test_save_and_load_policies(self, manager, temp_db):
        """Test saving and loading policies to/from database."""
        # Add custom policy
        manager.policies["custom_table"] = RetentionPolicy(
            table_name="custom_table",
            retention_days=120,
            is_active=True
        )
        
        # Save policies
        await manager.save_policies_to_database()
        
        # Create new manager and load policies
        new_manager = RetentionManager()
        new_manager.storage.db_path = temp_db
        await new_manager.load_policies_from_database()
        
        # Verify custom policy was loaded
        assert "custom_table" in new_manager.policies
        assert new_manager.policies["custom_table"].retention_days == 120
        assert new_manager.policies["custom_table"].is_active is True


class TestRetentionIntegration:
    """Integration tests for retention system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_cleanup(self, temp_db):
        """Test complete end-to-end cleanup process."""
        manager = RetentionManager()
        manager.storage.db_path = temp_db
        
        # Add metrics with old timestamps
        async with aiosqlite.connect(temp_db) as db:
            old_date = (datetime.now() - timedelta(days=120)).isoformat()
            recent_date = (datetime.now() - timedelta(days=10)).isoformat()
            
            await db.execute(
                "INSERT INTO metrics (request_id, service, metric_type, value, timestamp, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("req_1", "test", "auth_request", 1.0, old_date, old_date)
            )
            await db.execute(
                "INSERT INTO metrics (request_id, service, metric_type, value, timestamp, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("req_2", "test", "auth_request", 1.0, recent_date, recent_date)
            )
            await db.commit()
        
        # Preview cleanup
        preview = await manager.get_cleanup_preview("metrics")
        assert preview["metrics"]["records_to_delete"] == 1
        
        # Run actual cleanup
        result = await manager.cleanup_table("metrics", dry_run=False)
        assert result["records_deleted"] == 1
        
        # Verify only recent record remains
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM metrics")
            count = (await cursor.fetchone())[0]
            assert count == 1
            
            cursor = await db.execute("SELECT request_id FROM metrics")
            remaining_id = (await cursor.fetchone())[0]
            assert remaining_id == "req_2"