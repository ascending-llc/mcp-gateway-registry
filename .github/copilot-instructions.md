# MCP Gateway & Registry - Copilot Coding Instructions

## Repository Overview

**What This Project Does:**
The MCP Gateway & Registry is an enterprise-ready platform for centralizing access to MCP (Model Context Protocol) servers and AI agents. It provides:
- Unified gateway for multiple MCP servers with OAuth 2.0/3.0 authentication
- MCP server registry with dynamic tool discovery via semantic search
- A2A (Agent-to-Agent) protocol support for agent registration and communication
- Fine-grained access control with Keycloak/Cognito integration
- Comprehensive observability with Grafana dashboards and OTEL export

**Repository Stats:**
- Size: ~28MB
- Primary Language: Python 3.12 (68,000+ lines of code)
- Total Files: 323 source files (Python, Shell, YAML)
- Architecture: FastAPI backend, Docker-based microservices, MongoDB + Weaviate vector DB

**Key Technologies:**
- **Backend**: Python 3.12, FastAPI, Pydantic, uvicorn
- **Database**: MongoDB (Beanie ODM), Weaviate (vector search)
- **Auth**: Keycloak, OAuth 2.0/3.0, JWT tokens
- **Container**: Docker Compose V2 (v2.38+), multi-service architecture
- **Testing**: pytest with 80% coverage requirement
- **Security**: Bandit scanner, Cisco AI MCP Scanner

## Critical Build & Environment Setup

### Python Version & Dependencies
**ALWAYS use Python 3.12** (required in `pyproject.toml: requires-python = ">=3.12,<3.13"`).

**Installation sequence (MUST be done in this order):**
```bash
# 1. Upgrade pip first
python -m pip install --upgrade pip setuptools wheel

# 2. Install with dev dependencies
pip install -e .[dev]

# 3. Verify installation
pip check  # Must show "No broken requirements found"
```

**IMPORTANT:** The project uses `pip` (not `uv`) despite CLAUDE.md mentioning uv. CI/CD workflows (.github/workflows/test.yml) use pip exclusively.

### Database Schema Generation (Required Before Tests)
Tests will fail with `ModuleNotFoundError: No module named 'packages.models._generated'` if schemas are not generated.

**TWO OPTIONS for schema generation:**

**Option 1: Download from GitHub Release (requires GitHub token for private repo):**
```bash
# Install packages module
cd packages
pip install -e .
cd ..

# Generate from GitHub release (requires GH_TOKEN or --token)
# Tag version: see packages/README.md or GitHub releases for latest
python -m packages.models.import_schemas \
  --tag asc0.4.0 \
  --files user.json token.json mcpServer.json session.json \
  --output-dir ./packages/models \
  --repo ascending-llc/jarvis-api \
  --token $GITHUB_TOKEN  # or $(gh auth token) if using GitHub CLI
```

**Option 2: Local mode (if schemas already exist locally):**
```bash
# If you have schemas in a local directory
python -m packages.models.import_schemas \
  --mode local \
  --input-dir /path/to/json-schemas \
  --files user.json token.json mcpServer.json session.json \
  --output-dir ./packages/models
```

**Verify schema generation:**
```bash
ls -la packages/models/_generated/  # Should contain __init__.py and model files
```

**NOTE:** If schema generation fails or schemas are not available, check with the repository maintainer about access to the jarvis-api release or schema files.

## Testing - Complete Workflow

### Test Environment Requirements
Before running ANY tests:

1. **Docker services must be running**
   ```bash
   docker compose ps  # Verify services are up
   # If not running:
   docker compose up -d
   sleep 30  # Allow services to initialize
   ```

2. **Generate credentials (tokens expire in 5 minutes)**
   ```bash
   ./credentials-provider/generate_creds.sh
   ```

3. **Check MongoDB schemas are generated**
   ```bash
   ls packages/models/_generated/__init__.py || echo "Run schema import first!"
   ```

### Running Tests

**Unit tests only (fastest iteration):**
```bash
pytest tests/unit -v
# Expected: All tests pass
```

**Integration tests (requires Docker services):**
```bash
pytest tests/integration -v
# Expected: All tests pass
```

**Full test suite with coverage (for local development):**
```bash
pytest --cov=registry --cov-report=xml --cov-report=html
# Expected: 80%+ coverage
# Generates: coverage.xml, htmlcov/ directory
```

**Complete test suite (bash scripts, including E2E):**
```bash
# Local development (skip production tests for speed)
./tests/run_all_tests.sh --skip-production

# PR merge requirement (MUST include production tests)
./tests/run_all_tests.sh
# Expected: "ALL TESTS PASSED! Total Tests: 50, Passed Tests: 50, Failed Tests: 0"
```

**Domain-specific testing (as used in CI):**
```bash
# Test specific domains: auth, servers, search, health, core
pytest tests/unit tests/integration -m auth -v
pytest tests/unit tests/integration -m servers -v
```

### Test Troubleshooting

**"Token expired" errors:**
```bash
./credentials-provider/generate_creds.sh  # Tokens expire after 5 minutes
```

**"ModuleNotFoundError: packages.models._generated":**
```bash
python -m packages.models.import_schemas --mode local \
  --input-dir ./dist/json-schemas \
  --files user.json token.json mcpServer.json session.json \
  --output-dir ./packages/models
```

**Docker services not responding:**
```bash
docker compose down
docker compose up -d
sleep 30  # CRITICAL: Wait for services to initialize
./tests/run_all_tests.sh --skip-production
```

## Security Scanning

**Bandit (run before commits):**
```bash
bandit -r registry/ -f json -o bandit-report.json
# CI runs: bandit -r registry/ -f json -o bandit-report.json || true
# Note: CI continues on bandit errors but uploads report
```

**Expected bandit behavior:**
- Security issues flagged but don't fail CI (|| true)
- Report uploaded as GitHub artifact
- Review bandit-report.json for vulnerabilities

## Docker & Container Management

**Docker Compose V2 syntax (REQUIRED):**
```bash
docker compose up -d          # NOT docker-compose (old syntax)
docker compose ps             # Check service status
docker compose logs registry  # View logs
docker compose down           # Stop services
```

**Build Docker images (requires setup):**
```bash
# CRITICAL: Set these environment variables first
export AWS_REGION=us-east-1
source .venv/bin/activate  # Must be in virtual environment

# Build images
./scripts/build-images.sh build IMAGE=registry
./scripts/build-images.sh build-push  # Build and push all
```

**Build script requirements:**
- Must have AWS_REGION environment variable set
- Must be running in Python virtual environment
- Uses build-config.yaml for image definitions

## Project Structure & Key Files

### Root Directory Files
```
.env.example          # Environment template (copy to .env)
pyproject.toml        # Main Python project config (requires-python = ">=3.12,<3.13")
docker-compose.yml    # Multi-service Docker configuration
CLAUDE.md             # Coding standards (NOTE: Says uv but project uses pip)
DEV_INSTRUCTIONS.md   # Developer onboarding guide
CONTRIBUTING.md       # Contribution guidelines
```

### Major Directories
```
registry/             # Main FastAPI application
├── api/             # API routes (agent, server, proxy, search)
├── services/        # Business logic (agent_service, server_service)
├── models/          # Pydantic data models
├── health/          # Health check service
├── auth/            # Authentication logic
├── utils/           # Utilities (scopes_manager, keycloak_manager)
├── main.py          # FastAPI app entry point
└── constants.py     # Global constants

packages/            # Shared database ORM and models
├── database/        # MongoDB connection (Beanie ODM)
├── models/          # Schema definitions
│   ├── import_schemas.py      # Schema generator script
│   └── _generated/            # Auto-generated Beanie models (MUST create)
└── vector/          # Weaviate vector search

tests/               # Comprehensive test suite
├── unit/            # Unit tests
├── integration/     # Integration tests
├── run_all_tests.sh # Main test script (50+ tests)
├── conftest.py      # Pytest configuration & fixtures
└── README.md        # Test documentation

auth_server/         # Auth service
└── scopes.yml       # Permission definitions (admin, LOB1, LOB2 access)

docker/              # Dockerfiles for all services
.github/workflows/   # CI/CD pipelines
```

### Configuration Files
```
pyproject.toml                    # Python deps, pytest config, coverage settings
auth_server/scopes.yml           # Access control permissions
config/federation.json           # External registry integration
.env.example                     # Environment variables template
docker-compose.yml               # Service orchestration
```

## GitHub CI/CD Workflows

**Workflow file:** `.github/workflows/test.yml`

**Jobs (run on push/PR to main/develop):**

1. **test** - Main test suite
   ```bash
   pip install -e .[dev]
   pytest tests/unit -v
   pytest tests/integration -v
   pytest --cov=registry --cov-report=xml --cov-report=html
   # Uploads: coverage.xml, htmlcov/, tests/reports/
   ```

2. **lint** - Code quality
   ```bash
   pip install bandit black isort flake8
   bandit -r registry/ -f json -o bandit-report.json || true
   # Uploads: bandit-report.json (as artifact)
   ```

3. **domain-tests** - Parallel domain testing
   ```bash
   # Matrix: auth, servers, search, health, core
   python scripts/test.py ${{ matrix.domain }}
   ```

4. **fast-feedback** - Quick PR checks
   ```bash
   python scripts/test.py fast
   ```

**IMPORTANT:** All test jobs must pass for PR merge. Coverage must be ≥80%.

## Common Workarounds & Known Issues

**TODOs found in codebase (from grep):**
- `registry/api/internal_routes.py`: Many debug logger.warning() calls marked TODO
- `registry/api/wellknown_routes.py`: Health status hardcoded, needs actual health check
- `registry/health/service.py`: Temporary workaround for credentials manager

**Authentication tokens:**
- Tokens expire after **5 minutes** - regenerate frequently
- Generate with: `./credentials-provider/generate_creds.sh`
- LOB bot tokens: `./keycloak/setup/generate-agent-token.sh [admin-bot|lob1-bot|lob2-bot]`

## Access Control & Permissions

**Three-tier access model** (defined in `auth_server/scopes.yml`):

| Bot User | Keycloak Group | Agents Access | Services Access |
|----------|----------------|---------------|-----------------|
| admin-bot | mcp-registry-admin | All agents | All services |
| lob1-bot | registry-users-lob1 | /code-reviewer, /test-automation | currenttime, mcpgw |
| lob2-bot | registry-users-lob2 | /data-analysis, /security-analyzer | currenttime, mcpgw, fininfo |

**Test access control:**
```bash
./keycloak/setup/generate-agent-token.sh admin-bot
./keycloak/setup/generate-agent-token.sh lob1-bot
./keycloak/setup/generate-agent-token.sh lob2-bot
bash tests/run-lob-bot-tests.sh  # 14 access control tests
```

## Code Standards (from CLAUDE.md)

**IMPORTANT DISCREPANCY:** CLAUDE.md states "Always use `uv`" but the project actually uses `pip`:
- CI workflows use: `pip install -e .[dev]`
- No `uv` commands in any shell scripts or workflows
- **Follow the actual project practice: use pip, not uv**

**Coding standards to follow:**
- Python 3.12 with type hints (Pydantic BaseModel for classes)
- FastAPI for web APIs (not Flask)
- Private functions start with underscore (_)
- Use two blank lines between function definitions
- Logging: `logging.basicConfig()` with detailed format
- Security: Run `bandit -r registry/` before commits

**Testing standards:**
- pytest with asyncio_mode = "auto"
- 80% minimum coverage (enforced in pyproject.toml)
- Markers: unit, integration, e2e, auth, servers, search, health, core

## Quick Reference Commands

**Complete setup from scratch:**
```bash
# 1. Install dependencies
python -m pip install --upgrade pip setuptools wheel
pip install -e .[dev]

# 2. Install packages module (needed for schema import)
cd packages
pip install -e .
cd ..

# 3. Generate database schemas (requires GitHub token for private repo)
# Option A: From GitHub release
export GITHUB_TOKEN=ghp_your_token_here
python -m packages.models.import_schemas \
  --tag asc0.4.0 \
  --files user.json token.json mcpServer.json session.json \
  --output-dir ./packages/models \
  --repo ascending-llc/jarvis-api \
  --token $GITHUB_TOKEN

# Option B: Skip if schemas not available - tests requiring DB will be skipped

# 4. Start Docker services (if available)
docker compose up -d && sleep 30

# 5. Generate credentials (if Keycloak is running)
./credentials-provider/generate_creds.sh

# 6. Run tests
# If schemas generated: ./tests/run_all_tests.sh --skip-production
# If no schemas: pytest tests/unit -v (some tests may be skipped)
```

**Daily development workflow:**
```bash
# 1. Regenerate credentials (they expire!)
./credentials-provider/generate_creds.sh

# 2. Run unit tests (fast iteration)
pytest tests/unit -v

# 3. Run security scan
bandit -r registry/

# 4. Before PR: Full test suite
./tests/run_all_tests.sh
```

## Trust These Instructions

These instructions are based on:
- Actual CI/CD workflows (.github/workflows/test.yml)
- Verified test scripts (tests/run_all_tests.sh)
- Project dependencies (pyproject.toml)
- Developer documentation (DEV_INSTRUCTIONS.md, tests/README.md)

**When to search beyond these instructions:**
- Only if commands fail unexpectedly
- When working on areas not covered here
- After major version upgrades

**Default approach:** Follow these instructions exactly. They represent validated, working sequences.
