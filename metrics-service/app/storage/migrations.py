"""Database schema migration system for metrics service."""
import asyncio
import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Callable, Optional
from pathlib import Path
from ..config import settings
from .database import MetricsStorage
import aiosqlite

logger = logging.getLogger(__name__)


class Migration:
    """Represents a single database migration."""
    
    def __init__(
        self, 
        version: int, 
        name: str, 
        up_sql: str, 
        down_sql: str = None,
        python_up: Optional[Callable] = None,
        python_down: Optional[Callable] = None
    ):
        self.version = version
        self.name = name
        self.up_sql = up_sql
        self.down_sql = down_sql
        self.python_up = python_up
        self.python_down = python_down
    
    def __str__(self):
        return f"Migration {self.version:04d}: {self.name}"


class MigrationManager:
    """Manages database schema migrations."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.SQLITE_DB_PATH
        self.migrations: List[Migration] = []
        self._register_migrations()
    
    def _register_migrations(self):
        """Register all available migrations in order."""
        
        # Migration 0001: Initial schema (this is what we already have)
        self.migrations.append(Migration(
            version=1,
            name="initial_schema",
            up_sql="""
                -- Migration 0001: Initial schema
                -- This represents the current schema in database.py
                
                -- Schema version tracking table
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                
                -- API Keys table (already exists, but ensure consistency)
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_hash TEXT UNIQUE NOT NULL,
                    service_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    rate_limit INTEGER DEFAULT 1000
                );

                -- Main metrics table
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    service TEXT NOT NULL,
                    service_version TEXT,
                    instance_id TEXT,
                    metric_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    value REAL NOT NULL,
                    duration_ms REAL,
                    dimensions TEXT,  -- JSON
                    metadata TEXT,    -- JSON
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- Auth metrics table
                CREATE TABLE IF NOT EXISTS auth_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    service TEXT NOT NULL,
                    duration_ms REAL,
                    success BOOLEAN,
                    method TEXT,
                    server TEXT,
                    user_hash TEXT,
                    error_code TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- Discovery metrics table
                CREATE TABLE IF NOT EXISTS discovery_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    service TEXT NOT NULL,
                    duration_ms REAL,
                    query TEXT,
                    results_count INTEGER,
                    top_k_services INTEGER,
                    top_n_tools INTEGER,
                    embedding_time_ms REAL,
                    faiss_search_time_ms REAL,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- Tool metrics table
                CREATE TABLE IF NOT EXISTS tool_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    service TEXT NOT NULL,
                    duration_ms REAL,
                    tool_name TEXT,
                    server_path TEXT,
                    server_name TEXT,
                    success BOOLEAN,
                    error_code TEXT,
                    input_size_bytes INTEGER,
                    output_size_bytes INTEGER,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp);
                CREATE INDEX IF NOT EXISTS idx_metrics_service_type ON metrics(service, metric_type);
                CREATE INDEX IF NOT EXISTS idx_metrics_type_timestamp ON metrics(metric_type, timestamp);
                
                CREATE INDEX IF NOT EXISTS idx_auth_timestamp ON auth_metrics(timestamp);
                CREATE INDEX IF NOT EXISTS idx_auth_success ON auth_metrics(success, timestamp);
                CREATE INDEX IF NOT EXISTS idx_auth_user ON auth_metrics(user_hash, timestamp);
                
                CREATE INDEX IF NOT EXISTS idx_discovery_timestamp ON discovery_metrics(timestamp);
                CREATE INDEX IF NOT EXISTS idx_discovery_results ON discovery_metrics(results_count, timestamp);
                
                CREATE INDEX IF NOT EXISTS idx_tool_timestamp ON tool_metrics(timestamp);
                CREATE INDEX IF NOT EXISTS idx_tool_name ON tool_metrics(tool_name, timestamp);
                CREATE INDEX IF NOT EXISTS idx_tool_success ON tool_metrics(success, timestamp);
                
                CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
                CREATE INDEX IF NOT EXISTS idx_api_keys_service ON api_keys(service_name);
            """,
            down_sql="""
                -- Cannot rollback initial schema safely
                SELECT 'Initial schema rollback not supported' as error;
            """
        ))
        
        # Migration 0002: Add metrics aggregation tables
        self.migrations.append(Migration(
            version=2,
            name="add_aggregation_tables",
            up_sql="""
                -- Migration 0002: Add aggregation tables for better performance
                
                -- Hourly aggregated metrics
                CREATE TABLE IF NOT EXISTS metrics_hourly (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    hour_timestamp TEXT NOT NULL, -- ISO timestamp truncated to hour
                    count INTEGER DEFAULT 0,
                    sum_value REAL DEFAULT 0.0,
                    avg_value REAL DEFAULT 0.0,
                    min_value REAL,
                    max_value REAL,
                    sum_duration_ms REAL DEFAULT 0.0,
                    avg_duration_ms REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(service, metric_type, hour_timestamp)
                );
                
                -- Daily aggregated metrics  
                CREATE TABLE IF NOT EXISTS metrics_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    date TEXT NOT NULL, -- YYYY-MM-DD format
                    count INTEGER DEFAULT 0,
                    sum_value REAL DEFAULT 0.0,
                    avg_value REAL DEFAULT 0.0,
                    min_value REAL,
                    max_value REAL,
                    sum_duration_ms REAL DEFAULT 0.0,
                    avg_duration_ms REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(service, metric_type, date)
                );
                
                -- Indexes for aggregation tables
                CREATE INDEX IF NOT EXISTS idx_hourly_service_type_hour ON metrics_hourly(service, metric_type, hour_timestamp);
                CREATE INDEX IF NOT EXISTS idx_hourly_hour ON metrics_hourly(hour_timestamp);
                
                CREATE INDEX IF NOT EXISTS idx_daily_service_type_date ON metrics_daily(service, metric_type, date);
                CREATE INDEX IF NOT EXISTS idx_daily_date ON metrics_daily(date);
            """,
            down_sql="""
                -- Rollback aggregation tables
                DROP INDEX IF EXISTS idx_daily_date;
                DROP INDEX IF EXISTS idx_daily_service_type_date;
                DROP INDEX IF EXISTS idx_hourly_hour;
                DROP INDEX IF EXISTS idx_hourly_service_type_hour;
                DROP TABLE IF EXISTS metrics_daily;
                DROP TABLE IF EXISTS metrics_hourly;
            """
        ))
        
        # Migration 0003: Add retention policies table
        self.migrations.append(Migration(
            version=3,
            name="add_retention_policies",
            up_sql="""
                -- Migration 0003: Add retention policies management
                
                CREATE TABLE IF NOT EXISTS retention_policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT NOT NULL,
                    retention_days INTEGER NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(table_name)
                );
                
                -- Insert default retention policies
                INSERT OR IGNORE INTO retention_policies (table_name, retention_days) VALUES 
                    ('metrics', 90),           -- Keep raw metrics for 90 days
                    ('auth_metrics', 90),      -- Keep auth metrics for 90 days  
                    ('discovery_metrics', 90), -- Keep discovery metrics for 90 days
                    ('tool_metrics', 90),      -- Keep tool metrics for 90 days
                    ('metrics_hourly', 365),   -- Keep hourly aggregates for 1 year
                    ('metrics_daily', 1095);   -- Keep daily aggregates for 3 years
            """,
            down_sql="""
                -- Rollback retention policies
                DROP TABLE IF EXISTS retention_policies;
            """
        ))
        
        # Migration 0004: Add API key usage tracking
        self.migrations.append(Migration(
            version=4,
            name="add_api_key_usage_tracking",
            up_sql="""
                -- Migration 0004: Enhanced API key usage tracking
                
                -- Add columns to api_keys table
                ALTER TABLE api_keys ADD COLUMN usage_count INTEGER DEFAULT 0;
                ALTER TABLE api_keys ADD COLUMN daily_usage_limit INTEGER DEFAULT NULL;
                ALTER TABLE api_keys ADD COLUMN monthly_usage_limit INTEGER DEFAULT NULL;
                ALTER TABLE api_keys ADD COLUMN description TEXT DEFAULT NULL;
                
                -- API key usage log table
                CREATE TABLE IF NOT EXISTS api_key_usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_hash TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    request_count INTEGER DEFAULT 1,
                    bytes_processed INTEGER DEFAULT 0,
                    duration_ms REAL DEFAULT 0,
                    status_code INTEGER DEFAULT 200,
                    FOREIGN KEY (key_hash) REFERENCES api_keys(key_hash)
                );
                
                -- Indexes for usage tracking
                CREATE INDEX IF NOT EXISTS idx_usage_key_timestamp ON api_key_usage_log(key_hash, timestamp);
                CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON api_key_usage_log(timestamp);
                CREATE INDEX IF NOT EXISTS idx_usage_endpoint ON api_key_usage_log(endpoint, timestamp);
            """,
            down_sql="""
                -- Rollback API key usage tracking
                DROP INDEX IF EXISTS idx_usage_endpoint;
                DROP INDEX IF EXISTS idx_usage_timestamp;
                DROP INDEX IF EXISTS idx_usage_key_timestamp;
                DROP TABLE IF EXISTS api_key_usage_log;
                
                -- Note: Cannot easily remove columns from SQLite, would need table recreation
                -- For now, just mark as rolled back
            """
        ))
        
        # Migration 5: Fix missing tables and timestamp columns
        self.migrations.append(Migration(
            version=5,
            name="fix_missing_tables_and_columns",
            up_sql="""
                -- Create aggregated metrics tables that retention policies expect
                CREATE TABLE IF NOT EXISTS metrics_hourly (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hour_timestamp TEXT NOT NULL,
                    service TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    total_count INTEGER DEFAULT 0,
                    avg_duration_ms REAL DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(hour_timestamp, service, metric_type)
                );
                
                CREATE TABLE IF NOT EXISTS metrics_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    service TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    total_count INTEGER DEFAULT 0,
                    avg_duration_ms REAL DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(date, service, metric_type)
                );
                
                -- Create retention policies table
                CREATE TABLE IF NOT EXISTS retention_policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT UNIQUE NOT NULL,
                    retention_days INTEGER NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    cleanup_query TEXT,
                    timestamp_column TEXT DEFAULT 'created_at',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );
                
                -- Add missing indexes
                CREATE INDEX IF NOT EXISTS idx_metrics_hourly_timestamp ON metrics_hourly(hour_timestamp);
                CREATE INDEX IF NOT EXISTS idx_metrics_hourly_service ON metrics_hourly(service, metric_type);
                CREATE INDEX IF NOT EXISTS idx_metrics_daily_date ON metrics_daily(date);
                CREATE INDEX IF NOT EXISTS idx_metrics_daily_service ON metrics_daily(service, metric_type);
                CREATE INDEX IF NOT EXISTS idx_retention_policies_table ON retention_policies(table_name);
            """,
            down_sql="""
                DROP TABLE IF EXISTS metrics_hourly;
                DROP TABLE IF EXISTS metrics_daily;
                DROP TABLE IF EXISTS retention_policies;
                DROP INDEX IF EXISTS idx_metrics_hourly_timestamp;
                DROP INDEX IF EXISTS idx_metrics_hourly_service;
                DROP INDEX IF EXISTS idx_metrics_daily_date;
                DROP INDEX IF EXISTS idx_metrics_daily_service;
                DROP INDEX IF EXISTS idx_retention_policies_table;
            """
        ))
    
    async def get_current_version(self) -> int:
        """Get the current schema version from the database."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # First check if migrations table exists
                cursor = await db.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='schema_migrations'
                """)
                table_exists = await cursor.fetchone()
                
                if not table_exists:
                    return 0  # No migrations have been applied
                
                # Get the highest version number
                cursor = await db.execute("""
                    SELECT MAX(version) FROM schema_migrations
                """)
                result = await cursor.fetchone()
                return result[0] if result[0] else 0
                
        except Exception as e:
            logger.error(f"Failed to get current schema version: {e}")
            return 0
    
    async def get_applied_migrations(self) -> List[Dict[str, Any]]:
        """Get list of applied migrations."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT version, name, applied_at 
                    FROM schema_migrations 
                    ORDER BY version
                """)
                rows = await cursor.fetchall()
                return [
                    {
                        "version": row[0],
                        "name": row[1], 
                        "applied_at": row[2]
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to get applied migrations: {e}")
            return []
    
    async def apply_migration(self, migration: Migration) -> bool:
        """Apply a single migration."""
        logger.info(f"Applying {migration}")
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("BEGIN TRANSACTION")
                
                try:
                    # Execute the SQL migration
                    if migration.up_sql:
                        await db.executescript(migration.up_sql)
                    
                    # Execute Python migration if provided
                    if migration.python_up:
                        await migration.python_up(db)
                    
                    # Record the migration as applied
                    await db.execute("""
                        INSERT INTO schema_migrations (version, name, applied_at)
                        VALUES (?, ?, ?)
                    """, (migration.version, migration.name, datetime.now().isoformat()))
                    
                    await db.commit()
                    logger.info(f"Successfully applied {migration}")
                    return True
                    
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Failed to apply {migration}: {e}")
                    return False
                    
        except Exception as e:
            logger.error(f"Database connection error during migration: {e}")
            return False
    
    async def rollback_migration(self, migration: Migration) -> bool:
        """Rollback a single migration."""
        logger.info(f"Rolling back {migration}")
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("BEGIN TRANSACTION")
                
                try:
                    # Execute Python rollback if provided
                    if migration.python_down:
                        await migration.python_down(db)
                    
                    # Execute the SQL rollback
                    if migration.down_sql:
                        await db.executescript(migration.down_sql)
                    
                    # Remove the migration record
                    await db.execute("""
                        DELETE FROM schema_migrations WHERE version = ?
                    """, (migration.version,))
                    
                    await db.commit()
                    logger.info(f"Successfully rolled back {migration}")
                    return True
                    
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Failed to rollback {migration}: {e}")
                    return False
                    
        except Exception as e:
            logger.error(f"Database connection error during rollback: {e}")
            return False
    
    async def migrate_up(self, target_version: Optional[int] = None) -> bool:
        """Apply all pending migrations up to target version."""
        current_version = await self.get_current_version()
        target_version = target_version or max(m.version for m in self.migrations)
        
        logger.info(f"Current schema version: {current_version}")
        logger.info(f"Target schema version: {target_version}")
        
        if current_version >= target_version:
            logger.info("Database schema is up to date")
            return True
        
        # Find migrations to apply
        pending_migrations = [
            m for m in self.migrations 
            if current_version < m.version <= target_version
        ]
        
        if not pending_migrations:
            logger.info("No migrations to apply")
            return True
        
        logger.info(f"Applying {len(pending_migrations)} migrations...")
        
        for migration in sorted(pending_migrations, key=lambda x: x.version):
            success = await self.apply_migration(migration)
            if not success:
                logger.error(f"Migration failed at {migration}, aborting")
                return False
        
        logger.info("All migrations applied successfully")
        return True
    
    async def migrate_down(self, target_version: int) -> bool:
        """Rollback migrations down to target version."""
        current_version = await self.get_current_version()
        
        logger.info(f"Current schema version: {current_version}")
        logger.info(f"Target schema version: {target_version}")
        
        if current_version <= target_version:
            logger.info("No rollback needed")
            return True
        
        # Find migrations to rollback
        rollback_migrations = [
            m for m in self.migrations 
            if target_version < m.version <= current_version
        ]
        
        if not rollback_migrations:
            logger.info("No migrations to rollback")
            return True
        
        logger.info(f"Rolling back {len(rollback_migrations)} migrations...")
        
        # Rollback in reverse order
        for migration in sorted(rollback_migrations, key=lambda x: x.version, reverse=True):
            success = await self.rollback_migration(migration)
            if not success:
                logger.error(f"Rollback failed at {migration}, aborting")
                return False
        
        logger.info("All rollbacks completed successfully")
        return True
    
    def list_migrations(self) -> List[Migration]:
        """List all available migrations."""
        return sorted(self.migrations, key=lambda x: x.version)
    
    async def get_migration_status(self) -> Dict[str, Any]:
        """Get comprehensive migration status."""
        current_version = await self.get_current_version()
        applied_migrations = await self.get_applied_migrations()
        all_migrations = self.list_migrations()
        
        pending_migrations = [
            m for m in all_migrations 
            if m.version > current_version
        ]
        
        return {
            "current_version": current_version,
            "latest_version": max(m.version for m in all_migrations),
            "applied_count": len(applied_migrations),
            "pending_count": len(pending_migrations),
            "applied_migrations": applied_migrations,
            "pending_migrations": [
                {"version": m.version, "name": m.name}
                for m in pending_migrations
            ]
        }


# Global migration manager instance
migration_manager = MigrationManager()