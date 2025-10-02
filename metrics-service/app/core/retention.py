"""Data retention and cleanup policies for metrics service."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from ..storage.database import MetricsStorage
from ..config import settings
import aiosqlite

logger = logging.getLogger(__name__)


class RetentionPolicy:
    """Represents a data retention policy for a table."""
    
    def __init__(
        self, 
        table_name: str, 
        retention_days: int, 
        is_active: bool = True,
        cleanup_query: Optional[str] = None,
        timestamp_column: str = 'created_at'
    ):
        self.table_name = table_name
        self.retention_days = retention_days
        self.is_active = is_active
        self.cleanup_query = cleanup_query
        self.timestamp_column = timestamp_column
    
    def get_cleanup_query(self) -> str:
        """Get the cleanup query for this policy."""
        if self.cleanup_query:
            return self.cleanup_query
        
        # Default cleanup query
        cutoff_date = f"datetime('now', '-{self.retention_days} days')"
        return f"DELETE FROM {self.table_name} WHERE {self.timestamp_column} < {cutoff_date}"
    
    def get_count_query(self) -> str:
        """Get query to count records that would be deleted."""
        cutoff_date = f"datetime('now', '-{self.retention_days} days')"
        return f"SELECT COUNT(*) FROM {self.table_name} WHERE {self.timestamp_column} < {cutoff_date}"


class RetentionManager:
    """Manages data retention policies and cleanup operations."""
    
    def __init__(self):
        self.storage = MetricsStorage()
        self.policies: Dict[str, RetentionPolicy] = {}
        self._load_default_policies()
    
    def _load_default_policies(self):
        """Load default retention policies."""
        # Raw metrics tables
        self.policies['metrics'] = RetentionPolicy(
            table_name='metrics',
            retention_days=90,
            timestamp_column='created_at'
        )
        
        self.policies['auth_metrics'] = RetentionPolicy(
            table_name='auth_metrics',
            retention_days=90,
            timestamp_column='created_at'
        )
        
        self.policies['discovery_metrics'] = RetentionPolicy(
            table_name='discovery_metrics',
            retention_days=90,
            timestamp_column='created_at'
        )
        
        self.policies['tool_metrics'] = RetentionPolicy(
            table_name='tool_metrics',
            retention_days=90,
            timestamp_column='created_at'
        )
        
        # Aggregated metrics - longer retention
        self.policies['metrics_hourly'] = RetentionPolicy(
            table_name='metrics_hourly',
            retention_days=365,  # 1 year
            timestamp_column='created_at'
        )
        
        self.policies['metrics_daily'] = RetentionPolicy(
            table_name='metrics_daily',
            retention_days=1095,  # 3 years
            timestamp_column='created_at'
        )
        
        # API usage logs
        self.policies['api_key_usage_log'] = RetentionPolicy(
            table_name='api_key_usage_log',
            retention_days=90,
            timestamp_column='created_at'
        )
        
        # Note: api_keys table uses 'created_at', not 'timestamp'
        # Schema_migrations table may not have created_at in all environments
    
    async def load_policies_from_database(self):
        """Load retention policies from database."""
        try:
            async with aiosqlite.connect(self.storage.db_path) as db:
                cursor = await db.execute("""
                    SELECT table_name, retention_days, is_active
                    FROM retention_policies
                    WHERE is_active = 1
                """)
                
                db_policies = await cursor.fetchall()
                
                for row in db_policies:
                    table_name, retention_days, is_active = row
                    
                    # Update existing policy or create new one
                    if table_name in self.policies:
                        self.policies[table_name].retention_days = retention_days
                        self.policies[table_name].is_active = bool(is_active)
                    else:
                        self.policies[table_name] = RetentionPolicy(
                            table_name=table_name,
                            retention_days=retention_days,
                            is_active=bool(is_active)
                        )
                
                logger.info(f"Loaded {len(db_policies)} retention policies from database")
                
        except Exception as e:
            logger.error(f"Failed to load retention policies from database: {e}")
            logger.info("Using default retention policies")
    
    async def save_policies_to_database(self):
        """Save current policies to database."""
        try:
            async with aiosqlite.connect(self.storage.db_path) as db:
                await db.execute("BEGIN TRANSACTION")
                
                for policy in self.policies.values():
                    await db.execute("""
                        INSERT OR REPLACE INTO retention_policies 
                        (table_name, retention_days, is_active, updated_at)
                        VALUES (?, ?, ?, datetime('now'))
                    """, (
                        policy.table_name,
                        policy.retention_days,
                        1 if policy.is_active else 0
                    ))
                
                await db.commit()
                logger.info(f"Saved {len(self.policies)} retention policies to database")
                
        except Exception as e:
            logger.error(f"Failed to save retention policies: {e}")
            raise
    
    async def get_cleanup_preview(self, table_name: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Get preview of what would be cleaned up without actually deleting."""
        preview = {}
        
        policies_to_check = [self.policies[table_name]] if table_name else self.policies.values()
        
        for policy in policies_to_check:
            if not policy.is_active:
                continue
            
            try:
                async with aiosqlite.connect(self.storage.db_path) as db:
                    # Count records to be deleted
                    cursor = await db.execute(policy.get_count_query())
                    count_result = await cursor.fetchone()
                    records_to_delete = count_result[0] if count_result else 0
                    
                    # Get oldest and newest timestamps that would be deleted
                    cutoff_date = f"datetime('now', '-{policy.retention_days} days')"
                    cursor = await db.execute(f"""
                        SELECT 
                            MIN({policy.timestamp_column}) as oldest,
                            MAX({policy.timestamp_column}) as newest
                        FROM {policy.table_name} 
                        WHERE {policy.timestamp_column} < {cutoff_date}
                    """)
                    
                    time_range = await cursor.fetchone()
                    oldest_record = time_range[0] if time_range else None
                    newest_record = time_range[1] if time_range else None
                    
                    # Get total table size
                    cursor = await db.execute(f"SELECT COUNT(*) FROM {policy.table_name}")
                    total_records = (await cursor.fetchone())[0]
                    
                    preview[policy.table_name] = {
                        'retention_days': policy.retention_days,
                        'records_to_delete': records_to_delete,
                        'total_records': total_records,
                        'oldest_record_to_delete': oldest_record,
                        'newest_record_to_delete': newest_record,
                        'cutoff_date': datetime.now() - timedelta(days=policy.retention_days),
                        'percentage_to_delete': (records_to_delete / total_records * 100) if total_records > 0 else 0
                    }
                    
            except Exception as e:
                logger.error(f"Failed to preview cleanup for {policy.table_name}: {e}")
                preview[policy.table_name] = {
                    'error': str(e)
                }
        
        return preview
    
    async def cleanup_table(self, table_name: str, dry_run: bool = False) -> Dict[str, Any]:
        """Clean up a specific table according to its retention policy."""
        if table_name not in self.policies:
            raise ValueError(f"No retention policy found for table: {table_name}")
        
        policy = self.policies[table_name]
        
        if not policy.is_active:
            return {
                'table': table_name,
                'status': 'skipped',
                'reason': 'policy_inactive'
            }
        
        try:
            async with aiosqlite.connect(self.storage.db_path) as db:
                # Get preview first
                cursor = await db.execute(policy.get_count_query())
                count_result = await cursor.fetchone()
                records_to_delete = count_result[0] if count_result else 0
                
                if records_to_delete == 0:
                    return {
                        'table': table_name,
                        'status': 'completed',
                        'records_deleted': 0,
                        'reason': 'no_records_to_delete'
                    }
                
                if dry_run:
                    return {
                        'table': table_name,
                        'status': 'dry_run',
                        'records_would_delete': records_to_delete
                    }
                
                # Execute cleanup
                start_time = datetime.now()
                
                await db.execute("BEGIN IMMEDIATE")
                try:
                    cursor = await db.execute(policy.get_cleanup_query())
                    records_deleted = cursor.rowcount
                    await db.commit()
                    
                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    
                    logger.info(f"Cleaned up {records_deleted} records from {table_name} in {duration:.2f}s")
                    
                    return {
                        'table': table_name,
                        'status': 'completed',
                        'records_deleted': records_deleted,
                        'duration_seconds': duration,
                        'retention_days': policy.retention_days
                    }
                    
                except Exception as e:
                    await db.rollback()
                    raise e
                    
        except Exception as e:
            logger.error(f"Failed to cleanup table {table_name}: {e}")
            return {
                'table': table_name,
                'status': 'error',
                'error': str(e)
            }
    
    async def cleanup_all_tables(self, dry_run: bool = False) -> Dict[str, Any]:
        """Run cleanup on all tables with active retention policies."""
        results = {}
        total_deleted = 0
        start_time = datetime.now()
        
        logger.info(f"Starting {'dry run' if dry_run else 'cleanup'} for all tables")
        
        for policy in self.policies.values():
            if not policy.is_active:
                continue
            
            result = await self.cleanup_table(policy.table_name, dry_run)
            results[policy.table_name] = result
            
            if result['status'] == 'completed' and 'records_deleted' in result:
                total_deleted += result['records_deleted']
        
        # Run VACUUM after cleanup to reclaim space
        if not dry_run and total_deleted > 0:
            try:
                async with aiosqlite.connect(self.storage.db_path) as db:
                    logger.info("Running VACUUM to reclaim disk space...")
                    await db.execute("VACUUM")
                    logger.info("VACUUM completed successfully")
            except Exception as e:
                logger.error(f"Failed to run VACUUM: {e}")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        summary = {
            'operation': 'dry_run' if dry_run else 'cleanup',
            'total_records_processed': total_deleted,
            'tables_processed': len([r for r in results.values() if r['status'] in ['completed', 'dry_run']]),
            'duration_seconds': duration,
            'started_at': start_time.isoformat(),
            'completed_at': end_time.isoformat(),
            'table_results': results
        }
        
        logger.info(f"Cleanup {'dry run' if dry_run else 'operation'} completed: "
                   f"{total_deleted} records processed in {duration:.2f}s")
        
        return summary
    
    async def update_policy(self, table_name: str, retention_days: int, is_active: bool = True):
        """Update retention policy for a table."""
        if table_name in self.policies:
            self.policies[table_name].retention_days = retention_days
            self.policies[table_name].is_active = is_active
        else:
            self.policies[table_name] = RetentionPolicy(
                table_name=table_name,
                retention_days=retention_days,
                is_active=is_active
            )
        
        # Save to database
        await self.save_policies_to_database()
        logger.info(f"Updated retention policy for {table_name}: {retention_days} days, active: {is_active}")
    
    async def get_table_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get storage statistics for all tables."""
        stats = {}
        
        try:
            async with aiosqlite.connect(self.storage.db_path) as db:
                # Get all table names
                cursor = await db.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                tables = await cursor.fetchall()
                
                for (table_name,) in tables:
                    try:
                        # Get record count
                        cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
                        count = (await cursor.fetchone())[0]
                        
                        # Get approximate size
                        cursor = await db.execute(f"""
                            SELECT 
                                COUNT(*) as records,
                                COALESCE(
                                    (SELECT MIN(created_at) FROM {table_name} WHERE created_at IS NOT NULL), 
                                    (SELECT MIN(timestamp) FROM {table_name} WHERE timestamp IS NOT NULL)
                                ) as oldest_record,
                                COALESCE(
                                    (SELECT MAX(created_at) FROM {table_name} WHERE created_at IS NOT NULL),
                                    (SELECT MAX(timestamp) FROM {table_name} WHERE timestamp IS NOT NULL)
                                ) as newest_record
                        """)
                        
                        result = await cursor.fetchone()
                        
                        stats[table_name] = {
                            'record_count': count,
                            'oldest_record': result[1] if result else None,
                            'newest_record': result[2] if result else None,
                            'has_retention_policy': table_name in self.policies,
                            'retention_days': self.policies[table_name].retention_days if table_name in self.policies else None,
                            'policy_active': self.policies[table_name].is_active if table_name in self.policies else None
                        }
                        
                    except Exception as e:
                        logger.warning(f"Failed to get stats for table {table_name}: {e}")
                        stats[table_name] = {'error': str(e)}
                        
        except Exception as e:
            logger.error(f"Failed to get table statistics: {e}")
            raise
        
        return stats
    
    async def get_database_size(self) -> Dict[str, Any]:
        """Get database file size information."""
        try:
            import os
            db_path = self.storage.db_path
            
            size_info = {}
            
            if os.path.exists(db_path):
                # Main database file
                size_info['main_db_bytes'] = os.path.getsize(db_path)
                size_info['main_db_mb'] = round(size_info['main_db_bytes'] / 1024 / 1024, 2)
                
                # WAL file
                wal_path = db_path + '-wal'
                if os.path.exists(wal_path):
                    size_info['wal_bytes'] = os.path.getsize(wal_path)
                    size_info['wal_mb'] = round(size_info['wal_bytes'] / 1024 / 1024, 2)
                else:
                    size_info['wal_bytes'] = 0
                    size_info['wal_mb'] = 0
                
                # SHM file
                shm_path = db_path + '-shm'
                if os.path.exists(shm_path):
                    size_info['shm_bytes'] = os.path.getsize(shm_path)
                    size_info['shm_mb'] = round(size_info['shm_bytes'] / 1024 / 1024, 2)
                else:
                    size_info['shm_bytes'] = 0
                    size_info['shm_mb'] = 0
                
                # Total size
                total_bytes = size_info['main_db_bytes'] + size_info['wal_bytes'] + size_info['shm_bytes']
                size_info['total_bytes'] = total_bytes
                size_info['total_mb'] = round(total_bytes / 1024 / 1024, 2)
                size_info['total_gb'] = round(total_bytes / 1024 / 1024 / 1024, 3)
                
            else:
                size_info = {'error': 'Database file not found'}
            
            # Get SQLite page info
            async with aiosqlite.connect(self.storage.db_path) as db:
                cursor = await db.execute("PRAGMA page_count")
                page_count = (await cursor.fetchone())[0]
                
                cursor = await db.execute("PRAGMA page_size")
                page_size = (await cursor.fetchone())[0]
                
                cursor = await db.execute("PRAGMA freelist_count")
                free_pages = (await cursor.fetchone())[0]
                
                size_info['page_count'] = page_count
                size_info['page_size'] = page_size
                size_info['free_pages'] = free_pages
                size_info['used_pages'] = page_count - free_pages
                size_info['database_efficiency'] = round((size_info['used_pages'] / page_count * 100), 2) if page_count > 0 else 0
            
            return size_info
            
        except Exception as e:
            logger.error(f"Failed to get database size: {e}")
            return {'error': str(e)}


# Global retention manager instance
retention_manager = RetentionManager()