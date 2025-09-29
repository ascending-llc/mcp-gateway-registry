# Complete macOS Setup Guide: MCP Gateway & Registry

This guide provides a comprehensive, step-by-step walkthrough for setting up the MCP Gateway & Registry on macOS. Perfect for local development and testing.

## Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Cloning and Initial Setup](#2-cloning-and-initial-setup)
3. [Environment Configuration](#3-environment-configuration)
4. [Starting Keycloak Services](#4-starting-keycloak-services)
5. [Keycloak Configuration](#5-keycloak-configuration)
6. [Create Test Agent](#6-create-test-agent)
7. [Starting All Services](#7-starting-all-services)
8. [Verification and Testing](#8-verification-and-testing)
9. [Troubleshooting](#9-troubleshooting)

---

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
# Set authentication provider to Keycloak
AUTH_PROVIDER=keycloak

# Set secure passwords (CHANGE THESE!)
KEYCLOAK_ADMIN_PASSWORD=your_secure_admin_password_here
KEYCLOAK_DB_PASSWORD=your_secure_db_password_here

# Set your generated SECRET_KEY
SECRET_KEY=[paste-your-generated-key-here]


# Leave other Keycloak settings as default for now
KEYCLOAK_REALM=mcp-gateway
KEYCLOAK_CLIENT_ID=mcp-gateway-web
# Note: CLIENT_SECRET will be updated later after Keycloak initialization
```

**Important**: Choose strong, unique passwords and remember them - you'll need the admin password for Keycloak login!

---

## 4. Starting Keycloak Services

### Set Keycloak Passwords

**Important**: These environment variables will override the values in your `.env` file. Use the SAME passwords you configured in Step 4!

```bash
# Use the SAME passwords you set in the .env file in Step 4!
# Replace these with your actual passwords from Step 4
# Note: Use single quotes to prevent issues with special characters
export KEYCLOAK_ADMIN_PASSWORD='your-admin-password-here-from-env'
export KEYCLOAK_DB_PASSWORD='your-db-password-here-from-env'

# Verify they're set correctly
echo "Admin Password: $KEYCLOAK_ADMIN_PASSWORD"
echo "DB Password: $KEYCLOAK_DB_PASSWORD"
```

**Critical**: These passwords MUST match what you set in the `.env` file in Step 4. If they don't match, Keycloak initialization will fail!


### Start Database and Keycloak
```bash
# Start only the database and Keycloak services first
docker-compose up -d keycloak-db keycloak

# Check if services are starting
docker-compose ps

# Monitor Keycloak logs until ready
docker-compose logs -f keycloak
# Wait for: "Keycloak 25.x.x started in xxxms"
# Press Ctrl+C when you see this message
```

**Wait Time**: Allow 2-3 minutes for Keycloak to fully initialize.

### Verify Keycloak is Running
```bash
# Test basic connectivity
curl -s http://localhost:8080/realms/master | jq '.realm'
# Should return: "master"

# Check health status
docker-compose ps keycloak
# Should show "Up" status (may show "unhealthy" - this is normal for dev mode)
```

### Fix macOS SSL Requirement (Critical Step)
**Why this is needed on macOS**: Docker on macOS runs in a virtualized environment, which causes Keycloak to treat localhost requests as external network traffic. This triggers Keycloak's default security policy requiring HTTPS for external connections.

```bash
# Configure Keycloak admin CLI (use your actual admin password)
docker exec mcp-gateway-registry-keycloak-1 /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master --user admin --password "${KEYCLOAK_ADMIN_PASSWORD}"

# Disable SSL requirement for master realm
docker exec mcp-gateway-registry-keycloak-1 /opt/keycloak/bin/kcadm.sh update realms/master -s sslRequired=NONE

# Verify the fix worked
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/admin/"
# Should return: 302 (redirect to login - this is correct)
```

**Important**: This step MUST be completed before running the init-keycloak.sh script, or the initialization will fail.

---

## 5. Keycloak Configuration

### Initialize Keycloak Configuration

**Important**: This is a two-step process. The initialization script creates the realm and clients but does NOT save the credentials to files.

```bash
# Make the setup script executable
chmod +x keycloak/setup/init-keycloak.sh

# Step 1: Run the Keycloak initialization
./keycloak/setup/init-keycloak.sh

# Expected output:
# ✓ Waiting for Keycloak to be ready...
# ✓ Keycloak is ready!
# ✓ Logged in to Keycloak
# ✓ Created realm: mcp-gateway
# ✓ Created clients: mcp-gateway-web and mcp-gateway-m2m
# ... more success messages ...
# ✓ Client secrets generated!
#
# IMPORTANT: The script will tell you to run get-all-client-credentials.sh
# to retrieve and save the credentials. This is the next required step!

# Step 2: Retrieve and save all client credentials (REQUIRED)
chmod +x keycloak/setup/get-all-client-credentials.sh
./keycloak/setup/get-all-client-credentials.sh

# This will:
# - Connect to Keycloak and retrieve all client secrets
# - Save credentials to .oauth-tokens/keycloak-client-secrets.txt
# - Create individual JSON files: .oauth-tokens/<client-id>.json
# - Create individual env files: .oauth-tokens/<client-id>.env
# - Display a summary of all saved credentials

# Expected output:
# ✓ Admin token obtained
# ✓ Found and saved: mcp-gateway-web
# ✓ Found and saved: mcp-gateway-m2m
# Files created in: .oauth-tokens/
```

### Fix SSL Requirement for mcp-gateway Realm
**Important**: Now that the mcp-gateway realm is created, we need to disable SSL for it as well:

```bash
# Configure Keycloak admin CLI (if session expired)
docker exec mcp-gateway-registry-keycloak-1 /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master --user admin --password "${KEYCLOAK_ADMIN_PASSWORD}"

# Disable SSL requirement for the mcp-gateway realm
docker exec mcp-gateway-registry-keycloak-1 /opt/keycloak/bin/kcadm.sh update realms/mcp-gateway -s sslRequired=NONE

# Verify both realms are accessible
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/admin/"
# Should return: 302

curl -s http://localhost:8080/realms/mcp-gateway | jq '.realm'
# Should return: "mcp-gateway"
```

### Retrieve Client Credentials
```bash
# Make the credentials script executable
chmod +x keycloak/setup/get-all-client-credentials.sh

# Retrieve all client credentials
./keycloak/setup/get-all-client-credentials.sh
```

**Expected Output:**
```
Admin token obtained
Found and saved: mcp-gateway-web (Secret: JyJzW00JeUBaCmH9Z5xtYDhE2MsGqOSv)
Found and saved: mcp-gateway-m2m (Secret: iCjPsMLLmet124K8b7FCfcEcRJ9bx4Oo)
Files created in: .oauth-tokens/
```

### Update Environment with Client Secrets
```bash
# View the retrieved client secrets
cat .oauth-tokens/keycloak-client-secrets.txt

# Copy the secrets and update your .env file
nano .env

# Update these lines with the actual secret values:
# KEYCLOAK_CLIENT_SECRET=[paste-web-client-secret-here]
# KEYCLOAK_M2M_CLIENT_SECRET=[paste-m2m-client-secret-here]

# Save and exit (Ctrl+X, then Y, then Enter)
```

---

## 6. Create Your First AI Agent Account

```bash
# Make the agent setup script executable
chmod +x keycloak/setup/setup-agent-service-account.sh

# Create a test agent with full access
./keycloak/setup/setup-agent-service-account.sh \
  --agent-id test-agent \
  --group mcp-servers-unrestricted

# Create an agent for AI coding assistants (VS Code, cursor, etc.)
./keycloak/setup/setup-agent-service-account.sh \
  --agent-id ai-coding-assistant \
  --group mcp-servers-unrestricted

# Create an agent with restricted access for registry operations
./keycloak/setup/setup-agent-service-account.sh \
  --agent-id registry-operator \
  --group mcp-servers-restricted

# Note: The script does not display the credentials at the end.
# Your Client ID is: agent-test-agent-m2m

# Retrieve and save ALL client credentials (recommended):
./keycloak/setup/get-all-client-credentials.sh

# This will:
# - Retrieve credentials for ALL clients in the realm
# - Save all credentials to .oauth-tokens/keycloak-client-secrets.txt
# - Create individual JSON files: .oauth-tokens/<client-id>.json
# - Create individual env files: .oauth-tokens/<client-id>.env
# - Display a summary of all credentials saved

# Or to get just one specific client:
./keycloak/setup/get-agent-credentials.sh agent-test-agent-m2m
```

**Important**: Save the Client ID and Client Secret shown in the output. You'll need these to authenticate your AI agents.

### Update .env File with Client Secrets

**Critical Step**: After running `get-all-client-credentials.sh`, you MUST update your `.env` file with the retrieved client secrets:

```bash
# View the retrieved client secrets
cat .oauth-tokens/keycloak-client-secrets.txt

# You'll see output like:
# KEYCLOAK_CLIENT_ID=mcp-gateway-web
# KEYCLOAK_CLIENT_SECRET=JyJzW00JeUBaCmH9Z5xtYDhE2MsGqOSv
#
# KEYCLOAK_M2M_CLIENT_ID=mcp-gateway-m2m
# KEYCLOAK_M2M_CLIENT_SECRET=iCjPsMLLmet124K8b7FCfcEcRJ9bx4Oo

# Update your .env file with these exact secret values
nano .env

# Find and update these lines with the actual secret values from above:
# KEYCLOAK_CLIENT_SECRET=JyJzW00JeUBaCmH9Z5xtYDhE2MsGqOSv
# KEYCLOAK_M2M_CLIENT_SECRET=iCjPsMLLmet124K8b7FCfcEcRJ9bx4Oo

# Save and exit (Ctrl+X, then Y, then Enter)
```

**Note**: These secrets are auto-generated by Keycloak and are different each time you run `init-keycloak.sh`. Always use the latest values from `.oauth-tokens/keycloak-client-secrets.txt`.

### Generate Access Tokens for All Keycloak Users and Agents

Generate access tokens for all configured agents and users:

```bash
# Generate access tokens for all agents
./credentials-provider/keycloak/generate_tokens.py --all-agents
```

This will create access token files (both `.json` and `.env` formats) for all Keycloak service accounts in the `.oauth-tokens/` directory.

**Note**: If you want tokens to last longer than the default 5 minutes, see [Configure Token Lifetime](#configure-token-lifetime) before generating tokens.

### Verify Keycloak is Running

Open a web browser and navigate to:
```
http://localhost:8080
```

You should see the Keycloak login page. You can log in with:
- Username: `admin`
- Password: The password you set in KEYCLOAK_ADMIN_PASSWORD

---

## 7. Starting All Services

### Start Services with Pre-built Images

**Important macOS Docker Volume Sharing**: On macOS, Docker Desktop only shares certain directories by default (like `/Users`, `/tmp`, `/private`). The `/opt` and `/var/log` directories we need are NOT shared by default, so we must create them with proper ownership for Docker containers to access them.

**Note**: If you encounter permission issues, you may need to add `/opt` to Docker Desktop's shared directories:
1. Open Docker Desktop
2. Go to Settings > Resources > Virtual file shares
3. Add `/opt` to the list of shared directories
4. Click "Apply & Restart"

```bash
# Create necessary directories with proper ownership
# Note: /opt is not shared with Docker by default on macOS, so we need sudo + chown
sudo mkdir -p /opt/mcp-gateway/{servers,models,auth_server,secrets/fininfo}
sudo mkdir -p /opt/ssl /var/log/mcp-gateway

# Change ownership from root to your user so Docker containers can write to these directories
sudo chown -R $(whoami):$(id -gn) /opt/mcp-gateway
sudo chown -R $(whoami):$(id -gn) /opt/ssl
sudo chown -R $(whoami):$(id -gn) /var/log/mcp-gateway

# Make build script executable
chmod +x build_and_run.sh

# Start all services using pre-built images (faster, no build required)
./build_and_run.sh --prebuilt

# This will:
# - Use pre-built container images from Docker registry
# - Skip React frontend build (already included in images)
# - Create necessary directories
# - Start all services
# - Much faster than building locally!
```

**Benefits of using `--prebuilt`:**
- **Instant deployment**: No build time required
- **No Node.js issues**: Pre-built frontend already included
- **Consistent experience**: Same tested images for all users
- **Bandwidth efficient**: Optimized, compressed images

### Verify All Services are Running
```bash
# Check all services status
docker-compose ps

# Expected services (all should show "Up"):
# - keycloak-db
# - keycloak
# - auth-server
# - registry
# - nginx (or similar proxy)
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

## 8. Verification and Testing

### Test Web Interface
1. **Open your web browser** and navigate to:
   ```
   http://localhost
   ```

2. **Login Page**: You should see the MCP Gateway Registry login page

3. **Login with Keycloak**: Click "Login with Keycloak" and use:
   - Username: `admin`
   - Password: The password you set in KEYCLOAK_ADMIN_PASSWORD

### Test API Access
```bash
# Test registry health
curl http://localhost/health
# Expected: {"status":"healthy","timestamp":"..."}

# Test Keycloak realm
curl http://localhost:8080/realms/mcp-gateway | jq '.realm'
# Expected: "mcp-gateway"
```

### Test Python MCP Client
```bash
# Activate virtual environment
source .venv/bin/activate

# Load agent credentials
source .oauth-tokens/agent-test-agent-m2m.env

# Test connectivity
uv run python mcp_client.py ping

# Expected output:
# ✓ M2M authentication successful
# Session established: [session-id]
# {"jsonrpc": "2.0", "id": 2, "result": {}}

# List available tools
uv run python mcp_client.py list

# Test a simple tool
uv run python mcp_client.py --url http://localhost/currenttime/mcp call --tool current_time_by_timezone --args '{"tz_name":"America/New_York"}'
```

### Test Admin Console
```bash
# Access Keycloak admin console
open http://localhost:8080/admin/

# Login with:
# Username: admin
# Password: The password you set in KEYCLOAK_ADMIN_PASSWORD

# You should see the Keycloak admin interface
# Navigate to: mcp-gateway realm > Clients
# Verify: mcp-gateway-web and mcp-gateway-m2m clients exist
```

---

## 9. Troubleshooting

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

#### Permission Issues
```bash
# Fix Docker permissions
sudo chown -R $(whoami) ~/.docker

# Fix file permissions
chmod +x keycloak/setup/*.sh
chmod +x build_and_run.sh

# Fix directory ownership for Docker volumes (macOS specific)
sudo chown -R $(whoami):$(id -gn) /opt/mcp-gateway
sudo chown -R $(whoami):$(id -gn) /opt/ssl
sudo chown -R $(whoami):$(id -gn) /var/log/mcp-gateway
```

#### Keycloak "HTTPS Required" Error
```bash
# This was fixed in Section 4, but if it persists:

# Re-run SSL disable commands (use your actual admin password)
docker exec mcp-gateway-registry-keycloak-1 /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master --user admin --password "${KEYCLOAK_ADMIN_PASSWORD}"

docker exec mcp-gateway-registry-keycloak-1 /opt/keycloak/bin/kcadm.sh update realms/master -s sslRequired=NONE

# Also disable for the mcp-gateway realm after it's created
docker exec mcp-gateway-registry-keycloak-1 /opt/keycloak/bin/kcadm.sh update realms/mcp-gateway -s sslRequired=NONE
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

#### Authentication Failures
```bash
# Check client secrets match
cat .oauth-tokens/keycloak-client-secrets.txt
cat .env | grep KEYCLOAK_CLIENT_SECRET

# They should match! If not, update .env file

# Restart auth-server after updating secrets
docker-compose restart auth-server
```

#### "oauth2_callback_failed" Error
```bash
# Check auth-server logs
docker-compose logs auth-server | tail -20

# Usually caused by wrong client secret
# Regenerate credentials:
./keycloak/setup/get-all-client-credentials.sh

# Update .env file with new secrets
nano .env

# Restart auth-server
docker-compose restart auth-server
```

### Reset Everything
If you need to start over completely:
```bash
# Stop and remove all containers and data
docker-compose down -v

# Remove Docker images (optional)
docker system prune -a

# Remove generated files
rm -rf .oauth-tokens/
rm .env

# Start fresh from Section 3
cp .env.example .env
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

- **Authentication**: Enterprise-grade Keycloak identity provider
- **Registry**: Web-based interface for managing MCP servers
- **API Gateway**: Centralized access to multiple MCP servers
- **Agent Support**: Ready for AI coding assistants and agents

### Key URLs:
- **Registry**: http://localhost
- **Keycloak Admin**: http://localhost:8080/admin
- **API Gateway**: http://localhost/mcpgw/mcp
- **Individual Services**: http://localhost/[service-name]/mcp

### Key Files:
- **Configuration**: `.env`
- **Client Credentials**: `.oauth-tokens/keycloak-client-secrets.txt`
- **Agent Tokens**: `.oauth-tokens/agent-*-m2m.env`

### Next Steps:
1. **Configure your AI coding assistant** with the generated MCP configuration
2. **Create additional agents** using the setup-agent-service-account.sh script
3. **Add custom MCP servers** by editing docker-compose.yml
4. **Explore the web interface** to manage servers and view metrics

**Remember**: Save your credentials securely and keep Docker Desktop running when using the system!

### Getting Help
- **GitHub Issues**: https://github.com/agentic-community/mcp-gateway-registry/issues
- **Documentation**: Check `/docs` folder for additional guides
- **Logs**: Always check `docker-compose logs` for troubleshooting