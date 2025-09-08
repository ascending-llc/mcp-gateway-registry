# Testing MCP Gateway Registry

This guide covers different ways to test and interact with the MCP Gateway Registry, including both shell-based testing (no Python required) and Python agent testing.

## Testing Without Python

For enterprise environments with restricted package installation or when Python MCP packages are not available, use the provided shell scripts.

### Prerequisites

- `curl` - HTTP client (usually pre-installed)
- `jq` - JSON processor (`sudo apt install jq` or `brew install jq`)
- Standard Unix tools (`bash`, `sed`, `grep`)

### Shell Script Testing Tools

#### 1. `mcp_cmds.sh` - Core MCP Protocol Operations

Basic MCP server connectivity and tool operations using curl.

**Available Commands:**
```bash
# Test connectivity
./mcp_cmds.sh ping

# List available tools
./mcp_cmds.sh list

# Call a specific tool
./mcp_cmds.sh call get_current_time

# Get help
./mcp_cmds.sh help
```

**With Authentication:**

Using environment variable (see [Authentication for Both Methods](#authentication-for-both-methods) section below):
```bash
USER_ACCESS_TOKEN=your_token ./mcp_cmds.sh list
```

Using JSON token file:
```bash
# Place token in .oauth-tokens/user-token.json
./mcp_cmds.sh list
```

**Custom Server Targeting:**
```bash
# Target specific MCP server
GATEWAY_URL=http://localhost/currenttime/mcp ./mcp_cmds.sh ping

# Target remote server
GATEWAY_URL=https://your-server.com/currenttime/mcp ./mcp_cmds.sh list
```

#### 2. `mcp_demo.sh` - Intelligent Agent Workflows

Demonstrates multi-step AI agent workflows using natural language queries.

**Available Commands:**
```bash
# Run full agent demo (default)
./mcp_demo.sh demo

# Custom query and timezone
./mcp_demo.sh demo "What time is it now?" "Europe/London"

# Just test tool discovery
./mcp_demo.sh finder "time tools"

# Get help
./mcp_demo.sh help
```

**Agent Workflow Process:**
1. **Query → Discovery**: Uses `intelligent_tool_finder` to find relevant tools
2. **Tool Selection**: Parses response to identify appropriate server and tool  
3. **Server Switching**: Automatically switches to specific server context
4. **Tool Execution**: Calls the identified tool with parameters
5. **Result Extraction**: Processes and displays final results

**Example Output:**
```bash
$ ./mcp_demo.sh demo "What time is it now?" "Asia/Tokyo"

🤖 MCP Agent Demo - Mimicking agent.py workflow
==================================
Query: What time is it now?
Timezone: Asia/Tokyo
Gateway URL: http://localhost/mcpgw/mcp
==================================

🔍 Step 1: Calling intelligent_tool_finder to discover time-related tools...
🔍 Step 2: Parsing intelligent_tool_finder response...
🕒 Step 3: Calling the identified tool...
📋 Step 4: Extracting final result...
🎉 Final Result: Current time in Asia/Tokyo: 2024-01-15 15:30:45 JST
```

### Enterprise Use Cases

#### CI/CD Pipeline Integration
```bash
# Jenkins/GitLab CI step
#!/bin/bash
set -e
export USER_ACCESS_TOKEN=$MCP_TOKEN
./mcp_cmds.sh call validate_deployment '{"env":"staging"}'
```

#### Automated Monitoring
```bash
# Cron job for system monitoring
0 */4 * * * cd /opt/mcp && ./mcp_demo.sh demo "system status check"
```

#### Quick Prototyping
```bash
# Test new MCP servers without Python setup
./mcp_demo.sh finder "financial data tools"
./mcp_cmds.sh call get_stock_price '{"symbol":"AAPL"}'
```

### Troubleshooting Shell Scripts

**Authentication Issues:**
```bash
# Check if token is properly loaded
echo $USER_ACCESS_TOKEN

# Verify token file exists and has correct format
cat .oauth-tokens/user-token.json | jq .
```

**Connectivity Issues:**
```bash
# Test basic connectivity
curl -v http://localhost:7860/health

# Check if MCP server is responding
./mcp_cmds.sh ping
```

**JSON Parsing Issues:**
```bash
# Verify jq is installed
jq --version

# Debug raw responses
./mcp_cmds.sh list | grep "^data:" | sed 's/^data: //' | jq .
```

## Python Agent Testing

For environments where Python packages can be installed, use the full-featured Python agent.

### Prerequisites

```bash
# Install Python dependencies
pip install -r agents/requirements.txt

# Or if using the project's environment
cd agents && pip install -e .
```

### Python Agent Features

The `agents/agent.py` provides advanced AI capabilities with LangGraph-based multi-turn conversations:

**Core Features:**
- **LangGraph Integration**: Uses LangGraph reactive agents for complex reasoning
- **Multi-Turn Conversations**: Maintains conversation history across interactions
- **Anthropic Claude Integration**: Powered by ChatAnthropic for advanced language understanding
- **MCP Tool Discovery**: Intelligent tool finder for dynamic tool selection
- **Authentication Support**: Cognito-based authentication with token management
- **Interactive Mode**: Real-time conversation interface with continuous interaction

**Available Tools:**
- **`intelligent_tool_finder`**: AI-powered tool discovery using natural language
- **`invoke_mcp_tool`**: Direct MCP tool invocation with authentication
- **`calculator`**: Built-in mathematical expression evaluator

**Usage Examples:**

**Interactive Mode (Recommended):**
```bash
cd agents
# Interactive session with conversation history
python agent.py --interactive

# Interactive with initial prompt
python agent.py --prompt "Hello, help me find time tools" --interactive
```

**Single-Turn Mode:**
```bash
# Direct query execution
python agent.py --prompt "What's the current time in New York?"

# Complex multi-step workflow
python agent.py --prompt "Find financial tools and get Apple's stock price"
```

**Authentication Options:**
```bash
# Environment variables (.env file recommended)
COGNITO_CLIENT_ID=your_client_id
COGNITO_CLIENT_SECRET=your_client_secret  
COGNITO_USER_POOL_ID=your_user_pool_id
AWS_REGION=us-east-1
ANTHROPIC_API_KEY=your_api_key

python agent.py --interactive

# Command line parameters
python agent.py \
  --cognito-client-id your_client_id \
  --cognito-client-secret your_client_secret \
  --cognito-user-pool-id your_user_pool_id \
  --aws-region us-east-1 \
  --interactive
```

**Advanced Configuration:**
```bash
# Custom server and model configuration
python agent.py \
  --mcp-host localhost \
  --mcp-port 8000 \
  --model-id claude-3-5-sonnet-20241022 \
  --interactive

# With detailed logging
python agent.py --prompt "test query" --verbose
```

**Agent Workflow Process:**
1. **Query Analysis**: Uses Claude to understand natural language intent
2. **Tool Discovery**: Leverages `intelligent_tool_finder` for relevant tool identification
3. **Multi-Step Execution**: Chains multiple MCP tool calls as needed
4. **Context Maintenance**: Preserves conversation state across interactions
5. **Error Handling**: Automatic retry with fallback strategies

### Python vs Shell Comparison

| Feature | Shell Scripts | Python Agent |
|---------|--------------|---------------|
| **Installation** | Zero dependencies | Requires pip packages |
| **Enterprise Compatibility** | Works in restricted environments | May be blocked by firewalls |
| **Functionality** | Core MCP operations | Advanced AI capabilities |
| **Performance** | Fast, lightweight | More processing overhead |
| **Complexity** | Simple, straightforward | Rich feature set |
| **Error Handling** | Basic retry logic | Advanced recovery mechanisms |
| **Use Case** | Testing, automation, CI/CD | Development, complex workflows |

### Authentication for Both Methods

**Environment Variable (Recommended):**
```bash
export USER_ACCESS_TOKEN=your_registry_token
```

**Obtaining User Access Token:**
You can generate a user access token from the MCP Gateway Registry UI by clicking the "Generate Token" dropdown menu item in the top right corner of the screen.

**Note:** If you are using an HTTPS URL for your MCP Gateway Registry, the token will be automatically looked up from the `.oauth-tokens/ingress.json` file.

**JSON Token File:**
```json
{
  "access_token": "your_token_here",
  "user_pool_id": "us-east-1_example", 
  "client_id": "client_id_here",
  "region": "us-east-1"
}
```

**Token File Location:**
- Place in `.oauth-tokens/user-token.json` relative to script location
- Ensure proper JSON format and required fields

## Testing Scenarios

### Basic Connectivity Test
```bash
# Shell method
./mcp_cmds.sh ping

# Python method  
cd agents && python agent.py "ping the system"
```

### Tool Discovery Test
```bash
# Shell method
./mcp_cmds.sh list

# Python method with intelligent discovery
./mcp_demo.sh finder "available tools"
```

### Complex Workflow Test
```bash
# Shell method - multi-step agent workflow
./mcp_demo.sh demo "What's the weather like and what time is it?"

# Python method - advanced reasoning
cd agents && python agent.py "Get current conditions and time for planning"
```

## Integration Examples

### Docker Integration
```dockerfile
# Shell-based testing in container
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y curl jq
COPY mcp_cmds.sh mcp_demo.sh ./
RUN chmod +x *.sh
CMD ["./mcp_demo.sh", "demo"]
```

### GitHub Actions
```yaml
name: MCP Integration Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Test MCP Gateway
        run: |
          export USER_ACCESS_TOKEN=${{ secrets.MCP_TOKEN }}
          ./mcp_cmds.sh ping
          ./mcp_demo.sh demo "system health check"
```

### Kubernetes Job
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: mcp-test
spec:
  template:
    spec:
      containers:
      - name: mcp-test
        image: ubuntu:22.04
        command: ["/bin/bash", "-c"]
        args: 
        - |
          apt-get update && apt-get install -y curl jq
          export USER_ACCESS_TOKEN=$MCP_TOKEN
          ./mcp_cmds.sh list
      restartPolicy: Never
```

This testing guide provides comprehensive coverage for both enterprise environments requiring shell-based testing and development environments where Python packages are available.