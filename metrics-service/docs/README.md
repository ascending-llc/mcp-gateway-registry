# MCP Metrics Collection Service

The MCP Metrics Collection Service is a centralized, high-performance metrics collection and aggregation system designed specifically for the MCP Gateway Registry ecosystem. It provides real-time metrics collection, validation, rate limiting, and OpenTelemetry integration.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Database Schema](#database-schema)
- [Data Retention](#data-retention)
- [Configuration](#configuration)
- [Development](#development)
- [Deployment](#deployment)
- [Monitoring](#monitoring)

## Overview

### Purpose

The metrics service serves as the central hub for collecting, validating, and storing performance and usage metrics from all MCP Gateway Registry components including:

- Authentication servers
- Registry services  
- MCP servers and tools
- Client applications

### Key Features

- **High Performance**: Async/await architecture with connection pooling
- **Data Validation**: Comprehensive input validation with detailed error reporting
- **Rate Limiting**: Token bucket rate limiting (1000 requests/minute per API key)
- **Schema Evolution**: Version-controlled database migrations
- **OpenTelemetry Integration**: Native OTLP and Prometheus export
- **Secure Authentication**: SHA256-hashed API keys with usage tracking
- **Data Retention**: Configurable retention policies for different metric types
- **Containerized Deployment**: Docker-ready with SQLite persistence

## Architecture

### System Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Auth Server   │    │ Registry Service│    │   MCP Servers   │
│                 │    │                 │    │                 │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼──────────────┐
                    │   Metrics Collection API   │
                    │                            │
                    │  • Rate Limiting           │
                    │  • Data Validation         │
                    │  • API Key Auth           │
                    └─────────────┬──────────────┘
                                 │
                    ┌─────────────▼──────────────┐
                    │   Metrics Processor        │
                    │                            │
                    │  • Buffered Processing     │
                    │  • OTel Integration        │
                    │  • Error Handling          │
                    └─────────────┬──────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                       │                        │
┌───────▼────────┐    ┌─────────▼─────────┐    ┌────────▼────────┐
│  SQLite Store  │    │ Prometheus Export │    │   OTLP Export   │
│                │    │                   │    │                 │
│ • Raw Metrics  │    │ • Real-time       │    │ • External      │
│ • Aggregates   │    │ • Histograms      │    │ • APM Systems   │
│ • Retention    │    │ • Counters        │    │ • Observability │
└────────────────┘    └───────────────────┘    └─────────────────┘
```

### Data Flow

1. **Collection**: Services send metrics via HTTP POST to `/metrics` endpoint
2. **Authentication**: API key validation with rate limiting check
3. **Validation**: Comprehensive data validation using custom validator
4. **Processing**: Metrics processor handles buffering and format conversion
5. **Storage**: Atomic writes to SQLite with transaction safety
6. **Export**: Real-time export to Prometheus and optional OTLP endpoints

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- uv package manager (recommended)

### Installation

1. **Clone and setup**:
```bash
cd metrics-service
uv sync
```

2. **Start dependencies**:
```bash
docker-compose up -d metrics-db
```

3. **Initialize database**:
```bash
uv run python migrate.py up
```

4. **Create API keys**:
```bash
uv run python create_api_key.py
```

5. **Start the service**:
```bash
uv run python -m app.main
```

The service will be available at:
- HTTP API: `http://localhost:8890`
- Prometheus metrics: `http://localhost:9465/metrics`

### First Metrics Submission

```bash
curl -X POST http://localhost:8890/metrics \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{
    "service": "test-service",
    "version": "1.0.0",
    "instance_id": "test-01",
    "metrics": [
      {
        "type": "auth_request",
        "value": 1.0,
        "duration_ms": 45.2,
        "dimensions": {
          "method": "jwt",
          "success": true,
          "server": "auth-01"
        }
      }
    ]
  }'
```

## API Reference

### Authentication

All API endpoints require authentication via the `X-API-Key` header:

```http
X-API-Key: your-api-key-here
```

API keys are:
- SHA256 hashed for secure storage
- Rate limited to 1000 requests/minute by default
- Tracked for usage analytics
- Service-specific for isolation

### Rate Limiting

Rate limits are enforced per API key with the following headers returned:

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
```

When rate limit is exceeded, you'll receive a `429 Too Many Requests` response with:

```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
Retry-After: 60
```

### Endpoints

#### POST /metrics

Submit metrics data for collection and processing.

**Request Body**:
```json
{
  "service": "string",           // Required: Service name (alphanumeric, -, _)
  "version": "string",          // Optional: Semantic version (x.y.z)
  "instance_id": "string",      // Optional: Instance identifier
  "metrics": [                  // Required: Array of metrics (max 100)
    {
      "type": "metric_type",    // Required: One of supported metric types
      "value": 1.0,             // Required: Numeric value
      "duration_ms": 150.5,     // Optional: Duration in milliseconds
      "timestamp": "2024-01-01T00:00:00Z", // Optional: ISO timestamp
      "dimensions": {           // Optional: Key-value dimensions (max 20)
        "key": "value"
      },
      "metadata": {             // Optional: Additional metadata (max 30)
        "key": "value"
      }
    }
  ]
}
```

**Supported Metric Types**:
- `auth_request`: Authentication requests
- `tool_discovery`: Tool discovery operations
- `tool_execution`: Tool execution events

**Response**:
```json
{
  "status": "success",
  "accepted": 1,
  "rejected": 0,
  "errors": [],
  "request_id": "req_123"
}
```

**Validation Rules**:
- Service name: 100 chars max, alphanumeric with `-` and `_`
- Metric value: Required, numeric, range ±1e12
- Duration: Non-negative, max 24 hours in milliseconds
- Dimensions: Max 20 keys, 50 char key length, 200 char value length
- Metadata: Max 30 fields, 50 char key length, 1000 char value length

#### POST /flush

Force flush buffered metrics to storage.

**Response**:
```json
{
  "status": "success",
  "message": "Metrics flushed to storage"
}
```

#### GET /rate-limit

Get current rate limit status for your API key.

**Response**:
```json
{
  "service": "your-service",
  "rate_limit": 1000,
  "available_tokens": 950,
  "reset_time_seconds": 30
}
```

#### GET /health

Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "service": "metrics-collection"
}
```

#### GET /

Service information and available endpoints.

**Response**:
```json
{
  "service": "MCP Metrics Collection Service",
  "version": "1.0.0",
  "status": "running",
  "endpoints": {
    "metrics": "/metrics",
    "health": "/health",
    "flush": "/flush",
    "rate-limit": "/rate-limit"
  }
}
```

### Error Responses

All error responses follow this format:

```json
{
  "detail": "Error description",
  "status_code": 400
}
```

Common error codes:
- `400`: Bad Request - Invalid data format
- `401`: Unauthorized - Missing or invalid API key
- `422`: Validation Error - Data validation failed
- `429`: Too Many Requests - Rate limit exceeded
- `500`: Internal Server Error - Processing failure

## Database Schema

### Schema Overview

The database uses SQLite with the following table structure:

```sql
-- API key management
api_keys (
  id, key_hash, service_name, created_at, last_used_at,
  is_active, rate_limit, usage_count, daily_usage_limit,
  monthly_usage_limit, description
)

-- Raw metrics storage
metrics (
  id, request_id, service, service_version, instance_id,
  metric_type, timestamp, value, duration_ms, dimensions,
  metadata, created_at
)

-- Specialized metric tables
auth_metrics (...)
discovery_metrics (...)
tool_metrics (...)

-- Aggregation tables
metrics_hourly (...)
metrics_daily (...)

-- System tables
schema_migrations (...)
retention_policies (...)
api_key_usage_log (...)
```

### Schema Migrations

The service uses a version-controlled migration system:

```bash
# Check migration status
uv run python migrate.py status

# Apply pending migrations
uv run python migrate.py up

# Rollback to version
uv run python migrate.py down 2

# List all migrations
uv run python migrate.py list
```

Current migrations:
- **0001**: Initial schema with core tables
- **0002**: Aggregation tables for performance
- **0003**: Retention policies management
- **0004**: Enhanced API key usage tracking

## Data Retention

The service includes a comprehensive data retention system that automatically manages the lifecycle of metrics data to prevent unbounded database growth while maintaining optimal performance.

### Key Features

- **Automated Cleanup**: Daily background tasks remove old data based on configurable retention policies
- **Configurable Policies**: Different retention periods for raw metrics vs. aggregated data
- **Safe Operations**: Dry-run capabilities and atomic transactions prevent data loss
- **Administrative APIs**: Full control over retention policies and cleanup operations
- **Space Reclamation**: Automatic VACUUM operations after cleanup to reclaim disk space

### Default Retention Policies

```
Raw metrics: 90 days
├── metrics (auth requests, tool executions, etc.)
├── auth_metrics (authentication events)
├── discovery_metrics (tool discovery operations)
└── tool_metrics (individual tool usage)

Aggregated metrics: 1-3 years  
├── metrics_hourly (365 days)
└── metrics_daily (1095 days)

System data: 90 days
└── api_key_usage_log (API usage tracking)
```

### Quick Operations

```bash
# Preview what would be cleaned up
curl -H "X-API-Key: your-key" http://localhost:8890/admin/retention/preview

# Execute cleanup (dry-run by default)
curl -X POST -H "X-API-Key: your-key" http://localhost:8890/admin/retention/cleanup

# View current policies
curl -H "X-API-Key: your-key" http://localhost:8890/admin/retention/policies

# Update retention period for a table
curl -X PUT -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"retention_days": 120, "is_active": true}' \
  http://localhost:8890/admin/retention/policies/metrics
```

**📖 For comprehensive documentation on data retention, see [data-retention.md](data-retention.md)**

## Configuration

### Environment Variables

```bash
# Database
SQLITE_DB_PATH="/var/lib/sqlite/metrics.db"
METRICS_RETENTION_DAYS="90"
DB_CONNECTION_TIMEOUT="30"

# Service
METRICS_SERVICE_PORT="8890"
METRICS_SERVICE_HOST="0.0.0.0"

# OpenTelemetry
OTEL_SERVICE_NAME="mcp-metrics-service"
OTEL_PROMETHEUS_ENABLED="true"
OTEL_PROMETHEUS_PORT="9465"
OTEL_OTLP_ENDPOINT=""

# Security
METRICS_RATE_LIMIT="1000"
API_KEY_HASH_ALGORITHM="sha256"

# Performance
BATCH_SIZE="100"
FLUSH_INTERVAL_SECONDS="30"
MAX_REQUEST_SIZE="10MB"
```

### Docker Configuration

The service includes Docker configuration for containerized deployment:

```yaml
# docker-compose.yml
metrics-service:
  build: ./metrics-service
  ports:
    - "8890:8890"    # HTTP API
    - "9465:9465"    # Prometheus metrics
  environment:
    - SQLITE_DB_PATH=/var/lib/sqlite/metrics.db
  volumes:
    - metrics-db-data:/var/lib/sqlite
  depends_on:
    - metrics-db

metrics-db:
  image: nouchka/sqlite3:latest
  volumes:
    - metrics-db-data:/var/lib/sqlite
```

## Development

### Setting Up Development Environment

1. **Install dependencies**:
```bash
uv sync --dev
```

2. **Run tests**:
```bash
uv run pytest -v
```

3. **Run with hot reload**:
```bash
uv run uvicorn app.main:app --reload --port 8890
```

### Project Structure

```
metrics-service/
├── app/
│   ├── api/
│   │   ├── auth.py          # API key authentication
│   │   └── routes.py        # HTTP endpoints
│   ├── core/
│   │   ├── models.py        # Pydantic data models
│   │   ├── processor.py     # Metrics processing engine
│   │   ├── rate_limiter.py  # Rate limiting implementation
│   │   └── validator.py     # Data validation
│   ├── otel/
│   │   ├── exporters.py     # OpenTelemetry setup
│   │   └── instruments.py   # OTel instruments
│   ├── storage/
│   │   ├── database.py      # SQLite storage layer
│   │   └── migrations.py    # Schema migration system
│   ├── utils/
│   │   └── helpers.py       # Utility functions
│   ├── config.py            # Configuration management
│   └── main.py             # FastAPI application
├── tests/
│   ├── test_api.py         # API endpoint tests
│   ├── test_migrations.py  # Migration system tests
│   ├── test_processor.py   # Processing logic tests
│   ├── test_rate_limiter.py # Rate limiting tests
│   └── test_validator.py   # Validation tests
├── docs/                   # Documentation
├── migrate.py             # Migration CLI tool
├── create_api_key.py      # API key creation script
├── pyproject.toml         # Project configuration
└── README.md
```

### Testing

The service includes comprehensive test coverage:

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app

# Run specific test file
uv run pytest tests/test_api.py -v

# Run specific test
uv run pytest tests/test_validator.py::TestValidationResult::test_add_error -v
```

Test categories:
- **API Tests**: HTTP endpoint functionality
- **Validation Tests**: Data validation logic
- **Rate Limiting Tests**: Token bucket algorithm
- **Migration Tests**: Database schema evolution
- **Processor Tests**: Metrics processing pipeline

### Code Quality

The project uses modern Python tooling:

```bash
# Format code
uv run black app/ tests/

# Sort imports
uv run isort app/ tests/

# Type checking
uv run mypy app/

# Linting
uv run ruff check app/ tests/
```

## Deployment

### Production Deployment

1. **Build and deploy with Docker**:
```bash
docker-compose up -d
```

2. **Initialize database**:
```bash
docker-compose exec metrics-service python migrate.py up
```

3. **Create production API keys**:
```bash
docker-compose exec metrics-service python create_api_key.py
```

4. **Verify health**:
```bash
curl http://localhost:8890/health
```

### Environment-Specific Configuration

**Development**:
```bash
SQLITE_DB_PATH="./dev.db"
METRICS_SERVICE_HOST="127.0.0.1"
OTEL_PROMETHEUS_ENABLED="true"
```

**Production**:
```bash
SQLITE_DB_PATH="/var/lib/sqlite/metrics.db"
METRICS_SERVICE_HOST="0.0.0.0"
OTEL_OTLP_ENDPOINT="https://otel-collector.example.com"
METRICS_RATE_LIMIT="5000"
```

### Security Considerations

- **API Keys**: Never log API keys in plaintext
- **Database**: Ensure SQLite file permissions are restricted
- **Network**: Use HTTPS in production environments
- **Rate Limiting**: Adjust limits based on expected traffic
- **Monitoring**: Set up alerts for authentication failures

## Monitoring

### Built-in Metrics

The service exposes Prometheus metrics at `/metrics` (port 9465):

```
# HTTP request metrics
http_requests_total{method="POST", endpoint="/metrics", status="200"}
http_request_duration_seconds{method="POST", endpoint="/metrics"}

# Application metrics
metrics_processed_total{service="auth-server", type="auth_request"}
metrics_validation_errors_total{field="service", error_type="invalid"}
api_key_requests_total{service="auth-server", status="success"}

# Rate limiting metrics
rate_limit_hits_total{service="auth-server"}
rate_limit_available_tokens{service="auth-server"}

# Database metrics
database_operations_total{operation="insert", table="metrics"}
database_query_duration_seconds{operation="select", table="metrics"}
```

### Health Checks

The service provides multiple health check endpoints:

```bash
# Basic health
curl http://localhost:8890/health

# Database connectivity
curl http://localhost:8890/health/db

# Rate limiter status
curl -H "X-API-Key: your-key" http://localhost:8890/rate-limit
```

### Alerting

Recommended alerts:

```yaml
# High error rate
- alert: MetricsHighErrorRate
  expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
  
# Rate limit exhaustion
- alert: RateLimitExhausted
  expr: rate_limit_available_tokens < 10

# Database errors
- alert: DatabaseErrors
  expr: increase(database_errors_total[5m]) > 0
```

### Log Analysis

The service uses structured logging:

```json
{
  "timestamp": "2024-01-01T00:00:00Z",
  "level": "INFO",
  "logger": "app.api.routes",
  "message": "Processed 5 metrics from auth-server",
  "request_id": "req_123",
  "service": "auth-server",
  "accepted": 5,
  "rejected": 0
}
```

This documentation provides a comprehensive guide to understanding, deploying, and maintaining the MCP Metrics Collection Service.