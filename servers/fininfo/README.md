# Fininfo MCP Server

This MCP server provides financial information using the Polygon.io API with FastMCP 2.0.

## Features

- **Stock aggregate data**: Get historical stock data from Polygon.io
- **HTTP header debugging**: View HTTP headers sent to the server
- **FastMCP 2.0**: Built with the latest FastMCP framework

## Quick Start

### 1. Install Dependencies

```bash
# Install Python dependencies with uv
uv sync
```

### 2. Set Environment Variables

```bash
# Set your Polygon.io API key
export POLYGON_API_KEY="your_polygon_api_key_here"
```

### 3. Run the Server

```bash
# Using uv
uv run python server.py --port 8000 --transport sse

# Or activate the virtual environment first
source .venv/bin/activate
python server.py --port 8000 --transport sse
```

## Usage

### Using the Python Client

```bash
# Test the server
uv run python client.py

# Connect to remote server
uv run python client.py --host your-server.com --port 8000
```

### Available Tools

- `get_stock_aggregates`: Get stock aggregate data from Polygon.io
- `print_stock_data`: Get formatted stock data as a string
- `get_http_headers`: Debug tool to view HTTP headers

## Environment Variables

- `POLYGON_API_KEY`: Your Polygon.io API key (required)
- `MCP_SERVER_LISTEN_PORT`: Server port (default: 8000)
- `MCP_TRANSPORT`: Transport type (default: sse)

## Example API Call

```python
# Get Apple stock data for the last week
params = {
    "stock_ticker": "AAPL",
    "multiplier": 1,
    "timespan": "day",
    "from_date": "2023-01-01",
    "to_date": "2023-01-31",
    "adjusted": True,
    "sort": "desc",
    "limit": 10
}
```

## Development

The server includes comprehensive HTTP header debugging to help with development and troubleshooting. The `get_http_headers` tool shows all incoming headers with sensitive information masked for security.