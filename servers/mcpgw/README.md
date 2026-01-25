# MCP Gateway Interaction Server (mcpgw)

FastMCP server providing tools to interact with the MCP Gateway Registry API.

## Quick Start

```bash
# Install dependencies (from workspace root)
uv sync

# Run server
cd servers/mcpgw
python server.py --port 8003
```

## Testing

```bash
# From workspace root
uv run poe test-all        # Run all tests
uv run poe test-all-cov    # With coverage

# See pyproject.toml in root for all test commands
```

## Key Architecture

### Authentication
All registry API calls use **JWT-based authentication**:
- User context extracted from FastMCP `Context` (ctx.user_auth)
- JWT generated with HS256, signed with `JWT_SIGNING_SECRET`
- Token includes: user context, `mcpgw` as issuer, 5-min expiry
- See [core/registry.py](core/registry.py) `_generate_service_jwt()`

### Registry API Pattern
**All registry API calls MUST use centralized client:**
```python
from core.registry import call_registry_api

# Automatic: JWT generation, SSE handling, response unwrapping
result = await call_registry_api("POST", "/api/v1/endpoint", ctx, json=payload)
```

### Code Structure
```
mcpgw/
├── server.py              # FastMCP entry point
├── config.py              # Pydantic settings
├── core/
│   └── registry.py        # ⭐ Centralized API client + JWT auth
├── tools/                 # Tool implementations
│   ├── proxy_mcp_tools.py     # execute_tool
│   ├── search.py              # discover_tools  
│   └── service_mgmt.py        # Service management
└── search/                # Vector search (FAISS/external)
```

## Environment Variables

Required:
- `REGISTRY_URL`: Registry API URL (default: `http://localhost:7860`)
- `JWT_SIGNING_SECRET`: JWT secret key (from env or Keycloak)

## Installation Modes

**External mode (recommended):**
```bash
pip install -e .
```
