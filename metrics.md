MCP Gateway Registry - Metrics Collection Service Design
Overview
This document outlines the design for a standalone metrics collection microservice that receives metrics from various MCP Gateway Registry components via HTTP API, stores them in SQLite, and emits them to OpenTelemetry exporters.

Architecture Overview
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Auth Server   │    │ Registry Service│    │ MCP Servers     │
│                 │    │                 │    │ (mcpgw, etc.)   │
└─────┬───────────┘    └─────┬───────────┘    └─────┬───────────┘
      │ HTTP POST            │ HTTP POST            │ HTTP POST
      │ /metrics             │ /metrics             │ /metrics
      │                      │                      │
      └──────────────────────┼──────────────────────┘
                             │
             ┌───────────────▼────────────────┐
             │    Metrics Collection Service  │
             │         (Standalone)           │
             ├────────────┬───────────────────┤
             │ REST API   │ OTel Exporters    │
             │ Validation │ SQLite Storage    │
             │ Auth       │ Background Tasks  │
             └────────────┴───────────────────┘
                      │         │
          ┌───────────▼─┐   ┌───▼──────────┐
          │ OpenTel     │   │ SQLite DB    │
          │ Exporters   │   │ (Analytics)  │
          │ (Prometheus,│   │              │
          │  OTLP, etc.)│   │              │
          └─────────────┘   └──────────────┘
Service Design
Core Components
1. HTTP API Layer (api/)
Single /metrics POST endpoint for all metric types
API key authentication
Request validation and rate limiting
Async request handling with FastAPI
2. Metrics Processing (core/)
Metric type detection and validation
Data normalization and enrichment
Dual emission: OTel + SQLite storage
Background batch processing
3. Storage Layer (storage/)
SQLite database with optimized schema
Async operations with aiosqlite
Data retention and cleanup policies
Performance indexes
4. OpenTelemetry Integration (otel/)
Multiple exporter support (Prometheus, OTLP)
Standard metric instruments (counters, histograms, gauges)
Proper labeling and dimensions
REST API Specification
Endpoint: POST /metrics
Authentication
Header: X-API-Key: <api_key>
Validation: Against configured API keys in database
Rate Limiting: 1000 requests/minute per API key
Request Format
{
  "service": "auth-server",           // Required: service identifier
  "version": "1.0.0",                // Optional: service version  
  "instance_id": "auth-01",          // Optional: instance identifier
  "metrics": [                       // Required: array of metrics
    {
      "type": "auth_request",         // Required: metric type
      "timestamp": "2024-01-15T10:30:00Z", // Optional: defaults to now
      "value": 1.0,                   // Required: metric value
      "duration_ms": 45.2,            // Optional: operation duration
      "dimensions": {                 // Optional: labels/tags
        "method": "jwt",
        "success": true,
        "server": "mcpgw",
        "user_hash": "user_abc123"
      },
      "metadata": {                   // Optional: additional context
        "error_code": null,
        "request_size": 1024,
        "response_size": 512
      }
    }
  ]
}
Response Format
{
  "status": "success",
  "accepted": 1,
  "rejected": 0,
  "errors": [],
  "request_id": "req_abc123"
}
Error Responses
{
  "status": "error",
  "error": "invalid_api_key",
  "message": "API key is invalid or expired",
  "request_id": "req_abc123"
}
Data Models
Metric Types and Schemas
# core/models.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum

class MetricType(str, Enum):
    AUTH_REQUEST = "auth_request"
    TOOL_DISCOVERY = "tool_discovery"  
    TOOL_EXECUTION = "tool_execution"
    REGISTRY_OPERATION = "registry_operation"
    HEALTH_CHECK = "health_check"
    CUSTOM = "custom"

class MetricRequest(BaseModel):
    service: str = Field(..., max_length=50)
    version: Optional[str] = Field(None, max_length=20)
    instance_id: Optional[str] = Field(None, max_length=50)
    metrics: List['Metric']

class Metric(BaseModel):
    type: MetricType
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)
    value: float
    duration_ms: Optional[float] = None
    dimensions: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class MetricResponse(BaseModel):
    status: str
    accepted: int
    rejected: int
    errors: List[str] = []
    request_id: str
SQLite Database Schema
-- Database: metrics.db

-- API Keys table
CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT UNIQUE NOT NULL,
    service_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    is_active BOOLEAN DEFAULT 1,
    rate_limit INTEGER DEFAULT 1000
);

-- Main metrics table (partitioned by type for performance)
CREATE TABLE metrics (
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
    created_at TEXT DEFAULT (datetime('now')),
    INDEX(timestamp),
    INDEX(service, metric_type),
    INDEX(metric_type, timestamp)
);

-- Specialized tables for high-volume metrics
CREATE TABLE auth_metrics (
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
    created_at TEXT DEFAULT (datetime('now')),
    INDEX(timestamp),
    INDEX(success, timestamp),
    INDEX(user_hash, timestamp)
);

CREATE TABLE discovery_metrics (
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
    created_at TEXT DEFAULT (datetime('now')),
    INDEX(timestamp),
    INDEX(results_count, timestamp)
);

CREATE TABLE tool_metrics (
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
    created_at TEXT DEFAULT (datetime('now')),
    INDEX(timestamp),
    INDEX(tool_name, timestamp),
    INDEX(success, timestamp)
);
Enhanced Database Implementation for Container Integration
# app/storage/database.py
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

async def init_database():
    """Initialize database tables and indexes."""
    db_path = settings.SQLITE_DB_PATH
    
    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    async with aiosqlite.connect(db_path) as db:
        # Enable WAL mode for better concurrency in container
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=10000")
        await db.execute("PRAGMA temp_store=MEMORY")
        
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
                    error_code, input_size_bytes, output_size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                metric.metadata.get('output_size_bytes')
            ))
Service Implementation
Project Structure
metrics-service/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration settings
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py        # API endpoints
│   │   └── auth.py          # API key authentication
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py        # Pydantic models
│   │   ├── processor.py     # Metrics processing logic
│   │   └── validator.py     # Data validation
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py      # SQLite operations
│   │   └── migrations.py    # Schema migrations
│   ├── otel/
│   │   ├── __init__.py
│   │   ├── exporters.py     # OTel configuration
│   │   └── instruments.py   # Metric instruments
│   └── utils/
│       ├── __init__.py
│       └── helpers.py       # Utility functions
├── pyproject.toml
├── .env.example
└── README.md
Core Service Implementation
# app/main.py
from fastapi import FastAPI, HTTPException, Depends
from contextlib import asynccontextmanager
import logging
import asyncio
from .config import settings
from .api.routes import router as api_router
from .storage.database import init_database, wait_for_database
from .otel.exporters import setup_otel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Starting Metrics Collection Service...")
    
    # Wait for database container to be ready
    logger.info("Waiting for database container...")
    await wait_for_database()
    logger.info("Database container is ready")
    
    # Initialize database
    await init_database()
    logger.info("Database initialized")
    
    # Setup OpenTelemetry
    setup_otel()
    logger.info("OpenTelemetry configured")
    
    yield
    
    logger.info("Shutting down Metrics Collection Service")

app = FastAPI(
    title="MCP Metrics Collection Service",
    description="Centralized metrics collection for MCP Gateway Registry components",
    version="1.0.0",
    lifespan=lifespan
)

# Include API routes
app.include_router(api_router)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "metrics-collection"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8890)
# app/api/routes.py
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer
from typing import List
import uuid
import logging
from ..core.models import MetricRequest, MetricResponse
from ..core.processor import MetricsProcessor
from ..api.auth import verify_api_key

router = APIRouter()
logger = logging.getLogger(__name__)
processor = MetricsProcessor()

@router.post("/metrics", response_model=MetricResponse)
async def collect_metrics(
    request: MetricRequest,
    api_key: str = Depends(verify_api_key)
):
    """Collect metrics from MCP components."""
    request_id = f"req_{uuid.uuid4().hex[:8]}"
    
    try:
        # Process metrics
        result = await processor.process_metrics(request, request_id, api_key)
        
        logger.info(f"Processed {result.accepted} metrics from {request.service}")
        
        return MetricResponse(
            status="success",
            accepted=result.accepted,
            rejected=result.rejected,
            errors=result.errors,
            request_id=request_id
        )
        
    except Exception as e:
        logger.error(f"Error processing metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
# app/core/processor.py
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from opentelemetry import metrics
from ..core.models import MetricRequest, Metric, MetricType
from ..storage.database import MetricsStorage
from ..otel.instruments import MetricsInstruments

class ProcessingResult:
    def __init__(self):
        self.accepted = 0
        self.rejected = 0
        self.errors = []

class MetricsProcessor:
    """Core metrics processing engine."""
    
    def __init__(self):
        self.storage = MetricsStorage()
        self.otel = MetricsInstruments()
        self._buffer = []
        self._buffer_lock = asyncio.Lock()
        
    async def process_metrics(
        self, 
        request: MetricRequest, 
        request_id: str, 
        api_key: str
    ) -> ProcessingResult:
        """Process incoming metrics request."""
        result = ProcessingResult()
        
        for metric in request.metrics:
            try:
                # Validate metric
                if not self._validate_metric(metric):
                    result.rejected += 1
                    result.errors.append(f"Invalid metric: {metric.type}")
                    continue
                
                # Emit to OpenTelemetry
                await self._emit_to_otel(metric, request.service)
                
                # Store in SQLite (buffered)
                await self._buffer_for_storage(
                    metric, request, request_id
                )
                
                result.accepted += 1
                
            except Exception as e:
                result.rejected += 1
                result.errors.append(f"Error processing metric: {str(e)}")
        
        return result
    
    def _validate_metric(self, metric: Metric) -> bool:
        """Validate metric data."""
        if metric.value is None:
            return False
        if metric.type not in MetricType:
            return False
        return True
    
    async def _emit_to_otel(self, metric: Metric, service: str):
        """Emit metric to OpenTelemetry instruments."""
        labels = {
            "service": service,
            "metric_type": metric.type.value,
            **{k: str(v) for k, v in metric.dimensions.items()}
        }
        
        # Route to appropriate OTel instrument
        if metric.type == MetricType.AUTH_REQUEST:
            self.otel.auth_counter.add(metric.value, labels)
            if metric.duration_ms:
                self.otel.auth_histogram.record(metric.duration_ms / 1000, labels)
                
        elif metric.type == MetricType.TOOL_DISCOVERY:
            self.otel.discovery_counter.add(metric.value, labels)
            if metric.duration_ms:
                self.otel.discovery_histogram.record(metric.duration_ms / 1000, labels)
                
        elif metric.type == MetricType.TOOL_EXECUTION:
            self.otel.tool_counter.add(metric.value, labels)
            if metric.duration_ms:
                self.otel.tool_histogram.record(metric.duration_ms / 1000, labels)
    
    async def _buffer_for_storage(
        self, 
        metric: Metric, 
        request: MetricRequest, 
        request_id: str
    ):
        """Buffer metric for batch SQLite storage."""
        async with self._buffer_lock:
            self._buffer.append({
                'metric': metric,
                'request': request,
                'request_id': request_id
            })
            
            # Flush buffer if it's full
            if len(self._buffer) >= 100:
                await self._flush_buffer()
    
    async def _flush_buffer(self):
        """Flush buffered metrics to SQLite."""
        if not self._buffer:
            return
            
        buffer_copy = self._buffer.copy()
        self._buffer.clear()
        
        await self.storage.store_metrics_batch(buffer_copy)
Auth Server Integration Example
Auth Server Changes
# auth_server/metrics_client.py
import httpx
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class MetricsClient:
    """HTTP client for sending metrics to collection service."""
    
    def __init__(
        self, 
        metrics_url: str = "http://localhost:8890",
        api_key: str = None,
        service_name: str = "auth-server",
        timeout: float = 5.0
    ):
        self.metrics_url = f"{metrics_url}/metrics"
        self.api_key = api_key
        self.service_name = service_name
        self.timeout = timeout
        self._client = None
    
    async def _get_client(self):
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def emit_auth_metric(
        self,
        success: bool,
        method: str,
        duration_ms: float,
        server_name: Optional[str] = None,
        user_hash: Optional[str] = None,
        error_code: Optional[str] = None
    ):
        """Emit authentication metric."""
        try:
            client = await self._get_client()
            
            payload = {
                "service": self.service_name,
                "version": "1.0.0",
                "metrics": [{
                    "type": "auth_request",
                    "timestamp": datetime.utcnow().isoformat(),
                    "value": 1.0,
                    "duration_ms": duration_ms,
                    "dimensions": {
                        "success": success,
                        "method": method,
                        "server": server_name or "unknown",
                        "user_hash": user_hash or ""
                    },
                    "metadata": {
                        "error_code": error_code
                    }
                }]
            }
            
            headers = {"X-API-Key": self.api_key}
            
            response = await client.post(
                self.metrics_url,
                json=payload,
                headers=headers
            )
            
            if response.status_code != 200:
                logger.warning(f"Metrics API error: {response.status_code}")
            
        except Exception as e:
            # Never fail the main operation due to metrics
            logger.error(f"Failed to emit metric: {e}")
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()

# Global metrics client instance
metrics_client = MetricsClient(
    metrics_url=os.getenv("METRICS_SERVICE_URL", "http://localhost:8890"),
    api_key=os.getenv("METRICS_API_KEY", ""),
    service_name="auth-server"
)
Integration in /validate endpoint
# auth_server/server.py - Updated /validate endpoint
from .metrics_client import metrics_client

@app.get("/validate")
async def validate_request(request: Request):
    start_time = time.time()
    server_name = None
    username_hash = ""
    
    try:
        # ... existing validation logic ...
        
        # Extract server name and username hash
        server_name = server_name_from_url  
        username_hash = hash_username(validation_result.get('username', ''))
        
        # SUCCESS: Emit metrics
        asyncio.create_task(
            metrics_client.emit_auth_metric(
                success=True,
                method=validation_result.get('method', 'unknown'),
                duration_ms=(time.time() - start_time) * 1000,
                server_name=server_name,
                user_hash=username_hash
            )
        )
        
        return response
        
    except HTTPException as e:
        # FAILURE: Emit failure metrics  
        asyncio.create_task(
            metrics_client.emit_auth_metric(
                success=False,
                method="unknown",
                duration_ms=(time.time() - start_time) * 1000,
                server_name=server_name,
                user_hash=username_hash,
                error_code=str(e.status_code)
            )
        )
        raise
        
    except Exception as e:
        # ERROR: Emit error metrics
        asyncio.create_task(
            metrics_client.emit_auth_metric(
                success=False,
                method="unknown",
                duration_ms=(time.time() - start_time) * 1000,
                server_name=server_name,
                user_hash=username_hash,
                error_code=type(e).__name__
            )
        )
        raise
Configuration
Environment Variables
# .env file for metrics service
METRICS_SERVICE_PORT=8890
METRICS_SERVICE_HOST=0.0.0.0

# Database (Container-based SQLite)
DATABASE_URL=sqlite:///var/lib/sqlite/metrics.db
SQLITE_DB_PATH=/var/lib/sqlite/metrics.db
METRICS_RETENTION_DAYS=90
DB_CONNECTION_TIMEOUT=30
DB_MAX_RETRIES=5

# OpenTelemetry
OTEL_SERVICE_NAME=mcp-metrics-service
OTEL_PROMETHEUS_ENABLED=true
OTEL_PROMETHEUS_PORT=9465
OTEL_OTLP_ENDPOINT=http://jaeger:14250

# API Security
METRICS_RATE_LIMIT=1000
API_KEY_HASH_ALGORITHM=sha256

# Performance
BATCH_SIZE=100
FLUSH_INTERVAL_SECONDS=30
MAX_REQUEST_SIZE=10MB
API Key Management
# utils/api_keys.py
import hashlib
import secrets
from datetime import datetime

def generate_api_key() -> str:
    """Generate a new API key."""
    return f"mcp_metrics_{secrets.token_urlsafe(32)}"

def hash_api_key(api_key: str) -> str:
    """Hash API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()

async def create_api_key(service_name: str) -> str:
    """Create and store new API key."""
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    
    # Store in database
    await store_api_key(key_hash, service_name)
    
    return api_key
Deployment
Docker Configuration
# Dockerfile for metrics service
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install uv && uv pip install --system -e .

# Copy application
COPY app/ app/

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8890

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8890/health || exit 1

CMD ["python", "-m", "app.main"]
Docker Compose Integration
# docker-compose.yml addition
services:
  # ... existing services ...
  
  # SQLite container for metrics database
  metrics-db:
    image: nouchka/sqlite3:latest
    volumes:
      - metrics-db-data:/var/lib/sqlite
    command: sqlite3 /var/lib/sqlite/metrics.db
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "sqlite3", "/var/lib/sqlite/metrics.db", ".tables"]
      interval: 30s
      timeout: 10s
      retries: 3
  
  metrics-service:
    build: ./metrics-service
    ports:
      - "8890:8890"
      - "9465:9465"  # Prometheus metrics
    environment:
      - SQLITE_DB_PATH=/var/lib/sqlite/metrics.db
      - OTEL_PROMETHEUS_ENABLED=true
      - OTEL_PROMETHEUS_PORT=9465
      - DATABASE_URL=sqlite:///var/lib/sqlite/metrics.db
    volumes:
      - metrics-db-data:/var/lib/sqlite
    depends_on:
      - metrics-db
      - auth-server
      - registry
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8890/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  metrics-db-data:
Benefits and Trade-offs
Benefits
Centralized Collection: Single service handles all metrics
Standardized API: Consistent interface for all components
Dual Storage: OTel for external systems + SQLite for local analytics
Decoupled Design: Components don't need OTel dependencies
Failure Isolation: Metrics failures don't affect main operations
API Key Security: Controlled access with rate limiting
Trade-offs
Additional Service: Extra deployment and maintenance overhead
Network Dependency: Components depend on metrics service availability
Single Point of Failure: If metrics service is down, no metrics collected
Latency: HTTP calls add small overhead to operations
Next Steps
Create metrics service project structure
Implement core HTTP API and processing logic
Set up SQLite schema and storage layer
Configure OpenTelemetry exporters
Implement API key authentication system
Create metrics client library for auth server
Test integration with auth server /validate endpoint
Add monitoring and health checks
Document API and deployment procedures
Extend to other MCP components
This design provides a robust, scalable foundation for metrics collection across the entire MCP Gateway Registry ecosystem while maintaining simplicity and operational reliability.