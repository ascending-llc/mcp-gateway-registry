# Quick Start Guide

Get the MCP Gateway & Registry running in 5 minutes with this streamlined setup guide.

## What You'll Accomplish

By the end of this guide, you'll have:
- ✅ MCP Gateway & Registry running locally
- ✅ Authentication configured with Amazon Cognito  
- ✅ AI coding assistant (VS Code) connected to the gateway
- ✅ Access to curated enterprise MCP tools

## Prerequisites

- **Amazon Cognito Setup**: You'll need Cognito credentials (see [minimal setup](#amazon-cognito-minimal-setup))
- **Docker**: Docker and Docker Compose installed
- **Basic Command Line**: Comfort with terminal/command prompt

## Step 1: Clone and Configure

```bash
# Clone the repository
git clone https://github.com/agentic-community/mcp-gateway-registry.git
cd mcp-gateway-registry

# Copy and edit environment configuration
cp .env.example .env
```

**Edit `.env` with your values:**
```bash
# Required - Replace with your actual values
COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
COGNITO_CLIENT_ID=your_cognito_client_id
COGNITO_CLIENT_SECRET=your_cognito_client_secret
AWS_REGION=us-east-1
ADMIN_PASSWORD=your-secure-password

# Optional - Will be auto-generated if not provided
SECRET_KEY=optional-secret-key-for-sessions
```

## Step 2: Generate Authentication

```bash
# Configure OAuth credentials for client access
cp credentials-provider/oauth/.env.example credentials-provider/oauth/.env

# Edit with minimal configuration
nano credentials-provider/oauth/.env
```

**Add to `credentials-provider/oauth/.env`:**
```bash
# Ingress authentication (required for client access)
AWS_REGION=us-east-1
INGRESS_OAUTH_USER_POOL_ID=us-east-1_XXXXXXXXX
INGRESS_OAUTH_CLIENT_ID=your_cognito_client_id
INGRESS_OAUTH_CLIENT_SECRET=your_cognito_client_secret
```

```bash
# Generate authentication tokens and client configurations
./credentials-provider/generate_creds.sh
```

## Step 3: Install and Deploy

```bash
# Install Python environment
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Install Docker (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo usermod -a -G docker $USER
newgrp docker

# Deploy all services
./build_and_run.sh
```

⏱️ **This takes about 2-3 minutes** - Docker will build images and start services.

## Step 4: Verify Installation

```bash
# Check all services are running
docker-compose ps

# You should see services like:
# - registry (port 7860)  
# - auth-server (port 8888)
# - nginx (ports 80/443)
# - Various MCP servers (ports 8000-8003)
```

**Access the web interface:**
```bash
# Open in browser
open http://localhost:7860

# Or visit: http://localhost:7860
```

**Login options:**
- **Username**: `admin` (or your `ADMIN_USER` value)
- **Password**: Your `ADMIN_PASSWORD` value

## Step 5: Connect AI Coding Assistant

### VS Code Setup (Recommended for first test)

```bash
# Copy generated VS Code configuration
cp .oauth-tokens/vscode-mcp.json ~/.vscode/settings.json

# If you have existing settings, merge instead:
cat .oauth-tokens/vscode-mcp.json >> ~/.vscode/settings.json
```

### Test the Connection

1. **Open VS Code** with MCP extension installed
2. **Open Command Palette** (`Ctrl+Shift+P` or `Cmd+Shift+P`)
3. **Run MCP command** - you should see available MCP servers
4. **Try a tool** - test with "current time" tool

### Alternative: Roo Code Setup

```bash
# For Roo Code users
cp .oauth-tokens/mcp.json ~/.vscode/mcp-settings.json
```

## Step 6: Test Everything Works

```bash
# Test gateway connectivity
cd tests
./mcp_cmds.sh ping

# Should return successful ping response

# Test specific tool
./mcp_cmds.sh call currenttime current_time_by_timezone '{"tz_name": "America/New_York"}'
```

**Expected result:** Current time in New York timezone

## 🎉 Success! What's Next?

You now have a fully functional MCP Gateway & Registry! Here are your next steps:

### Immediate Next Steps
- 🔍 **Explore the Web Interface** - Browse available MCP servers and tools
- 🤖 **Try AI Assistant Integration** - Use tools through VS Code or your preferred AI assistant
- 🛠️ **Add Your Own MCP Servers** - Register custom tools for your team

### Expand Your Setup
- 📚 **[Full Installation Guide](installation.md)** - Production deployment options
- 🔐 **[Authentication Setup](auth.md)** - Advanced identity provider configuration
- 🎯 **[AI Assistants Guide](ai-coding-assistants-setup.md)** - Connect more development tools

### Enterprise Features
- 👥 **[Fine-Grained Access Control](scopes.md)** - Team-based permissions
- 📊 **[Monitoring & Analytics](monitoring.md)** - Usage tracking and health monitoring
- 🏢 **[Production Deployment](production-deployment.md)** - High availability and scaling

## Amazon Cognito Minimal Setup

If you don't have Amazon Cognito configured yet, here's the minimal setup:

### 1. Create User Pool

```bash
# Using AWS CLI
aws cognito-idp create-user-pool \
  --pool-name mcp-gateway-users \
  --policies PasswordPolicy='{MinimumLength=8,RequireUppercase=false,RequireLowercase=false,RequireNumbers=false,RequireSymbols=false}' \
  --region us-east-1
```

### 2. Create User Pool Client

```bash
# Create app client
aws cognito-idp create-user-pool-client \
  --user-pool-id us-east-1_XXXXXXXXX \
  --client-name mcp-gateway-client \
  --generate-secret \
  --explicit-auth-flows ADMIN_NO_SRP_AUTH CLIENT_CREDENTIALS \
  --supported-identity-providers COGNITO \
  --region us-east-1
```

### 3. Create Test User

```bash
# Create admin user
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_XXXXXXXXX \
  --username admin \
  --temporary-password TempPass123! \
  --message-action SUPPRESS \
  --region us-east-1

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_XXXXXXXXX \
  --username admin \
  --password YourSecurePassword123! \
  --permanent \
  --region us-east-1
```

**For complete Cognito setup:** See [Amazon Cognito Setup Guide](cognito.md)

## Troubleshooting Quick Fixes

### Services Won't Start
```bash
# Check Docker daemon
sudo systemctl status docker
sudo systemctl start docker

# Check port conflicts
sudo netstat -tlnp | grep -E ':(80|443|7860|8080)'
```

### Authentication Errors
```bash
# Verify Cognito configuration
aws cognito-idp describe-user-pool --user-pool-id YOUR_POOL_ID

# Regenerate credentials
./credentials-provider/generate_creds.sh
```

### Can't Access Web Interface
```bash
# Check if registry is running
curl http://localhost:7860/health

# Check logs
docker-compose logs registry
```

### AI Assistant Not Connecting
```bash
# Verify configuration file exists
ls -la ~/.vscode/settings.json

# Test authentication manually
curl -H "Authorization: Bearer $(cat .oauth-tokens/ingress.json | jq -r .access_token)" \
  http://localhost/mcpgw/sse
```

## Getting Help

- 📖 **[Full Documentation](/)** - Comprehensive guides and references
- 🐛 **[GitHub Issues](https://github.com/agentic-community/mcp-gateway-registry/issues)** - Bug reports and feature requests
- 💬 **[GitHub Discussions](https://github.com/agentic-community/mcp-gateway-registry/discussions)** - Community support and questions
- 📧 **[Troubleshooting Guide](troubleshooting.md)** - Common issues and detailed solutions

---

**🎯 Pro Tip:** Once you have the basic setup working, explore the [AI Coding Assistants Setup Guide](ai-coding-assistants-setup.md) to connect additional development tools like Cursor, Claude Code, and Cline for a complete enterprise AI development experience!