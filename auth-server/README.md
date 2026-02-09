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

### Setup

Run `uv sync` from project root, NOT this workspace member folder (`auth-server`).

### Environment Variables

Create a `.env` file in the `auth-server` directory.

### Running the Server

From this `auth-server` directory, run the following command.

```bash
# Development mode with auto-reload (recommended)
uv run poe dev
```

The server will be available at:
- API: http://localhost:8888
- Interactive docs: http://localhost:8888/docs
- Alternative docs: http://localhost:8888/redoc

## Testing

The test suite uses `pytest` with `poethepoet` (`poe`) for task management.

### Run Tests

If running from project root, use the following.

```bash
uv run --package auth-server pytest auth-server/tests/
```

If running form the workspace member directory `auth-server`, use the following.

```bash
# Run all tests
uv run poe test

# Run all tests with coverage report
uv run poe test-cov
```
