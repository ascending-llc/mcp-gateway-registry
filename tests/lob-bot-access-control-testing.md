# LOB Bot Access Control Testing

This document consolidates all testing information and commands for verifying that LOB1 and LOB2 bots can only access their permitted services and agents through the MCP Gateway Registry.

## Quick Start - Run All Tests

First, regenerate tokens (they expire after 5 minutes):

```bash
cd /home/ubuntu/repos/mcp-gateway-registry
./keycloak/setup/generate-agent-token.sh lob1-bot
./keycloak/setup/generate-agent-token.sh lob2-bot
./keycloak/setup/generate-agent-token.sh admin-bot
```

Then execute the automated test script to run all tests with color-coded output:

```bash
bash tests/run-lob-bot-tests.sh
```

---

## Permissions Overview

### LOB1 Bot (registry-users-lob1)

From `auth_server/scopes.yml`:

**Allowed MCP Services**:
- `currenttime` - Get current time by timezone
- `mcpgw` - List available services

**Allowed Agents**:
- `/code-reviewer`
- `/test-automation`

**Agent Permissions**:
- list_agents: [/code-reviewer, /test-automation]
- get_agent: [/code-reviewer, /test-automation]
- publish_agent: [/code-reviewer, /test-automation]
- modify_agent: [/code-reviewer, /test-automation]
- delete_agent: [/code-reviewer, /test-automation]

**Token File**: `~/.oauth-tokens/lob1-bot-token.json`

### LOB2 Bot (registry-users-lob2)

From `auth_server/scopes.yml`:

**Allowed MCP Services**:
- `fininfo` - Get financial information and stock aggregates
- `realserverfaketools` - Quantum flux analyzer and other tools
- `mcpgw` - List available services

**Allowed Agents**:
- `/data-analysis`
- `/security-analyzer`

**Agent Permissions**:
- list_agents: [/data-analysis, /security-analyzer]
- get_agent: [/data-analysis, /security-analyzer]
- publish_agent: [/data-analysis, /security-analyzer]
- modify_agent: [/data-analysis, /security-analyzer]
- delete_agent: [/data-analysis, /security-analyzer]

**Token File**: `~/.oauth-tokens/lob2-bot-token.json`

### Admin Bot (registry-admins)

From `auth_server/scopes.yml`:

**Allowed MCP Services**:
- All services via wildcard `server: '*'`

**Allowed Agents**:
- All agents via wildcard `all`

**Agent Permissions**:
- list_agents: [all]
- get_agent: [all]
- publish_agent: [all]
- modify_agent: [all]
- delete_agent: [all]

**Token File**: `~/.oauth-tokens/admin-bot-token.json`

---

## Token Information

All tokens are Keycloak M2M (Machine-to-Machine) tokens with a 5-minute expiration window. Regenerate using:

```bash
cd /home/ubuntu/repos/mcp-gateway-registry
./keycloak/setup/generate-agent-token.sh lob1-bot
./keycloak/setup/generate-agent-token.sh lob2-bot
./keycloak/setup/generate-agent-token.sh admin-bot
```

**Security Notes**:
- The full access token is never displayed in the terminal
- Token files are created in `.oauth-tokens/` directory (not tracked by git)
- Tokens expire after 5 minutes (300 seconds)
- Never share tokens or commit them to version control
- Token files contain sensitive credentials - keep them secure

---

## Test Matrix - MCP Service Access (Tests 1-6)

| # | Bot | Service | Expected | Description |
|---|-----|---------|----------|-------------|
| 1 | LOB1 | currenttime | ✓ Allow | Get current time |
| 2 | LOB1 | mcpgw | ✓ Allow | Find tools using intelligent_tool_finder |
| 3 | LOB1 | fininfo | ✗ Deny | Should be denied (LOB2 only) |
| 4 | LOB1 | realserverfaketools | ✗ Deny | Should be denied (LOB2 only) |
| 5 | LOB2 | fininfo | ✓ Allow | Get stock data |
| 6 | LOB2 | currenttime | ✗ Deny | Should be denied (LOB1 only) |

---

## Test Matrix - Agent Registry API Access (Tests 7-14)

| # | Bot | Operation | Agent | Expected | Description |
|---|-----|-----------|-------|----------|-------------|
| 7 | LOB1 | list_agents | (any) | /code-reviewer, /test-automation | LOB1 only sees assigned agents |
| 8 | LOB1 | get_agent | /code-reviewer | ✓ Allow | Can get assigned agent |
| 9 | LOB1 | get_agent | /data-analysis | ✗ Deny | Cannot get non-assigned agent |
| 10 | LOB2 | list_agents | (any) | /data-analysis, /security-analyzer | LOB2 only sees assigned agents |
| 11 | LOB2 | get_agent | /data-analysis | ✓ Allow | Can get assigned agent |
| 12 | LOB2 | get_agent | /code-reviewer | ✗ Deny | Cannot get non-assigned agent |
| 13 | ADMIN | list_agents | (any) | All agents | Admin sees all agents |
| 14 | ADMIN | get_agent | (any) | ✓ Allow | Admin can access any agent |

---

## Test 1: LOB1 - Access Allowed (currenttime)

```bash
cd /home/ubuntu/repos/mcp-gateway-registry

uv run python cli/mcp_client.py \
  --url http://localhost/currenttime/mcp \
  --token-file .oauth-tokens/lob1-bot-token.json \
  call \
  --tool current_time_by_timezone \
  --args '{"timezone": "America/New_York"}'
```

**Expected Result**: Returns current time in New York timezone

---

## Test 2: LOB1 - Access Allowed (mcpgw)

```bash
cd /home/ubuntu/repos/mcp-gateway-registry

uv run python cli/mcp_client.py \
  --url http://localhost/mcpgw/mcp \
  --token-file .oauth-tokens/lob1-bot-token.json \
  call \
  --tool intelligent_tool_finder \
  --args '{"natural_language_query": "get current time in New York"}'
```

**Expected Result**: Returns intelligent tool finder results

---

## Test 7: LOB1 - List Agents (Should Only See Assigned Agents)

```bash
cd /home/ubuntu/repos/mcp-gateway-registry

curl -s -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/lob1-bot-token.json)" \
  http://localhost/api/agents \
  | jq '.agents[] | {path, name}'
```

**Expected Result**: Only /code-reviewer and /test-automation

---

## Test 8: LOB1 - Get Assigned Agent (Should Succeed)

```bash
cd /home/ubuntu/repos/mcp-gateway-registry

curl -s -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/lob1-bot-token.json)" \
  http://localhost/api/agents/code-reviewer \
  | jq '.'
```

**Expected Result**: Returns /code-reviewer agent details (200 OK)

---

## Test 9: LOB1 - Get Non-Assigned Agent (Should Fail)

```bash
cd /home/ubuntu/repos/mcp-gateway-registry

curl -s -w "\nHTTP Status: %{http_code}\n" \
  -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/lob1-bot-token.json)" \
  http://localhost/api/agents/data-analysis \
  | jq '.'
```

**Expected Result**: 403 Forbidden (permission denied)

---

## Test 10: LOB2 - List Agents (Should Only See Assigned Agents)

```bash
cd /home/ubuntu/repos/mcp-gateway-registry

curl -s -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/lob2-bot-token.json)" \
  http://localhost/api/agents \
  | jq '.agents[] | {path, name}'
```

**Expected Result**: Only /data-analysis and /security-analyzer

---

## Test 13: Admin - List Agents (Should See All)

```bash
cd /home/ubuntu/repos/mcp-gateway-registry

curl -s -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/admin-bot-token.json)" \
  http://localhost/api/agents \
  | jq '.agents | length'
```

**Expected Result**: Returns total count of all agents (4+)

---

## Success Criteria

### MCP Service Access Tests (Tests 1-6):
- **Tests 1, 2, 5**: Should PASS (successful command execution)
- **Tests 3, 4, 6**: Should FAIL with access denied error

### Agent Registry API Tests (Tests 7-14):
- **Test 7**: LOB1 list_agents returns only /code-reviewer and /test-automation
- **Test 8**: LOB1 can get /code-reviewer (200 OK)
- **Test 9**: LOB1 cannot get /data-analysis (403 Forbidden)
- **Test 10**: LOB2 list_agents returns only /data-analysis and /security-analyzer
- **Test 11**: LOB2 can get /data-analysis (200 OK)
- **Test 12**: LOB2 cannot get /code-reviewer (403 Forbidden)
- **Test 13**: Admin list_agents returns all agents
- **Test 14**: Admin can get any agent (200 OK)

---

## References

- **Scopes Configuration**: `auth_server/scopes.yml`
- **Agent Routes**: `registry/api/agent_routes.py`
- **Auth Dependencies**: `registry/auth/dependencies.py`
- **MCP Client**: `cli/mcp_client.py`
- **Token Location**: `~/.oauth-tokens/lob1-bot-token.json`, `~/.oauth-tokens/lob2-bot-token.json`, `~/.oauth-tokens/admin-bot-token.json`
- **Registry API**: http://localhost/api/v1/

---

**Last Updated**: 2025-11-09
