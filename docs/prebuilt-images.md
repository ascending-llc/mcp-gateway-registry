# Pre-built Docker Images for MCP Gateway Registry

When using the `--prebuilt` option with `build_and_run.sh`, the following pre-built Docker images are pulled from Docker Hub. These images are published to the `mcpgateway` organization on Docker Hub.

## MCP Gateway Images

| Service | Image | Default Tag | Description | Port |
|---------|-------|-------------|-------------|------|
| Registry | `mcpgateway/registry:latest` | latest | Main registry service with nginx, SSL, FAISS, and models | 80, 443, 7860 |
| Auth Server | `mcpgateway/auth-server:latest` | latest | Authentication service supporting Cognito, GitHub, Google, and Keycloak | 8888 |
| Metrics Service | `mcpgateway/metrics-service:latest` | latest | Metrics collection service with SQLite storage and OTEL support | 8890, 9465 |
| Current Time Server | `mcpgateway/currenttime-server:latest` | latest | MCP server providing current time functionality | 8000 |
| Financial Info Server | `mcpgateway/fininfo-server:latest` | latest | MCP server for financial information | 8001 |
| MCPGW Server | `mcpgateway/mcpgw-server:latest` | latest | MCP Gateway server for service management | 8003 |
| Real Server Fake Tools | `mcpgateway/realserverfaketools-server:latest` | latest | Example MCP server with mock tools | 8002 |

## External Images

The following external images are pulled from their original sources:

| Service | Image | Source | Description | Port |
|---------|-------|--------|-------------|------|
| Atlassian Server | `ghcr.io/sooperset/mcp-atlassian:latest` | GitHub Container Registry | Atlassian (Jira/Confluence) integration MCP server | 8005 |
| Alpine Linux | `alpine:latest` | Docker Hub Official | Lightweight Linux for metrics database initialization | N/A |
| Prometheus | `prom/prometheus:latest` | Docker Hub Official | Metrics collection and time-series database | 9090 |
| Grafana | `grafana/grafana:latest` | Docker Hub Official | Metrics visualization and dashboards | 3000 |
| PostgreSQL | `postgres:16-alpine` | Docker Hub Official | Database for Keycloak | 5432 (internal) |
| Keycloak | `quay.io/keycloak/keycloak:25.0` | Quay.io | Identity and access management service | 8080 |

## Manual Download Commands

To manually pull these images for Kubernetes deployment or offline use:

```bash
# MCP Gateway images from Docker Hub
docker pull mcpgateway/registry:latest
docker pull mcpgateway/auth-server:latest
docker pull mcpgateway/metrics-service:latest
docker pull mcpgateway/currenttime-server:latest
docker pull mcpgateway/fininfo-server:latest
docker pull mcpgateway/mcpgw-server:latest
docker pull mcpgateway/realserverfaketools-server:latest

# External images
docker pull ghcr.io/sooperset/mcp-atlassian:latest
docker pull alpine:latest
docker pull prom/prometheus:latest
docker pull grafana/grafana:latest
docker pull postgres:16-alpine
docker pull quay.io/keycloak/keycloak:25.0
```

## HTTPS Configuration

By default, pre-built images run on HTTP (port 80) only. To enable HTTPS (port 443):

### Option 1: Let's Encrypt Certificates

```bash
# Install certbot
sudo apt-get update && sudo apt-get install -y certbot

# Obtain certificate (requires domain and port 80)
sudo certbot certonly --standalone -d your-domain.com

# Certificate files will be at:
# - /etc/letsencrypt/live/your-domain/fullchain.pem
# - /etc/letsencrypt/live/your-domain/privkey.pem
```

### Option 2: Commercial CA Certificates

Purchase SSL certificates from a trusted Certificate Authority.

### Copy Certificates to Expected Location

```bash
# Create the ssl directory structure
mkdir -p ${HOME}/mcp-gateway/ssl/certs
mkdir -p ${HOME}/mcp-gateway/ssl/private

# Copy your certificate files
# Replace paths below with your actual certificate locations
cp /etc/letsencrypt/live/your-domain/fullchain.pem ${HOME}/mcp-gateway/ssl/certs/fullchain.pem
cp /etc/letsencrypt/live/your-domain/privkey.pem ${HOME}/mcp-gateway/ssl/private/privkey.pem

# Set proper permissions
chmod 644 ${HOME}/mcp-gateway/ssl/certs/fullchain.pem
chmod 600 ${HOME}/mcp-gateway/ssl/private/privkey.pem
```

**Note**: If SSL certificates are not present at `${HOME}/mcp-gateway/ssl/certs/fullchain.pem` and `${HOME}/mcp-gateway/ssl/private/privkey.pem`, the MCP Gateway will automatically run in HTTP-only mode.

Then restart:

```bash
./build_and_run.sh --prebuilt
```

The registry container will detect the certificates and enable HTTPS automatically. Check logs:

```bash
docker compose logs registry | grep -i ssl
# Expected: "SSL certificates found - HTTPS enabled"
```