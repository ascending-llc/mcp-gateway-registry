# MCP Gateway Observability Guide

This guide covers how to access and query metrics collected by the MCP Gateway metrics service.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Accessing Metrics](#accessing-metrics)
- [SQLite Database Queries](#sqlite-database-queries)
- [OpenTelemetry Metrics](#opentelemetry-metrics)
- [Configuring OpenTelemetry Collector](#configuring-opentelemetry-collector)
- [Grafana Dashboards](#grafana-dashboards)

## Architecture Overview

The MCP Gateway collects comprehensive metrics through a dual-path observability system:

1. **SQLite Storage**: All metrics are stored in specialized database tables for detailed querying and analysis
2. **OpenTelemetry Export**: Metrics are simultaneously exported to OpenTelemetry for real-time monitoring via Prometheus and Grafana

### Metrics Collection Flow

```
Auth Server Middleware → Metrics Service API → Dual Path:
                                               ├─> SQLite Database (detailed storage)
                                               └─> OpenTelemetry (Prometheus/Grafana)
```

### Database Tables

- **`auth_metrics`**: Authentication requests and validation
- **`tool_metrics`**: Tool execution details (calls, methods, client info)
- **`discovery_metrics`**: Tool discovery/search queries
- **`metrics`**: Raw metrics data (all types)
- **`api_keys`**: API key management for metrics service

## Accessing Metrics

### Access SQLite Database

The metrics database is stored in a Docker volume and accessed via the `metrics-db` container:

```bash
# Connect to the metrics-db container
docker compose exec metrics-db sh

# Access SQLite database
sqlite3 /var/lib/sqlite/metrics.db

# Enable better formatting
.mode column
.headers on
```

### Alternative: Copy Database Locally

```bash
# Copy database from container to host
docker compose cp metrics-db:/var/lib/sqlite/metrics.db ./metrics.db

# Install sqlite3 locally if needed
sudo apt-get install -y sqlite3

# Query locally
sqlite3 ./metrics.db
```

## SQLite Database Queries

### Database Overview

#### List All Tables

```sql
.tables
```

**Output:**
```
_health            auth_metrics       metrics
api_keys           discovery_metrics  tool_metrics
```

#### Count Metrics by Table

```sql
SELECT 'auth_metrics' as table_name, COUNT(*) as count FROM auth_metrics
UNION ALL
SELECT 'tool_metrics', COUNT(*) FROM tool_metrics
UNION ALL
SELECT 'discovery_metrics', COUNT(*) FROM discovery_metrics
UNION ALL
SELECT 'metrics', COUNT(*) FROM metrics;
```

**Sample Output:**
```
table_name         count
-----------------  -----
auth_metrics       212
tool_metrics       183
discovery_metrics  0
metrics            475
```

### Authentication Metrics

#### Recent Auth Requests

```sql
SELECT
    datetime(timestamp) as time,
    server,
    success,
    method,
    duration_ms,
    user_hash,
    error_code
FROM auth_metrics
ORDER BY timestamp DESC
LIMIT 20;
```

**Sample Output:**
```
time                 server               success  method   duration_ms       user_hash  error_code
-------------------  -------------------  -------  -------  ----------------  ---------  ----------
2025-10-02 04:43:22  mcpgw                0        unknown  14.0132130181883             500
2025-10-02 04:43:22  currenttime          0        unknown  13.9779029996134             500
2025-10-02 04:43:22  atlassian            0        unknown  10.4731550090946             500
2025-10-02 04:43:22  realserverfaketools  0        unknown  12.8724499954842             500
2025-10-02 04:43:22  sre-gateway          0        unknown  8.54846101719886             500
```

#### Auth Success Rate by Server

```sql
SELECT
    server,
    COUNT(*) as total,
    SUM(success) as successful,
    ROUND(100.0 * SUM(success) / COUNT(*), 2) as success_pct,
    ROUND(AVG(duration_ms), 2) as avg_ms
FROM auth_metrics
GROUP BY server
ORDER BY total DESC;
```

#### Hourly Request Volume (Last 24 Hours)

```sql
SELECT
    strftime('%Y-%m-%d %H:00', timestamp) as hour,
    COUNT(*) as requests
FROM auth_metrics
WHERE timestamp > datetime('now', '-24 hours')
GROUP BY hour
ORDER BY hour DESC;
```

### Tool Execution Metrics

#### Recent Tool Executions

```sql
SELECT
    datetime(timestamp) as time,
    tool_name,
    server_name,
    success,
    ROUND(duration_ms, 2) as dur_ms,
    method,
    client_name
FROM tool_metrics
ORDER BY timestamp DESC
LIMIT 20;
```

**Sample Output:**
```
time                 tool_name   server_name          success  dur_ms  method      client_name
-------------------  ----------  -------------------  -------  ------  ----------  -----------
2025-10-02 04:43:22  initialize  mcpgw                0        14.01   initialize  claude-code
2025-10-02 04:43:22  initialize  currenttime          0        13.98   initialize  claude-code
2025-10-02 04:43:22  initialize  atlassian            0        10.47   initialize  claude-code
2025-10-02 04:42:59  initialize  currenttime          0        7.61    initialize  Roo Code
2025-10-02 04:42:59  initialize  mcpgw                0        10.24   initialize  Roo Code
```

#### Tool Usage Summary

```sql
SELECT
    tool_name,
    COUNT(*) as calls,
    SUM(success) as successful,
    ROUND(AVG(duration_ms), 2) as avg_ms,
    COUNT(DISTINCT client_name) as unique_clients
FROM tool_metrics
GROUP BY tool_name
ORDER BY calls DESC;
```

#### Client Usage Statistics

```sql
SELECT
    client_name,
    client_version,
    COUNT(*) as calls,
    COUNT(DISTINCT tool_name) as unique_tools,
    COUNT(DISTINCT server_name) as unique_servers
FROM tool_metrics
WHERE client_name IS NOT NULL
GROUP BY client_name, client_version
ORDER BY calls DESC;
```

#### Slowest Tool Executions

```sql
SELECT
    tool_name,
    server_name,
    ROUND(duration_ms, 2) as duration_ms,
    datetime(timestamp) as time,
    success
FROM tool_metrics
ORDER BY duration_ms DESC
LIMIT 20;
```

**Sample Output:**
```
tool_name                  server_name          duration_ms  time                 success
-------------------------  -------------------  -----------  -------------------  -------
initialize                 atlassian            637.67       2025-10-02 03:32:51  0
initialize                 atlassian            73.62        2025-10-02 03:08:40  0
initialize                 sre-gateway          45.2         2025-10-02 03:15:49  0
initialize                 sre-gateway          39.86        2025-10-02 03:42:27  0
initialize                 realserverfaketools  36.31        2025-10-02 03:42:27  0
```

#### Error Analysis

```sql
SELECT
    error_code,
    COUNT(*) as count,
    GROUP_CONCAT(DISTINCT tool_name) as affected_tools
FROM tool_metrics
WHERE success = 0 AND error_code IS NOT NULL
GROUP BY error_code
ORDER BY count DESC;
```

### Tool Discovery Metrics

#### Recent Discovery Queries

```sql
SELECT
    datetime(timestamp) as time,
    query,
    results_count,
    ROUND(duration_ms, 2) as dur_ms,
    ROUND(embedding_time_ms, 2) as embed_ms,
    ROUND(faiss_search_time_ms, 2) as search_ms
FROM discovery_metrics
ORDER BY timestamp DESC
LIMIT 20;
```

#### Discovery Performance Analysis

```sql
SELECT
    COUNT(*) as total_queries,
    ROUND(AVG(results_count), 2) as avg_results,
    ROUND(AVG(duration_ms), 2) as avg_duration_ms,
    ROUND(AVG(embedding_time_ms), 2) as avg_embedding_ms,
    ROUND(AVG(faiss_search_time_ms), 2) as avg_search_ms
FROM discovery_metrics;
```

### Advanced Queries

#### Tool Method Distribution

```sql
SELECT
    method,
    COUNT(*) as count,
    COUNT(DISTINCT server_name) as servers_using,
    ROUND(AVG(duration_ms), 2) as avg_ms
FROM tool_metrics
WHERE method IS NOT NULL
GROUP BY method
ORDER BY count DESC;
```

#### Daily Active Clients

```sql
SELECT
    DATE(timestamp) as date,
    COUNT(DISTINCT client_name) as unique_clients,
    COUNT(*) as total_calls
FROM tool_metrics
WHERE client_name IS NOT NULL
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

#### Server Performance Comparison

```sql
SELECT
    server_name,
    COUNT(*) as total_calls,
    SUM(success) as successful,
    ROUND(100.0 * SUM(success) / COUNT(*), 2) as success_rate,
    ROUND(AVG(duration_ms), 2) as avg_duration_ms,
    ROUND(MIN(duration_ms), 2) as min_ms,
    ROUND(MAX(duration_ms), 2) as max_ms
FROM tool_metrics
GROUP BY server_name
ORDER BY total_calls DESC;
```

#### Time-Based Performance Analysis

```sql
SELECT
    strftime('%H', timestamp) as hour_of_day,
    COUNT(*) as requests,
    ROUND(AVG(duration_ms), 2) as avg_duration_ms,
    ROUND(100.0 * SUM(success) / COUNT(*), 2) as success_rate
FROM tool_metrics
GROUP BY hour_of_day
ORDER BY hour_of_day;
```

## OpenTelemetry Metrics

The metrics service exports metrics to OpenTelemetry in two formats:

### Prometheus Endpoint

Access raw Prometheus metrics:

```bash
curl http://localhost:9465/metrics
```

**Available Metrics:**
- `mcp_auth_requests_total` - Counter of authentication requests
- `mcp_auth_request_duration_seconds` - Histogram of auth request durations
- `mcp_tool_executions_total` - Counter of tool executions
- `mcp_tool_execution_duration_seconds` - Histogram of tool execution durations
- `mcp_tool_discovery_total` - Counter of discovery requests
- `mcp_tool_discovery_duration_seconds` - Histogram of discovery durations
- `mcp_protocol_latency_seconds` - Histogram of protocol flow latencies
- `mcp_health_checks_total` - Counter of health checks
- `mcp_health_check_duration_seconds` - Histogram of health check durations

### OTLP Export

If configured, metrics are also exported to an OTLP endpoint (e.g., OpenTelemetry Collector).

Configuration in `.env`:
```bash
OTEL_OTLP_ENDPOINT=http://otel-collector:4318
```

## Configuring OpenTelemetry Collector

The OpenTelemetry Collector is a vendor-agnostic proxy that can receive, process, and export telemetry data to multiple backends (AWS CloudWatch, Datadog, New Relic, etc.).

### Step 1: Add OTel Collector to Docker Compose

Add this service to your `docker-compose.yml`:

```yaml
  # OpenTelemetry Collector
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./config/otel-collector-config.yaml:/etc/otel-collector-config.yaml
    ports:
      - "4318:4318"   # OTLP HTTP receiver
      - "4317:4317"   # OTLP gRPC receiver
      - "8888:8888"   # Prometheus metrics exposed by the collector
      - "8889:8889"   # Prometheus exporter metrics
    restart: unless-stopped
```

### Step 2: Create OTel Collector Configuration

Create `config/otel-collector-config.yaml`:

#### Basic Configuration (Prometheus Export)

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:
    timeout: 10s
    send_batch_size: 1024

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"
    namespace: mcp_gateway

  logging:
    loglevel: info

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus, logging]
```

#### Advanced Configuration (Multiple Backends)

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:
    timeout: 10s
    send_batch_size: 1024

  # Add resource attributes
  resource:
    attributes:
      - key: environment
        value: production
        action: insert
      - key: service.namespace
        value: mcp-gateway
        action: insert

  # Filter metrics if needed
  filter:
    metrics:
      include:
        match_type: regexp
        metric_names:
          - mcp_.*

exporters:
  # Export to Prometheus
  prometheus:
    endpoint: "0.0.0.0:8889"
    namespace: mcp_gateway

  # Export to AWS CloudWatch
  awscloudwatch:
    region: us-east-1
    namespace: MCP/Gateway
    endpoint: https://monitoring.us-east-1.amazonaws.com

  # Export to Datadog
  datadog:
    api:
      key: ${DATADOG_API_KEY}
      site: datadoghq.com

  # Export to New Relic
  otlphttp/newrelic:
    endpoint: https://otlp.nr-data.net:4318
    headers:
      api-key: ${NEW_RELIC_API_KEY}

  # Export to Grafana Cloud
  otlphttp/grafanacloud:
    endpoint: ${GRAFANA_CLOUD_OTLP_ENDPOINT}
    headers:
      authorization: Basic ${GRAFANA_CLOUD_AUTH}

  # Export to Honeycomb
  otlphttp/honeycomb:
    endpoint: https://api.honeycomb.io
    headers:
      x-honeycomb-team: ${HONEYCOMB_API_KEY}

  # Logging for debugging
  logging:
    loglevel: info

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch, resource, filter]
      exporters: [prometheus, awscloudwatch, logging]
      # Add other exporters as needed: datadog, otlphttp/newrelic, etc.
```

### Step 3: Update Metrics Service Configuration

Update your `.env` file:

```bash
# Enable OTLP export to collector
OTEL_OTLP_ENDPOINT=http://otel-collector:4318
```

Update `docker-compose.yml` metrics-service environment:

```yaml
  metrics-service:
    environment:
      - OTEL_OTLP_ENDPOINT=http://otel-collector:4318
      # ... other env vars
    depends_on:
      - metrics-db
      - otel-collector  # Add dependency
```

### Step 4: Configure Prometheus to Scrape OTel Collector

Update `config/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  # Scrape metrics directly from metrics-service
  - job_name: 'mcp-metrics-service'
    static_configs:
      - targets: ['metrics-service:9465']

  # Scrape metrics from OTel Collector
  - job_name: 'otel-collector'
    static_configs:
      - targets: ['otel-collector:8889']
```

### Step 5: Deploy and Verify

```bash
# Restart services
docker compose down
docker compose up -d

# Check OTel Collector logs
docker compose logs -f otel-collector

# Verify metrics are being received
curl http://localhost:8889/metrics | grep mcp_

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job == "otel-collector")'
```

### Cloud Provider Specific Configurations

#### AWS CloudWatch

```yaml
exporters:
  awscloudwatch:
    region: us-east-1
    namespace: MCP/Gateway
    dimension_rollup_option: NoDimensionRollup
    metric_declarations:
      - dimensions: [[service, metric_type]]
        metric_name_selectors:
          - mcp_.*
```

**Required IAM Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*"
    }
  ]
}
```

**Environment Variables:**
```bash
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

#### Datadog

```yaml
exporters:
  datadog:
    api:
      key: ${DATADOG_API_KEY}
      site: datadoghq.com  # or datadoghq.eu for EU
    host_metadata:
      enabled: true
      hostname_source: config_or_system
```

**Environment Variables:**
```bash
DATADOG_API_KEY=your-datadog-api-key
```

#### Grafana Cloud

```yaml
exporters:
  otlphttp/grafanacloud:
    endpoint: ${GRAFANA_CLOUD_OTLP_ENDPOINT}
    headers:
      authorization: Basic ${GRAFANA_CLOUD_AUTH}
```

**Setup:**
1. Get OTLP endpoint from Grafana Cloud console
2. Create service account and get API key
3. Base64 encode: `echo -n "instance_id:api_key" | base64`

**Environment Variables:**
```bash
GRAFANA_CLOUD_OTLP_ENDPOINT=https://otlp-gateway-prod-us-central-0.grafana.net/otlp
GRAFANA_CLOUD_AUTH=base64_encoded_credentials
```

#### New Relic

```yaml
exporters:
  otlphttp/newrelic:
    endpoint: https://otlp.nr-data.net:4318
    headers:
      api-key: ${NEW_RELIC_API_KEY}
```

**Environment Variables:**
```bash
NEW_RELIC_API_KEY=your-new-relic-license-key
```

### Troubleshooting OTel Collector

#### Check Collector Health

```bash
# View collector logs
docker compose logs otel-collector

# Check internal metrics
curl http://localhost:8888/metrics

# Verify receivers are active
docker compose exec otel-collector wget -qO- http://localhost:13133/
```

#### Common Issues

**Metrics not flowing to backend:**
```bash
# Enable debug logging in collector config
exporters:
  logging:
    loglevel: debug

# Check for export errors in logs
docker compose logs otel-collector | grep -i error
```

**Connection refused to OTLP endpoint:**
```bash
# Verify collector is reachable from metrics-service
docker compose exec metrics-service ping otel-collector

# Check port is open
docker compose exec metrics-service nc -zv otel-collector 4318
```

**Authentication failures:**
```bash
# Verify API keys are set
docker compose exec otel-collector env | grep -i key

# Test exporter authentication separately
```

### Best Practices

1. **Use Batch Processor**: Reduces network overhead
   ```yaml
   processors:
     batch:
       timeout: 10s
       send_batch_size: 1024
   ```

2. **Add Resource Attributes**: Tag metrics with environment/deployment info
   ```yaml
   processors:
     resource:
       attributes:
         - key: environment
           value: ${ENVIRONMENT}
           action: insert
   ```

3. **Filter Metrics**: Only export what you need
   ```yaml
   processors:
     filter:
       metrics:
         include:
           match_type: regexp
           metric_names:
             - mcp_auth_.*
             - mcp_tool_.*
   ```

4. **Enable Health Check**: Monitor collector itself
   ```yaml
   extensions:
     health_check:
       endpoint: 0.0.0.0:13133

   service:
     extensions: [health_check]
   ```

5. **Set Retention Policies**: Configure backend retention based on use case
   - Real-time alerts: 7-30 days
   - Compliance/auditing: 1-2 years
   - General monitoring: 90 days

### Example Complete Setup

See `config/otel-collector-config.example.yaml` for a complete production-ready configuration template.

## Grafana Dashboards

Access Grafana dashboards at: `http://localhost:3000`

**Default credentials:**
- Username: `admin`
- Password: `admin`

### Pre-configured Dashboards

The MCP Gateway includes pre-configured Grafana dashboards for:

1. **Authentication Metrics**
   - Success rates by server
   - Request volume over time
   - Error code distribution
   - Average response times

2. **Tool Execution Metrics**
   - Most used tools
   - Client distribution
   - Success rates
   - Performance trends

3. **Discovery Metrics**
   - Search query volume
   - Result counts
   - Performance breakdown (embedding vs. FAISS search)

4. **System Health**
   - Overall request volume
   - Error rates
   - Performance percentiles (p50, p95, p99)

### Prometheus Queries

Access Prometheus at: `http://localhost:9090`

**Sample PromQL Queries:**

```promql
# Authentication success rate
rate(mcp_auth_requests_total{success="true"}[5m]) / rate(mcp_auth_requests_total[5m])

# Average tool execution duration by server
rate(mcp_tool_execution_duration_seconds_sum[5m]) / rate(mcp_tool_execution_duration_seconds_count[5m])

# Top 5 most used tools
topk(5, sum by (tool_name) (rate(mcp_tool_executions_total[5m])))

# 95th percentile request duration
histogram_quantile(0.95, rate(mcp_auth_request_duration_seconds_bucket[5m]))
```

## Monitoring Best Practices

### Key Metrics to Monitor

1. **Authentication Success Rate**: Should be >95%
2. **Tool Execution Success Rate**: Should be >90%
3. **Average Response Time**: Should be <100ms for auth, <500ms for tools
4. **Error Rate**: Should be <5%
5. **Discovery Query Performance**: Embedding time should be <50ms

### Setting Up Alerts

Configure alerts in Grafana or Prometheus for:

- Authentication failure rate >10%
- Tool execution errors >5%
- Response time p95 >1000ms
- Discovery query failures

### Data Retention

- SQLite database: 90 days (configurable via `METRICS_RETENTION_DAYS`)
- Prometheus: 200 hours (configurable in `prometheus.yml`)
- Adjust retention based on storage capacity and compliance requirements

## Troubleshooting

### No Metrics Being Collected

1. Check metrics service is running:
   ```bash
   docker compose ps metrics-service
   ```

2. Verify API keys are configured:
   ```bash
   docker compose logs metrics-service | grep "API key"
   ```

3. Check middleware is enabled in auth-server logs:
   ```bash
   docker compose logs auth-server | grep "metrics"
   ```

### Database Connection Issues

```bash
# Check database volume
docker volume inspect mcp-gateway-registry_metrics-db-data

# Check database file permissions
docker compose exec metrics-db ls -la /var/lib/sqlite/

# Test database connectivity
docker compose exec metrics-db sqlite3 /var/lib/sqlite/metrics.db "SELECT COUNT(*) FROM metrics;"
```

### OpenTelemetry Export Issues

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check metrics-service OTEL configuration
docker compose logs metrics-service | grep -i otel
```

## Schema Reference

### auth_metrics Table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| request_id | TEXT | Unique request identifier |
| timestamp | TEXT | ISO 8601 timestamp |
| service | TEXT | Service name (e.g., "auth-server") |
| duration_ms | REAL | Request duration in milliseconds |
| success | BOOLEAN | Whether auth was successful |
| method | TEXT | Auth method used |
| server | TEXT | MCP server name |
| user_hash | TEXT | Hashed user identifier |
| error_code | TEXT | Error code if failed |
| created_at | TEXT | Record creation time |

### tool_metrics Table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| request_id | TEXT | Unique request identifier |
| timestamp | TEXT | ISO 8601 timestamp |
| service | TEXT | Service name |
| duration_ms | REAL | Execution duration in milliseconds |
| tool_name | TEXT | Tool or method name |
| server_path | TEXT | Server path |
| server_name | TEXT | MCP server name |
| success | BOOLEAN | Whether execution succeeded |
| error_code | TEXT | Error code if failed |
| input_size_bytes | INTEGER | Request payload size |
| output_size_bytes | INTEGER | Response payload size |
| client_name | TEXT | Client application name |
| client_version | TEXT | Client version |
| method | TEXT | MCP protocol method |
| user_hash | TEXT | Hashed user identifier |
| created_at | TEXT | Record creation time |

### discovery_metrics Table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| request_id | TEXT | Unique request identifier |
| timestamp | TEXT | ISO 8601 timestamp |
| service | TEXT | Service name |
| duration_ms | REAL | Total query duration |
| query | TEXT | Search query text |
| results_count | INTEGER | Number of results returned |
| top_k_services | INTEGER | Number of services requested |
| top_n_tools | INTEGER | Number of tools requested |
| embedding_time_ms | REAL | Time to generate embeddings |
| faiss_search_time_ms | REAL | Time for FAISS search |
| created_at | TEXT | Record creation time |

## Additional Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [SQLite Documentation](https://www.sqlite.org/docs.html)
