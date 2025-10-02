import aiosqlite
import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
from ..config import settings

logger = logging.getLogger(__name__)


async def wait_for_database(max_retries: int = 10, delay: float = 2.0):
    """Wait for SQLite database container to be ready."""
    db_path = settings.SQLITE_DB_PATH
    
    for attempt in range(max_retries):
        try:
            # Ensure directory exists first
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Try to connect to database
            async with aiosqlite.connect(db_path) as db:
                await db.execute("SELECT 1")
                logger.info(f"Database connection successful on attempt {attempt + 1}")
                return
        except Exception as e:
            logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
            else:
                raise Exception(f"Failed to connect to database after {max_retries} attempts")


async def _migrate_schema_if_needed(db):
    """Migrate database schema if needed."""
    try:
        # Check if tool_metrics table exists and has the new columns
        cursor = await db.execute("PRAGMA table_info(tool_metrics)")
        columns = await cursor.fetchall()
        existing_columns = [col[1] for col in columns] if columns else []

        # If table doesn't exist, creation will handle it
        if not existing_columns:
            return

        # Check if we need to add new columns
        required_columns = ['client_name', 'client_version', 'method', 'user_hash']
        missing_columns = [col for col in required_columns if col not in existing_columns]

        if missing_columns:
            logger.info(f"Adding missing columns to tool_metrics: {missing_columns}")
            for column in missing_columns:
                await db.execute(f"ALTER TABLE tool_metrics ADD COLUMN {column} TEXT")

            # Add indexes for new columns
            if 'client_name' in missing_columns:
                await db.execute("CREATE INDEX IF NOT EXISTS idx_tool_client ON tool_metrics(client_name, timestamp)")
            if 'method' in missing_columns:
                await db.execute("CREATE INDEX IF NOT EXISTS idx_tool_method ON tool_metrics(method, timestamp)")

            await db.commit()
            logger.info("Schema migration completed successfully")

    except Exception as e:
        logger.warning(f"Schema migration failed, will recreate tables: {e}")


async def init_database():
    """Initialize database with schema migrations."""
    db_path = settings.SQLITE_DB_PATH

    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        # Enable WAL mode for better concurrency
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=10000")
        await db.execute("PRAGMA temp_store=MEMORY")

        # Check if we need to migrate existing schema
        await _migrate_schema_if_needed(db)
        
        # Create tables
        await db.executescript("""
            -- API Keys table
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
                client_name TEXT,
                client_version TEXT,
                method TEXT,
                user_hash TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        
        # Create indexes for performance
        await db.executescript("""
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
            CREATE INDEX IF NOT EXISTS idx_tool_client ON tool_metrics(client_name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_tool_method ON tool_metrics(method, timestamp);
            
            CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
            CREATE INDEX IF NOT EXISTS idx_api_keys_service ON api_keys(service_name);
        """)
        
        await db.commit()
        logger.info("Database tables and indexes created successfully")
    


class MetricsStorage:
    """SQLite storage handler for containerized database."""
    
    def __init__(self):
        self.db_path = settings.SQLITE_DB_PATH
    
    async def store_metrics_batch(self, metrics_batch: List[Dict[str, Any]]):
        """Store a batch of metrics in the containerized database."""
        if not metrics_batch:
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            try:
                for metric_data in metrics_batch:
                    metric = metric_data['metric']
                    request = metric_data['request']
                    request_id = metric_data['request_id']
                    
                    # Store in main metrics table
                    await db.execute("""
                        INSERT INTO metrics (
                            request_id, service, service_version, instance_id,
                            metric_type, timestamp, value, duration_ms,
                            dimensions, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        request_id,
                        request.service,
                        request.version,
                        request.instance_id,
                        metric.type.value,
                        metric.timestamp.isoformat(),
                        metric.value,
                        metric.duration_ms,
                        json.dumps(metric.dimensions),
                        json.dumps(metric.metadata)
                    ))
                    
                    # Store in specialized table based on type
                    await self._store_specialized_metric(db, metric, request, request_id)
                
                await db.commit()
                logger.debug(f"Stored batch of {len(metrics_batch)} metrics to container DB")
                
            except Exception as e:
                await db.rollback()
                logger.error(f"Failed to store metrics batch: {e}")
                raise
    
    async def _store_specialized_metric(self, db, metric, request, request_id):
        """Store metric in specialized table based on type."""
        if metric.type.value == "auth_request":
            await db.execute("""
                INSERT INTO auth_metrics (
                    request_id, timestamp, service, duration_ms,
                    success, method, server, user_hash, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request_id,
                metric.timestamp.isoformat(),
                request.service,
                metric.duration_ms,
                metric.dimensions.get('success'),
                metric.dimensions.get('method'),
                metric.dimensions.get('server'),
                metric.dimensions.get('user_hash'),
                metric.metadata.get('error_code')
            ))
        
        elif metric.type.value == "tool_discovery":
            await db.execute("""
                INSERT INTO discovery_metrics (
                    request_id, timestamp, service, duration_ms,
                    query, results_count, top_k_services, top_n_tools,
                    embedding_time_ms, faiss_search_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request_id,
                metric.timestamp.isoformat(),
                request.service,
                metric.duration_ms,
                metric.dimensions.get('query'),
                metric.dimensions.get('results_count'),
                metric.dimensions.get('top_k_services'),
                metric.dimensions.get('top_n_tools'),
                metric.metadata.get('embedding_time_ms'),
                metric.metadata.get('faiss_search_time_ms')
            ))
        
        elif metric.type.value == "tool_execution":
            await db.execute("""
                INSERT INTO tool_metrics (
                    request_id, timestamp, service, duration_ms,
                    tool_name, server_path, server_name, success,
                    error_code, input_size_bytes, output_size_bytes,
                    client_name, client_version, method, user_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request_id,
                metric.timestamp.isoformat(),
                request.service,
                metric.duration_ms,
                metric.dimensions.get('tool_name'),
                metric.dimensions.get('server_path'),
                metric.dimensions.get('server_name'),
                metric.dimensions.get('success'),
                metric.metadata.get('error_code'),
                metric.metadata.get('input_size_bytes'),
                metric.metadata.get('output_size_bytes'),
                metric.dimensions.get('client_name'),
                metric.dimensions.get('client_version'),
                metric.dimensions.get('method'),
                metric.dimensions.get('user_hash')
            ))

    async def get_api_key(self, key_hash: str) -> Dict[str, Any] | None:
        """Get API key details from database."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT service_name, is_active, rate_limit, last_used_at
                FROM api_keys 
                WHERE key_hash = ?
            """, (key_hash,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'service_name': row[0],
                        'is_active': bool(row[1]),
                        'rate_limit': row[2],
                        'last_used_at': row[3]
                    }
                return None

    async def update_api_key_usage(self, key_hash: str):
        """Update last_used_at timestamp for API key."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE api_keys 
                SET last_used_at = datetime('now') 
                WHERE key_hash = ?
            """, (key_hash,))
            await db.commit()

    async def create_api_key(self, key_hash: str, service_name: str, rate_limit: int = 1000) -> bool:
        """Create a new API key in the database."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO api_keys (key_hash, service_name, created_at, is_active, rate_limit)
                    VALUES (?, ?, datetime('now'), 1, ?)
                """, (key_hash, service_name, rate_limit))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to create API key: {e}")
            return False