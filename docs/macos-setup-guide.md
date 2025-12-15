# Complete macOS Setup Guide: MCP Gateway & Registry

This guide provides a comprehensive, step-by-step walkthrough for setting up the MCP Gateway & Registry on macOS. Perfect for local development and testing.

## Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Cloning and Initial Setup](#2-cloning-and-initial-setup)
3. [Environment Configuration](#3-environment-configuration)
4. [Starting All Services](#4-starting-all-services)
5. [Verification and Testing](#5-verification-and-testing)
6. [Troubleshooting](#6-troubleshooting)

## 1. Prerequisites

### System Requirements
- **macOS**: 12.0 (Monterey) or later
- **RAM**: At least 8GB (16GB recommended)
- **Storage**: At least 10GB free space
- **Administrator Access**: Sudo privileges required for Docker volume setup

### Required Software
- **Docker Desktop**: Install from https://www.docker.com/products/docker-desktop/
- **Docker Compose**: Included with Docker Desktop
- **Node.js**: Version 20.x LTS - Install from https://nodejs.org/ or via Homebrew
- **Python**: Version 3.12+ - Install via Homebrew (`brew install python@3.12`)
- **UV Package Manager**: Install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Git**: Usually pre-installed on macOS
- **jq**: Install via Homebrew (`brew install jq`)

**Important**: Make sure Docker Desktop is running before proceeding!

---

## 2. Cloning and Initial Setup

### Clone the Repository
```bash
# Create workspace directory
mkdir -p ~/workspace
cd ~/workspace

# Clone the repository
git clone https://github.com/agentic-community/mcp-gateway-registry.git
cd mcp-gateway-registry

# Verify you're in the right directory
ls -la
# Should see: docker-compose.yml, .env.example, README.md, etc.
```

### Setup Python Virtual Environment
```bash
# Create and activate Python virtual environment
uv sync
# Create extra embedded-search dependency
uv sync --extra embedded-search
source .venv/bin/activate

# Verify virtual environment is active
which python
# Should show: /Users/[username]/workspace/mcp-gateway-registry/.venv/bin/python
```

---

## 3. Environment Configuration

### Create Environment File
```bash
# Copy the example environment file
cp .env.example .env

# Generate a secure SECRET_KEY
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
echo "Generated SECRET_KEY: $SECRET_KEY"

# Open .env file for editing
nano .env
```

### Configure Essential Settings
In the `.env` file, make these changes:

```bash
# Set authentication provider to Microsoft Entra ID
AUTH_PROVIDER=entra

# Set Entra ID Settings
ENTRA_TENANT_ID=your_tenant_id
ENTRA_CLIENT_ID=your_client_id
ENTRA_CLIENT_SECRET=your_client_secret

# Set your generated SECRET_KEY
SECRET_KEY=[paste-your-generated-key-here]
```

### Download Required Embeddings Model

The MCP Gateway requires a sentence-transformers model for intelligent tool discovery. Download it to the shared models directory:

```bash
# Download the embeddings model (this may take a few minutes)
huggingface-cli download sentence-transformers/all-MiniLM-L6-v2 --local-dir ${HOME}/mcp-gateway/models/all-MiniLM-L6-v2

# Verify the model was downloaded
ls -la ${HOME}/mcp-gateway/models/all-MiniLM-L6-v2/
# You should see model files like model.safetensors, config.json, etc.
```

**Note**: This command automatically creates the necessary directory structure and downloads all required model files (~90MB). If you don't have `huggingface-cli` command installed, install it first with `uv pip install huggingface_hub[cli]` or `uv tool install huggingface-cli`.


### Create Docker Compose Override File 

```bash
cp .docker-compose.override.yml.example .docker-compose.override.yml

# open docker compose override file for editing
nano .docker-compose.override.yml
```

### Configure Docker Compose 

```yaml
  # Example: Disable Keycloak if using Entra ID
  keycloak:
    profiles:
      - disabled
    keycloak-db:
      profiles:
      - disabled
  
  # Example: Disable Frontend container if running Vite Server
  # registry-frontend:
  #  profiles:
  #   - disabled 
```

## 4. Starting All Services

### Start Services with Docker Compose

```bash
docker-compose up -d
```

**Important macOS Docker Volume Sharing**: On macOS, Docker Desktop only shares certain directories by default (like `/Users`, `/tmp`, `/private`). The `/opt` and `/var/log` directories we need are NOT shared by default, so we must create them with proper ownership for Docker containers to access them.

**Note**: If you encounter permission issues, you may need to add `/opt` to Docker Desktop's shared directories:
1. Open Docker Desktop
2. Go to Settings > Resources > Virtual file shares
3. Add `/opt` to the list of shared directories
4. Click "Apply & Restart"


### Verify All Services are Running
```bash
# Check all services status
docker-compose ps

# Expected services (all should show "Up"):
# - auth-server
# - registry
# - registry-frontend
# - currenttime-server
# - fininfo-server
# - mcpgw-server
# - realserverfaketools-server
```

### Monitor Service Logs
```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f auth-server
docker-compose logs -f registry

# Press Ctrl+C to exit log viewing
```

---

## 5. Verification and Testing

### Test Web Interface
1. **Open your web browser** and navigate to:
   ```
   http://localhost
   ```

2. **Login Page**: You should see the MCP Gateway Registry login page

3. **Login with Entra ID**: Click "Login with Entra ID" and use:

### Test API Access
```bash
# Test registry health
curl http://localhost/health
# Expected: {"status":"healthy","timestamp":"..."}

```

### Test Python MCP Client
```bash
# Activate virtual environment
source .venv/bin/activate

# Load agent credentials
source .oauth-tokens/agent-test-agent-m2m.env

# Test connectivity
uv run cli/mcp_client.py ping

# Expected output:
# ✓ M2M authentication successful
# Session established: [session-id]
# {"jsonrpc": "2.0", "id": 2, "result": {}}

# List available tools
uv run cli/mcp_client.py list

# Test a simple tool
uv run cli/mcp_client.py --url http://localhost/currenttime/mcp call --tool current_time_by_timezone --args '{"tz_name":"America/New_York"}'
```

---

## 6. Troubleshooting

### Common macOS Issues

#### Docker Not Running
```bash
# Check if Docker is running
docker ps

# If error, start Docker Desktop from Applications
# Wait for whale icon to appear in menu bar
```

#### Port Conflicts
```bash
# Check what's using ports
lsof -i :80
lsof -i :8080
lsof -i :7860

# Kill conflicting processes if needed
sudo lsof -ti :80 | xargs kill
```

#### Services Won't Start
```bash
# Check Docker memory/CPU limits in Docker Desktop preferences
# Recommended: 4GB RAM, 2 CPUs minimum

# Check disk space
df -h

# Restart all services
docker-compose down
docker-compose up -d
```

### Reset Everything
If you need to start over completely:
```bash
# Stop and remove all containers and data
docker-compose down -v

# Remove Docker images (optional)
docker system prune -a

# Start fresh from Section 3
cp .env.example .env
cp .docker-compose.override.yml.example .docker-compose.override.yml
```

### View Service Status
```bash
# Check all service status
docker-compose ps

# Check specific service health
docker-compose logs [service-name] --tail 50

# Check resource usage
docker stats
```

### macOS-Specific Logs
```bash
# Check Console.app for system logs
# Check Docker Desktop logs via Docker Desktop > Troubleshoot > Get support

# Check local network issues
ping localhost
telnet localhost 8080
```

---

## Summary

You now have a fully functional MCP Gateway & Registry running on macOS! The system provides:

- **Authentication**: Micosoft Entra ID identity provider
- **Registry**: Web-based interface for managing MCP servers
- **API Gateway**: Centralized access to multiple MCP servers
- **Agent Support**: Ready for AI coding assistants and agents

### Key URLs:
- **Registry**: http://localhost
- **API Gateway**: http://localhost/mcpgw/mcp
- **Individual Services**: http://localhost/[service-name]/mcp

### Key Files:
- **Configuration**: `.env`
- **MCP Server Data**: `registry/servers/*.json`
- **Agent Tokens**: `.oauth-tokens/agent-*-m2m.env`

### Next Steps:
1. **Configure your AI coding assistant** with the generated MCP configuration
2. **Create additional agents** using the setup-agent-service-account.sh script
3. **Add custom MCP servers** by editing docker-compose.yml
4. **Explore the web interface** to manage servers and view metrics

**Remember**: Save your credentials securely and keep Docker Desktop running when using the system!

### Getting Help
- **Documentation**: Check `/docs` folder for additional guides
- **Logs**: Always check `docker-compose logs` for troubleshooting