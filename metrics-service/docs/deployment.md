# Deployment Guide

This guide covers deploying the MCP Metrics Collection Service in various environments, from development to production.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Development Deployment](#development-deployment)
- [Production Deployment](#production-deployment)
- [Container Deployment](#container-deployment)
- [Environment Configuration](#environment-configuration)
- [Database Setup](#database-setup)
- [Security Considerations](#security-considerations)
- [Monitoring Setup](#monitoring-setup)
- [Troubleshooting](#troubleshooting)

## Overview

The metrics service can be deployed in several ways:

1. **Local Development**: Direct Python execution with local SQLite
2. **Docker Compose**: Containerized development environment
3. **Production Container**: Docker deployment with external database
4. **Kubernetes**: Scalable cloud deployment (configuration provided)

## Prerequisites

### System Requirements

- **CPU**: 1 core minimum, 2+ cores recommended
- **Memory**: 512MB minimum, 1GB+ recommended  
- **Storage**: 10GB minimum for database growth
- **Network**: HTTP/HTTPS access on configured ports

### Software Dependencies

- **Python**: 3.11+ (for direct deployment)
- **Docker**: 20.10+ (for container deployment)
- **Docker Compose**: 2.0+ (for development)
- **uv**: Latest version (recommended package manager)

### Network Ports

- **8890**: HTTP API (configurable via `METRICS_SERVICE_PORT`)
- **9465**: Prometheus metrics (configurable via `OTEL_PROMETHEUS_PORT`)

## Development Deployment

### Quick Start

1. **Clone and setup**:
```bash
cd metrics-service
uv sync --dev
```

2. **Initialize database**:
```bash
uv run python migrate.py up
```

3. **Create development API key**:
```bash
uv run python create_api_key.py
# Save the generated API key for testing
```

4. **Start development server**:
```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8890
```

5. **Verify deployment**:
```bash
curl http://localhost:8890/health
```

### Development Configuration

Create a `.env` file for local development:

```bash
# .env
SQLITE_DB_PATH="./dev_metrics.db"
METRICS_SERVICE_HOST="127.0.0.1"
METRICS_SERVICE_PORT="8890"
OTEL_PROMETHEUS_ENABLED="true"
OTEL_PROMETHEUS_PORT="9465"
METRICS_RATE_LIMIT="100"  # Lower for development
```

Load environment:
```bash
uv run --env-file .env uvicorn app.main:app --reload
```

### Hot Reload Development

For active development with auto-reload:

```bash
# Terminal 1: Start service with reload
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8890

# Terminal 2: Watch tests
uv run pytest --watch

# Terminal 3: Test API changes
curl -X POST http://localhost:8890/metrics \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-dev-key" \
  -d '{"service": "test", "metrics": [{"type": "auth_request", "value": 1.0}]}'
```

## Production Deployment

### Production Checklist

Before deploying to production, ensure:

- ✅ Database backup strategy in place
- ✅ SSL/TLS certificates configured
- ✅ API keys generated and securely stored
- ✅ Monitoring and alerting configured
- ✅ Log aggregation setup
- ✅ Rate limits configured for expected load
- ✅ Data retention policies defined
- ✅ Disaster recovery plan documented

### Direct Production Deployment

1. **System setup**:
```bash
# Create dedicated user
sudo useradd -m -s /bin/bash metrics
sudo su - metrics

# Install uv and dependencies
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

2. **Application setup**:
```bash
cd /opt/metrics-service
uv sync --no-dev
```

3. **Database initialization**:
```bash
# Ensure data directory exists with proper permissions
sudo mkdir -p /var/lib/sqlite
sudo chown metrics:metrics /var/lib/sqlite
sudo chmod 750 /var/lib/sqlite

# Initialize database
uv run python migrate.py up
```

4. **Create production API keys**:
```bash
uv run python create_api_key.py
# Store keys securely in your secrets management system
```

5. **Create systemd service**:
```ini
# /etc/systemd/system/metrics-service.service
[Unit]
Description=MCP Metrics Collection Service
After=network.target
Wants=network.target

[Service]
Type=exec
User=metrics
Group=metrics
WorkingDirectory=/opt/metrics-service
Environment=PATH=/home/metrics/.local/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=/etc/metrics-service/config
ExecStart=/home/metrics/.local/bin/uv run python -m app.main
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=metrics-service

[Install]
WantedBy=multi-user.target
```

6. **Production configuration**:
```bash
# /etc/metrics-service/config
SQLITE_DB_PATH="/var/lib/sqlite/metrics.db"
METRICS_SERVICE_HOST="0.0.0.0"
METRICS_SERVICE_PORT="8890"
OTEL_PROMETHEUS_ENABLED="true"
OTEL_PROMETHEUS_PORT="9465"
METRICS_RATE_LIMIT="5000"
METRICS_RETENTION_DAYS="90"
BATCH_SIZE="500"
FLUSH_INTERVAL_SECONDS="10"
```

7. **Start and enable service**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable metrics-service
sudo systemctl start metrics-service
sudo systemctl status metrics-service
```

### Reverse Proxy Configuration

#### Nginx Configuration

```nginx
# /etc/nginx/sites-available/metrics-service
upstream metrics_backend {
    server 127.0.0.1:8890;
}

server {
    listen 80;
    server_name metrics.yourdomain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name metrics.yourdomain.com;
    
    # SSL Configuration
    ssl_certificate /etc/ssl/certs/metrics.crt;
    ssl_certificate_key /etc/ssl/private/metrics.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_prefer_server_ciphers off;
    
    # Security Headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req zone=api burst=20 nodelay;
    
    # Main API
    location / {
        proxy_pass http://metrics_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        
        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }
    
    # Prometheus metrics (separate location for monitoring)
    location /prometheus {
        proxy_pass http://127.0.0.1:9465/metrics;
        allow 10.0.0.0/8;      # Internal network
        allow 172.16.0.0/12;   # Docker networks
        allow 192.168.0.0/16;  # Private networks
        deny all;
    }
    
    # Health check (no auth required)
    location /health {
        proxy_pass http://metrics_backend/health;
        access_log off;
    }
}
```

#### Apache Configuration

```apache
# /etc/apache2/sites-available/metrics-service.conf
<VirtualHost *:80>
    ServerName metrics.yourdomain.com
    Redirect permanent / https://metrics.yourdomain.com/
</VirtualHost>

<VirtualHost *:443>
    ServerName metrics.yourdomain.com
    
    # SSL Configuration
    SSLEngine on
    SSLCertificateFile /etc/ssl/certs/metrics.crt
    SSLCertificateKeyFile /etc/ssl/private/metrics.key
    SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1
    SSLCipherSuite ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384
    
    # Security Headers
    Header always set X-Frame-Options DENY
    Header always set X-Content-Type-Options nosniff
    Header always set X-XSS-Protection "1; mode=block"
    Header always set Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
    
    # Proxy Configuration
    ProxyPreserveHost On
    ProxyPass /health http://127.0.0.1:8890/health
    ProxyPassReverse /health http://127.0.0.1:8890/health
    
    ProxyPass / http://127.0.0.1:8890/
    ProxyPassReverse / http://127.0.0.1:8890/
</VirtualHost>
```

## Container Deployment

### Docker Compose Production

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  metrics-db:
    image: nouchka/sqlite3:latest
    volumes:
      - metrics-db-data:/var/lib/sqlite
    restart: unless-stopped
    
  metrics-service:
    build: 
      context: .
      target: production
    ports:
      - "8890:8890"
      - "9465:9465"
    environment:
      - SQLITE_DB_PATH=/var/lib/sqlite/metrics.db
      - METRICS_SERVICE_HOST=0.0.0.0
      - METRICS_RATE_LIMIT=5000
      - BATCH_SIZE=500
      - FLUSH_INTERVAL_SECONDS=10
    volumes:
      - metrics-db-data:/var/lib/sqlite
    depends_on:
      - metrics-db
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8890/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
      
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/ssl:ro
    depends_on:
      - metrics-service
    restart: unless-stopped

volumes:
  metrics-db-data:
    driver: local
```

### Multi-stage Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Development stage
FROM base as development
RUN uv sync --dev
COPY . .
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8890", "--reload"]

# Production stage
FROM base as production
RUN uv sync --no-dev
COPY . .

# Create non-root user
RUN useradd -m -u 1001 metrics
USER metrics

# Initialize database on startup
RUN uv run python migrate.py up

EXPOSE 8890 9465

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8890/health || exit 1

CMD ["uv", "run", "python", "-m", "app.main"]
```

### Kubernetes Deployment

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: metrics-system

---
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: metrics-config
  namespace: metrics-system
data:
  METRICS_SERVICE_HOST: "0.0.0.0"
  METRICS_SERVICE_PORT: "8890"
  OTEL_PROMETHEUS_ENABLED: "true"
  OTEL_PROMETHEUS_PORT: "9465"
  METRICS_RATE_LIMIT: "5000"
  BATCH_SIZE: "500"
  FLUSH_INTERVAL_SECONDS: "10"

---
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: metrics-secrets
  namespace: metrics-system
type: Opaque
data:
  # Base64 encoded values
  database-url: c3FsaXRlOi8vL3Zhci9saWIvc3FsaXRlL21ldHJpY3MuZGI=

---
# k8s/pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: metrics-storage
  namespace: metrics-system
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi

---
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: metrics-service
  namespace: metrics-system
  labels:
    app: metrics-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: metrics-service
  template:
    metadata:
      labels:
        app: metrics-service
    spec:
      containers:
      - name: metrics-service
        image: metrics-service:latest
        ports:
        - containerPort: 8890
          name: http
        - containerPort: 9465
          name: metrics
        envFrom:
        - configMapRef:
            name: metrics-config
        - secretRef:
            name: metrics-secrets
        volumeMounts:
        - name: data
          mountPath: /var/lib/sqlite
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8890
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8890
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: metrics-storage

---
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: metrics-service
  namespace: metrics-system
  labels:
    app: metrics-service
spec:
  selector:
    app: metrics-service
  ports:
  - name: http
    port: 80
    targetPort: 8890
  - name: metrics
    port: 9465
    targetPort: 9465

---
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: metrics-ingress
  namespace: metrics-system
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
spec:
  tls:
  - hosts:
    - metrics.yourdomain.com
    secretName: metrics-tls
  rules:
  - host: metrics.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: metrics-service
            port:
              number: 80
```

Deploy to Kubernetes:
```bash
kubectl apply -f k8s/
```

## Environment Configuration

### Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SQLITE_DB_PATH` | `/var/lib/sqlite/metrics.db` | SQLite database file path |
| `METRICS_SERVICE_HOST` | `0.0.0.0` | Service bind address |
| `METRICS_SERVICE_PORT` | `8890` | Service port |
| `OTEL_PROMETHEUS_ENABLED` | `true` | Enable Prometheus metrics |
| `OTEL_PROMETHEUS_PORT` | `9465` | Prometheus metrics port |
| `OTEL_OTLP_ENDPOINT` | `""` | OTLP endpoint URL |
| `METRICS_RATE_LIMIT` | `1000` | Requests per minute per API key |
| `METRICS_RETENTION_DAYS` | `90` | Data retention in days |
| `BATCH_SIZE` | `100` | Metrics batch size |
| `FLUSH_INTERVAL_SECONDS` | `30` | Buffer flush interval |
| `MAX_REQUEST_SIZE` | `10MB` | Maximum request size |

### Environment-Specific Configurations

#### Development
```bash
SQLITE_DB_PATH="./dev.db"
METRICS_SERVICE_HOST="127.0.0.1"
METRICS_RATE_LIMIT="100"
OTEL_PROMETHEUS_ENABLED="true"
BATCH_SIZE="10"
FLUSH_INTERVAL_SECONDS="5"
```

#### Staging
```bash
SQLITE_DB_PATH="/var/lib/sqlite/staging_metrics.db"
METRICS_SERVICE_HOST="0.0.0.0"
METRICS_RATE_LIMIT="1000"
OTEL_OTLP_ENDPOINT="https://staging-otel.company.com"
BATCH_SIZE="100"
FLUSH_INTERVAL_SECONDS="15"
```

#### Production
```bash
SQLITE_DB_PATH="/var/lib/sqlite/metrics.db"
METRICS_SERVICE_HOST="0.0.0.0"
METRICS_RATE_LIMIT="5000"
OTEL_OTLP_ENDPOINT="https://otel.company.com"
BATCH_SIZE="500"
FLUSH_INTERVAL_SECONDS="10"
```

## Database Setup

### Database Initialization

1. **Run migrations**:
```bash
uv run python migrate.py status
uv run python migrate.py up
```

2. **Verify schema**:
```bash
sqlite3 /var/lib/sqlite/metrics.db ".schema"
```

3. **Create initial API keys**:
```bash
uv run python create_api_key.py
```

### Database Maintenance

#### Backup Strategy

```bash
#!/bin/bash
# backup-metrics-db.sh

DB_PATH="/var/lib/sqlite/metrics.db"
BACKUP_DIR="/backups/metrics"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Create backup with vacuum
sqlite3 "$DB_PATH" ".backup $BACKUP_DIR/metrics_$DATE.db"

# Compress backup
gzip "$BACKUP_DIR/metrics_$DATE.db"

# Clean old backups (keep 30 days)
find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete

echo "Backup completed: metrics_$DATE.db.gz"
```

Schedule backups:
```bash
# Add to crontab
0 2 * * * /opt/scripts/backup-metrics-db.sh
```

#### Database Optimization

```bash
# Vacuum and analyze (run weekly)
sqlite3 /var/lib/sqlite/metrics.db "VACUUM; ANALYZE;"

# Check database integrity
sqlite3 /var/lib/sqlite/metrics.db "PRAGMA integrity_check;"

# View database statistics
sqlite3 /var/lib/sqlite/metrics.db "PRAGMA table_info(metrics);"
```

## Security Considerations

### API Key Security

1. **Generation**: Use cryptographically secure random generators
2. **Storage**: Store only SHA256 hashes, never plaintext
3. **Transmission**: Always use HTTPS in production
4. **Rotation**: Implement key rotation policies
5. **Monitoring**: Log and alert on authentication failures

### Network Security

1. **TLS/SSL**: Enforce HTTPS with strong cipher suites
2. **Firewalls**: Restrict access to necessary ports only
3. **Rate Limiting**: Implement both application and network-level limiting
4. **IP Allowlisting**: Consider IP restrictions for sensitive environments

### File System Security

```bash
# Set proper permissions
sudo chown -R metrics:metrics /var/lib/sqlite
sudo chmod 750 /var/lib/sqlite
sudo chmod 640 /var/lib/sqlite/metrics.db

# SELinux context (if enabled)
sudo setsebool -P httpd_can_network_connect 1
sudo semanage fcontext -a -t httpd_exec_t "/opt/metrics-service(/.*)?"
sudo restorecon -R /opt/metrics-service
```

### Container Security

```dockerfile
# Use non-root user
USER 1001

# Read-only filesystem
RUN chmod -R a-w /app

# Drop capabilities
USER 1001:1001
```

## Monitoring Setup

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'metrics-service'
    static_configs:
      - targets: ['localhost:9465']
    metrics_path: /metrics
    scrape_interval: 15s
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "MCP Metrics Service",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ]
      },
      {
        "title": "Error Rate",
        "type": "graph", 
        "targets": [
          {
            "expr": "rate(http_requests_total{status=~\"4..|5..\"}[5m])",
            "legendFormat": "{{status}}"
          }
        ]
      },
      {
        "title": "Rate Limit Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "rate_limit_available_tokens",
            "legendFormat": "{{service}}"
          }
        ]
      }
    ]
  }
}
```

### Alerting Rules

```yaml
# alerts.yml
groups:
  - name: metrics-service
    rules:
      - alert: MetricsServiceDown
        expr: up{job="metrics-service"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Metrics service is down"
          
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          
      - alert: RateLimitExhaustion
        expr: rate_limit_available_tokens < 10
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Rate limit nearly exhausted"
```

## Troubleshooting

### Common Issues

#### Service Won't Start

1. **Check logs**:
```bash
journalctl -u metrics-service -f
```

2. **Verify database permissions**:
```bash
ls -la /var/lib/sqlite/
sudo chown metrics:metrics /var/lib/sqlite/metrics.db
```

3. **Test database connection**:
```bash
sqlite3 /var/lib/sqlite/metrics.db "SELECT 1;"
```

#### High Memory Usage

1. **Check SQLite cache settings**:
```sql
PRAGMA cache_size;  -- Should be reasonable
PRAGMA temp_store;  -- Should be MEMORY
```

2. **Monitor buffer sizes**:
```bash
# Check if batch size is too large
grep BATCH_SIZE /etc/metrics-service/config
```

#### Rate Limiting Issues

1. **Check rate limiter status**:
```bash
curl -H "X-API-Key: your-key" http://localhost:8890/rate-limit
```

2. **Review rate limit logs**:
```bash
journalctl -u metrics-service | grep "rate limit"
```

#### Database Lock Issues

1. **Check for long-running transactions**:
```sql
PRAGMA wal_checkpoint;
```

2. **Monitor WAL file size**:
```bash
ls -la /var/lib/sqlite/metrics.db-wal
```

### Log Analysis

#### Structured Logging Format

```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "logger": "app.api.routes",
  "message": "Processed metrics",
  "request_id": "req_123",
  "service": "auth-server",
  "accepted": 5,
  "rejected": 0,
  "duration_ms": 45.2
}
```

#### Log Aggregation with ELK Stack

```yaml
# filebeat.yml
filebeat.inputs:
- type: log
  enabled: true
  paths:
    - /var/log/metrics-service/*.log
  json.keys_under_root: true
  json.add_error_key: true

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  
logging.level: info
```

### Performance Tuning

#### Database Optimization

```sql
-- Analyze query performance
EXPLAIN QUERY PLAN SELECT * FROM metrics WHERE timestamp > '2024-01-01';

-- Update statistics
ANALYZE;

-- Optimize settings
PRAGMA optimize;
```

#### Application Tuning

```bash
# Increase batch size for high throughput
BATCH_SIZE=1000

# Reduce flush interval for low latency
FLUSH_INTERVAL_SECONDS=5

# Adjust rate limits based on capacity
METRICS_RATE_LIMIT=10000
```

This deployment guide provides comprehensive instructions for deploying the metrics service across different environments with proper security, monitoring, and maintenance procedures.