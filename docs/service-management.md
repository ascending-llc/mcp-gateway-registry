# Service Management Guide

This guide documents how to manage MCP servers, users, and access groups in the MCP Gateway Registry.

## Table of Contents
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Service Management](#service-management)
  - [Add Server](#add-server)
  - [Delete Server](#delete-server)
  - [Monitor Services](#monitor-services)
  - [Test Server](#test-server)
- [Group Management](#group-management)
  - [Create Group](#create-group)
  - [Delete Group](#delete-group)
  - [List Groups](#list-groups)
  - [Add Server to Group](#add-server-to-group)
  - [Remove Server from Group](#remove-server-from-group)
- [User Management](#user-management)
  - [Create M2M User](#create-m2m-user)
  - [Create Human User](#create-human-user)
  - [Delete User](#delete-user)
  - [List Users](#list-users)
- [Complete Workflow Example](#complete-workflow-example)
- [Configuration Format](#configuration-format)
- [Troubleshooting](#troubleshooting)

## Overview

The MCP Gateway Registry provides three main management scripts:

- **`service_mgmt.sh`**: Manages MCP servers (add, delete, monitor, test)
- **`user_mgmt.sh`**: Manages users and M2M service accounts (create, delete, list)
- **Group management** (via `service_mgmt.sh`): Manages access control groups (create, delete, list)

These tools work together to provide:
- **Server Registration**: Validates config and registers new servers
- **Access Control**: Fine-grained permissions via groups
- **User Management**: M2M service accounts and human users
- **Health Verification**: Confirms servers are working and discoverable
- **Testing**: Validates server searchability through intelligent tool finder
- **Monitoring**: Provides health status for all or specific services

## Prerequisites

Before using `service_mgmt.sh`, ensure:

1. **MCP Gateway is running**: All containers should be up
   ```bash
   docker compose ps
   ```

2. **Authentication is configured**: The script automatically handles credential refresh
   ```bash
   # Credentials are automatically checked by the script
   ./cli/service_mgmt.sh monitor
   ```

## Quick Start

### Service Commands
```bash
# Add a new server
./cli/service_mgmt.sh add cli/examples/example-server-config.json

# Monitor all services
./cli/service_mgmt.sh monitor

# Delete a server
./cli/service_mgmt.sh delete cli/examples/example-server-config.json
```

### Group Commands
```bash
# Create a new group
./cli/service_mgmt.sh create-group mcp-servers-finance/read "Finance services read access"

# List all groups
./cli/service_mgmt.sh list-groups

# Add server to group
./cli/service_mgmt.sh add-to-groups mcpgw mcp-servers-finance/read

# Delete a group
./cli/service_mgmt.sh delete-group mcp-servers-finance/read
```

### User Commands
```bash
# Create M2M service account
./cli/user_mgmt.sh create-m2m --name my-bot --groups 'mcp-servers-finance/read'

# Create human user
./cli/user_mgmt.sh create-human --username jdoe --email jdoe@example.com \
  --firstname John --lastname Doe --groups 'mcp-servers-restricted/read'

# List all users
./cli/user_mgmt.sh list-users

# Delete a user
./cli/user_mgmt.sh delete-user --username my-bot
```

---

## Service Management

This section covers managing MCP servers in the registry using `./cli/service_mgmt.sh`.

### Add Server

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
2. Check Docker container logs: `docker compose logs server-name`
3. Test direct connectivity to the server

### Debug Commands

```bash
# Check if containers are running
docker compose ps

# View registry logs
docker compose logs registry

# View auth server logs
docker compose logs auth-server

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

---

## Group Management

This section covers managing access control groups using `./cli/service_mgmt.sh`. Groups control which users can access which servers and tools.

### Create Group

Create a new access control group in both Keycloak and scopes.yml:

```bash
./cli/service_mgmt.sh create-group <group-name> [description]
```

**Example:**
```bash
./cli/service_mgmt.sh create-group mcp-servers-finance/read "Finance services with read access"
```

**What this does:**
- ✓ Creates the group in Keycloak
- ✓ Adds the group to scopes.yml
- ✓ Reloads the auth server to apply changes immediately
- ✓ Validates synchronization between Keycloak and scopes.yml

### List Groups

List all groups in the realm with their synchronization status:

```bash
./cli/service_mgmt.sh list-groups
```

**Example Output:**
```
mcp-servers-unrestricted (✓ Synced)
mcp-servers-restricted (✓ Synced)
mcp-servers-finance/read (✓ Synced)
mcp-servers-finance/execute (✓ Synced)
```

### Delete Group

Delete a group from both Keycloak and scopes.yml:

```bash
./cli/service_mgmt.sh delete-group <group-name>
```

**Example:**
```bash
./cli/service_mgmt.sh delete-group mcp-servers-finance/read
```

**What this does:**
- ✓ Removes the group from Keycloak
- ✓ Removes the group from scopes.yml
- ✓ Reloads the auth server to apply changes

### Add Server to Group

Add an existing server to one or more groups:

```bash
./cli/service_mgmt.sh add-to-groups <server-name> <groups>
```

**Parameters:**
- `<server-name>`: Name of the server (e.g., `mcpgw`, `currenttime`)
- `<groups>`: Comma-separated list of group names

**Example:**
```bash
# Add to single group
./cli/service_mgmt.sh add-to-groups mcpgw mcp-servers-finance/read

# Add to multiple groups
./cli/service_mgmt.sh add-to-groups fininfo 'mcp-servers-finance/read,mcp-servers-finance/execute'
```

**What this does:**
- ✓ Retrieves all tools from the server's last health check
- ✓ Adds the server and all its tools to the specified groups
- ✓ Updates scopes.yml with the server entry
- ✓ Automatically triggers auth server reload

### Remove Server from Group

Remove a server from one or more groups:

```bash
./cli/service_mgmt.sh remove-from-groups <server-name> <groups>
```

**Example:**
```bash
./cli/service_mgmt.sh remove-from-groups fininfo 'mcp-servers-finance/read'
```

**What this does:**
- ✓ Removes the server from the specified scopes groups
- ✓ Updates scopes.yml
- ✓ Automatically triggers auth server reload

---

## User Management

This section covers managing users and M2M service accounts using `./cli/user_mgmt.sh`.

### Create M2M User

Create a machine-to-machine (M2M) service account for programmatic access:

```bash
./cli/user_mgmt.sh create-m2m \
  --name <client-name> \
  --groups '<group1>,<group2>' \
  --description '<description>'
```

**Parameters:**
- `--name`: Client ID for the M2M account (required)
- `--groups`: Comma-separated list of groups (required)
- `--description`: Description of the service account (optional)

**Example:**
```bash
./cli/user_mgmt.sh create-m2m \
  --name finance-analyst-bot \
  --groups 'mcp-servers-finance/read,mcp-servers-finance/execute' \
  --description 'Finance analyst bot with full access'
```

**What this does:**
- ✓ Creates a new Keycloak M2M client with service account
- ✓ Assigns the service account to the specified groups
- ✓ Generates client credentials (client_id and client_secret)
- ✓ Creates four credential files:
  - `.oauth-tokens/<name>.json` - Client credentials
  - `.oauth-tokens/<name>-token.json` - Access token
  - `.oauth-tokens/<name>.env` - Environment variables
  - `.oauth-tokens/keycloak-client-secrets.txt` - Updated with new entry
- ✓ Automatically generates an access token

### Create Human User

Create a human user account with Keycloak login capabilities:

```bash
./cli/user_mgmt.sh create-human \
  --username <username> \
  --email <email> \
  --firstname <firstname> \
  --lastname <lastname> \
  --groups '<group1>,<group2>' \
  --password <password>  # Optional, will prompt if not provided
```

**Example:**
```bash
./cli/user_mgmt.sh create-human \
  --username jdoe \
  --email jdoe@example.com \
  --firstname John \
  --lastname Doe \
  --groups 'mcp-servers-restricted/read'
```

**What this does:**
- ✓ Creates a new user in Keycloak
- ✓ Assigns the user to the specified groups
- ✓ Sets up password (prompts if not provided)
- ✓ Enables the user account

**User can login at:**
- Keycloak Account Console: `http://localhost:8080/realms/mcp-gateway/account`
- API authentication using password grant

### List Users

List all users in the mcp-gateway realm:

```bash
./cli/user_mgmt.sh list-users
```

**Example Output:**
```
Username: admin, Email: admin@example.com, Enabled: true, ID: b413260d-9ca1-4d4a-a5bb-b3d515780da5
Username: finance-analyst-bot, Email: N/A, Enabled: true, ID: 356db59e-5377-439f-a57f-b98d1485cee8
Username: jdoe, Email: jdoe@example.com, Enabled: true, ID: 434829b0-3f4e-4217-ab0e-2496a1804990

Total users: 3
```

### Delete User

Delete a user (M2M or human) from Keycloak:

```bash
./cli/user_mgmt.sh delete-user --username <username>
```

**Example:**
```bash
./cli/user_mgmt.sh delete-user --username finance-analyst-bot
```

**What this does:**
- ✓ Deletes the user from Keycloak
- ✓ Refreshes all credential files to remove the user
- ✓ Updates keycloak-client-secrets.txt

---

## Complete Workflow Example

This section demonstrates the complete workflow for creating a custom access group, adding servers to it, creating users with access to that group, and testing the setup.

### Step 1: Create a New Group

First, create a custom group for your specific use case. For example, let's create a group for time-related services:

```bash
# Create a new group for time services with read access
./cli/service_mgmt.sh create-group mcp-servers-time/read "Time-related services with read access"
```

**What this does:**
- ✓ Creates the group in Keycloak
- ✓ Adds the group to scopes.yml
- ✓ Reloads the auth server to apply changes
- ✓ Validates synchronization between Keycloak and scopes.yml

**Example Output:**
```
Creating group 'mcp-servers-time/read' via internal endpoint by admin 'admin'
Group 'mcp-servers-time/read' created in Keycloak
Successfully added group mcp-servers-time/read to scopes.yml
Successfully triggered auth server scope reload
✓ Group created and synchronized successfully!
```

### Step 2: Add Servers to the Group

Now add servers to your newly created group. You can add existing servers without re-registering them.

**Important Note:** If you want to use the `intelligent_tool_finder` functionality to search for tools across servers, you should always add the `mcpgw` server to your group. The `mcpgw` server provides essential MCP protocol methods and the intelligent tool finder capability.

```bash
# Add the mcpgw server (provides intelligent_tool_finder and core MCP methods)
./cli/service_mgmt.sh add-to-groups mcpgw mcp-servers-time/read

# Add the currenttime server (provides time-related tools)
./cli/service_mgmt.sh add-to-groups currenttime mcp-servers-time/read
```

**What this does:**
- ✓ Retrieves all tools from the server's last health check
- ✓ Adds the server and all its tools to the specified group
- ✓ Updates scopes.yml with the server entry
- ✓ Automatically triggers auth server reload

**Example Output:**
```
Adding server 'mcpgw' to groups: mcp-servers-time/read
✓ Server successfully added to groups
Server path: /mcpgw
Groups: mcp-servers-time/read
✓ Scopes groups updated and auth server reloaded
```

**Alternative: Adding Servers During Registration**

If you're adding a new server and want to assign it to a custom group immediately, see the [Adding a New Server](#adding-a-new-server) section and then use the `add-to-groups` command. The server is automatically added to unrestricted groups during registration, and you can add it to additional custom groups afterward.

### Step 3: Create an M2M User with Group Access

Create a machine-to-machine (M2M) service account that has access to your custom group:

```bash
# Create M2M service account with access to the time services group
./cli/user_mgmt.sh create-m2m \
  --name time-service-bot \
  --groups 'mcp-servers-time/read' \
  --description 'Bot for accessing time-related services'
```

**What this does:**
- ✓ Creates a new Keycloak M2M client with service account
- ✓ Assigns the service account to the specified group(s)
- ✓ Generates client credentials (client_id and client_secret)
- ✓ Creates four credential files:
  - `.oauth-tokens/time-service-bot.json` - Client credentials
  - `.oauth-tokens/time-service-bot-token.json` - Access token
  - `.oauth-tokens/time-service-bot.env` - Environment variables
  - `.oauth-tokens/keycloak-client-secrets.txt` - Updated with new entry
- ✓ Automatically generates an access token

**Example Output:**
```
Creating M2M Service Account
==============================================
Name: time-service-bot
Groups: mcp-servers-time/read
Description: Bot for accessing time-related services

✓ M2M client created successfully
Client UUID: 9c576aad-3056-46c1-8b55-00825b73682c
✓ Groups mapper configured
✓ Assigned to group: mcp-servers-time/read

Refreshing all client credentials...
✓ All credentials refreshed

Generating access token for: time-service-bot
✓ Access token generated

SUCCESS! M2M service account created
==============================================
Client ID: time-service-bot
Client Secret: abc123...xyz789
Groups: mcp-servers-time/read

Credentials saved to:
  .oauth-tokens/time-service-bot.json (client credentials)
  .oauth-tokens/time-service-bot-token.json (access token)
  .oauth-tokens/time-service-bot.env (environment variables)
  .oauth-tokens/keycloak-client-secrets.txt (all client secrets)
```

### Step 4: Test the Setup with an Agent

Now test that the M2M user can access the servers in the group using the AI agent:

```bash
# Use the agent to call a tool from the currenttime server
uv run python agents/agent.py \
  --agent-name time-service-bot \
  --prompt "What is the current time in NYC?"
```

**What happens:**
1. The agent loads credentials from `.oauth-tokens/time-service-bot-token.json`
2. Authenticates to the MCP Gateway using the access token
3. The auth server validates the token and checks group membership
4. The agent can access tools from `mcpgw` and `currenttime` servers (both in `mcp-servers-time/read` group)
5. Uses `intelligent_tool_finder` (from mcpgw) to search for time-related tools
6. Finds and calls `current_time_by_timezone` tool from the currenttime server
7. Returns the current time in NYC

**Example Output:**
```
2025-10-05 19:08:48,778,p2873330,{agent.py:1003},INFO,Loaded credentials for agent: time-service-bot
2025-10-05 19:08:48,779,p2873330,{agent.py:1052},INFO,Connecting to MCP server: https://mcpgateway.ddns.net/mcpgw/mcp
2025-10-05 19:08:48,870,p2873330,{agent.py:1228},INFO,Connected to MCP server successfully with authentication

The current time in New York City is 3:08 PM EDT on October 5, 2025.
```

### Verification and Troubleshooting

**Verify Group Membership:**
```bash
# List all groups to confirm your new group exists
./cli/service_mgmt.sh list-groups

# List all users to verify your M2M account was created
./cli/user_mgmt.sh list-users
```

**Check Server Assignment:**
```bash
# View the scopes.yml file to verify servers are in the group
# Note: scopes.yml is in the mcp-gateway directory (mounted volume)
cat ~/mcp-gateway/auth_server/scopes.yml | grep -A 10 "mcp-servers-time/read"
```

**Common Issues:**

1. **403 Forbidden Error**: The user doesn't have access to required MCP methods
   - **Solution**: Ensure `mcpgw` server is added to your group (provides `initialize`, `ping`, `tools/list` methods)
   - Add with: `./cli/service_mgmt.sh add-to-groups mcpgw mcp-servers-time/read`

2. **Group Not Found**: The group doesn't exist in Keycloak
   - **Solution**: Create the group first with `./cli/service_mgmt.sh create-group`

3. **Server Not Found**: Server path doesn't exist in registry
   - **Solution**: Verify server name with `./cli/service_mgmt.sh monitor`
   - Check that server was successfully registered

4. **Token Expired**: Access token has expired (tokens expire after 5 minutes by default)
   - **Solution**: Regenerate token with `./keycloak/setup/generate-agent-token.sh time-service-bot`

### Complete Example: LOB1 (Line of Business 1) Services Group

Here's a complete example for creating a LOB1 services group:

```bash
# 1. Create the group (you can use any name - /read suffix is optional)
./cli/service_mgmt.sh create-group mcp-servers-lob1 "LOB1 services"

# 2. Add servers to the group
# Add mcpgw for intelligent_tool_finder and core MCP methods
./cli/service_mgmt.sh add-to-groups mcpgw mcp-servers-lob1

# Add your LOB1-related servers
./cli/service_mgmt.sh add-to-groups currenttime mcp-servers-lob1

# 3. Create M2M user with access to the group
./cli/user_mgmt.sh create-m2m \
  --name lob1-bot \
  --groups 'mcp-servers-lob1' \
  --description 'LOB1 bot with access'

# 4. Create a human user for web interface access
./cli/user_mgmt.sh create-human \
  --username lob1-user \
  --email lob1-user@example.com \
  --firstname LOB1 \
  --lastname User \
  --groups 'mcp-servers-lob1'

# 5. Test the setup with the M2M bot
uv run python agents/agent.py \
  --agent-name lob1-bot \
  --prompt "What is the current time in NYC?"
```

**Note:** Group names are flexible - you can use patterns like `mcp-servers-lob1/read`, `mcp-servers-lob1`, or any custom name like `finance-team`. The `/read` and `/execute` suffixes are just naming conventions for clarity, not requirements.

**Web Interface Access:**
When the human user (`lob1-user`) logs into the registry web interface (either at `http://localhost:7860` or through your custom domain if configured), they will only see the servers they have access to based on their group membership (`mcp-servers-lob1`):
- ✓ **mcpgw** - Core MCP methods and intelligent_tool_finder
- ✓ **currenttime** - Time-related tools

All other servers in the registry will be hidden from this user, providing secure, role-based access control.

### Best Practices

1. **Always include mcpgw in custom groups**: The `mcpgw` server provides essential functionality including `intelligent_tool_finder` which allows agents to search for tools across all servers they have access to.

2. **Use descriptive group names**: Follow the pattern `mcp-servers-{category}/{permission}` for consistency (e.g., `mcp-servers-finance/read`, `mcp-servers-analytics/execute`).

3. **Separate read and execute permissions**: Create separate groups for read-only and execute access to implement least-privilege access control.

4. **Document group purposes**: Use the description field when creating groups to document their intended use case.

5. **Test after each step**: Verify group creation, server assignment, and user access at each step to catch issues early.

6. **Regenerate tokens when needed**: Access tokens expire periodically. Use `generate-agent-token.sh` to get fresh tokens when needed.

For advanced CLI operations, see the [CLI Guide](cli.md) for direct `mcp_client.py` usage.