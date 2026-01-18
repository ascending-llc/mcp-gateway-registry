# Auth Server

OAuth 2.0 Authorization Server with Device Flow support (RFC 8628) and OIDC Discovery.

## Features

- ✅ **OAuth 2.0 Device Authorization Grant** (RFC 8628)
- ✅ **OAuth 2.0 Authorization Server Metadata** (RFC 8414)
- ✅ **OpenID Connect Discovery**
- ✅ **JWKS Endpoint** for token verification
- ✅ **Multi-provider support**: Keycloak, AWS Cognito, Azure Entra ID
- ✅ **FastAPI** with automatic API documentation

## Local Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Install dependencies
uv sync
```

### Environment Variables

Create a `.env` file in the `auth_server` directory:
```

### Running the Server

```bash
# Development mode with auto-reload
uvicorn auth_server.server:app --reload --host 0.0.0.0 --port 8888

# Or using Python module
python -m uvicorn auth_server.server:app --reload --port 8888
```

The server will be available at:
- API: http://localhost:8888
- Interactive docs: http://localhost:8888/docs
- Alternative docs: http://localhost:8888/redoc

## Testing

The test suite uses **pytest** with **poethepoet** (poe) for task management.

### Install Test Dependencies

```bash
uv sync --extra dev
```

### Run Tests

```bash
# Run all tests
uv run poe test

# Run all tests with coverage report
uv run poe test-cov
```