#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# Unified entrypoint for registry frontend and backend.
# Usage:
#   /entrypoint.sh frontend
#   /entrypoint.sh backend

MODE="${1}"

SSL_CERT_PATH="${SSL_CERT_PATH:-/etc/ssl/certs/fullchain.pem}"
SSL_KEY_PATH="${SSL_KEY_PATH:-/etc/ssl/private/privkey.pem}"

install_nginx_template() {
    HTTP_ONLY_TEMPLATE_PATH="${1:?}"
    HTTP_AND_HTTPS_TEMPLATE_PATH="${2:?}"
    DEST_PATH="${3:?}"

    echo "Checking for SSL certificates..."
    if [ ! -f "$SSL_CERT_PATH" ] || [ ! -f "$SSL_KEY_PATH" ]; then
        echo "=========================================="
        echo "SSL certificates not found - HTTPS will not be available"
        echo "=========================================="
        echo ""
        echo "To enable HTTPS, mount your certificates to:"
        echo "  - $SSL_CERT_PATH"
        echo "  - $SSL_KEY_PATH"
        echo ""
        echo "Example for docker-compose.yml:"
        echo "  volumes:"
        echo "    - /path/to/fullchain.pem:/etc/ssl/certs/fullchain.pem:ro"
        echo "    - /path/to/privkey.pem:/etc/ssl/private/privkey.pem:ro"
        echo ""
        echo "HTTP server will be available on port 80"
        echo "=========================================="
    else
        echo "=========================================="
        echo "SSL certificates found - HTTPS enabled"
        echo "=========================================="
        echo "Certificate: $SSL_CERT_PATH"
        echo "Private key: $SSL_KEY_PATH"
        echo "HTTPS server will be available on port 443"
        echo "=========================================="
    fi

    # Check if SSL certificates exist and use appropriate config
    if [ ! -f "$SSL_CERT_PATH" ] || [ ! -f "$SSL_KEY_PATH" ]; then
        echo "Using HTTP-only Nginx configuration (no SSL certificates)..."
        cp "$HTTP_ONLY_TEMPLATE_PATH" "$DEST_PATH"
        echo "HTTP-only Nginx configuration installed."
    else
        echo "Using HTTP + HTTPS Nginx configuration (SSL certificates found)..."
        cp "$HTTP_AND_HTTPS_TEMPLATE_PATH" "$DEST_PATH"
        echo "HTTP + HTTPS Nginx configuration installed."
    fi
}


setup_backend() {
    # --- Environment Variable Setup ---
    echo "Setting up environment variables..."

    # Generate secret key if not provided
    if [ -z "$SECRET_KEY" ]; then
        SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
    fi

    ADMIN_USER_VALUE=${ADMIN_USER:-admin}

    # Check if ADMIN_PASSWORD is set
    if [ -z "${ADMIN_PASSWORD:-}" ]; then
        echo "ERROR: ADMIN_PASSWORD environment variable is not set."
        echo "Please set ADMIN_PASSWORD to a secure value before running the container."
        exit 1
    fi

    # Create .env file for registry
    REGISTRY_ENV_FILE="${REGISTRY_ENV_FILE:-/app/registry/.env}"
    echo "Creating Registry .env file..."
    echo "SECRET_KEY=${SECRET_KEY}" > "$REGISTRY_ENV_FILE"
    echo "ADMIN_USER=${ADMIN_USER_VALUE}" >> "$REGISTRY_ENV_FILE"
    echo "ADMIN_PASSWORD=${ADMIN_PASSWORD}" >> "$REGISTRY_ENV_FILE"
    echo "Registry .env created."
}


setup_lua() {
    # --- Lua Module Setup ---
    echo "Setting up Lua support for nginx..."
    LUA_SCRIPTS_DIR="/etc/nginx/lua"
    mkdir -p "$LUA_SCRIPTS_DIR"

    cat > "$LUA_SCRIPTS_DIR/capture_body.lua" <<'EOF'
-- capture_body.lua: Read request body and encode it in X-Body header for auth_request
local cjson = require "cjson"

-- Read the request body
ngx.req.read_body()
local body_data = ngx.req.get_body_data()

if body_data then
    ngx.req.set_header("X-Body", body_data)
    ngx.log(ngx.INFO, "Captured request body (" .. string.len(body_data) .. " bytes) for auth validation")
else
    ngx.log(ngx.INFO, "No request body found")
end
EOF

    echo "Lua script created."
}

check_model() {
    EMBEDDINGS_MODEL_NAME="all-MiniLM-L6-v2"
    EMBEDDINGS_MODEL_DIR="/app/registry/models/$EMBEDDINGS_MODEL_NAME"

    echo "Checking for sentence-transformers model..."
    if [ ! -d "$EMBEDDINGS_MODEL_DIR" ] || [ -z "$(ls -A "$EMBEDDINGS_MODEL_DIR")" ]; then
        echo "=========================================="
        echo "WARNING: Embeddings model not found!"
        echo "=========================================="
        echo ""
        echo "The registry requires the sentence-transformers model to function properly."
        echo "Please download the model to: $EMBEDDINGS_MODEL_DIR"
        echo ""
        echo "Run this command to download the model:"
        echo "  docker run --rm -v \$(pwd)/models:/models huggingface/transformers-pytorch-cpu python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/$EMBEDDINGS_MODEL_NAME').save('/models/$EMBEDDINGS_MODEL_NAME')\""
        echo ""
        echo "Or see the README for alternative download methods."
        echo "=========================================="
    else
        echo "Embeddings model found at $EMBEDDINGS_MODEL_DIR"
    fi
}

substitute_mcp_server_env_tokens() {
    echo "Processing MCP Server configuration files..."
    for i in $(seq 1 99); do
        env_var_name="MCP_SERVER${i}_AUTH_TOKEN"
        env_var_value=$(eval echo \$$env_var_name)

    if [ ! -z "$env_var_value" ]; then
        echo "Found $env_var_name, substituting in server JSON files..."
        # Replace the literal environment variable name with its value in all JSON files
        find /app/registry/servers -name "*.json" -type f -exec sed -i "s|$env_var_name|$env_var_value|g" {} \;
    fi
    done
    echo "MCP Server configuration processing completed."
}

start_backend_services() {
    export EMBEDDINGS_MODEL_NAME="${EMBEDDINGS_MODEL_NAME:-all-MiniLM-L6-v2}"
    export EMBEDDINGS_MODEL_DIMENSIONS=384

    echo "Starting MCP Registry in the background..."
    cd /app
    source /app/.venv/bin/activate
    uvicorn registry.main:app --host 0.0.0.0 --port 7860 &
    echo "MCP Registry started."

    # Give registry a moment to initialize
    sleep 10
}

case "$MODE" in
    frontend)
        echo "Starting Registry Frontend Setup..."

        # Template paths matching Dockerfile.registry-frontend
        NGINX_TEMPLATE_HTTP_ONLY="/nginx_http_only.conf"
        NGINX_TEMPLATE_HTTP_AND_HTTPS="/nginx_http_and_https.conf"
        NGINX_CONFIG_PATH="/etc/nginx/conf.d/default.conf" 

        install_nginx_template "$NGINX_TEMPLATE_HTTP_ONLY" "$NGINX_TEMPLATE_HTTP_AND_HTTPS" "$NGINX_CONFIG_PATH"

        echo "Starting Nginx..."
        nginx -g 'daemon off;'
        ;;
    backend)
        echo "Starting Registry Service Setup..."

        # Run backend-specific setup steps
        setup_backend

        # Lua + model checks are backend-only
        setup_lua

        # Template paths matching REGISTRY_CONSTANTS in registry/constants.py
        NGINX_TEMPLATE_HTTP_ONLY="/app/docker/nginx_rev_proxy_http_only.conf"
        NGINX_TEMPLATE_HTTP_AND_HTTPS="/app/docker/nginx_rev_proxy_http_and_https.conf"
        NGINX_CONFIG_PATH="/etc/nginx/conf.d/nginx_rev_proxy.conf"

        install_nginx_template "$NGINX_TEMPLATE_HTTP_ONLY" "$NGINX_TEMPLATE_HTTP_AND_HTTPS" "$NGINX_CONFIG_PATH"

        check_model
        substitute_mcp_server_env_tokens
        start_backend_services

        echo "Starting Nginx..."
        nginx

        echo "Registry service fully started. Keeping container alive..."
        # Keep the container running indefinitely
        tail -f /dev/null
        ;;
    *)
        echo "Unknown MODE: $MODE"
        echo "Valid modes: frontend, backend"
        exit 2
        ;;
esac
