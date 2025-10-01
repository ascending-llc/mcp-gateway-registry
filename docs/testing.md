# MCP Gateway Testing Guide

This guide provides comprehensive testing instructions for the MCP Gateway using both the CLI client and the Python agent.

## Table of Contents
- [Regenerate Credentials](#regenerate-credentials)
- [Quick Start Testing](#quick-start-testing)
- [CLI Testing with mcp_client.py](#cli-testing-with-mcp_clientpy)
- [Python Agent Testing](#python-agent-testing)
- [Authentication Testing](#authentication-testing)
- [Service Management Testing](#service-management-testing)
- [Troubleshooting](#troubleshooting)

## Regenerate Credentials

**⚠️ Important:** Unless changed, Keycloak has an access token lifetime of only 5 minutes. You will most likely need to regenerate credentials before testing.

### Generate Fresh Credentials

Run the credential generation script to create fresh tokens:

```bash
# Generate new credentials for all agents and services
./credentials-provider/generate_creds.sh
```

This script will:
- Generate fresh access tokens for all configured agents
- Create M2M (machine-to-machine) tokens for service authentication
- Update all credential files in `.oauth-tokens/` directory
- Ensure tokens are valid for the current testing session

**Note:** The script should be run whenever you encounter authentication errors or when tokens have expired (every 5 minutes by default).

## Quick Start Testing

### Prerequisites
1. Ensure all containers are running:
   ```bash
   docker-compose ps
   ```

2. Set up authentication (choose one method):
   ```bash
   # Method 1: Source M2M credentials
   source .oauth-tokens/agent-test-agent-m2m.env

   # Method 2: Automatic ingress token
   # The CLI will automatically use .oauth-tokens/ingress.json if available
   ```

### Basic Connectivity Test
```bash
# Test gateway connectivity
uv run python cli/mcp_client.py ping

# List available tools
uv run python cli/mcp_client.py list
```

## CLI Testing with mcp_client.py

The `mcp_client.py` tool provides direct access to MCP servers and gateway functionality.

### Core Commands

#### 1. Ping (Connectivity Test)
```bash
# Ping default gateway
uv run python cli/mcp_client.py ping

# Ping specific server
uv run python cli/mcp_client.py --url http://localhost/currenttime/mcp ping
```

#### 2. List Tools
```bash
# List tools from gateway
uv run python cli/mcp_client.py list

# List tools from specific server
uv run python cli/mcp_client.py --url http://localhost/currenttime/mcp list
```

#### 3. Call Tools
```bash
# Find tools using natural language
uv run python cli/mcp_client.py call \
  --tool intelligent_tool_finder \
  --args '{"natural_language_query": "get current time"}'

# Call specific tool with arguments
uv run python cli/mcp_client.py --url http://localhost/currenttime/mcp call \
  --tool current_time_by_timezone \
  --args '{"tz_name": "America/New_York"}'

# Health check all services
uv run python cli/mcp_client.py --url http://localhost/mcpgw/mcp call \
  --tool healthcheck \
  --args '{}'
```

### Advanced Examples

#### Tool Discovery
```bash
# Find tools by description
uv run python cli/mcp_client.py call \
  --tool intelligent_tool_finder \
  --args '{"natural_language_query": "time zone tools", "top_n_tools": 5}'

# Find tools by tags
uv run python cli/mcp_client.py call \
  --tool intelligent_tool_finder \
  --args '{"tags": ["time", "timezone"], "top_n_tools": 3}'
```

#### Service Management
```bash
# List all registered services
uv run python cli/mcp_client.py --url http://localhost/mcpgw/mcp call \
  --tool list_services \
  --args '{}'

# Register a new service
uv run python cli/mcp_client.py --url http://localhost/mcpgw/mcp call \
  --tool register_service \
  --args '{"server_name": "Test Server", "path": "/test", "proxy_pass_url": "http://test:8000"}'

# Remove a service
uv run python cli/mcp_client.py --url http://localhost/mcpgw/mcp call \
  --tool remove_service \
  --args '{"service_path": "/test"}'
```

## Python Agent Testing

The Python agent (`agents/agent.py`) provides advanced AI capabilities with LangGraph-based multi-turn conversations.

### Prerequisites
```bash
# Install dependencies
cd agents
pip install -r requirements.txt
```

### Basic Usage

#### Non-Interactive Mode
```bash
# Simple query with default settings
uv run python agents/agent.py --prompt "What time is it in Tokyo?"

# Use specific model provider
uv run python agents/agent.py --provider anthropic --prompt "Get the current time"

# Use Amazon Bedrock
uv run python agents/agent.py --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0 \
  --prompt "What tools are available?"
```

#### Interactive Mode
```bash
# Start interactive conversation
uv run python agents/agent.py --interactive

# Interactive with specific model
uv run python agents/agent.py --interactive --provider anthropic

# Interactive with verbose output
uv run python agents/agent.py --interactive --verbose
```

### Authentication Options

#### Using Agent Credentials
```bash
# Load credentials from .oauth-tokens/{agent-name}.json
uv run python agents/agent.py --agent-name test-agent --prompt "List available tools"
```

#### Using JWT Token
```bash
# Use pre-generated JWT token
uv run python agents/agent.py --jwt-token "your-jwt-token" --prompt "Get current time"
```

#### Using Session Cookie
```bash
# Use session cookie authentication
uv run python agents/agent.py --use-session-cookie --prompt "What tools are available?"
```

#### Using Direct Access Token
```bash
# Override with direct access token
uv run python agents/agent.py --access-token "your-token" --prompt "List services"
```

### Advanced Agent Examples

#### Tool Filtering
```bash
# Filter to use specific MCP tool
uv run python agents/agent.py --mcp-tool-name current_time_by_timezone \
  --prompt "What time is it in Paris?"
```

#### Custom MCP Registry URL
```bash
# Use different registry
uv run python agents/agent.py --mcp-registry-url https://your-registry.com \
  --prompt "List available services"
```

#### Verbose Debugging
```bash
# Enable HTTP debugging
uv run python agents/agent.py --verbose --prompt "Test connection"
```

## Authentication Testing

### M2M Authentication
```bash
# Set environment variables
export CLIENT_ID=your_client_id
export CLIENT_SECRET=your_client_secret
export KEYCLOAK_URL=http://localhost:8080
export KEYCLOAK_REALM=mcp-gateway

# Test with M2M auth
uv run python cli/mcp_client.py list
```

### Ingress Token
```bash
# CLI automatically uses .oauth-tokens/ingress.json if available
uv run python cli/mcp_client.py ping
```

### Testing Different Scopes
```bash
# Test with specific scopes (agent.py)
uv run python agents/agent.py --scopes "read:tools" "execute:tools" \
  --prompt "List and execute time tools"
```

## Service Management Testing

Use the `service_mgmt.sh` script for comprehensive server lifecycle management:

### Add a Service
```bash
# Add service from config file
./cli/service_mgmt.sh add cli/examples/example-server-config.json
```

### Monitor Services
```bash
# Monitor all services
./cli/service_mgmt.sh monitor

# Monitor specific service
./cli/service_mgmt.sh monitor cli/examples/example-server-config.json
```

### Test Service Searchability
```bash
# Test if service is discoverable
./cli/service_mgmt.sh test cli/examples/example-server-config.json
```

### Delete a Service
```bash
# Remove service
./cli/service_mgmt.sh delete cli/examples/example-server-config.json
```

## Troubleshooting

### Common Issues

#### Connection Refused
```bash
# Check if services are running
docker-compose ps

# Test direct registry access
curl http://localhost:7860/health

# Check if MCP server is responding
uv run python cli/mcp_client.py ping
```

#### Authentication Errors
```bash
# Verify credentials are loaded
echo $CLIENT_ID
echo $CLIENT_SECRET

# Check token file exists
ls -la .oauth-tokens/ingress.json

# Test with explicit credentials
CLIENT_ID=test CLIENT_SECRET=secret uv run python cli/mcp_client.py list
```

#### Tool Not Found
```bash
# List all available tools
uv run python cli/mcp_client.py list

# Search for specific tools
uv run python cli/mcp_client.py call \
  --tool intelligent_tool_finder \
  --args '{"natural_language_query": "your tool description"}'
```

### Debug Mode

#### CLI Debug Output
```bash
# The CLI client shows detailed error messages by default
uv run python cli/mcp_client.py call --tool nonexistent --args '{}'
```

#### Agent Verbose Mode
```bash
# Enable verbose HTTP debugging
uv run python agents/agent.py --verbose --prompt "test"
```

### Health Checks

#### Check All Services
```bash
# Full health check
uv run python cli/mcp_client.py --url http://localhost/mcpgw/mcp call \
  --tool healthcheck \
  --args '{}'
```

#### Check Specific Server
```bash
# Direct server ping
uv run python cli/mcp_client.py --url http://localhost/currenttime/mcp ping
```

## Integration Testing

### CI/CD Pipeline Example
```yaml
name: MCP Gateway Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Start services
        run: docker-compose up -d

      - name: Wait for services
        run: sleep 10

      - name: Test connectivity
        run: |
          uv run python cli/mcp_client.py ping

      - name: Test tool discovery
        run: |
          uv run python cli/mcp_client.py list

      - name: Test agent
        run: |
          uv run python agents/agent.py --prompt "system health check"
```

### Docker Container Testing
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY cli/ cli/
COPY agents/ agents/
CMD ["python", "cli/mcp_client.py", "ping"]
```

## Performance Testing

### Load Testing
```bash
# Simple load test with multiple requests
for i in {1..10}; do
  uv run python cli/mcp_client.py ping &
done
wait
```

### Response Time Testing
```bash
# Measure response time
time uv run python cli/mcp_client.py list
```

## Security Testing

### Test Authentication
```bash
# Test without credentials (should fail appropriately)
unset CLIENT_ID CLIENT_SECRET
uv run python cli/mcp_client.py list

# Test with invalid credentials
CLIENT_ID=invalid CLIENT_SECRET=invalid uv run python cli/mcp_client.py list
```

### Test Authorization
```bash
# Test tool access with different scopes
uv run python cli/mcp_client.py call \
  --tool restricted_tool \
  --args '{}'
```

## Notes

- All examples assume you're running from the project root directory
- The CLI client (`mcp_client.py`) automatically handles authentication via environment variables or ingress tokens
- The Python agent (`agent.py`) provides more advanced AI capabilities for complex interactions
- Use `service_mgmt.sh` for comprehensive server lifecycle management
- For production testing, always use proper authentication and secure connections