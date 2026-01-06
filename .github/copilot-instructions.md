# Copilot Instructions for Code Review - MCP Gateway & Registry

## Project Context
Enterprise platform for MCP (Model Context Protocol) servers with OAuth authentication.
**Stack:** Python 3.12, FastAPI, MongoDB (Beanie), Weaviate vector DB, Keycloak auth.

## Code Review Rules

### Rule 1: Duplicate Code Detection
- **Scan for duplicate code blocks** across the codebase
- **Identify similar functions** that could be consolidated into reusable utilities
- **Look for repeated logic patterns** that should be extracted into shared services
- **Flag copy-pasted code** that differs only in minor details
- **Suggest creating utility functions** when similar code appears 3+ times
- **Check for duplicate constants** - should be centralized in `registry/constants.py`
- **Identify similar API calls** that could use a shared service method

### Rule 2: Maintain Project Structure
Enforce strict file organization according to responsibility:

#### Project Structure

```text
registry/              # Main FastAPI app
├── api/              # Routes ONLY: agent, server, proxy, search, internal
├── services/         # Business logic: agent_service, server_service, etc.
├── auth/             # Authentication/authorization logic
├── main.py           # App entry point
└── constants.py      # Global constants (no hardcoded values elsewhere)

packages/             # Shared ORM and database
├── models/           # Beanie models and data definitions
│   └── _generated/   # Auto-generated models (DO NOT manually edit)
└── database/         # MongoDB connection utilities

tests/                # Test suite (80% coverage required)
├── unit/             # Unit tests
├── integration/      # Integration tests
└── conftest.py       # Pytest fixtures
```

#### File Placement Rules

- **`/api`** - Route definitions ONLY. No business logic, no database calls.
- **`/services`** - All business logic, data processing, external integrations.
- **`/auth`** - Authentication and authorization logic only.
- **`/models`** - Data schemas, Beanie models, type definitions.
- **`/constants.py`** - All application constants (no magic values in code).

## Code Standards (Python 3.12)

### Required Patterns

- ✅ **Type hints** on all functions and methods
- ✅ **Pydantic BaseModel** for data validation
- ✅ **FastAPI** decorators for routes
- ✅ **Private functions** prefixed with `_`
- ✅ **Two blank lines** between top-level functions/classes
- ✅ **`logging.basicConfig()`** for logging setup
- ✅ **Async/await** for I/O operations (database, external APIs)

### Naming Conventions

- **Routes**: `registry/api/{domain}_routes.py` (e.g., `agent_routes.py`)
- **Services**: `registry/services/{domain}_service.py` (e.g., `agent_service.py`)
- **Models**: `packages/models/{entity}.py` (lowercase, singular)
- **Private functions**: `_internal_function_name()`
- **Constants**: `UPPER_SNAKE_CASE` in `constants.py`

## Testing Requirements

### Coverage Rules

- ✅ **Minimum 80% code coverage** (enforced by CI)
- ✅ **Unit tests** for all service functions (`tests/unit/`)
- ✅ **Integration tests** for API endpoints (`tests/integration/`)
- ✅ **Domain markers**: Use `@pytest.mark.{domain}` (auth, servers, search, health, core)

### Test Commands

```bash
pytest tests/unit -v                    # Unit tests
pytest tests/integration -v             # Integration tests
pytest --cov=registry --cov-report=xml  # Coverage check (≥80%)
pytest -m auth -v                       # Domain-specific tests
```

## Security Requirements

- ✅ **Bandit scan** must pass: `bandit -r registry/ -f json -o bandit-report.json`
- ✅ **No hardcoded secrets** (use environment variables)
- ✅ **Input validation** via Pydantic models
- ✅ **Access control** via scopes (defined in `auth_server/scopes.yml`)

## Code Review Checklist

### ✅ Structure & Organization

- Routes are in `/api`, services in `/services`, models in `/models`
- No business logic in route handlers (delegate to services)
- No direct database access in routes (use services)
- Constants defined in `constants.py`, not hardcoded
- Files follow naming conventions

### ✅ Duplicate Code

- No duplicate functions across services
- Repeated patterns extracted to utilities
- Similar database queries consolidated
- No copy-pasted validation logic

### ✅ Python Standards

- Type hints on all functions
- Pydantic models for validation
- Private functions use `_` prefix
- Two blank lines between functions
- Proper async/await usage

### ✅ Testing & Security

- Unit tests written for new services
- Integration tests for new endpoints
- Bandit scan passes (no security issues)
- No sensitive data in logs
- Environment variables for configuration
