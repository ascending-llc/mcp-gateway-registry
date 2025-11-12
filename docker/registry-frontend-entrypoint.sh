#!/bin/bash
set -e

echo "Starting Registry Frontend Setup..."

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

NGINX_TEMPLATE_HTTP_ONLY="/nginx_http_only.conf"
NGINX_TEMPLATE_HTTP_AND_HTTPS="/nginx_http_and_https.conf"
NGINX_CONFIG_PATH="/etc/nginx/conf.d/default.conf" 

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

# Run Nginx in the foreground
echo "Starting Nginx..."
nginx -g 'daemon off;'