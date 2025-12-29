# Management API End-to-End Test Guide

**Date:** 2025-12-12
**Purpose:** Comprehensive end-to-end test of the Management API functionality
**Location:** `api/test-management-api-e2e.sh`

## Overview

This guide demonstrates the complete lifecycle of IAM and resource management using the Management API. The test script creates a group, users (both human and M2M), registers servers and agents, verifies the configuration, and then cleans up all resources.

## Prerequisites

### For Local Testing (Docker Compose)

1. Ensure the registry and Keycloak services are running:
   ```bash
   docker-compose up -d
   ```

2. Generate authentication tokens:
   ```bash
   cd credentials-provider
   ./generate_creds.sh
   cd ..
   ```

3. Verify token file exists:
   ```bash
   ls -la .oauth-tokens/ingress.json
   ```

**Note:** The script automatically validates that:
- The token file exists and is readable
- The token contains a valid `access_token` field
- The token has not expired (checks JWT expiration time)

### For Remote Testing (AWS Deployment)

Set the required environment variables:

```bash
export REGISTRY_URL="https://registry.us-east-1.aroraai.people.aws.dev"
export AWS_REGION="us-east-1"
export KEYCLOAK_URL="https://kc.us-east-1.aroraai.people.aws.dev"
```

## Test Workflow

The script performs the following operations in sequence:

### Phase 1: Resource Creation

1. **Create IAM Group**
   - Creates a new group with a timestamped name (e.g., `test-team-1702405678`)
   - Description: "Test group for end-to-end testing"
   - Command: `group-create --name <group> --description <desc>`

2. **Create Human User**
   - Creates a human user account with:
     - Username: `test.user.<timestamp>`
     - Email: `test.user.<timestamp>@example.com`
     - First name: "Test"
     - Last name: "User"
     - Group membership: The newly created group
     - Password: "TempPassword123!"
   - Command: `user-create-human --username <user> --email <email> --first-name <fn> --last-name <ln> --groups <group> --password <pwd>`

3. **Create M2M Service Account**
   - Creates a machine-to-machine service account with:
     - Name: `test-service-bot-<timestamp>`
     - Group membership: The newly created group
     - Description: "Test service account for end-to-end testing"
   - Returns client credentials (client_id and client_secret)
   - Command: `user-create-m2m --name <name> --groups <group> --description <desc>`
   - **Important:** The client secret is only shown once - save it!

4. **Register MCP Server**
   - Registers the Cloudflare Documentation MCP Server
   - Uses JSON configuration from `cli/examples/cloudflare-docs-server-config.json`
   - Server details:
     - Name: "Cloudflare Documentation MCP Server"
     - Path: `/cloudflare-docs`
     - Proxy URL: `https://docs.mcp.cloudflare.com/mcp`
     - Transport: streamable-http
   - Command: `register --config <file>`

5. **Register Agent**
   - Registers the Flight Booking Agent
   - Uses JSON configuration from `cli/examples/flight_booking_agent_card.json`
   - Agent details:
     - Name: "Flight Booking Agent"
     - Path: `/flight-booking`
     - URL: `http://flight-booking-agent:9000/`
     - Skills: check_availability, reserve_flight, confirm_booking, process_payment, manage_reservation
   - Command: `agent-register --config <file>`

### Phase 2: Verification

6. **List All Users**
   - Lists all users in the system
   - **Validates** that both the human user and M2M service account are present in the response
   - Shows user status (enabled/disabled), email, groups
   - Command: `user-list`
   - Test fails if created users are not found in the list

7. **List All Groups**
   - Lists all groups in the system
   - **Validates** that the test group appears in the response
   - Shows group ID, name, path, and attributes
   - Command: `group-list`
   - Test fails if created group is not found in the list

8. **List All Servers**
   - Lists all registered servers
   - **Validates** that the Cloudflare Documentation MCP Server appears in the response
   - Shows server configuration and group assignment
   - Command: `list`
   - Test fails if registered server is not found in the list

9. **List All Agents**
   - Lists all registered agents
   - **Validates** that the Flight Booking Agent appears in the response
   - Shows agent capabilities and group assignment
   - Command: `agent-list`
   - Test fails if registered agent is not found in the list

10. **Search for Test Users**
    - Searches for users with "test" in their username
    - Demonstrates user search functionality
    - Command: `user-list --search test --limit 50`

### Phase 3: Cleanup (Automatic)

The cleanup phase runs automatically via a trap on script exit, ensuring all resources are deleted even if the script fails:

11. **Delete Agent**
    - Removes the Flight Booking Agent
    - Command: `agent-delete --path /flight-booking --force`

12. **Delete Server**
    - Removes the Cloudflare Documentation MCP Server
    - Command: `remove --path /cloudflare-docs --force`

13. **Delete M2M Account**
    - Removes the M2M service account
    - Command: `user-delete --username <m2m-name> --force`

14. **Delete Human User**
    - Removes the human user account
    - Command: `user-delete --username <username> --force`

15. **Delete Group**
    - Removes the test group
    - Command: `group-delete --name <group> --force`

## Usage

The script requires the `--token-file` parameter and optionally accepts `--registry-url`, `--aws-region`, `--keycloak-url`, and `--quiet`.

### Command Syntax

```bash
./test-management-api-e2e.sh --token-file <path-to-token-file> [--registry-url <url>] [--aws-region <region>] [--keycloak-url <url>] [--quiet]
```

**Required Arguments:**
- `--token-file <path>` - Path to the OAuth token file (e.g., `.oauth-tokens/ingress.json`)

**Optional Arguments:**
- `--registry-url <url>` - Registry URL (default: `http://localhost`)
- `--aws-region <region>` - AWS region (e.g., `us-east-1`)
- `--keycloak-url <url>` - Keycloak base URL (e.g., `https://kc.us-east-1.aroraai.people.aws.dev`)
- `--quiet` - Suppress verbose output (verbose mode is enabled by default to show all intermediate command outputs)

### Local Testing (Docker Compose)

```bash
# First, ensure tokens are generated
cd credentials-provider
./generate_creds.sh
cd ..

# Run the test script with token file (verbose by default)
cd api
./test-management-api-e2e.sh --token-file ../.oauth-tokens/ingress.json

# Or run in quiet mode
./test-management-api-e2e.sh --token-file ../.oauth-tokens/ingress.json --quiet
```

### Remote Testing (AWS Deployment)

```bash
# Generate M2M token and save to file
./api/get-m2m-token.sh \
  --aws-region us-east-1 \
  --keycloak-url https://kc.us-east-1.aroraai.people.aws.dev \
  --output-file api/.token

# Run the test script with all AWS parameters (verbose by default)
cd api
./test-management-api-e2e.sh \
  --token-file api/.token \
  --registry-url https://registry.us-east-1.aroraai.people.aws.dev \
  --aws-region us-east-1 \
  --keycloak-url https://kc.us-east-1.aroraai.people.aws.dev

# Or run in quiet mode
./test-management-api-e2e.sh \
  --token-file api/.token \
  --registry-url https://registry.us-east-1.aroraai.people.aws.dev \
  --aws-region us-east-1 \
  --keycloak-url https://kc.us-east-1.aroraai.people.aws.dev \
  --quiet
```

### Getting Help

```bash
./test-management-api-e2e.sh --help
```

Output:
```
Usage: ./test-management-api-e2e.sh --token-file <path-to-token-file> [--registry-url <url>] [--aws-region <region>] [--keycloak-url <url>] [--quiet]

Required arguments:
  --token-file <path>      Path to the OAuth token file (e.g., .oauth-tokens/ingress.json)

Optional arguments:
  --registry-url <url>     Registry URL (default: http://localhost)
  --aws-region <region>    AWS region (e.g., us-east-1)
  --keycloak-url <url>     Keycloak base URL (e.g., https://kc.us-east-1.aroraai.people.aws.dev)
  --quiet                  Suppress verbose output (verbose is enabled by default)

Examples:
  # Local testing with verbose output (default)
  ./test-management-api-e2e.sh --token-file .oauth-tokens/ingress.json

  # Remote testing with all parameters
  ./test-management-api-e2e.sh --token-file api/.token --registry-url https://registry.us-east-1.aroraai.people.aws.dev --aws-region us-east-1 --keycloak-url https://kc.us-east-1.aroraai.people.aws.dev
```

## Expected Output

### Successful Run

```
========================================
Management API End-to-End Test
========================================

Configuration:
  Registry URL: http://localhost
  Token File: ../.oauth-tokens/ingress.json
  Group Name: test-team-1702405678
  Human User: test.user.1702405678
  M2M Account: test-service-bot-1702405678

========================================
Phase 1: Resource Creation
========================================

[Step 1] Creating IAM group: test-team-1702405678
Group created successfully

[Step 2] Creating human user: test.user.1702405678
Human user created successfully

[Step 3] Creating M2M service account: test-service-bot-1702405678
Client ID: test-service-bot-1702405678
Client Secret: <SECRET>
Groups: test-team-1702405678
M2M service account created successfully
Note: Save the client secret from the output above - it will not be shown again!

[Step 4] Registering server: Cloudflare Documentation MCP Server
Server registered successfully

[Step 5] Registering agent: Flight Booking Agent
Agent registered successfully

========================================
Phase 2: Verification
========================================

[Step 6] Listing all users (should include test.user.1702405678 and test-service-bot-1702405678)
Found 8 users:
...

[Step 7] Listing all groups (should include test-team-1702405678)
Found 13 groups:
...

[Step 8] Listing all servers (should include Cloudflare Documentation MCP Server)
Servers:
...

[Step 9] Listing all agents (should include Flight Booking Agent)
Agents:
...

[Step 10] Checking server health for: /cloudflare-docs
...

[Step 11] Searching for test users
Found 2 users matching 'test':
...

========================================
All verification steps completed!
========================================

The cleanup function will now run automatically...

========================================
Cleanup: Deleting resources
========================================

[Step 12] Deleting agent: Flight Booking Agent
[Step 13] Deleting server: Cloudflare Documentation MCP Server
[Step 14] Deleting M2M account: test-service-bot-1702405678
[Step 15] Deleting human user: test.user.1702405678
[Step 16] Deleting group: test-team-1702405678

========================================
Cleanup complete!
========================================
```

## Troubleshooting

### Error: Missing --token-file argument

**Problem:**
```
Error: --token-file is required

Usage: ./test-management-api-e2e.sh --token-file <path-to-token-file> [--registry-url <url>]
```

**Solution:** Provide the required `--token-file` parameter:
```bash
./test-management-api-e2e.sh --token-file ../.oauth-tokens/ingress.json
```

### Error: Token file not found

**Problem:**
```
Error: Token file not found: .oauth-tokens/ingress.json

To generate tokens for local testing:
  cd credentials-provider && ./generate_creds.sh && cd ..
```

**Solution:** Generate tokens first:
```bash
cd credentials-provider
./generate_creds.sh
cd ..
```

### Error: 403 Forbidden (Unauthorized)

**Problem:** The user executing the script does not have admin privileges.

**Solution:** Ensure the token used belongs to an admin user. For local testing, the `ingress.json` token should have admin rights. For remote testing, ensure you're using proper credentials.

### Error: 422 Unprocessable Entity

**Problem:** Invalid input data in the request.

**Solution:** Check that:
- Group names are valid (alphanumeric with hyphens/underscores)
- Email addresses are properly formatted
- All required fields are provided

### Error: Server or Agent Registration Failed

**Problem:** JSON configuration file is missing or invalid.

**Solution:** Ensure the JSON files exist:
```bash
ls -la cli/examples/cloudflare-docs-server-config.json
ls -la cli/examples/flight_booking_agent_card.json
```

If missing, the script will attempt to create them automatically.

### Warning: Health Check Failed

**Problem:** Server health check returns an error.

**Solution:** This is expected if the actual server is not running. The health check is included to demonstrate the functionality, but the script will continue even if it fails.

### Cleanup Failures

**Problem:** Cleanup phase reports errors when deleting resources.

**Solution:** This can happen if:
- Resources were manually deleted during the test
- Network connectivity issues
- Permission issues

You can manually clean up remaining resources:
```bash
# List and delete remaining resources
uv run python registry_management.py --registry-url http://localhost --token-file ../.oauth-tokens/ingress.json user-list
uv run python registry_management.py --registry-url http://localhost --token-file ../.oauth-tokens/ingress.json group-list
uv run python registry_management.py --registry-url http://localhost --token-file ../.oauth-tokens/ingress.json list
uv run python registry_management.py --registry-url http://localhost --token-file ../.oauth-tokens/ingress.json agent-list

# Delete manually if needed
uv run python registry_management.py --registry-url http://localhost --token-file ../.oauth-tokens/ingress.json user-delete --username <username> --force
uv run python registry_management.py --registry-url http://localhost --token-file ../.oauth-tokens/ingress.json group-delete --name <group> --force
```

## API Endpoints Used

This test script exercises the following Management API endpoints:

### User Management
- `POST /api/management/iam/users/human` - Create human user
- `POST /api/management/iam/users/m2m` - Create M2M service account
- `GET /api/management/iam/users` - List users
- `DELETE /api/management/iam/users/{username}` - Delete user

### Group Management
- `POST /api/management/iam/groups` - Create group
- `GET /api/management/iam/groups` - List groups
- `DELETE /api/management/iam/groups/{group_name}` - Delete group

### Server Management
- `POST /api/servers/register` - Register server
- `GET /api/servers` - List servers
- `GET /api/servers/health` - Check server health
- `DELETE /api/servers/{path}` - Remove server

### Agent Management
- `POST /api/agents/register` - Register agent
- `GET /api/agents` - List agents
- `DELETE /api/agents/{path}` - Delete agent

## Integration with CI/CD

This script can be integrated into CI/CD pipelines for automated testing:

```yaml
# Example GitHub Actions workflow
test-management-api:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v2
    - name: Start services
      run: docker-compose up -d
    - name: Generate tokens
      run: |
        cd credentials-provider
        ./generate_creds.sh
        cd ..
    - name: Run end-to-end test
      run: |
        cd api
        ./test-management-api-e2e.sh --token-file ../.oauth-tokens/ingress.json
```

## Notes

- **Timestamped Names:** All resource names include timestamps to avoid conflicts with existing resources
- **Automatic Cleanup:** The script uses a bash trap to ensure cleanup runs even if the script fails
- **Idempotent:** The script can be run multiple times safely due to unique timestamped names
- **Admin Only:** All Management API operations require admin privileges
- **Client Secrets:** M2M client secrets are only shown once during creation - save them immediately
- **Resource Dependencies:** The cleanup happens in reverse order to respect dependencies (agents/servers before users, users before groups)

## Related Documentation

- [PR #267 Implementation Summary](.scratchpad/pr267-implementation-summary.md)
- [Management API Complete Testing](.scratchpad/management-api-complete-testing.md)
- [Group CRUD Implementation](.scratchpad/group-crud-implementation-summary.md)
- [Management API OpenAPI Specification](../docs/api-specs/management-api.yaml)
- [Registry Management CLI Tool](./registry_management.py)

## Next Steps

After running this test successfully:

1. **Test on AWS Deployment:** Run the script against the remote registry to verify production readiness
2. **Verify Keycloak:** Check Keycloak admin console to confirm users and groups were created correctly
3. **Test Authentication:** Use the M2M credentials to authenticate and access protected resources
4. **Performance Testing:** Run the script multiple times in parallel to test concurrency
5. **Security Testing:** Verify non-admin users cannot execute Management API operations
