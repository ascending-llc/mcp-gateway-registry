# Test Suite Quick Reference

## Quick Start

```bash
# Run all tests (including production) - REQUIRED for PR merge
./tests/run_all_tests.sh

# Run tests for local development only
./tests/run_all_tests.sh --skip-production

# Show help
./tests/run_all_tests.sh --help
```

## What Gets Tested

| Category | Tests | Environment |
|----------|-------|-------------|
| **Infrastructure** | Docker, Registry, Auth, Keycloak | Localhost |
| **Credentials** | Generation, validation, expiration | Localhost |
| **MCP Client** | List tools, call services, health | Localhost + Production |
| **Agent** | Prompt execution, tool calls | Localhost + Production |
| **Anthropic API** | List servers, get details | Localhost + Production |
| **Service Mgmt** | Import, registration, CRUD | Localhost |
| **Access Control** | LOB bot permissions, agent filtering | Localhost |
| **Code Quality** | Syntax, linting, validation | N/A |
| **Production** | All above against production URL | **Production** |

## Common Commands

### Before Testing
```bash
# Always generate fresh credentials first!
./credentials-provider/generate_creds.sh
```

### Run Tests
```bash
# Full test suite (for PR merge)
./tests/run_all_tests.sh

# Skip production (for local dev)
./tests/run_all_tests.sh --skip-production

# LOB Bot Access Control Tests (separate)
# See lob-bot-access-control-testing.md for details
bash tests/run-lob-bot-tests.sh
```

### Check Results
```bash
# View test logs
ls -lh /tmp/*_*.log

# Search for errors
grep -i "error\|fail" /tmp/*.log
```

## Quick Fixes

### Token Expired
```bash
./credentials-provider/generate_creds.sh
./tests/run_all_tests.sh
```

### Docker Not Running
```bash
docker-compose up -d
sleep 30
./tests/run_all_tests.sh
```

### Production Tests Failing
```bash
# Test connectivity
curl -k https://mcpgateway.ddns.net/health

# Check if local tests pass
./tests/run_all_tests.sh --skip-production
```

## Test Results

### Success
```
============================================================
ALL TESTS PASSED!
============================================================
Total Tests:   50
Passed Tests:  50
Failed Tests:  0
```
✅ **Safe to merge PR**

### Failure
```
============================================================
TESTS FAILED!
============================================================
Total Tests:   50
Passed Tests:  45
Failed Tests:  5
```
❌ **DO NOT merge PR**

## PR Merge Requirements

**MANDATORY** checklist:

- [ ] Run `./tests/run_all_tests.sh` (without --skip-production)
- [ ] All tests pass (0 failures)
- [ ] Production tests pass
- [ ] Logs show no errors or warnings
- [ ] Token is not about to expire

## LOB Bot Access Control Testing

For comprehensive testing of access control for LOB1, LOB2, and Admin bots:

**See:** [lob-bot-access-control-testing.md](./lob-bot-access-control-testing.md)

This covers:
- **MCP Service Access** (Tests 1-6): Verify bots can only call permitted services
- **Agent Registry API** (Tests 7-14): Verify bots only see/access permitted agents

Quick run:
```bash
# Regenerate tokens (5-minute expiration)
./keycloak/setup/generate-agent-token.sh lob1-bot
./keycloak/setup/generate-agent-token.sh lob2-bot
./keycloak/setup/generate-agent-token.sh admin-bot

# Run all access control tests
bash tests/run-lob-bot-tests.sh
```

## Agent CRUD Test

Simple script to demonstrate all CRUD operations on an A2A agent:

```bash
bash tests/agent_crud_test.sh
```

**What it tests:**
1. CREATE - Register new agent (POST /api/agents/register)
2. READ - Retrieve agent details (GET /api/agents/{path})
3. UPDATE - Modify agent (PUT /api/agents/{path})
4. LIST - List all agents (GET /api/agents)
5. TOGGLE - Disable agent (POST /api/agents/{path}/toggle)
6. TOGGLE - Re-enable agent (POST /api/agents/{path}/toggle)
7. DELETE - Remove agent (DELETE /api/agents/{path})
8. VERIFY - Confirm deletion (GET /api/agents/{path} → 404)
9. RE-CREATE - Restore agent to clean state (POST /api/agents/register)

**Token usage:**
```bash
# Default (uses .oauth-tokens/admin-bot-token.json)
bash tests/agent_crud_test.sh

# With custom token path
bash tests/agent_crud_test.sh /path/to/token.json

# With environment variable
TOKEN_FILE=/path/to/token.json bash tests/agent_crud_test.sh
```

**Features:**
- Colored output with checkmarks and X marks
- Pretty-printed JSON requests and responses
- HTTP status code display
- Automatic token expiration detection
- 5-minute token validation with helpful regeneration messages

**Verify results:**
```bash
cat registry/agents/agent_state.json | jq .
```

## Test Logs Location

All logs saved to `/tmp/`:

```bash
/tmp/creds_output.log          # Credentials generation
/tmp/mcp_list.log              # MCP client list tools
/tmp/mcp_list_services.log     # MCP client services
/tmp/mcp_health.log            # Health check
/tmp/agent_output.log          # Agent execution
/tmp/anthropic_list.log        # Anthropic API tests
/tmp/import_dryrun.log         # Import dry-run
/tmp/prod_*.log                # Production tests
/tmp/nginx_test.log            # Nginx validation
```

## Emergency Contact

If tests are failing and you can't figure out why:

1. **Check logs:** `tail -50 /tmp/*.log`
2. **Check containers:** `docker ps`
3. **Check services:** `curl http://localhost/health`
4. **Review docs:** `docs/testing.md`
5. **Create issue** with full test output

## Related Documentation

- [Full Testing Guide](../docs/testing.md)
- [Anthropic API](../docs/anthropic_registry_api.md)
- [LOB Bot Access Control Testing](./lob-bot-access-control-testing.md)
- [Scopes Configuration](../auth_server/scopes.yml)
- [Agent Routes](../registry/api/agent_routes.py)

## Tips

1. **Always regenerate credentials** before testing (tokens expire in 5 min)
2. **Run locally first** with `--skip-production` for faster iteration
3. **Check logs immediately** if any test fails
4. **Production tests are mandatory** for PR merge
5. **Don't skip tests** - they catch real issues!
6. **Test access control separately** with LOB bot tests - see [lob-bot-access-control-testing.md](./lob-bot-access-control-testing.md)

## Typical Runtimes

| Test Type | Time | Notes |
|-----------|------|-------|
| Localhost only | ~2-3 min | Fast iteration |
| Full suite | ~5-7 min | Includes production |
| Credential gen | ~30 sec | Run before tests |

## Success Criteria

For **PR merge**, you need:

✅ 0 failed tests
✅ Production tests passed
✅ No errors in logs
✅ All containers running
✅ Token valid for >60 seconds

---

**Remember:** Production tests are **MANDATORY** for PR merge!

Run: `./tests/run_all_tests.sh` (without --skip-production flag)
