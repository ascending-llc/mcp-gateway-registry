# Service Management Guide

This guide documents how to add, test, and delete MCP servers using the `service_mgmt.sh` script - the recommended tool for server lifecycle management.

## Table of Contents
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Adding a New Server](#adding-a-new-server)
- [Testing a Server](#testing-a-server)
- [Monitoring Services](#monitoring-services)
- [Deleting a Server](#deleting-a-server)
- [Configuration Format](#configuration-format)
- [Troubleshooting](#troubleshooting)

## Overview

The `service_mgmt.sh` script provides a comprehensive workflow for managing MCP servers in the registry. It handles:

- **Server Registration**: Validates config and registers new servers
- **Health Verification**: Confirms servers are working and discoverable
- **Testing**: Validates server searchability through intelligent tool finder
- **Monitoring**: Provides health status for all or specific services
- **Cleanup**: Removes servers and verifies complete deletion

## Prerequisites

Before using `service_mgmt.sh`, ensure:

1. **MCP Gateway is running**: All containers should be up
   ```bash
   docker-compose ps
   ```

2. **Authentication is configured**: The script automatically handles credential refresh
   ```bash
   # Credentials are automatically checked by the script
   ./cli/service_mgmt.sh monitor
   ```

## Quick Start

### Basic Commands
```bash
# Add a new server
./cli/service_mgmt.sh add cli/examples/example-server-config.json

# Monitor all services
./cli/service_mgmt.sh monitor

# Test server searchability
./cli/service_mgmt.sh test cli/examples/example-server-config.json

# Delete a server
./cli/service_mgmt.sh delete cli/examples/example-server-config.json
```

## Adding a New Server

### Step 1: Create Configuration File

Create a JSON configuration file with your server details:

```json
{
  "server_name": "My MCP Server",
  "path": "/my-server",
  "proxy_pass_url": "http://my-server:8000",
  "description": "Description of what this server does",
  "tags": ["productivity", "automation"],
  "is_python": true,
  "license": "MIT"
}
```

### Step 2: Add the Server

```bash
./cli/service_mgmt.sh add path/to/your-config.json
```

**What happens during registration:**
1. ✓ **Config Validation**: Validates required fields and constraints
2. ✓ **Credential Check**: Ensures authentication is working
3. ✓ **Server Registration**: Registers server with the gateway
4. ✓ **Service List Verification**: Confirms server appears in registry
5. ✓ **Scopes Update**: Verifies server is added to scopes.yml
6. ✓ **FAISS Indexing**: Confirms server is searchable
7. ✓ **Health Check**: Validates server is healthy and responsive

### Example Output
```bash
=== Adding Service: my-server ===
✓ Credentials ready
✓ Registering service completed
✓ Server found in service list
✓ Server found in container scopes.yml (4 occurrences)
✓ Server found in host scopes.yml (4 occurrences)
✓ Server found in FAISS metadata (1 occurrences)
✓ Health check completed

Health Check Results:
==================================================
Service: /my-server
  Status: ✓ healthy
  Last checked: 5 seconds ago
  Tools available: 3

✓ Service my-server successfully added and verified!
```

## Testing a Server

Test server discoverability and search functionality:

```bash
./cli/service_mgmt.sh test cli/examples/example-server-config.json
```

**What happens during testing:**
1. ✓ **Search by Description**: Tests intelligent tool finder with server description
2. ✓ **Search by Tags**: Tests search using server tags
3. ✓ **Combined Search**: Tests search with both description and tags

### Example Output
```bash
=== Testing Service: example-server ===
ℹ Testing search with description: "An example MCP server demonstrating basic functionality"
✓ Search with description completed

ℹ Testing search with tags: ["example", "demonstration"]
✓ Search with tags completed

ℹ Testing combined search with description and tags
✓ Combined search completed

✓ Service testing completed!
```

## Monitoring Services

### Monitor All Services
```bash
./cli/service_mgmt.sh monitor
```

### Monitor Specific Service
```bash
./cli/service_mgmt.sh monitor cli/examples/example-server-config.json
```

### Example Output
```bash
=== Monitoring All Services ===
✓ Health check completed

Health Check Results:
==================================================
Service: /currenttime
  Status: ✓ healthy
  Last checked: 8 seconds ago
  Tools available: 1

Service: /mcpgw
  Status: ✓ healthy
  Last checked: 8 seconds ago
  Tools available: 6

Service: /example-server
  Status: ✓ healthy
  Last checked: 8 seconds ago
  Tools available: 3

✓ Monitoring completed!
```

## Deleting a Server

Remove a server and verify complete cleanup:

```bash
./cli/service_mgmt.sh delete cli/examples/example-server-config.json
```

**What happens during deletion:**
1. ✓ **Config Validation**: Validates config file and extracts service info
2. ✓ **Server Removal**: Removes server from registry
3. ✓ **Service List Verification**: Confirms server is removed from list
4. ✓ **Scopes Cleanup**: Verifies server is removed from scopes.yml
5. ✓ **FAISS Cleanup**: Confirms server is removed from search index

### Example Output
```bash
=== Deleting Service: example-server (path: /example-server) ===
✓ Credentials ready
✓ Removing service completed
✓ Server not found in service list (expected)
✓ Server not found in container scopes.yml (expected)
✓ Server not found in host scopes.yml (expected)
✓ Server not found in FAISS metadata (expected)

✓ Service example-server successfully deleted and verified!
```

## Configuration Format

### Required Fields
```json
{
  "server_name": "Display name for the server",
  "path": "/unique-url-path",
  "proxy_pass_url": "http://server-host:port"
}
```

### Complete Example
```json
{
  "server_name": "Advanced MCP Server",
  "path": "/advanced-server",
  "proxy_pass_url": "http://advanced-server:8001/",
  "description": "A server with all optional fields",
  "tags": ["productivity", "automation", "enterprise"],
  "num_tools": 5,
  "num_stars": 4,
  "is_python": true,
  "license": "MIT"
}
```

### Field Constraints

**Required Fields:**
- `server_name`: Non-empty string
- `path`: Must start with `/` and be more than just `/`
- `proxy_pass_url`: Must start with `http://` or `https://`

**Optional Fields:**
- `description`: String description
- `tags`: Array of strings
- `num_tools`: Non-negative integer
- `num_stars`: Non-negative integer
- `is_python`: Boolean
- `license`: String

## Troubleshooting

### Common Issues

#### Config Validation Errors
```bash
ERROR: Config validation failed:
  - path must start with "/"
  - proxy_pass_url must start with http:// or https://
```
**Solution**: Fix the configuration file according to the constraints listed above.

#### Credential Issues
```bash
✗ Failed to setup credentials
```
**Solution**: Ensure the MCP Gateway authentication system is running and configured.

#### Server Not Found in Verifications
```bash
✗ Server not found in service list
```
**Solution**: Check if the registration actually succeeded. Look at the registration output for errors.

#### Health Check Failures
```bash
✗ Health check failed
```
**Solution**:
1. Verify the server is running at the `proxy_pass_url`
2. Check Docker container logs: `docker-compose logs server-name`
3. Test direct connectivity to the server

### Debug Commands

```bash
# Check if containers are running
docker-compose ps

# View registry logs
docker-compose logs registry

# View auth server logs
docker-compose logs auth-server

# Test server connectivity directly
curl http://localhost:port/health

# List all services manually
uv run cli/mcp_client.py --url http://localhost/mcpgw/mcp call --tool list_services --args '{}'
```

### Getting Help

```bash
# Show usage and examples
./cli/service_mgmt.sh
```

## Best Practices

1. **Always use config files**: Store server configurations in version control
2. **Test after adding**: Run `test` command to verify searchability
3. **Monitor regularly**: Use `monitor` to check service health
4. **Clean up properly**: Use `delete` to ensure complete removal
5. **Use descriptive names**: Make server names and descriptions clear and searchable

## Integration with CI/CD

The script is designed for automation and returns appropriate exit codes:

```bash
#!/bin/bash
# Example deployment script

CONFIG_FILE="production-server.json"

# Add server
if ./cli/service_mgmt.sh add "$CONFIG_FILE"; then
    echo "✓ Server deployed successfully"
else
    echo "✗ Server deployment failed"
    exit 1
fi

# Test searchability
if ./cli/service_mgmt.sh test "$CONFIG_FILE"; then
    echo "✓ Server testing passed"
else
    echo "⚠ Server testing had issues"
fi
```

## End-to-End Example

This section provides a complete example using the `example-server` that you can run to understand the full workflow.

### Step 1: Build the Example Server

First, build the example server Docker image:

```bash
# Build the example server
docker build -f docker/Dockerfile.mcp-server --build-arg SERVER_PATH=servers/example-server -t example-server .
```

### Step 2: Run the Example Server

Start the example server in a Docker container:

```bash
# Run the example server on port 8010
docker run -d --name example-server-container --network mcp-gateway-registry_default -p 8010:8010 -e PORT=8010 example-server
```

### Step 3: Add the Server to Registry

Use the service management script to add the server:

```bash
# Add the example server using the provided config
./cli/service_mgmt.sh add cli/examples/example-server-config.json
```

This will:
- ✓ Register the server with the gateway
- ✓ Enable the server and add it to FAISS index
- ✓ Update scopes.yml with discovered tools
- ✓ Perform health check verification

### Step 4: Test the Server

Verify the server is discoverable through intelligent search:

```bash
# Test server searchability
./cli/service_mgmt.sh test cli/examples/example-server-config.json
```

This will test:
- ✓ Search by description
- ✓ Search by tags
- ✓ Combined search functionality

### Step 5: Monitor the Server

Check the server's health status:

```bash
# Monitor all services (including the example server)
./cli/service_mgmt.sh monitor

# Or monitor just the example server
./cli/service_mgmt.sh monitor cli/examples/example-server-config.json
```

### Step 6: Clean Up When Done

When you're finished testing, remove the server:

```bash
# Delete the server from registry
./cli/service_mgmt.sh delete cli/examples/example-server-config.json

# Stop and remove the Docker container
docker stop example-server-container
docker rm example-server-container
```

This complete example demonstrates the full lifecycle of server management using the `service_mgmt.sh` script.

## Advanced Scopes Management

### Default Server Registration Behavior

When a new server is registered, it is **automatically added to unrestricted scopes groups only**:
- `mcp-servers-unrestricted/read`
- `mcp-servers-unrestricted/execute`

This means that by default, newly registered servers are accessible to users with unrestricted permissions. If you need to add a server to restricted groups or change its access level, use the commands below.

### Adding Servers to Custom Scopes Groups

You can dynamically add servers to specific scopes groups using the service management script. This is useful for fine-grained access control where you want to assign different servers to different user groups.

```bash
# Add a server to specific scopes groups using the service management script
./cli/service_mgmt.sh add-to-groups example-server 'mcp-servers-restricted/read,mcp-servers-restricted/execute'
```

**Alternative: Direct MCP tool usage**
```bash
# Add a server to specific scopes groups using the MCP tool directly
uv run cli/mcp_client.py --url http://localhost/mcpgw/mcp call \
  --tool add_server_to_scopes_groups \
  --args '{
    "server_name": "example-server",
    "group_names": ["mcp-servers-restricted/read", "mcp-servers-restricted/execute"]
  }'
```

**What this does:**
- ✓ Retrieves all tools discovered during the last health check for the server
- ✓ Adds the server and all its tools to the specified scopes groups
- ✓ Uses the same MCP methods format as other servers (initialize, ping, tools/list, etc.)
- ✓ Automatically triggers auth server reload to apply changes immediately

**Example Response:**
```json
{
  "success": true,
  "message": "Server successfully added to groups",
  "server_name": "example-server",
  "groups": ["mcp-servers-restricted/read", "mcp-servers-restricted/execute"],
  "server_path": "/example-server"
}
```

**Available Scopes Groups:**
- `mcp-servers-unrestricted/read` - Full read access to all server methods and tools
- `mcp-servers-unrestricted/execute` - Full execute access to all server methods and tools
- `mcp-servers-restricted/read` - Limited read access for standard users
- `mcp-servers-restricted/execute` - Limited execute access for standard users

### Removing Servers from Scopes Groups

You can also remove servers from specific scopes groups for access revocation or role changes:

```bash
# Remove a server from specific scopes groups using the service management script
./cli/service_mgmt.sh remove-from-groups example-server 'mcp-servers-restricted/read,mcp-servers-restricted/execute'
```

**Alternative: Direct MCP tool usage**
```bash
# Remove a server from specific scopes groups using the MCP tool directly
uv run cli/mcp_client.py --url http://localhost/mcpgw/mcp call \
  --tool remove_server_from_scopes_groups \
  --args '{
    "server_name": "example-server",
    "group_names": ["mcp-servers-restricted/read", "mcp-servers-restricted/execute"]
  }'
```

**What this does:**
- ✓ Removes the server from the specified scopes groups
- ✓ Automatically triggers auth server reload to apply changes immediately
- ✓ Useful for access revocation or moving servers between access levels

**Use Cases:**
- Assign development servers to restricted groups for testing
- Grant production servers unrestricted access for administrators
- Create custom access patterns for different user roles
- Dynamically adjust permissions without manual scopes.yml editing
- Revoke access when servers are decommissioned or compromised
- Move servers between access levels (restricted ↔ unrestricted)

For advanced CLI operations, see the [CLI Guide](cli.md) for direct `mcp_client.py` usage.