# Database Schema Documentation

This document provides comprehensive documentation of the database schema, migration system, and data management for the MCP Metrics Collection Service.

## Table of Contents

- [Overview](#overview)
- [Schema Architecture](#schema-architecture)
- [Table Definitions](#table-definitions)
- [Migration System](#migration-system)
- [Data Retention](#data-retention)
- [Performance Considerations](#performance-considerations)
- [Backup and Recovery](#backup-and-recovery)

## Overview

The metrics service uses SQLite as its primary data store with a carefully designed schema optimized for:

- **High-volume writes**: Optimized for metric ingestion
- **Time-series data**: Efficient timestamp-based queries
- **Aggregation support**: Pre-computed summaries for performance
- **Data retention**: Automatic cleanup of old data
- **Schema evolution**: Version-controlled migrations

### Design Principles

1. **Write Optimization**: Tables designed for fast inserts
2. **Query Performance**: Strategic indexing for common queries
3. **Data Integrity**: Foreign key constraints and validation
4. **Storage Efficiency**: Normalized structure with JSON for flexible data
5. **Horizontal Scaling**: Partitionable by time and service

## Schema Architecture

### Entity Relationship Diagram

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   api_keys      │     │     metrics     │     │ schema_migrations│
│                 │     │                 │     │                 │
│ • id (PK)       │     │ • id (PK)       │     │ • version (PK)  │
│ • key_hash      │────▶│ • request_id    │     │ • name          │
│ • service_name  │     │ • service       │     │ • applied_at    │
│ • rate_limit    │     │ • metric_type   │     └─────────────────┘
│ • usage_count   │     │ • timestamp     │              
│ • created_at    │     │ • value         │     ┌─────────────────┐
└─────────────────┘     │ • duration_ms   │     │retention_policies│
                        │ • dimensions    │     │                 │
┌─────────────────┐     │ • metadata      │     │ • id (PK)       │
│ api_key_usage   │     └─────────────────┘     │ • table_name    │
│                 │              │              │ • retention_days│
│ • id (PK)       │              │              │ • is_active     │
│ • key_hash      │──────────────┘              └─────────────────┘
│ • timestamp     │              │
│ • endpoint      │              │
│ • request_count │              ▼
│ • status_code   │     ┌─────────────────┐
└─────────────────┘     │ Specialized     │
                        │ Metric Tables   │
┌─────────────────┐     │                 │
│ metrics_hourly  │     │ • auth_metrics  │
│                 │     │ • discovery_    │
│ • id (PK)       │◀────│   metrics       │
│ • service       │     │ • tool_metrics  │
│ • metric_type   │     └─────────────────┘
│ • hour_timestamp│
│ • count         │     ┌─────────────────┐
│ • sum_value     │     │ metrics_daily   │
│ • avg_value     │     │                 │
│ • min_value     │     │ • id (PK)       │
│ • max_value     │     │ • service       │
└─────────────────┘     │ • metric_type   │
                        │ • date          │
                        │ • count         │
                        │ • aggregates... │
                        └─────────────────┘
```

## Table Definitions

### Core Tables

#### api_keys
Stores API key information and configuration.

```sql
CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT UNIQUE NOT NULL,           -- SHA256 hash of API key
    service_name TEXT NOT NULL,              -- Associated service name
    created_at TEXT NOT NULL,                -- ISO timestamp
    last_used_at TEXT,                       -- Last request timestamp
    is_active BOOLEAN DEFAULT 1,             -- Key status
    rate_limit INTEGER DEFAULT 1000,         -- Requests per minute
    usage_count INTEGER DEFAULT 0,           -- Total requests made
    daily_usage_limit INTEGER DEFAULT NULL,  -- Optional daily limit
    monthly_usage_limit INTEGER DEFAULT NULL,-- Optional monthly limit
    description TEXT DEFAULT NULL            -- Optional description
);

-- Indexes
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_service ON api_keys(service_name);
```

**Sample Data**:
```sql
INSERT INTO api_keys VALUES (
    1,
    'a1b2c3d4e5f6...', 
    'auth-server',
    '2024-01-01T00:00:00Z',
    '2024-01-01T12:30:15Z',
    1,
    1000,
    15842,
    NULL,
    NULL,
    'Production auth server API key'
);
```

#### metrics
Primary table for all metrics data.

```sql
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,                -- Request correlation ID
    service TEXT NOT NULL,                   -- Source service
    service_version TEXT,                    -- Service version
    instance_id TEXT,                        -- Service instance ID
    metric_type TEXT NOT NULL,               -- Type of metric
    timestamp TEXT NOT NULL,                 -- Metric timestamp (ISO)
    value REAL NOT NULL,                     -- Metric value
    duration_ms REAL,                        -- Optional duration
    dimensions TEXT,                         -- JSON key-value pairs
    metadata TEXT,                           -- JSON additional data
    created_at TEXT DEFAULT (datetime('now')) -- Row creation time
);

-- Indexes
CREATE INDEX idx_metrics_timestamp ON metrics(timestamp);
CREATE INDEX idx_metrics_service_type ON metrics(service, metric_type);
CREATE INDEX idx_metrics_type_timestamp ON metrics(metric_type, timestamp);
```

**Sample Data**:
```sql
INSERT INTO metrics VALUES (
    1,
    'req_abc123',
    'auth-server',
    '1.2.0',
    'auth-pod-01',
    'auth_request',
    '2024-01-01T12:30:15.123Z',
    1.0,
    45.2,
    '{"method":"jwt","success":true,"server":"auth-01"}',
    '{"error_code":null,"request_size":1024}',
    '2024-01-01T12:30:15.500Z'
);
```

### Specialized Metric Tables

#### auth_metrics
Authentication-specific metrics with optimized schema.

```sql
CREATE TABLE auth_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    service TEXT NOT NULL,
    duration_ms REAL,
    success BOOLEAN,                         -- Authentication result
    method TEXT,                             -- Auth method (jwt, oauth, etc)
    server TEXT,                             -- Handling server
    user_hash TEXT,                          -- Hashed user identifier
    error_code TEXT,                         -- Error code if failed
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX idx_auth_timestamp ON auth_metrics(timestamp);
CREATE INDEX idx_auth_success ON auth_metrics(success, timestamp);
CREATE INDEX idx_auth_user ON auth_metrics(user_hash, timestamp);
```

#### discovery_metrics
Tool discovery operation metrics.

```sql
CREATE TABLE discovery_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    service TEXT NOT NULL,
    duration_ms REAL,
    query TEXT,                              -- Search query
    results_count INTEGER,                   -- Number of results
    top_k_services INTEGER,                  -- Services considered
    top_n_tools INTEGER,                     -- Tools returned
    embedding_time_ms REAL,                  -- Vector generation time
    faiss_search_time_ms REAL,              -- Search engine time
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX idx_discovery_timestamp ON discovery_metrics(timestamp);
CREATE INDEX idx_discovery_results ON discovery_metrics(results_count, timestamp);
```

#### tool_metrics
Tool execution metrics.

```sql
CREATE TABLE tool_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    service TEXT NOT NULL,
    duration_ms REAL,
    tool_name TEXT,                          -- Executed tool name
    server_path TEXT,                        -- Server endpoint
    server_name TEXT,                        -- Server identifier
    success BOOLEAN,                         -- Execution result
    error_code TEXT,                         -- Error code if failed
    input_size_bytes INTEGER,                -- Input payload size
    output_size_bytes INTEGER,               -- Output payload size
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX idx_tool_timestamp ON tool_metrics(timestamp);
CREATE INDEX idx_tool_name ON tool_metrics(tool_name, timestamp);
CREATE INDEX idx_tool_success ON tool_metrics(success, timestamp);
```

### Aggregation Tables

#### metrics_hourly
Pre-computed hourly aggregates for performance.

```sql
CREATE TABLE metrics_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    metric_type TEXT NOT NULL,
    hour_timestamp TEXT NOT NULL,            -- Truncated to hour
    count INTEGER DEFAULT 0,                 -- Number of metrics
    sum_value REAL DEFAULT 0.0,              -- Sum of values
    avg_value REAL DEFAULT 0.0,              -- Average value
    min_value REAL,                          -- Minimum value
    max_value REAL,                          -- Maximum value
    sum_duration_ms REAL DEFAULT 0.0,        -- Sum of durations
    avg_duration_ms REAL DEFAULT 0.0,        -- Average duration
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(service, metric_type, hour_timestamp)
);

-- Indexes
CREATE INDEX idx_hourly_service_type_hour ON metrics_hourly(service, metric_type, hour_timestamp);
CREATE INDEX idx_hourly_hour ON metrics_hourly(hour_timestamp);
```

#### metrics_daily
Pre-computed daily aggregates for long-term analysis.

```sql
CREATE TABLE metrics_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    metric_type TEXT NOT NULL,
    date TEXT NOT NULL,                      -- YYYY-MM-DD format
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

-- Indexes
CREATE INDEX idx_daily_service_type_date ON metrics_daily(service, metric_type, date);
CREATE INDEX idx_daily_date ON metrics_daily(date);
```

### System Tables

#### schema_migrations
Tracks applied database migrations.

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,             -- Migration version number
    name TEXT NOT NULL,                      -- Migration name
    applied_at TEXT NOT NULL                 -- Application timestamp
);
```

#### retention_policies
Configures data retention for different tables.

```sql
CREATE TABLE retention_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,                -- Target table
    retention_days INTEGER NOT NULL,         -- Retention period
    is_active BOOLEAN DEFAULT 1,             -- Policy status
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(table_name)
);

-- Default policies
INSERT INTO retention_policies (table_name, retention_days) VALUES 
    ('metrics', 90),           -- Raw metrics: 90 days
    ('auth_metrics', 90),      -- Auth metrics: 90 days  
    ('discovery_metrics', 90), -- Discovery metrics: 90 days
    ('tool_metrics', 90),      -- Tool metrics: 90 days
    ('metrics_hourly', 365),   -- Hourly aggregates: 1 year
    ('metrics_daily', 1095);   -- Daily aggregates: 3 years
```

#### api_key_usage_log
Detailed API key usage tracking.

```sql
CREATE TABLE api_key_usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL,                  -- API key hash
    service_name TEXT NOT NULL,              -- Service making request
    timestamp TEXT NOT NULL,                 -- Request timestamp
    endpoint TEXT NOT NULL,                  -- API endpoint called
    request_count INTEGER DEFAULT 1,         -- Number of requests
    bytes_processed INTEGER DEFAULT 0,       -- Data processed
    duration_ms REAL DEFAULT 0,              -- Request duration
    status_code INTEGER DEFAULT 200,         -- HTTP status code
    FOREIGN KEY (key_hash) REFERENCES api_keys(key_hash)
);

-- Indexes
CREATE INDEX idx_usage_key_timestamp ON api_key_usage_log(key_hash, timestamp);
CREATE INDEX idx_usage_timestamp ON api_key_usage_log(timestamp);
CREATE INDEX idx_usage_endpoint ON api_key_usage_log(endpoint, timestamp);
```

## Migration System

### Migration Architecture

The migration system provides:
- **Version Control**: Sequential migration numbering
- **Rollback Support**: Down migrations for reverting changes
- **Transaction Safety**: Atomic migration application
- **Python Integration**: Support for data migrations alongside DDL

### Migration CLI

```bash
# Check migration status
python migrate.py status

# Apply all pending migrations
python migrate.py up

# Apply up to specific version
python migrate.py up --to 3

# Rollback to specific version
python migrate.py down 2

# List all available migrations
python migrate.py list

# Create new migration template
python migrate.py create "add_user_preferences"
```

### Migration Versions

#### Migration 0001: Initial Schema
- Creates all core tables
- Establishes indexes
- Sets up initial constraints

#### Migration 0002: Aggregation Tables
- Adds `metrics_hourly` table
- Adds `metrics_daily` table
- Creates aggregation indexes

#### Migration 0003: Retention Policies
- Creates `retention_policies` table
- Inserts default retention settings
- Enables automated cleanup

#### Migration 0004: API Key Usage Tracking
- Extends `api_keys` table with usage fields
- Creates `api_key_usage_log` table
- Adds usage tracking indexes

### Migration Example

```python
# Example migration structure
from app.storage.migrations import Migration

migration = Migration(
    version=5,
    name="add_metric_labels",
    up_sql="""
        -- Add labels column to metrics table
        ALTER TABLE metrics ADD COLUMN labels TEXT;
        
        -- Create index on labels
        CREATE INDEX idx_metrics_labels ON metrics(labels);
        
        -- Update existing metrics with empty labels
        UPDATE metrics SET labels = '{}' WHERE labels IS NULL;
    """,
    down_sql="""
        -- Remove labels functionality
        DROP INDEX idx_metrics_labels;
        
        -- Note: Cannot drop column in SQLite easily
        -- Would require table recreation in production
    """,
    python_up=async_migrate_labels,      # Optional Python function
    python_down=async_rollback_labels    # Optional Python rollback
)
```

## Data Retention

### Retention Strategy

The service implements a multi-tiered retention strategy:

1. **Raw Data**: 90 days for detailed analysis
2. **Hourly Aggregates**: 365 days for trend analysis  
3. **Daily Aggregates**: 3 years for historical reporting
4. **Audit Logs**: 90 days for compliance

### Automated Cleanup

```sql
-- Example cleanup procedures (run via cron)

-- Clean old raw metrics
DELETE FROM metrics 
WHERE created_at < datetime('now', '-90 days');

-- Clean old hourly aggregates
DELETE FROM metrics_hourly 
WHERE hour_timestamp < datetime('now', '-365 days');

-- Clean old daily aggregates
DELETE FROM metrics_daily 
WHERE date < date('now', '-1095 days');

-- Clean old API usage logs
DELETE FROM api_key_usage_log 
WHERE timestamp < datetime('now', '-90 days');
```

### Retention Policy Management

```python
# Python API for managing retention
from app.storage.database import MetricsStorage

storage = MetricsStorage()

# Update retention policy
await storage.update_retention_policy('metrics', 120)  # 120 days

# Get all policies
policies = await storage.get_retention_policies()

# Apply cleanup based on policies
await storage.apply_retention_cleanup()
```

## Performance Considerations

### Query Optimization

#### Common Query Patterns

```sql
-- Time-range queries (most common)
SELECT * FROM metrics 
WHERE timestamp BETWEEN ? AND ?
  AND service = ?;

-- Aggregation queries
SELECT service, metric_type, COUNT(*), AVG(value)
FROM metrics 
WHERE timestamp > datetime('now', '-1 hour')
GROUP BY service, metric_type;

-- Recent metrics by type
SELECT * FROM auth_metrics
WHERE timestamp > datetime('now', '-5 minutes')
  AND success = 1
ORDER BY timestamp DESC
LIMIT 100;
```

#### Index Strategy

```sql
-- Primary indexes for time-series queries
CREATE INDEX idx_metrics_timestamp ON metrics(timestamp);
CREATE INDEX idx_metrics_service_timestamp ON metrics(service, timestamp);
CREATE INDEX idx_metrics_type_timestamp ON metrics(metric_type, timestamp);

-- Composite indexes for common filters
CREATE INDEX idx_auth_success_timestamp ON auth_metrics(success, timestamp);
CREATE INDEX idx_tool_name_timestamp ON tool_metrics(tool_name, timestamp);

-- Covering indexes for aggregations
CREATE INDEX idx_metrics_service_type_time_value ON metrics(service, metric_type, timestamp, value);
```

### SQLite Optimizations

#### PRAGMA Settings

```sql
-- WAL mode for better concurrency
PRAGMA journal_mode = WAL;

-- Optimize for write performance
PRAGMA synchronous = NORMAL;

-- Large cache for read performance
PRAGMA cache_size = 10000;

-- Memory temp store
PRAGMA temp_store = MEMORY;

-- Auto-vacuum for space management
PRAGMA auto_vacuum = INCREMENTAL;
```

#### Connection Pool Settings

```python
# Connection configuration
SQLITE_CONFIG = {
    'database': '/var/lib/sqlite/metrics.db',
    'timeout': 30.0,
    'isolation_level': None,  # Autocommit mode
    'check_same_thread': False,
    'factory': sqlite3.Row,   # Row factory for dict-like access
}

# Connection pool
connection_pool = aiosqlite.connect(**SQLITE_CONFIG)
```

### Write Performance

#### Batch Processing

```python
# Efficient batch inserts
async def batch_insert_metrics(metrics_batch):
    async with aiosqlite.connect(db_path) as db:
        await db.execute('BEGIN IMMEDIATE')
        try:
            await db.executemany(
                'INSERT INTO metrics (...) VALUES (...)',
                metrics_batch
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
```

#### Prepared Statements

```python
# Reuse prepared statements
INSERT_METRIC = """
    INSERT INTO metrics (
        request_id, service, metric_type, timestamp, 
        value, duration_ms, dimensions, metadata
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

async def insert_metrics(db, metrics):
    await db.executemany(INSERT_METRIC, metrics)
```

### Read Performance

#### Aggregation Queries

```sql
-- Use pre-computed aggregates when possible
SELECT sum_value, avg_value, count
FROM metrics_hourly
WHERE service = 'auth-server'
  AND metric_type = 'auth_request'
  AND hour_timestamp >= '2024-01-01T00:00:00Z';

-- Fallback to raw data for recent metrics
SELECT SUM(value), AVG(value), COUNT(*)
FROM metrics
WHERE service = 'auth-server'
  AND metric_type = 'auth_request'
  AND timestamp >= '2024-01-01T23:00:00Z';
```

#### Query Plan Analysis

```sql
-- Analyze query performance
EXPLAIN QUERY PLAN 
SELECT COUNT(*) FROM metrics 
WHERE timestamp > '2024-01-01T00:00:00Z' 
  AND service = 'auth-server';

-- Expected plan should use index
-- SEARCH TABLE metrics USING INDEX idx_metrics_service_timestamp
```

## Backup and Recovery

### Backup Strategy

#### Hot Backup (Online)

```bash
#!/bin/bash
# hot-backup.sh - SQLite online backup

DB_PATH="/var/lib/sqlite/metrics.db"
BACKUP_PATH="/backups/metrics/$(date +%Y%m%d_%H%M%S).db"

# Use SQLite's online backup API
sqlite3 "$DB_PATH" ".backup $BACKUP_PATH"

# Verify backup integrity
if sqlite3 "$BACKUP_PATH" "PRAGMA integrity_check;" | grep -q "ok"; then
    echo "Backup completed successfully: $BACKUP_PATH"
    gzip "$BACKUP_PATH"
else
    echo "Backup verification failed!"
    rm "$BACKUP_PATH"
    exit 1
fi
```

#### Cold Backup (Offline)

```bash
#!/bin/bash
# cold-backup.sh - File system level backup

systemctl stop metrics-service

# Copy database files
cp /var/lib/sqlite/metrics.db /backups/
cp /var/lib/sqlite/metrics.db-wal /backups/
cp /var/lib/sqlite/metrics.db-shm /backups/

systemctl start metrics-service
```

### Recovery Procedures

#### Point-in-Time Recovery

```bash
# Restore from backup
systemctl stop metrics-service

# Restore database
gunzip -c /backups/metrics/20240101_120000.db.gz > /var/lib/sqlite/metrics.db

# Verify integrity
sqlite3 /var/lib/sqlite/metrics.db "PRAGMA integrity_check;"

# Restart service
systemctl start metrics-service
```

#### Corruption Recovery

```sql
-- Check for corruption
PRAGMA integrity_check;
PRAGMA foreign_key_check;

-- Recover from corruption
.output /tmp/recovery.sql
.dump
.quit

-- Create new database
rm metrics.db
sqlite3 metrics.db < /tmp/recovery.sql
```

### Disaster Recovery

#### Full System Recovery

1. **Provision new server**
2. **Install application**
3. **Restore latest backup**
4. **Apply any missing migrations**
5. **Verify data integrity**
6. **Update DNS/load balancers**

```bash
# Recovery script
#!/bin/bash
set -e

# Download latest backup
aws s3 cp s3://backups/metrics/latest.db.gz ./

# Restore database
gunzip latest.db.gz
mv latest.db /var/lib/sqlite/metrics.db

# Apply migrations
uv run python migrate.py up

# Verify
sqlite3 /var/lib/sqlite/metrics.db "PRAGMA integrity_check;"

# Start service
systemctl start metrics-service
```

This documentation provides a complete reference for understanding and managing the database schema, migrations, and data lifecycle of the MCP Metrics Collection Service.