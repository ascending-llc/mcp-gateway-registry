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

# --- SSL Certificate Check ---
# These paths match REGISTRY_CONSTANTS.SSL_CERT_PATH and SSL_KEY_PATH in registry/constants.py
SSL_CERT_PATH="/etc/ssl/certs/fullchain.pem"
SSL_KEY_PATH="/etc/ssl/private/privkey.pem"

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
echo "Preparing Nginx configuration..."

# Template paths matching REGISTRY_CONSTANTS in registry/constants.py
NGINX_TEMPLATE_HTTP_ONLY="/app/docker/nginx_rev_proxy_http_only.conf"
NGINX_TEMPLATE_HTTP_AND_HTTPS="/app/docker/nginx_rev_proxy_http_and_https.conf"
NGINX_CONFIG_PATH="/etc/nginx/conf.d/nginx_rev_proxy.conf"

# Check if SSL certificates exist and use appropriate config
if [ ! -f "$SSL_CERT_PATH" ] || [ ! -f "$SSL_KEY_PATH" ]; then
    echo "Using HTTP-only Nginx configuration (no SSL certificates)..."
    cp "$NGINX_TEMPLATE_HTTP_ONLY" "$NGINX_CONFIG_PATH"
    echo "HTTP-only Nginx configuration installed."
else
    echo "Using HTTP + HTTPS Nginx configuration (SSL certificates found)..."
    cp "$NGINX_TEMPLATE_HTTP_AND_HTTPS" "$NGINX_CONFIG_PATH"
    echo "HTTP + HTTPS Nginx configuration installed."
fi

# --- Embeddings Configuration ---
# Get embeddings configuration from environment or use defaults
EMBEDDINGS_PROVIDER="${EMBEDDINGS_PROVIDER:-sentence-transformers}"
EMBEDDINGS_MODEL_NAME="${EMBEDDINGS_MODEL_NAME:-all-MiniLM-L6-v2}"
EMBEDDINGS_MODEL_DIMENSIONS="${EMBEDDINGS_MODEL_DIMENSIONS:-384}"

echo "Embeddings Configuration:"
echo "  Provider: $EMBEDDINGS_PROVIDER"
echo "  Model: $EMBEDDINGS_MODEL_NAME"
echo "  Dimensions: $EMBEDDINGS_MODEL_DIMENSIONS"

# Only check for local model if using sentence-transformers
if [ "$EMBEDDINGS_PROVIDER" = "sentence-transformers" ]; then
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
elif [ "$EMBEDDINGS_PROVIDER" = "litellm" ]; then
    echo "Using LiteLLM provider - no local model download required"
    echo "Model: $EMBEDDINGS_MODEL_NAME"
    if [[ "$EMBEDDINGS_MODEL_NAME" == bedrock/* ]]; then
        echo "Bedrock model will use AWS credential chain for authentication"
    elif [ ! -z "$EMBEDDINGS_API_KEY" ]; then
        echo "API key configured for cloud embeddings"
    else
        echo "WARNING: No EMBEDDINGS_API_KEY set for cloud provider"
    fi
fi

# --- Environment Variable Substitution for MCP Server Auth Tokens ---
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

# --- Start Background Services ---
# Export embeddings configuration for the registry service
export EMBEDDINGS_PROVIDER=$EMBEDDINGS_PROVIDER
export EMBEDDINGS_MODEL_NAME=$EMBEDDINGS_MODEL_NAME
export EMBEDDINGS_MODEL_DIMENSIONS=$EMBEDDINGS_MODEL_DIMENSIONS

echo "Starting MCP Registry in the background..."
cd /app
source /app/.venv/bin/activate
uvicorn registry.main:app --host 0.0.0.0 --port 7860 &
echo "MCP Registry started."

# Wait for nginx config to be generated (check that placeholders are replaced)
echo "Waiting for nginx configuration to be generated..."
WAIT_TIME=0
MAX_WAIT=120
while [ $WAIT_TIME -lt $MAX_WAIT ]; do
    if [ -f "/etc/nginx/conf.d/nginx_rev_proxy.conf" ]; then
        # Check if placeholders have been replaced
        if ! grep -q "{{EC2_PUBLIC_DNS}}" "/etc/nginx/conf.d/nginx_rev_proxy.conf" && \
           ! grep -q "{{LOCATION_BLOCKS}}" "/etc/nginx/conf.d/nginx_rev_proxy.conf"; then
            echo "Nginx configuration generated successfully"
            break
        fi
    fi
    sleep 2
    WAIT_TIME=$((WAIT_TIME + 2))
done

if [ $WAIT_TIME -ge $MAX_WAIT ]; then
    echo "WARNING: Timeout waiting for nginx configuration. Starting nginx anyway..."
fi

echo "Starting Nginx..."
nginx

echo "Registry service fully started. Keeping container alive..."
# Keep the container running indefinitely
tail -f /dev/null 
