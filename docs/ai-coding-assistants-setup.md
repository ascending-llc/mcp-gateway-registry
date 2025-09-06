# AI Coding Assistants Setup Guide

Complete guide for integrating the MCP Gateway & Registry with popular AI development tools.

## Overview

The MCP Gateway automatically generates configuration files for various AI coding assistants, enabling seamless access to enterprise-curated MCP servers with proper authentication and governance.

## Prerequisites

- MCP Gateway & Registry deployed and running
- Authentication credentials generated via `./credentials-provider/generate_creds.sh`
- Access to the AI coding assistant of your choice

## Supported AI Development Tools

### VS Code MCP Extension

Microsoft's popular editor with native MCP support.

**Setup:**
```bash
# Copy generated configuration
cp .oauth-tokens/vscode-mcp.json ~/.vscode/settings.json

# Alternative: Merge with existing settings
cat .oauth-tokens/vscode-mcp.json >> ~/.vscode/settings.json
```

**Configuration Format:**
```json
{
  "mcp": {
    "servers": {
      "atlassian": {
        "url": "https://your-gateway.com/atlassian/sse",
        "headers": {
          "Authorization": "Bearer eyJ...",
          "X-User-Pool-Id": "us-east-1_vm1115QSU",
          "X-Client-Id": "5v2rav1v93...",
          "X-Region": "us-east-1"
        },
        "transport": "sse"
      }
    }
  }
}
```

### Roo Code Plugin - Enterprise Showcase

Roo Code demonstrates the power of enterprise governance for AI development tools.

**Setup:**
```bash
# Copy Roo Code configuration
cp .oauth-tokens/mcp.json ~/.vscode/mcp_settings.json
```

**Alternative Setup Options:**
```bash
# Option 1: Direct copy (recommended)
cp .oauth-tokens/mcp.json ~/.vscode/mcp_settings.json

# Option 2: Create symbolic link for automatic updates
ln -sf "$(pwd)/.oauth-tokens/mcp.json" ~/.vscode/mcp_settings.json
```

**Enterprise Use Case:**

<table>
<tr>
<td width="50%">

![Roo Code MCP Configuration](img/roo.png)

**Enterprise Tool Catalog**
- Curated MCP servers approved by IT
- Consistent across all developer environments  
- Centralized authentication and governance
- Real-time health monitoring

</td>
<td width="50%">

![Roo Code Agent in Action](img/roo_agent.png)

**AI Assistant in Action**
- Natural language tool discovery
- Secure execution of enterprise tools
- Complete audit trail for compliance
- Seamless developer experience

</td>
</tr>
</table>

**Key Enterprise Benefits:**

**Centralized Control**
- IT teams manage approved MCP servers across all development environments
- Consistent tool availability regardless of developer setup
- Rapid deployment of new tools to entire organization

**Secure Authentication**  
- All tool access routes through enterprise identity systems (Amazon Cognito)
- No individual API key management required
- Automatic token refresh and rotation via [Token Refresh Service](token-refresh-service.md)

**Usage Analytics & Compliance**
- Track which developers use which tools and when
- Generate compliance reports for audit requirements
- Monitor tool adoption and usage patterns across teams

**Developer Productivity**
- Zero configuration required for approved tools
- Instant access to new enterprise tools as they're approved
- Same experience across VS Code, Cursor, Claude Code, and other assistants

### Claude Code

Anthropic's coding assistant with standardized MCP configurations.

**Setup:**
```bash
# Claude Code uses similar JSON format
cp .oauth-tokens/vscode-mcp.json ~/.claude-code/mcp-config.json
```

**Features:**
- Natural language interaction with MCP tools
- Context-aware tool suggestions
- Integrated code generation and tool execution

### Cursor

AI-first code editor with advanced MCP integration.

**Setup:**
```bash
# Cursor configuration (similar to VS Code)
cp .oauth-tokens/vscode-mcp.json ~/.cursor/mcp-settings.json
```

**Advanced Features:**
- Multi-file context for tool operations
- Predictive tool suggestions based on code context
- Integrated diff view for tool-generated changes

### Cline (formerly Claude Dev)

Autonomous coding agent compatible with VS Code.

**Setup:**
```bash
# Cline uses VS Code-style configuration
cp .oauth-tokens/vscode-mcp.json ~/.vscode/settings.json
```

**Autonomous Capabilities:**
- Goal-directed tool usage
- Multi-step task execution
- Error handling and retry logic

### Custom MCP Clients

For custom applications or other MCP clients:

**Use Raw Authentication:**
```bash
# Access authentication details directly
cat .oauth-tokens/ingress.json
```

**Example Integration:**
```python
import json
import mcp
from mcp.client.sse import sse_client

# Load authentication from generated file
with open('.oauth-tokens/ingress.json') as f:
    auth = json.load(f)

headers = {
    'Authorization': f'Bearer {auth["access_token"]}',
    'X-User-Pool-Id': auth['user_pool_id'],
    'X-Client-Id': auth['client_id'],
    'X-Region': auth['region']
}

# Connect to MCP server
async with sse_client('https://gateway.com/mcpgw/sse', headers=headers) as (read, write):
    async with mcp.ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
```

## Configuration Management

### Automatic Token Refresh

The MCP Gateway includes an [Automated Token Refresh Service](token-refresh-service.md) that provides continuous token management:

```bash
# Start the token refresh service (runs in background)
./start_token_refresher.sh

# Service automatically:
# - Monitors token expiration (1-hour buffer by default)
# - Refreshes tokens before they expire
# - Updates all MCP client configurations
# - Generates fresh configs for all AI assistants
```

**Key Benefits:**
- **Zero Downtime**: Tokens refresh automatically before expiration
- **Continuous Operation**: AI assistants never lose access due to expired tokens
- **Multiple Client Support**: Updates configurations for VS Code, Roo Code, Claude Code, etc.
- **Background Operation**: Runs as a service with comprehensive logging

### Manual Configuration Updates

If you need to manually regenerate configurations:

```bash
# Regenerate all configurations
./credentials-provider/generate_creds.sh

# Copy updated configurations to AI assistants
./scripts/update-ai-assistants.sh  # Custom script you can create
```

**For AI assistants using symbolic links** (recommended setup), configuration updates are automatic since they point to the live `.oauth-tokens/` files.

### Environment-Specific Configurations

**Development Environment:**
```bash
# Generate development configurations
ENVIRONMENT=dev ./credentials-provider/generate_creds.sh
cp .oauth-tokens/dev-* ~/.vscode/
```

**Production Environment:**
```bash
# Generate production configurations  
ENVIRONMENT=prod ./credentials-provider/generate_creds.sh
cp .oauth-tokens/prod-* ~/.vscode/
```

## Troubleshooting

### Authentication Issues

**Token Expired:**

*If using Token Refresh Service (recommended):*
```bash
# Check if token refresh service is running
ps aux | grep token_refresher

# Restart token refresh service if needed
./start_token_refresher.sh

# Check service logs
tail -f token_refresher.log
```

*Manual token refresh:*
```bash
# Regenerate credentials
./credentials-provider/generate_creds.sh
# Update AI assistant configurations
```

**Permission Denied:**
```bash
# Check user permissions in Cognito
aws cognito-idp admin-list-groups-for-user \
  --user-pool-id YOUR_POOL_ID \
  --username YOUR_USERNAME

# Verify scope configuration
cat auth_server/scopes.yml
```

### Configuration Issues

**Tools Not Appearing:**
```bash
# Verify MCP server health
curl -H "Authorization: Bearer TOKEN" \
  https://your-gateway.com/server-name/sse

# Check AI assistant logs
tail -f ~/.vscode/logs/mcp.log
```

**Connection Failures:**
```bash
# Test gateway connectivity
./tests/mcp_cmds.sh ping

# Verify SSL certificates (if using HTTPS)
openssl s_client -connect your-gateway.com:443
```

## Best Practices

### Security

1. **Credential Storage**
   - Store generated configurations in secure locations
   - Use environment-specific credentials
   - Regularly rotate authentication tokens

2. **Access Control**
   - Follow principle of least privilege
   - Regularly review user permissions
   - Monitor tool usage for anomalies

3. **Network Security**
   - Use HTTPS in production environments
   - Restrict network access to authorized IP ranges
   - Monitor for unauthorized access attempts

### Development Workflow

1. **Team Onboarding**
   ```bash
   # Create onboarding script
   #!/bin/bash
   ./credentials-provider/generate_creds.sh
   cp .oauth-tokens/vscode-mcp.json ~/.vscode/settings.json
   echo "MCP Gateway configured successfully!"
   ```

2. **Tool Discovery**
   - Use natural language queries: "find tools for database operations"
   - Explore available tools through web interface
   - Share useful tool combinations with team

3. **Automation**
   ```bash
   # Automate configuration updates
   crontab -e
   # Add: 0 9 * * * /path/to/update-mcp-config.sh
   ```

## Enterprise Deployment Considerations

### Scale Considerations

- **Large Teams (100+ developers)**: Consider load balancing and caching
- **Global Teams**: Deploy regional gateways for reduced latency
- **High Security**: Use private networking and enhanced monitoring

### Compliance & Governance

- **Audit Requirements**: Enable comprehensive logging
- **Data Residency**: Deploy in compliant regions
- **Access Reviews**: Implement periodic permission audits

### Cost Optimization

- **Resource Management**: Monitor gateway resource usage
- **Tool Usage**: Analyze tool usage patterns for optimization
- **License Management**: Track per-developer tool usage

## Support & Resources

- [Configuration Reference](configuration.md) - Complete configuration options
- [Authentication Guide](auth.md) - Identity provider setup
- [Troubleshooting Guide](troubleshooting.md) - Common issues and solutions
- [API Reference](registry_api.md) - Programmatic management
- [GitHub Discussions](https://github.com/agentic-community/mcp-gateway-registry/discussions) - Community support