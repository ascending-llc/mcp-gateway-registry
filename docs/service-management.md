# Service Management Guide

This guide documents how to manage MCP servers, users, and access groups in the MCP Gateway Registry using the **Registry Management API**.

## Table of Contents
- [Overview](#overview)
- [What's New](#whats-new)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Service Management](#service-management)
  - [Add Server](#add-server)
  - [Delete Server](#delete-server)
  - [List Servers](#list-servers)
  - [Enable/Disable Server](#enabledisable-server)
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

The MCP Gateway Registry provides a comprehensive **Registry Management API** for programmatic access to all registry operations. This API replaces the previous shell script approach with a modern, type-safe Python interface.

**Management Options:**

1. **Registry Management API** (`api/registry_management.py`): Core API for server, group, and user management
2. **Registry Client** (`api/registry_client.py`): High-level Python client with authentication handling
3. **REST API Endpoints**: Direct HTTP API access at `/api/management/*`

These tools work together to provide:
- **Server Registration**: Validates config and registers new servers
- **Access Control**: Fine-grained permissions via groups
- **User Management**: M2M service accounts and human users
- **Health Verification**: Confirms servers are working and discoverable
- **FAISS Integration**: Automatic indexing for intelligent tool discovery

## What's New

**Registry Management API** (New in v1.0.7):
- Modern Python API for all registry operations
- Type-safe interfaces using Pydantic models
- Automatic FAISS indexing on server registration
- Integrated health checking and validation
- RESTful HTTP endpoints for external integrations
- Comprehensive error handling and logging

The new API provides the same functionality as the previous shell scripts but with better error handling, type safety, and integration capabilities.

## Prerequisites

Before using the Registry Management API, ensure:

1. **MCP Gateway is running**: All containers should be up
   ```bash
   docker compose ps
   ```

2. **Authentication is configured**: You need admin credentials
   ```bash
   # Admin credentials from .env file
   export ADMIN_USER=admin
   export ADMIN_PASSWORD=your_admin_password
   ```

3. **Python environment**: Use `uv` for package management
   ```bash
   # Ensure uv is installed
   uv --version
   ```

## Quick Start

### Using the Registry Client (Python)

```python
from api.registry_client import RegistryClient

# Initialize client
client = RegistryClient(
    base_url="http://localhost",
    admin_user="admin",
    admin_password="your_password"
)

# Add a server
client.add_server(
    server_name="My MCP Server",
    path="/my-server",
    proxy_pass_url="http://my-server:8000",
    description="My custom MCP server",
    tags=["productivity", "automation"]
)

# List all servers
servers = client.list_servers()
for server in servers:
    print(f"{server['name']}: {server['path']}")

# Delete a server
client.delete_server("my-server")
```

### Using the REST API (HTTP)

```bash
# Get admin access token
TOKEN=$(curl -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}' | jq -r '.access_token')

# Add a server
curl -X POST http://localhost/api/management/servers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "server_name": "My MCP Server",
    "path": "/my-server",
    "proxy_pass_url": "http://my-server:8000",
    "description": "My custom MCP server",
    "tags": ["productivity", "automation"]
  }'

# List servers
curl -X GET http://localhost/api/management/servers \
  -H "Authorization: Bearer $TOKEN"

# Delete a server
curl -X DELETE http://localhost/api/management/servers/my-server \
  -H "Authorization: Bearer $TOKEN"
```

## Service Management

### Add Server

#### Using Python Client

```python
from api.registry_client import RegistryClient

client = RegistryClient(
    base_url="http://localhost",
    admin_user="admin",
    admin_password="your_password"
)

# Add server with all options
response = client.add_server(
    server_name="Advanced MCP Server",
    path="/advanced-server",
    proxy_pass_url="http://advanced-server:8001/",
    description="A server with all optional fields",
    tags=["productivity", "automation", "enterprise"],
    num_tools=5,
    num_stars=4,
    is_python=True,
    license="MIT"
)

print(f"Server added: {response['name']}")
```

#### What Happens During Registration

1. Config validation (required fields, constraints)
2. Server registration with the gateway
3. Nginx configuration update
4. FAISS index update (automatic)
5. Health check verification

### Delete Server

```python
# Delete by server name
client.delete_server("advanced-server")
```

### List Servers

```python
# Get all servers
servers = client.list_servers()

for server in servers:
    print(f"Name: {server['name']}")
    print(f"Path: {server['path']}")
    print(f"Status: {server['enabled']}")
    print(f"Tags: {', '.join(server.get('tags', []))}")
    print("---")
```

### Enable/Disable Server

```python
# Disable a server (removes from FAISS, keeps in registry)
client.disable_server("my-server")

# Enable a server (adds back to FAISS)
client.enable_server("my-server")
```

## Group Management

### Create Group

```python
# Create a new access control group
client.create_group(
    group_name="mcp-servers-finance/read",
    description="Finance services with read access"
)
```

**What this does:**
- Creates the group in Keycloak
- Adds the group to scopes.yml
- Reloads the auth server to apply changes immediately

### List Groups

```python
# Get all groups
groups = client.list_groups()

for group in groups:
    print(f"Group: {group['name']}")
    print(f"Synced: {group['synced']}")
```

### Delete Group

```python
# Delete a group
client.delete_group("mcp-servers-finance/read")
```

### Add Server to Group

```python
# Add server to one or more groups
client.add_server_to_groups(
    server_name="mcpgw",
    groups=["mcp-servers-finance/read"]
)

# Add to multiple groups
client.add_server_to_groups(
    server_name="fininfo",
    groups=["mcp-servers-finance/read", "mcp-servers-finance/execute"]
)
```

### Remove Server from Group

```python
# Remove server from groups
client.remove_server_from_groups(
    server_name="fininfo",
    groups=["mcp-servers-finance/read"]
)
```

## User Management

### Create M2M User

```python
# Create machine-to-machine service account
credentials = client.create_m2m_user(
    name="finance-analyst-bot",
    groups=["mcp-servers-finance/read", "mcp-servers-finance/execute"],
    description="Finance analyst bot with full access"
)

print(f"Client ID: {credentials['client_id']}")
print(f"Client Secret: {credentials['client_secret']}")
```

**What this does:**
- Creates a new Keycloak M2M client with service account
- Assigns the service account to specified groups
- Generates client credentials
- Returns client_id and client_secret

### Create Human User

```python
# Create human user account
client.create_human_user(
    username="jdoe",
    email="jdoe@example.com",
    firstname="John",
    lastname="Doe",
    password="secure_password",
    groups=["mcp-servers-restricted/read"]
)
```

### List Users

```python
# Get all users
users = client.list_users()

for user in users:
    print(f"Username: {user['username']}")
    print(f"Email: {user.get('email', 'N/A')}")
    print(f"Enabled: {user['enabled']}")
```

### Delete User

```python
# Delete a user
client.delete_user(username="finance-analyst-bot")
```

## Complete Workflow Example

This example demonstrates the complete workflow using the Registry Management API:

```python
from api.registry_client import RegistryClient

# Initialize client
client = RegistryClient(
    base_url="http://localhost",
    admin_user="admin",
    admin_password="your_password"
)

# Step 1: Create a new access group
print("Creating group...")
client.create_group(
    group_name="mcp-servers-time/read",
    description="Time-related services with read access"
)

# Step 2: Add servers to the group
print("Adding servers to group...")

# Add mcpgw (provides intelligent_tool_finder)
client.add_server_to_groups(
    server_name="mcpgw",
    groups=["mcp-servers-time/read"]
)

# Add currenttime server
client.add_server_to_groups(
    server_name="currenttime",
    groups=["mcp-servers-time/read"]
)

# Step 3: Create M2M service account
print("Creating M2M user...")
credentials = client.create_m2m_user(
    name="time-service-bot",
    groups=["mcp-servers-time/read"],
    description="Bot for accessing time-related services"
)

print(f"M2M Account Created:")
print(f"  Client ID: {credentials['client_id']}")
print(f"  Client Secret: {credentials['client_secret']}")

# Step 4: Create human user
print("Creating human user...")
client.create_human_user(
    username="time-user",
    email="time-user@example.com",
    firstname="Time",
    lastname="User",
    password="secure_password",
    groups=["mcp-servers-time/read"]
)

# Step 5: Verify setup
print("\nVerifying setup...")
print(f"Groups: {client.list_groups()}")
print(f"Servers: {[s['name'] for s in client.list_servers()]}")
print(f"Users: {[u['username'] for u in client.list_users()]}")

print("\nWorkflow complete!")
```

## Configuration Format

### Required Fields

```python
{
    "server_name": "Display name for the server",
    "path": "/unique-url-path",
    "proxy_pass_url": "http://server-host:port"
}
```

### Complete Example

```python
{
    "server_name": "Advanced MCP Server",
    "path": "/advanced-server",
    "proxy_pass_url": "http://advanced-server:8001/",
    "description": "A server with all optional fields",
    "tags": ["productivity", "automation", "enterprise"],
    "num_tools": 5,
    "num_stars": 4,
    "is_python": True,
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

#### Authentication Errors
```
ERROR: Authentication failed: 401 Unauthorized
```
**Solution**: Verify admin credentials in `.env` file

#### Server Already Exists
```
ERROR: Server already exists: /my-server
```
**Solution**: Delete the existing server first or use a different path

#### Group Not Found
```
ERROR: Group not found: mcp-servers-custom/read
```
**Solution**: Create the group first using `create_group()`

#### Connection Refused
```
ERROR: Connection refused to http://localhost
```
**Solution**: Ensure MCP Gateway is running (`docker compose ps`)

### Debug Tips

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Test connectivity
from api.registry_client import RegistryClient
client = RegistryClient(base_url="http://localhost", admin_user="admin", admin_password="password")

# This will show detailed request/response logs
servers = client.list_servers()
```

### API Documentation

For complete API reference, see:
- Registry Management API: `api/registry_management.py`
- Registry Client: `api/registry_client.py`
- REST API endpoints: `http://localhost/api/management/docs` (OpenAPI/Swagger)

## Best Practices

1. **Use the Python Client**: The `RegistryClient` handles authentication and error handling automatically
2. **Version Control Configurations**: Store server configurations in JSON files
3. **Test After Adding**: Verify servers are accessible after registration
4. **Use Descriptive Names**: Make server names and groups clear and searchable
5. **Always Include mcpgw**: Add `mcpgw` to custom groups for `intelligent_tool_finder` functionality
6. **Handle Errors**: Wrap API calls in try/except blocks for production use

## Integration with CI/CD

```python
#!/usr/bin/env python3
from api.registry_client import RegistryClient
import sys

def deploy_server(config_file):
    """Deploy server from configuration file"""
    client = RegistryClient(
        base_url="http://localhost",
        admin_user="admin",
        admin_password="password"
    )

    try:
        # Load configuration
        with open(config_file) as f:
            config = json.load(f)

        # Add server
        response = client.add_server(**config)
        print(f"Server deployed successfully: {response['name']}")
        return 0
    except Exception as e:
        print(f"Deployment failed: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(deploy_server("production-server.json"))
```

For advanced operations and direct API usage, see the [API documentation](../api/README.md).
