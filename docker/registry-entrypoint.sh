#!/bin/bash
set -e

# Unified entrypoint for registry frontend and backend.
# Usage:
#   /entrypoint.sh frontend
#   /entrypoint.sh backend

MODE="${1}"

SSL_CERT_PATH="${SSL_CERT_PATH:-/etc/ssl/certs/fullchain.pem}"
SSL_KEY_PATH="${SSL_KEY_PATH:-/etc/ssl/private/privkey.pem}"

install_nginx_config() {
    HTTP_ONLY_TEMPLATE_PATH="${1:?}"
    HTTP_AND_HTTPS_TEMPLATE_PATH="${2:?}"
    DEST_PATH="${3:?}"

    # NGINX_BASE_PATH defaults to empty string (root path /)
    export NGINX_BASE_PATH="${NGINX_BASE_PATH:-}"
    echo "NGINX_BASE_PATH configured as: '${NGINX_BASE_PATH:-/}'"

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
        envsubst '${NGINX_BASE_PATH}' < "$HTTP_ONLY_TEMPLATE_PATH" > "$DEST_PATH"
        echo "HTTP-only Nginx configuration installed."
    else
        echo "Using HTTP + HTTPS Nginx configuration (SSL certificates found)..."
        envsubst '${NGINX_BASE_PATH}' < "$HTTP_AND_HTTPS_TEMPLATE_PATH" > "$DEST_PATH"
        echo "HTTP + HTTPS Nginx configuration installed."
    fi
}

case "$MODE" in
    frontend)
        echo "Starting Registry Frontend Setup..."

        # Config paths matching Dockerfile.registry-frontend
        NGINX_HTTP_ONLY_CONF="/nginx_http_only.conf"
        NGINX_HTTP_AND_HTTPS_CONF="/nginx_http_and_https.conf"
        NGINX_CONFIG_PATH="/etc/nginx/conf.d/default.conf" 

        install_nginx_config "$NGINX_HTTP_ONLY_CONF" "$NGINX_HTTP_AND_HTTPS_CONF" "$NGINX_CONFIG_PATH"

        echo "Starting Nginx..."
        nginx -g 'daemon off;'
        ;;
    backend)
        echo "Starting MCP Registry Service..."

        # Validate required environment variables
        if [ -z "${SECRET_KEY:-}" ]; then
            echo "ERROR: SECRET_KEY environment variable is not set."
            echo "Please set SECRET_KEY to a secure value before running the container."
            exit 1
        fi

        if [ -z "${ADMIN_PASSWORD:-}" ]; then
            echo "ERROR: ADMIN_PASSWORD environment variable is not set."
            echo "Please set ADMIN_PASSWORD to a secure value before running the container."
            exit 1
        fi

        if [ -z "${ADMIN_USER:-}" ]; then
            echo "ERROR: ADMIN_USER environment variable is not set."
            echo "Please set ADMIN_USER before running the container."
            exit 1
        fi

        # Check for embeddings model only in embedded mode
        if [ "${TOOL_DISCOVERY_MODE}" = "embedded" ]; then
            EMBEDDINGS_MODEL_NAME="${EMBEDDINGS_MODEL_NAME:-all-MiniLM-L6-v2}"
            EMBEDDINGS_MODEL_DIR="/app/registry/models/$EMBEDDINGS_MODEL_NAME"

            echo "Checking for sentence-transformers model (embedded mode)..."
            if [ ! -d "$EMBEDDINGS_MODEL_DIR" ] || [ -z "$(ls -A "$EMBEDDINGS_MODEL_DIR" 2>/dev/null)" ]; then
                echo "=========================================="
                echo "WARNING: Embeddings model not found!"
                echo "=========================================="
                echo ""
                echo "The registry requires the sentence-transformers model to function properly in embedded mode."
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
        else
            echo "Running in external tool discovery mode - skipping embeddings model check"
        fi

        # Start the registry
        echo "Starting MCP Registry on port 7860..."
        cd /app
        exec uvicorn registry.main:app --host 0.0.0.0 --port 7860
        ;;
    *)
        echo "Unknown MODE: $MODE"
        echo "Valid modes: frontend, backend"
        exit 2
        ;;
esac
