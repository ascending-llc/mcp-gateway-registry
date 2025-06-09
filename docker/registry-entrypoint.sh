#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

echo "Starting Registry Service Setup..."

# --- Environment Variable Setup ---
echo "Setting up environment variables..."

# Generate secret key if not provided
if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
fi

ADMIN_USER_VALUE=${ADMIN_USER:-admin}

# Check if ADMIN_PASSWORD is set
if [ -z "$ADMIN_PASSWORD" ]; then
    echo "ERROR: ADMIN_PASSWORD environment variable is not set."
    echo "Please set ADMIN_PASSWORD to a secure value before running the container."
    exit 1
fi

# Create .env file for registry
REGISTRY_ENV_FILE="/app/registry/.env"
echo "Creating Registry .env file..."
echo "SECRET_KEY=${SECRET_KEY}" > "$REGISTRY_ENV_FILE"
echo "ADMIN_USER=${ADMIN_USER_VALUE}" >> "$REGISTRY_ENV_FILE"
echo "ADMIN_PASSWORD=${ADMIN_PASSWORD}" >> "$REGISTRY_ENV_FILE"
echo "Registry .env created."

# --- SSL Certificate Generation ---
SSL_CERT_DIR="/etc/ssl/certs"
SSL_KEY_DIR="/etc/ssl/private"
SSL_CERT_PATH="$SSL_CERT_DIR/fullchain.pem"
SSL_KEY_PATH="$SSL_KEY_DIR/privkey.pem"

echo "Checking for SSL certificates..."
if [ ! -f "$SSL_CERT_PATH" ] || [ ! -f "$SSL_KEY_PATH" ]; then
    echo "Generating self-signed SSL certificate for Nginx..."
    mkdir -p "$SSL_CERT_DIR" "$SSL_KEY_DIR"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$SSL_KEY_PATH" \
        -out "$SSL_CERT_PATH" \
        -subj "/C=US/ST=State/L=City/O=Organization/OU=OrgUnit/CN=localhost"
    echo "SSL certificate generated."
else
    echo "SSL certificates already exist, skipping generation."
fi

# --- Lua Module Setup ---
echo "Setting up Lua support for nginx..."
LUA_SCRIPTS_DIR="/etc/nginx/lua"
mkdir -p "$LUA_SCRIPTS_DIR"

cat > "$LUA_SCRIPTS_DIR/capture_body.lua" << 'EOF'
-- capture_body.lua: Read request body and encode it in X-Body header for auth_request
local cjson = require "cjson"

-- Read the request body
ngx.req.read_body()
local body_data = ngx.req.get_body_data()

if body_data then
    -- Set the X-Body header with the raw body data
    ngx.req.set_header("X-Body", body_data)
    ngx.log(ngx.INFO, "Captured request body (" .. string.len(body_data) .. " bytes) for auth validation")
else
    ngx.log(ngx.INFO, "No request body found")
end
EOF

echo "Lua script created."

# --- Nginx Configuration ---
echo "Copying custom Nginx configuration..."
cp "/app/docker/nginx_rev_proxy.conf" "/etc/nginx/conf.d/nginx_rev_proxy.conf"
echo "Nginx configuration copied."

# --- Model Download ---
EMBEDDINGS_MODEL_NAME="all-MiniLM-L6-v2"
EMBEDDINGS_MODEL_DIR="/app/registry/models/$EMBEDDINGS_MODEL_NAME"

echo "Checking for sentence-transformers model..."
if [ ! -d "$EMBEDDINGS_MODEL_DIR" ] || [ -z "$(ls -A "$EMBEDDINGS_MODEL_DIR")" ]; then
    echo "Downloading sentence-transformers model..."
    mkdir -p "$EMBEDDINGS_MODEL_DIR"
    source "/app/.venv/bin/activate"
    
    # Ensure CA certificates are installed for SSL verification
    echo "Ensuring CA certificates are installed..."
    apt-get update && apt-get install -y ca-certificates && update-ca-certificates
    
    # Try standard download method first
    echo "Downloading model using standard method..."
    if huggingface-cli download sentence-transformers/$EMBEDDINGS_MODEL_NAME --local-dir "$EMBEDDINGS_MODEL_DIR" --quiet; then
        echo "Model downloaded successfully using standard method."
    else
        echo "Standard download failed, trying alternative methods..."
        uv pip install "huggingface-hub[hf_xet]" "hf_xet>=0.1.0" --quiet
        
        if ! huggingface-cli download sentence-transformers/$EMBEDDINGS_MODEL_NAME --local-dir "$EMBEDDINGS_MODEL_DIR" --quiet; then
            echo "Trying download with SSL verification disabled..."
            export CURL_CA_BUNDLE=""
            export SSL_CERT_FILE=""
            huggingface-cli download sentence-transformers/$EMBEDDINGS_MODEL_NAME --local-dir "$EMBEDDINGS_MODEL_DIR" --quiet
        fi
    fi
    echo "Model downloaded to $EMBEDDINGS_MODEL_DIR"
else
    echo "Model already exists, skipping download."
fi

# --- Start Background Services ---
export EMBEDDINGS_MODEL_NAME=$EMBEDDINGS_MODEL_NAME
export EMBEDDINGS_MODEL_DIMENSIONS=384

echo "Starting MCP Registry in the background..."
cd /app/registry
source "/app/.venv/bin/activate"
uvicorn main:app --host 0.0.0.0 --port 7860 &
echo "MCP Registry started."

# Give registry a moment to initialize
sleep 10

echo "Starting Nginx..."
nginx

echo "Registry service fully started. Keeping container alive..."
# Keep the container running indefinitely
tail -f /dev/null 