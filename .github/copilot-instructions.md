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

#### Project Structure (key directories and their purposes)

```text
registry/              # Main FastAPI app (Registry Service)
├── api/              # Routes ONLY: agent, server, proxy, search, internal
├── services/         # Business logic: agent_service, server_service, etc.
├── auth/             # Authentication/authorization logic
├── main.py           # App entry point
└── constants.py      # Global constants (no hardcoded values elsewhere)

auth_server/          # OAuth 2.0 Authorization Server (Standalone FastAPI app)
├── server.py         # Auth server entry point
├── providers/        # OAuth provider implementations (Keycloak, Cognito, Entra)
├── utils/            # Auth utilities and helpers
├── scopes.yml        # OAuth scope definitions
├── oauth2_providers.yml  # Provider configurations
└── metrics_middleware.py # Prometheus metrics

frontend/             # React/TypeScript Web UI (Vite + Tailwind CSS)
├── src/              # React components and application logic
├── public/           # Static assets
├── vite.config.ts    # Vite configuration
├── tailwind.config.js # Tailwind CSS configuration
└── package.json      # Node.js dependencies

servers/              # Example MCP Servers
├── mcpgw/            # MCP Gateway server implementation
├── fininfo/          # Financial information MCP server
├── currenttime/      # Time service MCP server
└── example-server/   # Template MCP server for reference

packages/             # Shared ORM and database utilities
├── models/           # Beanie models and data definitions
│   └── _generated/   # Auto-generated models (DO NOT manually edit)
└── database/         # MongoDB connection utilities

tests/                # Test suite (80% coverage required)
├── unit/             # Unit tests for services and business logic
├── integration/      # Integration tests for API endpoints
└── conftest.py       # Pytest fixtures and test configuration
```

#### File Placement Rules

**Registry Service (`/registry`):**
- **`/api`** - Route definitions ONLY. No business logic, no database calls.
- **`/services`** - All business logic, data processing, external integrations.
- **`/auth`** - Authentication and authorization logic only.
- **`/models`** - Data schemas for registry such as response, request etc.
- **`/constants.py`** - All application constants (no magic values in code).

**Auth Server (`/auth_server`):**
- **`server.py`** - OAuth 2.0 server implementation and endpoints.
- **`/providers`** - Provider-specific implementations (Keycloak, Cognito, Entra ID).
- **`/utils`** - Shared authentication utilities and token helpers.
- **`scopes.yml`** - OAuth scope definitions (source of truth).
- **`oauth2_providers.yml`** - Provider connection configurations.

**Frontend (`/frontend`):**
- **`/src`** - React components, hooks, services, and TypeScript code.
- **`/public`** - Static assets (images, fonts, etc.).
- **`vite.config.ts`** - Build configuration (DO NOT modify without team review).
- **`tailwind.config.js`** - UI styling configuration.

**MCP Servers (`/servers`):**
- Each subdirectory is a standalone MCP server implementation.
- Follow MCP protocol specifications for server implementations.
- Include `README.md` with setup and usage instructions.

**Shared Libraries (`/packages`):**
- **`/models`** - ORM models.
- **`/database`** - Database connection and utility functions.
- Code here must be framework-agnostic and reusable.

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

### Test Review Guidelines

**🎯 Focus on application code quality, not test code perfection:**

- **Be lenient with test code** - Minor issues in tests (unused imports, unused variables, minor style) are acceptable if tests pass
- **Prioritize test functionality** - Tests that verify correct behavior are more important than perfect test code style
- **Ignore minor test issues** - Don't flag: unused fixtures, verbose assertions, test data duplication, minor formatting
- **Focus review on production code** - Routes, services, models, auth logic, and business logic require strict review
- **Test code exceptions allowed**:
  - Unused mock imports (if tests pass)
  - Duplicate test data setup (acceptable for readability)
  - Long test functions (comprehensive testing is good)
  - Minor linting issues in test files

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

- **Production code**: Unit tests written for new services
- **Production code**: Integration tests for new endpoints
- **Production code**: Bandit scan passes (no security issues)
- **Production code**: No sensitive data in logs
- **Production code**: Environment variables for configuration
- **Test code**: Be lenient - passing tests are priority over perfect test code
- **Test code**: Minor issues (unused imports, verbose tests) are acceptable
