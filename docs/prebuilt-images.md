# Pre-built Docker Images for MCP Gateway Registry

When using the `--prebuilt` option with `build_and_run.sh`, the following pre-built Docker images are pulled from Docker Hub. These images are published to the `mcpgateway` organization on Docker Hub.

## MCP Gateway Images

| Service | Image | Default Tag | Description | Port |
|---------|-------|-------------|-------------|------|
| Registry | `mcpgateway/registry:latest` | latest | Main registry service with nginx, SSL, FAISS, and models | 80, 443, 7860 |
| Auth Server | `mcpgateway/auth-server:latest` | latest | Authentication service supporting Cognito, GitHub, Google, and Keycloak | 8888 |
| Current Time Server | `mcpgateway/currenttime-server:latest` | latest | MCP server providing current time functionality | 8000 |
| Financial Info Server | `mcpgateway/fininfo-server:latest` | latest | MCP server for financial information | 8001 |
| MCPGW Server | `mcpgateway/mcpgw-server:latest` | latest | MCP Gateway server for service management | 8003 |
| Real Server Fake Tools | `mcpgateway/realserverfaketools-server:latest` | latest | Example MCP server with mock tools | 8002 |

## External Images

| Service | Image | Source | Description | Port |
|---------|-------|--------|-------------|------|
| Atlassian Server | `ghcr.io/sooperset/mcp-atlassian:latest` | GitHub Container Registry | Atlassian (Jira/Confluence) integration MCP server | 8005 |
| PostgreSQL | `postgres:16-alpine` | Docker Hub Official | Database for Keycloak | 5432 (internal) |
| Keycloak | `quay.io/keycloak/keycloak:25.0` | Quay.io | Identity and access management service | 8080 |

## Manual Download Commands

To manually pull these images for Kubernetes deployment or offline use:

```bash
# MCP Gateway images from Docker Hub
docker pull mcpgateway/registry:latest
docker pull mcpgateway/auth-server:latest
docker pull mcpgateway/currenttime-server:latest
docker pull mcpgateway/fininfo-server:latest
docker pull mcpgateway/mcpgw-server:latest
docker pull mcpgateway/realserverfaketools-server:latest

# External images
docker pull ghcr.io/sooperset/mcp-atlassian:latest
docker pull postgres:16-alpine
docker pull quay.io/keycloak/keycloak:25.0
```