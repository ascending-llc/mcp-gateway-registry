# MCP Gateway & Registry - Copilot Instructions

## What This Repository Does
Enterprise platform for centralizing MCP (Model Context Protocol) servers and AI agents with OAuth authentication, dynamic tool discovery, A2A protocol support, and fine-grained access control. **Stack:** Python 3.12, FastAPI, MongoDB (Beanie), Weaviate vector DB, Keycloak auth, Docker Compose V2.

## Critical Setup (MUST Follow Order)

### 1. Install Dependencies
**Python 3.12 REQUIRED**. Project uses `pip` NOT `uv` (ignore CLAUDE.md).
```bash
python -m pip install --upgrade pip setuptools wheel && pip install -e .[dev] && pip check
```

### 2. Generate Database Schemas (Tests Fail Without This!)
```bash
cd packages && pip install -e . && cd ..
# Requires GITHUB_TOKEN for private ascending-llc/jarvis-api repo
python -m packages.models.import_schemas --tag asc0.4.0 \
  --files user.json token.json mcpServer.json session.json \
  --output-dir ./packages/models --repo ascending-llc/jarvis-api --token $GITHUB_TOKEN
# If unavailable, coordinate with repo maintainer
```

### 3. Start Docker & Generate Credentials
```bash
docker compose up -d && sleep 30  # 30s wait is CRITICAL
./credentials-provider/generate_creds.sh  # Tokens expire in 5min!
```

## Testing (80% Coverage Required)

```bash
pytest tests/unit -v                         # Fast unit tests
pytest tests/integration -v                  # Integration tests (needs Docker)
pytest --cov=registry --cov-report=xml       # Coverage (80% min)
./tests/run_all_tests.sh --skip-production  # Local dev
./tests/run_all_tests.sh                    # PR merge (REQUIRED)
pytest -m auth -v                            # Domain tests (auth, servers, search, health, core)
```

**Troubleshooting:** Token expired? Run `./credentials-provider/generate_creds.sh`. ModuleNotFoundError? Run schema import (step 2). Docker errors? `docker compose down && docker compose up -d && sleep 30`

## Security, Docker, CI/CD

**Security:** `bandit -r registry/ -f json -o bandit-report.json` (CI continues on errors, uploads report)

**Docker:** Use V2 syntax: `docker compose up -d` (NOT `docker-compose`). Commands: `ps`, `logs registry`, `down`

**CI/CD** (.github/workflows/test.yml): test job (unit + integration + coverage 80%), lint job (bandit), domain-tests (auth/servers/search/health/core), fast-feedback. All must pass for PR merge.

## Project Structure (Key Locations)

```
registry/              # Main FastAPI app
├── api/              # Routes: agent, server, proxy, search, internal
├── services/         # Business logic: agent_service, server_service
├── main.py           # App entry point
├── constants.py      # Global constants
└── auth/             # Auth logic

packages/             # Shared ORM (install with: cd packages && pip install -e .)
├── models/_generated/  # Auto-generated Beanie models (MUST create via import_schemas)
└── database/         # MongoDB connection

tests/                # Test suite
├── run_all_tests.sh  # Main test script (50+ tests)
├── unit/             # Unit tests  
├── integration/      # Integration tests
└── conftest.py       # Pytest fixtures

auth_server/scopes.yml  # Access control (admin-bot, lob1-bot, lob2-bot permissions)
pyproject.toml         # Python deps, pytest config (coverage ≥80% required)
docker-compose.yml     # Multi-service config
.env.example           # Copy to .env
```

## Critical Gotchas

- **Tokens expire in 5min** - regenerate with `./credentials-provider/generate_creds.sh`
- **Schema needs private repo access** - ask maintainer for GITHUB_TOKEN
- **Docker startup** - ALWAYS `sleep 30` after `docker compose up -d`
- **Use pip not uv** - CLAUDE.md is wrong, follow CI workflows
- **TODOs:** debug logging in `registry/api/internal_routes.py`, credentials workaround in `registry/health/service.py`

## Access Control & Environment

**Access tiers** (auth_server/scopes.yml): admin-bot (all), lob1-bot (/code-reviewer + /test-automation, currenttime+mcpgw), lob2-bot (/data-analysis + /security-analyzer, currenttime+mcpgw+fininfo). Test: `./keycloak/setup/generate-agent-token.sh [bot]` → `tests/run-lob-bot-tests.sh`

**Key env vars** (.env.example → .env): APP_HOME=/opt, MONGO_URI, KEYCLOAK_ADMIN_URL/EXTERNAL_URL/REALM/M2M_CLIENT_ID/M2M_CLIENT_SECRET, AWS_REGION (for builds), GITHUB_TOKEN (schemas)

## Code Standards
Python 3.12, type hints, Pydantic BaseModel, FastAPI, private functions with `_` prefix, two blank lines between functions, `logging.basicConfig()`. **Ignore CLAUDE.md's uv requirement - use pip.**

## Quick Commands

**Setup:** `pip install --upgrade pip setuptools wheel && pip install -e .[dev] && cd packages && pip install -e . && cd .. && docker compose up -d && sleep 30 && ./credentials-provider/generate_creds.sh`

**Daily:** `./credentials-provider/generate_creds.sh && pytest tests/unit -v && bandit -r registry/ && ./tests/run_all_tests.sh`

**Build images:** `export AWS_REGION=us-east-1 && source .venv/bin/activate && ./scripts/build-images.sh build IMAGE=registry`

---
**Trust these instructions** - based on verified CI/CD, test scripts, pyproject.toml. Search only if commands fail unexpectedly.
