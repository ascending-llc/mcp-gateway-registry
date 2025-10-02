#!/usr/bin/env python3
"""Add a test API key to the database"""
import asyncio
import aiosqlite
import sys
from pathlib import Path

async def add_test_key():
    db_path = "/var/lib/sqlite/metrics.db"
    key_hash = "1f8e8c97805e4ad56c611029fbba4c04dab40bf05d18c46655696357705cc136"  # hash of "test_key_123"
    
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO api_keys (key_hash, service_name, created_at, is_active)
            VALUES (?, ?, datetime('now'), 1)
        """, (key_hash, "test-service"))
        await db.commit()
        print(f"Added test API key for service: test-service")
        print(f"API Key: test_key_123")
        print(f"Key Hash: {key_hash}")

if __name__ == "__main__":
    asyncio.run(add_test_key())