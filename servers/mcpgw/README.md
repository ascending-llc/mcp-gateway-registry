# MCP Gateway Interaction Server (mcpgw)

This MCP server provides tools to interact with the main MCP Gateway Registry API.

## Features

Exposes the following registry API endpoints as MCP tools:

*   `toggle_service`: Enables/disables a registered server in the gateway.
*   `register_service`: Registers a new MCP server with the gateway.
*   `get_server_details`: Retrieves configuration details for a specific server.
*   `get_service_tools`: Lists the tools provided by a specific server.
*   `refresh_service`: Refreshes the tool list for a specific server.

## Setup

1.  **Create a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```
    *(Use `.venv\Scripts\activate` on Windows)*

2.  **Install dependencies:**
    ```bash
    pip install -e .
    ```
    *(This installs the package in editable mode based on `pyproject.toml`)*

3.  **Configure environment variables:**
    Copy the `.env.template` file to `.env`:
    ```bash
    cp .env.template .env
    ```
    Edit the `.env` file and set the following variables:
    *   `REGISTRY_BASE_URL`: The correct URL of your running MCP Gateway Registry (e.g., `http://localhost:7860`).
    *   `REGISTRY_USERNAME`: The username for authenticating with the registry API (defaults to `admin` if not set).
    *   `REGISTRY_PASSWORD`: The password for authenticating with the registry API (defaults to `password` if not set).

    You can also uncomment and set `MCP_SERVER_LISTEN_PORT` if you don't want to use the default port 8000 (as defined in `server.py`).

## Running the Server

```bash
python server.py
```

The server will start and listen on the configured port (default 8001).

## Running the Client (Example)

Ensure the server is running. In a separate terminal (with the virtual environment activated):

```bash
python client.py
```

This will connect to the server, list its tools, and attempt to call the `get_server_details` tool for the `/current_time` service path as an example.