# Copilot Instructions for Code Standard - Jarvis Registry

## Project Context
Enterprise platform for MCP (Model Context Protocol) servers with OAuth authentication.
**Stack:** Python 3.12, FastAPI, MongoDB (Beanie), Weaviate vector DB, Keycloak auth.

## Development Workflow

### Rule 1: Complex Problem-Solving Approach
**🧠 Think Before You Code**

When tackling complex problems or features:

1. **Present Technical Approach First**
   - Outline your thought process and proposed solution
   - Explain the technical approach, architecture decisions, and trade-offs
   - Break down the problem into logical steps
   - Identify potential risks or challenges

2. **Wait for Developer Agreement**
   - Do NOT start implementation until the developer reviews and agrees with the approach
   - Be open to feedback and alternative suggestions
   - Refine the approach based on discussion

3. **Then Implement**
   - Only after agreement, proceed with code implementation
   - Follow the agreed-upon approach faithfully
   - Communicate any deviations or unexpected issues

**Example:**
```
Developer: "Add OAuth token refresh logic to the auth service"

✅ CORRECT:
Assistant: "Here's my proposed approach for token refresh:
1. Create a background task in auth_service.py to check token expiration
2. Add a refresh_token() method that calls the OAuth provider
3. Store refresh tokens securely in MongoDB with encryption
4. Add retry logic with exponential backoff

Concerns:
- Need to handle race conditions if multiple requests trigger refresh
- Should we use a distributed lock (Redis) or database lock?

Does this approach work for you?"

❌ INCORRECT:
Assistant: [immediately starts writing code without discussion]
```

### Rule 2: Modular Code Design
**🔧 Break Complex Code into Testable Functions**

- **Single Responsibility**: Each function should do ONE thing well
- **Small Functions**: Aim for functions under 50 lines
- **Extract Logic**: Pull out complex logic into separate functions
- **Enable Testing**: Small functions are easier to unit test

**Example:**
```python
# ❌ BAD: Complex monolithic function
async def process_user_registration(email: str, password: str) -> User:
    # 150 lines of validation, hashing, database operations, email sending...
    pass

# ✅ GOOD: Broken into testable functions
async def validate_email_format(email: str) -> bool:
    """Validate email format."""
    pass

async def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    pass

async def create_user_record(email: str, hashed_password: str) -> User:
    """Create user in database."""
    pass

async def send_welcome_email(user: User) -> None:
    """Send welcome email to new user."""
    pass

async def process_user_registration(email: str, password: str) -> User:
    """Register new user - orchestrates the process."""
    if not await validate_email_format(email):
        raise ValueError("Invalid email")

    hashed_pwd = await hash_password(password)
    user = await create_user_record(email, hashed_pwd)
    await send_welcome_email(user)
    return user
```

### Rule 3: Unit Test File Organization
**📁 One-to-One Mapping with Source Files**

- **Mirror Source Structure**: Test file paths should try to mirror source code structure
- **Never Create Duplicates**: If a test file exists for a source file, ALWAYS use it
- **Check Before Creating**: Always search for existing test files before creating new ones

**File Mapping Rules:**

| Source File | Test File |
|-------------|-----------|
| `registry/src/registry/services/agent_service.py` | `tests/unit/services/test_agent_service.py` |
| `registry/src/registry/api/proxy_routes.py` | `tests/unit/api/test_proxy_routes.py` |

**Workflow:**

1. **Before Writing Tests**: Always check if test file exists
   ```bash
   # For source file: registry/src/registry/services/agent_service.py
   # Check: tests/unit/services/test_agent_service.py
   ```

2. **If Test File Exists**: Add tests to existing file, never create a new one

3. **If Test File Doesn't Exist**: Create it following the naming convention

4. **Never Create**: `test_agent_service_v2.py`, `test_agent_service_new.py`, etc.

### Rule 4: Running Unit Tests
**⚙️ Developer Runs Tests - Do NOT Auto-Run After Code Changes**

- **NEVER automatically run tests** after making code changes unless explicitly requested
- **Developer runs tests manually** - they will execute tests when ready
- **Update test files when needed** - writing or updating test code is appreciated
- **When tests ARE run** (only when explicitly requested):
  - Change directory into the right workspace member and use `uv run poe test` as the test runner.
  - Consult `pytest.ini` for pytest configuration (test paths, markers, coverage settings)
  - Respect the project's test configuration defined in `pytest.ini`

**Workflow:**

1. **Code Changes**: Make production code changes and update test files as needed

2. **Do NOT Run Tests Automatically**: Let the developer run tests themselves

3. **If Developer Explicitly Asks to Run Tests**:

   ```bash
   # Use uv to run pytest (respects pytest.init)
   cd registry && uv run poe test

   # With coverage
   cd registry && uv run poe test-cov

   # Specific test markers
   cd registry && uv run pytest tests/ -m "auth and not slow"
   ```

4. **Read `pytest.init` for Configuration**:

   ```init
   [pytest]
   # Test discovery
   testpaths = tests
   python_files = test_*.py
   python_classes = Test*
   python_functions = test_*

   # Add current directory to Python path for imports
   pythonpath = .

   # Disable coverage and other complex reporting for simple test runs
   addopts = -v --tb=short

   # Markers (optional, for categorizing tests)
   markers =
       slow: marks tests as slow (deselect with '-m "not slow"')
       unit: unit tests
       integration: integration tests
       telemetry: OpenTelemetry related tests
       metrics: OpenTelemetry metrics related tests
   ```

**Key Points:**
- ✅ Write/update test files when making code changes
- ✅ Explain what tests were added/updated
- ❌ Do NOT automatically run tests after code changes
- ✅ Use `uv run poe test-all` when tests are explicitly requested
- ✅ Always check `pytest.ini` for test configuration

## Code Review Rules

### Rule 1: Duplicate Code Detection
- **Scan for duplicate code blocks** across the codebase
- **Identify similar functions** that could be consolidated into reusable utilities
- **Look for repeated logic patterns** that should be extracted into shared services
- **Flag copy-pasted code** that differs only in minor details
- **Suggest creating utility functions** when similar code appears 3+ times
- **Check for duplicate constants** - should be centralized in `registry/src/registry/constants.py`
- **Identify similar API calls** that could use a shared service method

### Rule 2: Maintain Project Structure
Enforce strict file organization according to responsibility:

#### Project Structure (key directories and their purposes)

```text
registry/src/registry/                # Main FastAPI app (Registry Service)
├── api/                              # Routes ONLY: agent, server, proxy, search, internal
├── services/                         # Business logic: agent_service, server_service, etc.
├── auth/                             # Authentication/authorization logic
├── main.py                           # App entry point
└── constants.py                      # Global constants (no hardcoded values elsewhere)

auth-server/src/auth_server/          # OAuth 2.0 Authorization Server (Standalone FastAPI app)
├── server.py                         # Auth server entry point
├── providers/                        # OAuth provider implementations (Keycloak, Cognito, Entra)
├── utils/                            # Auth utilities and helpers
├── scopes.yml                        # OAuth scope definitions
└── oauth2_providers.yml              # Provider configurations

frontend/                             # React/TypeScript Web UI (Vite + Tailwind CSS)
├── src/                              # React components and application logic
├── public/                           # Static assets
├── vite.config.ts                    # Vite configuration
├── tailwind.config.js                # Tailwind CSS configuration
└── package.json                      # Node.js dependencies

servers/                              # Example MCP Servers
├── mcpgw/                            # MCP Gateway server implementation
├── fininfo/                          # Financial information MCP server
├── currenttime/                      # Time service MCP server
└── example-server/                   # Template MCP server for reference

registry-pkgs/src/registry_pkgs/      # Shared ORM and database utilities
├── models/                           # Beanie models and data definitions
│   └── _generated/                   # Auto-generated models (DO NOT manually edit)
└── database/                         # MongoDB connection utilities

# Within each workspace member folder (`registry`, `auth-server`, `registry-pkgs`, `servers/mcpgw`),
# use the following structure for tests. The point is that the `tests` folder should be on the same level
# as the `src` folder in the workspace member folder. This is the standard Python "src layout".
tests/                                # Test suite (80% coverage required)
├── unit/                             # Unit tests for services and business logic
├── integration/                      # Integration tests for API endpoints
└── conftest.py                       # Pytest fixtures and test configuration
```

#### File Placement Rules

**Registry Service (`registry/src/registry/`):**
- **`api`/** - Route definitions ONLY. No business logic, no database calls.
- **`services/`** - All business logic, data processing, external integrations.
- **`auth/`** - Authentication and authorization logic only.
- **`models/`** - Data schemas for registry such as response, request etc.
- **`constants.py`** - All application constants (no magic values in code).

**Auth Server (`auth-server/src/auth_server`):**
- **`server.py`** - OAuth 2.0 server implementation and endpoints.
- **`providers/`** - Provider-specific implementations (Keycloak, Cognito, Entra ID).
- **`utils/`** - Shared authentication utilities and token helpers.
- **`scopes.yml`** - OAuth scope definitions (source of truth).
- **`oauth2_providers.yml`** - Provider connection configurations.

**Frontend (`frontend/`):**
- **`src/`** - React components, hooks, services, and TypeScript code.
- **`public/`** - Static assets (images, fonts, etc.).
- **`vite.config.ts`** - Build configuration (DO NOT modify without team review).
- **`tailwind.config.js`** - UI styling configuration.

**MCP Servers (`servers/`):**
- Each subdirectory is a standalone MCP server implementation.
- Follow MCP protocol specifications for server implementations.
- Include `README.md` with setup and usage instructions.

**Shared Libraries for the registry service (`registry-pkgs/src/registry_pkgs`):**
- **`models/`** - ORM models.
- **`database/`** - Database connection and utility functions.
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
- **Models**: `registry_pkgs/models/{entity}.py` (lowercase, singular)
- **Private functions**: `_internal_function_name()`
- **Constants**: `UPPER_SNAKE_CASE` in `constants.py`

## Testing Requirements

### Coverage Rules

- ✅ **Minimum 80% code coverage** (enforced by CI)
- ✅ **Unit tests** for all service functions (`tests/unit/`)
- ✅ **Integration tests** for API endpoints (`tests/integration/`)
- ✅ **Domain markers**: Use `@pytest.mark.{domain}` (auth, servers, search, health, core)
- ✅ **One-to-One File Mapping**: Test files should try to mirror source file structure (see Development Workflow Rule 3)
- ✅ **Consult pyproject.toml**: Always check `pytest.ini` for pytest CLI configuration before running tests

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
# cd into the workspace member directory first. Then use the following commands
uv run pytest tests/unit -v                    # Unit tests
uv run pytest tests/integration -v             # Integration tests
uv run pytest --cov=registry --cov-report=xml  # Coverage check (≥80%)
uv run pytest -m auth -v                       # Domain-specific tests
```

## Security Requirements

- ✅ **Bandit scan** must pass: `bandit -r registry/ -f json -o bandit-report.json`
- ✅ **No hardcoded secrets** (use environment variables)
- ✅ **Input validation** via Pydantic models
- ✅ **Access control** via scopes (defined in `auth-server/src/auth_server/scopes.yml`)

## Code Review Checklist

### ✅ Structure & Organization

- Routes are in `api/`, services in `services/`, models in `models/`
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
