# MCP Gateway Interaction Server (`mcpgw`)

FastMCP server providing tools to interact with the MCP Gateway Registry API.

## Quick Start

```bash
# Install dependencies (from workspace root)
uv sync

# Run server
cd servers/mcpgw
python server.py --port 8003
```

## Key Architecture

### Authentication

All registry API calls use **JWT-based authentication**:
- User context extracted from FastMCP `Context` (`ctx.user_auth`).
- JWT generated with HS256, signed with `JWT_SIGNING_SECRET`.
- Token includes: user context, `mcpgw` as issuer, 5-min expiration.
- See [core/registry.py](core/registry.py) `_generate_service_jwt()`.

### Registry API Pattern

**All registry API calls MUST use centralized client:**

```python
from core.registry import call_registry_api

# Automatic: JWT generation, SSE handling, response unwrapping
result = await call_registry_api("POST", "/api/v1/endpoint", ctx, json=payload)
```

### Code Structure

```
servers/mcpgw/src/mcpgw/
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
- `SECRET_KEY`: JWT secret key (from env or Keycloak)
