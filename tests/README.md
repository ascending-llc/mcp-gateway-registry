# MCP Gateway Registry Test Suite

Comprehensive test suite for validating all functionality before PR merge.

## Getting Started

New to testing this project? Start here:

1. **First time?** Review [Agent Access Control & Permissions](#agent-access-control--permissions) below
2. **Running tests?** Jump to [Quick Start](#quick-start)
3. **Need details?** See [Test Coverage](#test-coverage) and links below
4. **Testing access control?** See [LOB Bot Testing](#lob-bot-testing)

## Quick Start

```bash
# Run all tests (including production) - REQUIRED for PR merge
./tests/run_all_tests.sh

# Run tests for local development only (skip production)
./tests/run_all_tests.sh --skip-production

# Show help
./tests/run_all_tests.sh --help
```

## Test Coverage

The test suite validates **9 categories** with **~30 tests**:

1. **Infrastructure Health** - Docker, services, connectivity
2. **Credentials** - Generation, validation, expiration
3. **MCP Client** - Tools, services, health checks
4. **Agent** - Prompt execution, tool calls
5. **Anthropic Registry API** - REST API endpoints (version defined in `registry/constants.py`)
6. **Service Management** - Import, CRUD operations
7. **Code Quality** - Syntax, linting
8. **Production** - All tests against production URL (MANDATORY for PR merge)
9. **Configuration** - Nginx, environment

## Agent Access Control & Permissions

This project uses **three-tier access control** defined in [../auth_server/scopes.yml](../auth_server/scopes.yml):

### Permission Tiers

1. **UI-Scopes** - What agents and services each group can see/access
2. **Group Mappings** - Maps Keycloak groups to internal scope names
3. **MCP Server Scopes** - What methods/tools each group can call on specific services

### Bot Users (for testing)

The test suite validates access control for three bot users:

| Bot | Group | Agents | Services |
|-----|-------|--------|----------|
| **admin-bot** | `mcp-registry-admin` | All agents | All services |
| **lob1-bot** | `registry-users-lob1` | `/code-reviewer`, `/test-automation` | currenttime, mcpgw |
| **lob2-bot** | `registry-users-lob2` | `/data-analysis`, `/security-analyzer` | currenttime, mcpgw, fininfo |

**See:** [auth_server/scopes.yml](../auth_server/scopes.yml) for complete permission definitions

## Files in This Directory

### Test Scripts
- **[run_all_tests.sh](run_all_tests.sh)** - Main test suite (run ~30 tests across all categories)
- **[agent_crud_test.sh](agent_crud_test.sh)** - Simple CRUD demo (register, read, update, delete, verify agent)
- **[run-lob-bot-tests.sh](run-lob-bot-tests.sh)** - Access control validation (14 tests for bot permissions)

### Documentation
- **[TEST_QUICK_REFERENCE.md](TEST_QUICK_REFERENCE.md)** - Quick reference for all tests (start here for how-to)
- **[lob-bot-access-control-testing.md](lob-bot-access-control-testing.md)** - Detailed access control test documentation
- **README.md** - This file (navigation and overview)

### External References
- **[Full Testing Guide](../docs/testing.md)** - Comprehensive testing documentation
- **[Scopes Configuration](../auth_server/scopes.yml)** - Permission definitions (admin, LOB1, LOB2)

## Requirements

Before running tests:

```bash
# 1. Ensure services are running
docker-compose ps

# 2. Generate fresh credentials (tokens expire in 5 minutes)
./credentials-provider/generate_creds.sh

# 3. Run tests
./tests/run_all_tests.sh
```

## Test Environments

Tests run against two environments:

| Environment | URL | Purpose | Required |
|-------------|-----|---------|----------|
| Localhost | `http://localhost` | Development | Always |
| Production | `https://mcpgateway.ddns.net` | Pre-merge validation | PR merge only |

## Expected Results

### Success (all tests pass)
```
============================================================
ALL TESTS PASSED!
============================================================
Total Tests:   50
Passed Tests:  50
Failed Tests:  0
```

✅ Safe to merge PR (if production tests included)

### Failure (one or more tests fail)
```
============================================================
TESTS FAILED!
============================================================
Total Tests:   50
Passed Tests:  45
Failed Tests:  5
```

❌ DO NOT merge PR - fix issues first

## Common Test Workflows

### Workflow 1: Local Development Testing
```bash
# 1. Generate fresh tokens
./credentials-provider/generate_creds.sh

# 2. Run tests (skip production for speed)
./tests/run_all_tests.sh --skip-production

# 3. Fix any issues, repeat
```

See [TEST_QUICK_REFERENCE.md](TEST_QUICK_REFERENCE.md) for details.

### Workflow 2: Testing Agent CRUD Operations
```bash
# 1. Generate token
./credentials-provider/generate_creds.sh

# 2. Run simple agent registration/deletion test
bash tests/agent_crud_test.sh

# 3. Verify agent state
cat registry/agents/agent_state.json | jq .
```

See [TEST_QUICK_REFERENCE.md#agent-crud-test](TEST_QUICK_REFERENCE.md#agent-crud-test) for details.

### Workflow 3: Testing Access Control (LOB Bots)
```bash
# 1. Generate tokens for all bots (5-minute TTL)
./keycloak/setup/generate-agent-token.sh admin-bot
./keycloak/setup/generate-agent-token.sh lob1-bot
./keycloak/setup/generate-agent-token.sh lob2-bot

# 2. Run 14 access control tests (MCP services + Agent API)
bash tests/run-lob-bot-tests.sh
```

See [lob-bot-access-control-testing.md](lob-bot-access-control-testing.md) for details.

### Workflow 4: Full PR Merge Testing (REQUIRED)
```bash
# 1. Generate fresh tokens
./credentials-provider/generate_creds.sh

# 2. Run complete test suite (includes production)
./tests/run_all_tests.sh

# 3. Verify all tests pass (0 failures)
# This is MANDATORY before merging PR
```

See [TEST_QUICK_REFERENCE.md](TEST_QUICK_REFERENCE.md) for details.

## Troubleshooting

### Token Expired
```bash
./credentials-provider/generate_creds.sh
./tests/run_all_tests.sh --skip-production
```

**Note:** Tokens expire after 5 minutes - regenerate before each test run.

### Docker Not Running
```bash
docker-compose up -d
sleep 30
./tests/run_all_tests.sh --skip-production
```

### Check Logs
```bash
# List all test logs
ls -lh /tmp/*_*.log

# View specific log
tail -50 /tmp/mcp_list.log

# Search for errors
grep -i "error\|fail" /tmp/*.log
```

### Access Control Tests Failing

If LOB bot tests fail, verify:
1. Tokens exist: `ls -la .oauth-tokens/*.json`
2. Agents are registered: `curl -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/admin-bot-token.json)" http://localhost/api/agents`
3. Check scopes configuration: `cat auth_server/scopes.yml | head -80`

See [lob-bot-access-control-testing.md](lob-bot-access-control-testing.md) for troubleshooting.

## Next Steps

### For New Developers
1. Read [Agent Access Control & Permissions](#agent-access-control--permissions) above
2. Review [TEST_QUICK_REFERENCE.md](TEST_QUICK_REFERENCE.md) for quick how-to
3. Run `bash tests/agent_crud_test.sh` to see tests in action
4. Check [auth_server/scopes.yml](../auth_server/scopes.yml) to understand bot permissions

### For Access Control Testing
1. Read [lob-bot-access-control-testing.md](lob-bot-access-control-testing.md)
2. Run `bash tests/run-lob-bot-tests.sh` to validate LOB bot permissions
3. Check [Agent Access Control & Permissions](#agent-access-control--permissions) above for quick reference

### For Full Test Suite
1. See [TEST_QUICK_REFERENCE.md](TEST_QUICK_REFERENCE.md) for all available tests
2. Run `./tests/run_all_tests.sh --skip-production` for local testing
3. Run `./tests/run_all_tests.sh` for complete PR merge validation

## Contributing

When adding new functionality:

1. Add corresponding tests to `run_all_tests.sh` or create new test script
2. Update relevant documentation:
   - [TEST_QUICK_REFERENCE.md](TEST_QUICK_REFERENCE.md) - For quick start
   - [lob-bot-access-control-testing.md](lob-bot-access-control-testing.md) - For access control tests
3. Update [auth_server/scopes.yml](../auth_server/scopes.yml) if adding new bot groups
4. Ensure all tests pass before creating PR
5. Repository admin runs full suite (with production) before merge

## Support

For issues with tests:

1. **Check logs:** `ls -lh /tmp/*_*.log`
2. **Review troubleshooting:** See [Troubleshooting](#troubleshooting) section
3. **Check token expiration:** Tokens expire after 5 minutes
4. **Review scopes:** See [Agent Access Control & Permissions](#agent-access-control--permissions)
5. **Full guide:** [Full Testing Guide](../docs/testing.md)
6. **Create issue:** Include test output and logs

---

## Documentation Map

| Document | Purpose | Audience |
|----------|---------|----------|
| **README.md** (this file) | Navigation & overview | Everyone (start here) |
| **[TEST_QUICK_REFERENCE.md](TEST_QUICK_REFERENCE.md)** | How-to for all tests | Developers running tests |
| **[lob-bot-access-control-testing.md](lob-bot-access-control-testing.md)** | Access control details | Developers testing permissions |
| **[../docs/testing.md](../docs/testing.md)** | Comprehensive guide | Developers needing details |
| **[../auth_server/scopes.yml](../auth_server/scopes.yml)** | Permission definitions | System architects |

---

**For PR Merge:** Repository admin MUST run `./tests/run_all_tests.sh` (with production tests) and all tests must pass.
