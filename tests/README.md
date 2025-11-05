# MCP Gateway Registry Test Suite

Comprehensive test suite for validating all functionality before PR merge.

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

## Files in this Directory

- **[run_all_tests.sh](run_all_tests.sh)** - Main test suite script
- **[TEST_QUICK_REFERENCE.md](TEST_QUICK_REFERENCE.md)** - Quick reference guide
- **README.md** - This file

## Documentation

- **[Full Testing Guide](../docs/testing.md)** - Comprehensive testing documentation

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

## Troubleshooting

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

### Check Logs
```bash
# List all test logs
ls -lh /tmp/*_*.log

# View specific log
tail -50 /tmp/mcp_list.log

# Search for errors
grep -i "error\|fail" /tmp/*.log
```

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: Test Suite
on: [pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Start services
        run: docker-compose up -d
      - name: Wait for services
        run: sleep 30
      - name: Run tests
        run: ./tests/run_all_tests.sh --skip-production
```

## Contributing

When adding new functionality:

1. Add corresponding tests to `run_all_tests.sh`
2. Update test documentation
3. Ensure all tests pass before creating PR
4. Repository admin runs full suite (with production) before merge

## Support

For issues with tests:

1. Check logs in `/tmp/`
2. Review troubleshooting section above
3. Check [full testing guide](../docs/testing.md)
4. Create issue with test output

---

**For PR Merge:** Repository admin MUST run `./tests/run_all_tests.sh` (with production tests) and all tests must pass.
