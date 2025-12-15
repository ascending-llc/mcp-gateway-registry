# MCP Gateway Interaction Server (mcpgw)

This MCP server provides tools to interact with the main MCP Gateway Registry API.

## Architecture

The server has been refactored with a modular structure for better maintainability:

```
mcpgw/
├── server.py                 # Main entry point and tool registration
├── config.py                 # Configuration and constants
├── core/                     # Core business logic
│   ├── auth.py              # Authentication and authorization
│   ├── scopes.py            # Scopes management
│   └── registry.py          # Registry API client
├── tools/                    # Tool implementations
│   ├── auth_tools.py        # Authentication debugging tools
│   ├── service_mgmt.py      # Service management tools
│   ├── scopes_mgmt.py       # Scopes and groups management
│   └── search_tools.py      # Intelligent tool finder
└── search/                   # Vector search service
    ├── base.py              # Base service interface
    ├── embedded_service.py  # Embedded FAISS service
    ├── external_service.py  # External service client
    └── service.py           # Service factory
```

## Features

### Service Management
- `toggle_service`: Enables/disables a registered server in the gateway
- `register_service`: Registers a new MCP server with the gateway
- `list_services`: Lists all registered MCP services
- `remove_service`: Removes a registered MCP server
- `refresh_service`: Refreshes the tool list for a specific server
- `healthcheck`: Retrieves health status information

### Authentication & Debugging
- `debug_auth_context`: Explores available authentication context
- `get_http_headers`: Accesses HTTP headers including auth headers

### Scopes & Groups Management
- `add_server_to_scopes_groups`: Adds a server to specific scopes groups
- `remove_server_from_scopes_groups`: Removes a server from scopes groups
- `create_group`: Creates a new access control group
- `delete_group`: Deletes an access control group
- `list_groups`: Lists all groups with synchronization status

### Intelligent Tool Discovery
- `intelligent_tool_finder`: Semantic search to find relevant tools across all services

## Setup

1. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
   *(Use `.venv\Scripts\activate` on Windows)*

2. **Install dependencies:**
   
   **For external mode (recommended, lightweight):**
   ```bash
   pip install -e .
   ```
   This installs only core dependencies (~50MB), perfect for production.
   
   **For embedded mode (requires heavy ML dependencies ~2-3GB):**
   ```bash
   pip install -e ".[embedded-search]"
   ```
   This additionally installs FAISS, sentence-transformers, and scikit-learn.
   
   **Note**: The server intelligently loads dependencies based on `TOOL_DISCOVERY_MODE`:
   - `external` mode: No FAISS/ML dependencies loaded (lightweight ✨)
   - `embedded` mode: Only loads FAISS when actually initialized

3. **Configure environment variables:**
   Copy the `.env.template` file to `.env`:
   ```bash
   cp .env.template .env
   ```
   
   Edit the `.env` file and set the following variables:
   - `REGISTRY_BASE_URL`: The URL of your MCP Gateway Registry (e.g., `http://localhost:7860`)
   - `REGISTRY_USERNAME`: Username for authenticating with the registry API
   - `REGISTRY_PASSWORD`: Password for authenticating with the registry API
   - `MCP_SERVER_LISTEN_PORT`: Port for the server to listen on (default: 8003)
   - `TOOL_DISCOVERY_MODE`: Vector search mode - 'embedded' or 'external' (default: external)
   
   **Note**: This project uses `pydantic-settings` for configuration management, providing:
   - Type-safe configuration with automatic validation
   - Environment variable support with proper typing
   - Clear error messages for configuration issues

## Running the Server

```bash
python server.py
```

Or with custom options:

```bash
python server.py --port 8003 --transport streamable-http
```

The server will start and listen on the configured port (default: 8003).

## Configuration Options

### Environment Variables (via pydantic-settings)

All configuration is managed through `pydantic-settings` with automatic validation:

- **REGISTRY_BASE_URL** (required): URL of the MCP Gateway Registry
  - Example: `http://localhost:7860` (direct) or `http://localhost` (via nginx)
  - Automatically validated and normalized (trailing slash removed)

- **REGISTRY_USERNAME**: Username for registry authentication
  - Default: `""` (empty)
  - Used for Basic Auth with registry API

- **REGISTRY_PASSWORD**: Password for registry authentication
  - Default: `""` (empty)
  - Required for internal API access

- **MCP_SERVER_LISTEN_PORT**: Port for the server to listen on
  - Default: `8003`
  - Can be overridden via `--port` command line argument

- **MCP_TRANSPORT**: Transport type
  - Default: `streamable-http`
  - Can be overridden via `--transport` command line argument

- **TOOL_DISCOVERY_MODE**: Vector search mode
  - Options: `embedded` or `external`
  - Default: `external` (recommended, lightweight)
  - Validated to ensure only valid values

- **AUTH_SERVER_URL**: URL of the auth server
  - Default: `http://localhost:8888`

- **EMBEDDINGS_MODEL_NAME**: Sentence-transformers model name (embedded mode only)
  - Default: `all-MiniLM-L6-v2`

- **EMBEDDINGS_MODEL_DIMENSION**: Embedding dimension (embedded mode only)
  - Default: `384`

- **FAISS_CHECK_INTERVAL**: Interval to check for FAISS index updates (embedded mode only)
  - Default: `5.0` seconds

### Command Line Options

- `--port PORT`: Port for the MCP server to listen on
- `--transport TRANSPORT`: Transport type for the MCP server (default: streamable-http)

## Development

### Code Organization

All code is organized into logical modules:

- **config.py**: Centralized configuration management
- **core/**: Core business logic (auth, scopes, registry client)
- **tools/**: Tool implementations separated by functionality
- **search/**: Vector search service for intelligent tool discovery

### Adding New Tools

1. Implement the tool function in the appropriate module under `tools/`
2. Register the tool in `server.py` using the `@mcp.tool()` decorator
3. Add proper type hints and docstrings
4. Ensure all comments are in English

## License

Same as the parent project.
