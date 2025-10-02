# API Reference

This document provides detailed API reference for the MCP Metrics Collection Service.

## Table of Contents

- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Endpoints](#endpoints)
- [Data Models](#data-models)
- [Error Handling](#error-handling)
- [Examples](#examples)

## Authentication

### API Key Authentication

All API endpoints require authentication using the `X-API-Key` header.

```http
X-API-Key: your-api-key-here
```

#### API Key Properties

- **Format**: Alphanumeric string (e.g., `mcp_key_1a2b3c4d5e6f`)
- **Hashing**: SHA256 hashed for secure storage
- **Scope**: Service-specific isolation
- **Tracking**: Usage analytics and rate limiting

#### Creating API Keys

Use the provided script to create API keys:

```bash
uv run python create_api_key.py
```

Or create for specific service:

```python
from app.utils.helpers import generate_api_key, hash_api_key
from app.storage.database import MetricsStorage

api_key = generate_api_key()
key_hash = hash_api_key(api_key)

storage = MetricsStorage()
await storage.create_api_key(key_hash, "your-service-name")
```

## Rate Limiting

### Rate Limit Policy

- **Default Limit**: 1000 requests per minute per API key
- **Algorithm**: Token bucket with refill rate
- **Scope**: Per API key (service isolation)
- **Granularity**: Per-minute windows

### Rate Limit Headers

Every response includes rate limit information:

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
```

### Rate Limit Exceeded

When rate limit is exceeded (HTTP 429):

```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
Retry-After: 60
Content-Type: application/json

{
  "detail": "Rate limit exceeded. Limit: 1000 requests/minute"
}
```

### Rate Limit Status Endpoint

Check current rate limit status:

```http
GET /rate-limit
X-API-Key: your-api-key-here
```

Response:
```json
{
  "service": "auth-server",
  "rate_limit": 1000,
  "available_tokens": 950,
  "reset_time_seconds": 30
}
```

## Endpoints

### Core Endpoints

#### POST /metrics

Submit metrics data for collection and processing.

#### Request

```http
POST /metrics
Content-Type: application/json
X-API-Key: your-api-key-here

{
  "service": "auth-server",
  "version": "1.0.0",
  "instance_id": "auth-01",
  "metrics": [
    {
      "type": "auth_request",
      "value": 1.0,
      "duration_ms": 45.2,
      "timestamp": "2024-01-01T12:00:00Z",
      "dimensions": {
        "method": "jwt",
        "success": true,
        "server": "auth-01",
        "user_hash": "user_abc123"
      },
      "metadata": {
        "error_code": null,
        "request_size": 1024,
        "response_size": 512
      }
    }
  ]
}
```

#### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service` | string | Yes | Service name (alphanumeric, `-`, `_`, max 100 chars) |
| `version` | string | No | Semantic version (e.g., "1.0.0") |
| `instance_id` | string | No | Instance identifier (alphanumeric, `-`, `_`, `.`, max 100 chars) |
| `metrics` | array | Yes | Array of metric objects (max 100) |

#### Metric Object Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Metric type (see [Metric Types](#metric-types)) |
| `value` | number | Yes | Numeric value (range: ±1e12) |
| `duration_ms` | number | No | Duration in milliseconds (0-86400000) |
| `timestamp` | string | No | ISO 8601 timestamp (defaults to current time) |
| `dimensions` | object | No | Key-value dimensions (max 20 fields) |
| `metadata` | object | No | Additional metadata (max 30 fields) |

#### Response

```json
{
  "status": "success",
  "accepted": 1,
  "rejected": 0,
  "errors": [],
  "request_id": "req_8a7b6c5d"
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | "success" or "error" |
| `accepted` | integer | Number of metrics successfully processed |
| `rejected` | integer | Number of metrics rejected due to validation |
| `errors` | array | Array of error messages for rejected metrics |
| `request_id` | string | Unique request identifier for tracking |

### POST /flush

Force flush buffered metrics to storage.

#### Request

```http
POST /flush
X-API-Key: your-api-key-here
```

#### Response

```json
{
  "status": "success",
  "message": "Metrics flushed to storage"
}
```

### GET /rate-limit

Get current rate limit status for the authenticated API key.

#### Request

```http
GET /rate-limit
X-API-Key: your-api-key-here
```

#### Response

```json
{
  "service": "auth-server",
  "rate_limit": 1000,
  "available_tokens": 950,
  "reset_time_seconds": 30
}
```

### GET /health

Health check endpoint (no authentication required).

#### Request

```http
GET /health
```

#### Response

```json
{
  "status": "healthy",
  "service": "metrics-collection"
}
```

### GET /

Service information endpoint (no authentication required).

#### Request

```http
GET /
```

#### Response

```json
{
  "service": "MCP Metrics Collection Service",
  "version": "1.0.0",
  "status": "running",
  "endpoints": {
    "metrics": "/metrics",
    "health": "/health",
    "flush": "/flush",
    "rate-limit": "/rate-limit",
    "admin": {
      "retention": "/admin/retention/*",
      "database": "/admin/database/*"
    }
  }
}
```

### Administrative Endpoints

All administrative endpoints require API key authentication and are designed for operational management of the metrics service.

#### GET /admin/retention/preview

Preview data cleanup operations without executing them.

**Parameters:**
- `table_name` (optional): Specific table to preview

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

#### POST /admin/retention/cleanup

Execute data cleanup operations with optional dry-run mode.

**Request:**
```json
{
  "table_name": "metrics",  // Optional: specific table
  "dry_run": true          // Optional: default true
}
```

**Response:**
```json
{
  "table": "metrics",
  "status": "completed",
  "records_deleted": 1250,
  "duration_seconds": 2.34,
  "retention_days": 90
}
```

#### GET /admin/retention/policies

View current retention policies for all tables.

**Response:**
```json
{
  "metrics": {
    "table_name": "metrics",
    "retention_days": 90,
    "is_active": true,
    "timestamp_column": "created_at"
  }
}
```

#### PUT /admin/retention/policies/{table_name}

Update retention policy for a specific table.

**Request:**
```json
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

#### GET /admin/database/stats

Get comprehensive database table statistics.

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
  }
}
```

#### GET /admin/database/size

Get detailed database size and efficiency metrics.

**Response:**
```json
{
  "main_db_bytes": 104857600,
  "main_db_mb": 100.0,
  "wal_bytes": 1048576,
  "wal_mb": 1.0,
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

**📖 For detailed retention management documentation, see [data-retention.md](data-retention.md)**

## Data Models

### Metric Types

The service supports the following metric types:

#### auth_request
Authentication request metrics.

**Dimensions**:
- `method` (string): Authentication method ("jwt", "oauth", "basic")
- `success` (boolean): Whether authentication succeeded
- `server` (string): Server handling the request
- `user_hash` (string): Hashed user identifier

**Metadata**:
- `error_code` (string): Error code if authentication failed
- `request_size` (integer): Request size in bytes
- `response_size` (integer): Response size in bytes

#### tool_discovery
Tool discovery operation metrics.

**Dimensions**:
- `query` (string): Search query or pattern
- `results_count` (integer): Number of results returned
- `top_k_services` (integer): Number of top services considered
- `top_n_tools` (integer): Number of top tools returned

**Metadata**:
- `embedding_time_ms` (number): Time to generate embeddings
- `faiss_search_time_ms` (number): FAISS search time
- `cache_hit` (boolean): Whether results came from cache

#### tool_execution
Tool execution event metrics.

**Dimensions**:
- `tool_name` (string): Name of the executed tool
- `server_path` (string): Server path or endpoint
- `server_name` (string): Server identifier
- `success` (boolean): Whether execution succeeded

**Metadata**:
- `error_code` (string): Error code if execution failed
- `input_size_bytes` (integer): Input payload size
- `output_size_bytes` (integer): Output payload size
- `tool_version` (string): Tool version if available

### Validation Rules

#### Service Name Validation
- **Pattern**: `^[a-zA-Z0-9_-]+$`
- **Length**: 1-100 characters
- **Examples**: ✅ `auth-server`, `metrics_service`, `tool123`
- **Invalid**: ❌ `auth server` (space), `auth@server` (special char)

#### Version Validation
- **Recommended**: Semantic versioning (`x.y.z`)
- **Examples**: ✅ `1.0.0`, `2.1.0-beta`, `0.1.0-alpha.1`
- **Warnings**: `v1.0.0`, `latest`, `1.0` (non-semantic)

#### Instance ID Validation
- **Pattern**: `^[a-zA-Z0-9_.-]+$`
- **Length**: 1-100 characters
- **Examples**: ✅ `auth-01`, `server_1`, `pod.123`

#### Dimensions Validation
- **Max Count**: 20 key-value pairs
- **Key Pattern**: `^[a-zA-Z_][a-zA-Z0-9_]*$`
- **Key Length**: 1-50 characters
- **Value Length**: 0-200 characters
- **Value Types**: string, number, boolean (converted to string)

#### Metadata Validation
- **Max Count**: 30 key-value pairs
- **Key Length**: 1-50 characters
- **Value Length**: 0-1000 characters
- **Value Types**: Any JSON-serializable type

#### Timestamp Validation
- **Format**: ISO 8601 with timezone
- **Future Limit**: Max 5 minutes in the future
- **Past Warning**: Warns if older than 7 days
- **Examples**: ✅ `2024-01-01T12:00:00Z`, `2024-01-01T12:00:00+00:00`

#### Value Validation
- **Type**: Number (integer or float)
- **Range**: -1e12 to +1e12
- **Invalid**: NaN, Infinity, null/undefined

#### Duration Validation
- **Type**: Number (integer or float)
- **Range**: 0 to 86400000 milliseconds (24 hours)
- **Unit**: Milliseconds

## Error Handling

### Error Response Format

All errors return a consistent JSON format:

```json
{
  "detail": "Error description",
  "status_code": 400
}
```

### Error Codes

#### 400 Bad Request
Invalid request format or structure.

```json
{
  "detail": "Invalid JSON in request body",
  "status_code": 400
}
```

#### 401 Unauthorized
Missing or invalid API key.

```json
{
  "detail": "API key required in X-API-Key header",
  "status_code": 401
}
```

```json
{
  "detail": "Invalid API key",
  "status_code": 401
}
```

```json
{
  "detail": "API key is inactive",
  "status_code": 401
}
```

#### 422 Unprocessable Entity
Data validation failed.

```json
{
  "detail": [
    {
      "type": "string_pattern_mismatch",
      "loc": ["service"],
      "msg": "String should match pattern '^[a-zA-Z0-9_-]+$'",
      "input": "invalid service name"
    }
  ],
  "status_code": 422
}
```

#### 429 Too Many Requests
Rate limit exceeded.

```json
{
  "detail": "Rate limit exceeded. Limit: 1000 requests/minute",
  "status_code": 429
}
```

#### 500 Internal Server Error
Server-side processing error.

```json
{
  "detail": "Internal server error: Database connection failed",
  "status_code": 500
}
```

### Validation Errors

When data validation fails, detailed error messages are provided:

```json
{
  "status": "error",
  "accepted": 0,
  "rejected": 2,
  "errors": [
    "metrics[0].dimensions.invalid-key: Dimension key must start with letter/underscore",
    "metrics[1].value: Metric value is required"
  ],
  "request_id": "req_error_123"
}
```

Error message format: `{field_path}: {error_description}`

## Examples

### Authentication Request Metrics

```bash
curl -X POST http://localhost:8890/metrics \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "service": "auth-server",
    "version": "1.2.0",
    "instance_id": "auth-pod-01",
    "metrics": [
      {
        "type": "auth_request",
        "value": 1.0,
        "duration_ms": 45.2,
        "dimensions": {
          "method": "jwt",
          "success": true,
          "server": "auth-01",
          "user_hash": "user_abc123"
        },
        "metadata": {
          "error_code": null,
          "request_size": 1024,
          "response_size": 512,
          "user_agent": "Mozilla/5.0..."
        }
      }
    ]
  }'
```

### Tool Discovery Metrics

```bash
curl -X POST http://localhost:8890/metrics \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "service": "registry-service",
    "version": "2.1.0",
    "metrics": [
      {
        "type": "tool_discovery",
        "value": 1.0,
        "duration_ms": 125.7,
        "dimensions": {
          "query": "file operations",
          "results_count": 15,
          "top_k_services": 5,
          "top_n_tools": 10
        },
        "metadata": {
          "embedding_time_ms": 12.3,
          "faiss_search_time_ms": 8.9,
          "cache_hit": false
        }
      }
    ]
  }'
```

### Tool Execution Metrics

```bash
curl -X POST http://localhost:8890/metrics \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "service": "mcpgw-server",
    "version": "1.0.0",
    "instance_id": "mcpgw-01",
    "metrics": [
      {
        "type": "tool_execution",
        "value": 1.0,
        "duration_ms": 1250.5,
        "dimensions": {
          "tool_name": "file_reader",
          "server_path": "/tools/file/read",
          "server_name": "file-server",
          "success": true
        },
        "metadata": {
          "error_code": null,
          "input_size_bytes": 256,
          "output_size_bytes": 1024,
          "tool_version": "1.2.0"
        }
      }
    ]
  }'
```

### Batch Metrics Submission

```bash
curl -X POST http://localhost:8890/metrics \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "service": "multi-service",
    "version": "1.0.0",
    "metrics": [
      {
        "type": "auth_request",
        "value": 1.0,
        "duration_ms": 45.2,
        "dimensions": {
          "method": "jwt",
          "success": true
        }
      },
      {
        "type": "tool_discovery",
        "value": 1.0,
        "duration_ms": 125.7,
        "dimensions": {
          "query": "search tools",
          "results_count": 10
        }
      },
      {
        "type": "tool_execution",
        "value": 1.0,
        "duration_ms": 890.3,
        "dimensions": {
          "tool_name": "calculator",
          "success": true
        }
      }
    ]
  }'
```

### Error Example

Request with validation errors:

```bash
curl -X POST http://localhost:8890/metrics \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "service": "invalid service name",
    "metrics": [
      {
        "type": "auth_request",
        "value": null,
        "dimensions": {
          "invalid-key": "value"
        }
      }
    ]
  }'
```

Response:
```json
{
  "status": "error",
  "accepted": 0,
  "rejected": 1,
  "errors": [
    "service: Service name must contain only alphanumeric characters, underscores, and hyphens",
    "metrics[0].value: Metric value is required",
    "metrics[0].dimensions.invalid-key: Dimension key must start with letter/underscore and contain only alphanumeric/underscore characters"
  ],
  "request_id": "req_error_abc123"
}
```

### Rate Limit Check

```bash
# Check rate limit status
curl -H "X-API-Key: your-api-key" http://localhost:8890/rate-limit

# Response
{
  "service": "auth-server",
  "rate_limit": 1000,
  "available_tokens": 995,
  "reset_time_seconds": 45
}
```

### Health Check

```bash
curl http://localhost:8890/health

# Response
{
  "status": "healthy",
  "service": "metrics-collection"
}
```