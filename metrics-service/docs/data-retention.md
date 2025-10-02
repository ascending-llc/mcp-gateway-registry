# Data Retention and Cleanup

This document provides comprehensive guidance on the data retention and cleanup system for the MCP Metrics Collection Service.

## Table of Contents

- [Overview](#overview)
- [Retention Policies](#retention-policies)
- [API Reference](#api-reference)
- [Background Tasks](#background-tasks)
- [Configuration](#configuration)
- [Operations Guide](#operations-guide)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

## Overview

The data retention system automatically manages the lifecycle of metrics data by:

- **Automated Cleanup**: Daily background tasks remove old data based on retention policies
- **Configurable Policies**: Different retention periods for raw vs. aggregated data
- **Safe Operations**: Dry-run capabilities and atomic transactions
- **Space Reclamation**: Automatic VACUUM operations after cleanup
- **Administrative APIs**: Full control over policies and cleanup operations

### Key Benefits

- **Storage Optimization**: Prevents unbounded database growth
- **Performance Maintenance**: Keeps query performance optimal by managing table sizes
- **Compliance Support**: Configurable retention periods for data governance requirements
- **Operational Safety**: Preview and dry-run capabilities before actual cleanup

## Retention Policies

### Default Policies

The service comes with predefined retention policies optimized for different data types:

```python
# Raw metrics - shorter retention
metrics: 90 days
auth_metrics: 90 days  
discovery_metrics: 90 days
tool_metrics: 90 days

# Aggregated metrics - longer retention
metrics_hourly: 365 days (1 year)
metrics_daily: 1095 days (3 years)

# System data
api_key_usage_log: 90 days
```

### Policy Configuration

Each retention policy consists of:

| Property | Description | Default |
|----------|-------------|---------|
| `table_name` | Target table name | Required |
| `retention_days` | Days to retain data | Required |
| `is_active` | Whether policy is enabled | `true` |
| `timestamp_column` | Column for age calculation | `created_at` |
| `cleanup_query` | Custom cleanup SQL | Auto-generated |

### Policy Types

#### Standard Policies
Use automatic cleanup queries based on timestamp columns:
```sql
DELETE FROM {table_name} WHERE {timestamp_column} < datetime('now', '-{retention_days} days')
```

#### Custom Policies
Define specific cleanup logic for complex scenarios:
```python
RetentionPolicy(
    table_name="complex_metrics",
    retention_days=30,
    cleanup_query="DELETE FROM complex_metrics WHERE status = 'processed' AND created_at < datetime('now', '-30 days')"
)
```

## API Reference

### Preview Cleanup Operations

Get a preview of what would be cleaned up without executing the operation.

```http
GET /admin/retention/preview?table_name={table}
X-API-Key: your-api-key
```

**Parameters:**
- `table_name` (optional): Specific table to preview, or all tables if omitted

**Response:**
```json
{
  "metrics": {
    "retention_days": 90,
    "records_to_delete": 1250,
    "total_records": 5000,
    "oldest_record_to_delete": "2024-01-01T00:00:00Z",
    "newest_record_to_delete": "2024-03-15T23:59:59Z",
    "cutoff_date": "2024-06-15T00:00:00Z",
    "percentage_to_delete": 25.0
  }
}
```

### Execute Cleanup

Run data cleanup operations with optional dry-run mode.

```http
POST /admin/retention/cleanup
X-API-Key: your-api-key
Content-Type: application/json

{
  "table_name": "metrics",  // Optional: specific table
  "dry_run": false          // Optional: default true
}
```

**Response (Single Table):**
```json
{
  "table": "metrics",
  "status": "completed",
  "records_deleted": 1250,
  "duration_seconds": 2.34,
  "retention_days": 90
}
```

**Response (All Tables):**
```json
{
  "operation": "cleanup",
  "total_records_processed": 3500,
  "tables_processed": 5,
  "duration_seconds": 8.92,
  "started_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:00:08Z",
  "table_results": {
    "metrics": {
      "status": "completed",
      "records_deleted": 1250
    },
    "auth_metrics": {
      "status": "completed", 
      "records_deleted": 2250
    }
  }
}
```

### Manage Retention Policies

#### View Current Policies

```http
GET /admin/retention/policies
X-API-Key: your-api-key
```

**Response:**
```json
{
  "metrics": {
    "table_name": "metrics",
    "retention_days": 90,
    "is_active": true,
    "timestamp_column": "created_at"
  },
  "metrics_hourly": {
    "table_name": "metrics_hourly", 
    "retention_days": 365,
    "is_active": true,
    "timestamp_column": "created_at"
  }
}
```

#### Update Policy

```http
PUT /admin/retention/policies/metrics
X-API-Key: your-api-key
Content-Type: application/json

{
  "retention_days": 120,
  "is_active": true
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Updated retention policy for metrics",
  "table_name": "metrics",
  "retention_days": 120,
  "is_active": true
}
```

### Database Statistics

#### Table Statistics

Get detailed statistics for all tables:

```http
GET /admin/database/stats  
X-API-Key: your-api-key
```

**Response:**
```json
{
  "metrics": {
    "record_count": 50000,
    "oldest_record": "2024-01-01T00:00:00Z",
    "newest_record": "2024-06-15T23:59:59Z", 
    "has_retention_policy": true,
    "retention_days": 90,
    "policy_active": true
  },
  "auth_metrics": {
    "record_count": 25000,
    "oldest_record": "2024-02-01T00:00:00Z",
    "newest_record": "2024-06-15T23:59:59Z",
    "has_retention_policy": true,
    "retention_days": 90,
    "policy_active": true
  }
}
```

#### Database Size Information

Get comprehensive database size metrics:

```http
GET /admin/database/size
X-API-Key: your-api-key
```

**Response:**
```json
{
  "main_db_bytes": 104857600,
  "main_db_mb": 100.0,
  "wal_bytes": 1048576,
  "wal_mb": 1.0,
  "shm_bytes": 32768,
  "shm_mb": 0.03,
  "total_bytes": 105938944,
  "total_mb": 101.03,
  "total_gb": 0.099,
  "page_count": 25600,
  "page_size": 4096,
  "free_pages": 128,
  "used_pages": 25472,
  "database_efficiency": 99.5
}
```

## Background Tasks

### Automatic Cleanup Task

The service runs a daily background task for automatic data cleanup:

```python
async def retention_cleanup_task():
    """Background task to run data retention cleanup."""
    while True:
        try:
            await asyncio.sleep(86400)  # Run once per day (24 hours)
            logger.info("Starting scheduled data retention cleanup...")
            result = await retention_manager.cleanup_all_tables(dry_run=False)
            
            total_deleted = result.get('total_records_processed', 0)
            duration = result.get('duration_seconds', 0)
            
            if total_deleted > 0:
                logger.info(f"Retention cleanup completed: {total_deleted} records deleted in {duration:.2f}s")
            else:
                logger.info("Retention cleanup completed: no records to delete")
                
        except Exception as e:
            logger.error(f"Error in retention cleanup task: {e}")
            await asyncio.sleep(3600)  # Wait an hour before retry
```

### Task Characteristics

- **Frequency**: Every 24 hours
- **Execution**: Non-blocking background operation
- **Error Handling**: Automatic retry with exponential backoff
- **Logging**: Comprehensive operation logging
- **Safety**: Uses configured retention policies only

### Manual Task Control

Start manual cleanup outside of scheduled runs:

```bash
# Using API
curl -X POST http://localhost:8890/admin/retention/cleanup \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'

# Using Python directly
uv run python -c "
import asyncio
from app.core.retention import retention_manager

async def main():
    result = await retention_manager.cleanup_all_tables(dry_run=False)
    print(f'Cleaned up {result[\"total_records_processed\"]} records')

asyncio.run(main())
"
```

## Configuration

### Environment Variables

Configure retention behavior through environment variables:

```bash
# Default retention period (days)
METRICS_RETENTION_DAYS=90

# Background task frequency (seconds)
RETENTION_CLEANUP_INTERVAL=86400

# Enable/disable automatic cleanup
RETENTION_CLEANUP_ENABLED=true

# Database vacuum after cleanup
RETENTION_VACUUM_ENABLED=true
```

### Database Configuration

Retention policies are stored in the `retention_policies` table:

```sql
CREATE TABLE retention_policies (
    table_name TEXT PRIMARY KEY,
    retention_days INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    cleanup_query TEXT,
    timestamp_column TEXT DEFAULT 'created_at',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Policy Management

#### Add New Policy

```python
from app.core.retention import retention_manager

await retention_manager.update_policy(
    table_name="custom_metrics",
    retention_days=60,
    is_active=True
)
```

#### Disable Policy

```python
await retention_manager.update_policy(
    table_name="important_metrics", 
    retention_days=365,
    is_active=False  # Disable cleanup
)
```

## Operations Guide

### Daily Operations

#### Morning Check
Review overnight cleanup results:

```bash
# Check recent cleanup logs
docker logs metrics-service | grep "retention cleanup"

# Get current database size
curl -H "X-API-Key: $API_KEY" http://localhost:8890/admin/database/size
```

#### Weekly Review
Analyze retention effectiveness:

```bash
# Get table statistics
curl -H "X-API-Key: $API_KEY" http://localhost:8890/admin/database/stats

# Preview next cleanup
curl -H "X-API-Key: $API_KEY" http://localhost:8890/admin/retention/preview
```

### Emergency Procedures

#### Immediate Space Reclamation

When database size becomes critical:

```bash
# 1. Emergency cleanup (shorter retention)
curl -X PUT http://localhost:8890/admin/retention/policies/metrics \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"retention_days": 30, "is_active": true}'

# 2. Execute immediate cleanup
curl -X POST http://localhost:8890/admin/retention/cleanup \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'

# 3. Manual VACUUM for maximum space reclamation
uv run python -c "
import asyncio
import aiosqlite
from app.config import settings

async def vacuum():
    async with aiosqlite.connect(settings.SQLITE_DB_PATH) as db:
        await db.execute('VACUUM')
    print('VACUUM completed')

asyncio.run(vacuum())
"
```

#### Disable All Cleanup

In case of data issues:

```bash
# Disable all policies
for table in metrics auth_metrics discovery_metrics tool_metrics; do
  curl -X PUT http://localhost:8890/admin/retention/policies/$table \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"retention_days": 999, "is_active": false}'
done
```

### Maintenance Windows

#### Pre-Maintenance
```bash
# 1. Preview cleanup scope
curl -H "X-API-Key: $API_KEY" http://localhost:8890/admin/retention/preview

# 2. Backup critical data if needed
sqlite3 /var/lib/sqlite/metrics.db ".backup /backup/metrics_$(date +%Y%m%d).db"

# 3. Execute cleanup
curl -X POST http://localhost:8890/admin/retention/cleanup \
  -H "X-API-Key: $API_KEY" \
  -d '{"dry_run": false}'
```

#### Post-Maintenance
```bash
# 1. Verify cleanup results
curl -H "X-API-Key: $API_KEY" http://localhost:8890/admin/database/stats

# 2. Check database integrity
uv run python -c "
import asyncio
import aiosqlite
from app.config import settings

async def check():
    async with aiosqlite.connect(settings.SQLITE_DB_PATH) as db:
        result = await db.execute('PRAGMA integrity_check')
        print(await result.fetchone())

asyncio.run(check())
"
```

## Monitoring

### Key Metrics to Monitor

#### Database Size Trends
```bash
# Daily size tracking
curl -s -H "X-API-Key: $API_KEY" http://localhost:8890/admin/database/size | \
  jq '{date: now | todateiso8601, size_mb: .total_mb, efficiency: .database_efficiency}'
```

#### Cleanup Effectiveness
```bash
# Records deleted per cleanup
grep "retention cleanup completed" /var/log/metrics-service.log | \
  tail -7 | sed 's/.*: \([0-9]*\) records.*/\1/'
```

#### Policy Compliance
```bash
# Tables exceeding retention period
curl -s -H "X-API-Key: $API_KEY" http://localhost:8890/admin/retention/preview | \
  jq 'to_entries[] | select(.value.records_to_delete > 0) | {table: .key, overdue: .value.records_to_delete}'
```

### Alerting Rules

#### Prometheus Alerts

```yaml
# Database size growth
- alert: DatabaseSizeGrowth
  expr: increase(database_size_bytes[24h]) > 100MB
  labels:
    severity: warning
  annotations:
    summary: "Database growing faster than expected"

# Cleanup failures  
- alert: RetentionCleanupFailed
  expr: increase(retention_cleanup_errors_total[24h]) > 0
  labels:
    severity: critical
  annotations:
    summary: "Data retention cleanup failing"

# Large cleanup operations
- alert: LargeCleanupOperation
  expr: retention_records_deleted > 100000
  labels:
    severity: info
  annotations:
    summary: "Large cleanup operation detected"
```

#### Log-Based Alerts

```bash
# Setup log monitoring for cleanup failures
tail -f /var/log/metrics-service.log | grep -E "(ERROR|CRITICAL).*retention" | \
  while read line; do
    echo "ALERT: Retention system error - $line"
    # Send notification
  done
```

### Performance Impact

#### Cleanup Operation Metrics
- **Duration**: Typical cleanup takes 1-10 seconds per 10K records
- **I/O Impact**: Moderate during cleanup, high during VACUUM
- **CPU Usage**: Low-moderate during operation
- **Memory Usage**: Minimal additional memory required

#### Optimization Tips
- **Schedule During Low Traffic**: Run cleanup during off-peak hours
- **Batch Size Tuning**: Adjust retention periods to avoid massive single cleanups  
- **Index Maintenance**: Ensure timestamp columns are indexed
- **WAL Mode**: Use WAL mode for concurrent operations during cleanup

## Troubleshooting

### Common Issues

#### Cleanup Not Running

**Symptoms:**
- Database size keeps growing
- No cleanup logs in recent history
- Old data still present

**Diagnosis:**
```bash
# Check if policies are active
curl -H "X-API-Key: $API_KEY" http://localhost:8890/admin/retention/policies | \
  jq '.[] | select(.is_active == false)'

# Check background task status
docker logs metrics-service | grep -E "(retention|cleanup)" | tail -10

# Manual cleanup test
curl -X POST http://localhost:8890/admin/retention/cleanup \
  -H "X-API-Key: $API_KEY" \
  -d '{"dry_run": true}'
```

**Solutions:**
- Enable inactive policies
- Restart service if background task stopped
- Check for blocking database locks

#### Cleanup Errors

**Symptoms:**
- Error logs during cleanup operations
- Partial cleanup results
- Database integrity issues

**Diagnosis:**
```bash
# Check recent errors
grep -E "(ERROR|exception).*retention" /var/log/metrics-service.log | tail -5

# Test database connectivity
uv run python -c "
import asyncio
import aiosqlite
from app.config import settings

async def test():
    try:
        async with aiosqlite.connect(settings.SQLITE_DB_PATH) as db:
            await db.execute('SELECT 1')
            print('Database connection OK')
    except Exception as e:
        print(f'Database error: {e}')

asyncio.run(test())
"

# Check database integrity
sqlite3 /var/lib/sqlite/metrics.db "PRAGMA integrity_check"
```

**Solutions:**
- Fix database permissions
- Resolve disk space issues
- Repair database corruption if found

#### Performance Issues

**Symptoms:**
- Slow cleanup operations
- High CPU/I/O during cleanup
- Service timeouts

**Diagnosis:**
```bash
# Check table sizes
curl -H "X-API-Key: $API_KEY" http://localhost:8890/admin/database/stats | \
  jq 'to_entries[] | {table: .key, records: .value.record_count}' | \
  sort -k2 -nr

# Monitor cleanup duration
curl -X POST http://localhost:8890/admin/retention/cleanup \
  -H "X-API-Key: $API_KEY" \
  -d '{"table_name": "metrics", "dry_run": true}' | \
  jq '.duration_seconds'
```

**Solutions:**
- Add indexes on timestamp columns
- Implement incremental cleanup
- Adjust retention periods to reduce batch sizes

### Recovery Procedures

#### Restore from Backup

If cleanup removes needed data:

```bash
# 1. Stop service
docker stop metrics-service

# 2. Restore database
cp /backup/metrics_YYYYMMDD.db /var/lib/sqlite/metrics.db

# 3. Adjust retention policies before restart
sqlite3 /var/lib/sqlite/metrics.db "
UPDATE retention_policies 
SET retention_days = retention_days * 2
WHERE table_name IN ('metrics', 'auth_metrics');
"

# 4. Restart service
docker start metrics-service
```

#### Reset Retention System

To completely reset retention configuration:

```bash
# 1. Clear all policies
sqlite3 /var/lib/sqlite/metrics.db "DELETE FROM retention_policies;"

# 2. Restart service (will reload defaults)
docker restart metrics-service

# 3. Verify default policies loaded
curl -H "X-API-Key: $API_KEY" http://localhost:8890/admin/retention/policies
```

### Debug Mode

Enable detailed retention logging:

```bash
# Add to environment
export RETENTION_DEBUG=true
export LOG_LEVEL=DEBUG

# Restart service
docker restart metrics-service

# Monitor detailed logs
docker logs -f metrics-service | grep retention
```

This comprehensive documentation provides all the information needed to effectively manage the data retention system in production environments.