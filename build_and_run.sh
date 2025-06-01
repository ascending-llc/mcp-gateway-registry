#!/bin/bash

# Enable error handling
set -e

# Function for logging with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function for error handling
handle_error() {
    log "ERROR: $1"
    exit 1
}

log "Starting MCP Gateway deployment script"

# Check if .env.docker file exists
if [ ! -f .env.docker ]; then
    log "ERROR: .env.docker file not found"
    log "Please create a .env.docker file by copying .env.docker.template and filling in your values:"
    log "cp .env.docker.template .env.docker"
    log "Then edit .env.docker with your configuration values"
    exit 1
fi

log "Found .env.docker file"

# Stop and remove existing container if it exists
log "Stopping and removing existing container (if any)..."
if docker ps -a | grep -q mcp-gateway-container; then
    docker stop mcp-gateway-container || log "Container was not running"
    docker rm mcp-gateway-container || handle_error "Failed to remove container"
    log "Container stopped and removed successfully"
else
    log "No existing container found"
fi

# Build the Docker image
log "Building Docker image..."
docker build -t mcp-gateway . || handle_error "Docker build failed"
log "Docker image built successfully"

# Generate a random SECRET_KEY if not already in .env.docker
if ! grep -q "SECRET_KEY=" .env.docker; then
    log "Generating SECRET_KEY..."
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))') || handle_error "Failed to generate SECRET_KEY"
    echo "SECRET_KEY=$SECRET_KEY" >> .env.docker
    log "SECRET_KEY added to .env.docker"
fi

# Run the Docker container
log "Starting Docker container..."
docker run -d \
    -p 80:80 \
    -p 443:443 \
    -p 7860:7860 \
    -p 8888:8888 \
    --env-file .env.docker \
    -v /path/to/certs:/etc/ssl/certs \
    -v /path/to/private:/etc/ssl/private \
    -v /var/log/mcp-gateway:/app/logs \
    -v /opt/mcp-gateway/servers:/app/registry/servers \
    --name mcp-gateway-container \
    mcp-gateway || handle_error "Failed to start container"

# Keep .env.docker file for future runs
log "Keeping .env.docker file for future runs"

# Verify container is running
if docker ps | grep -q mcp-gateway-container; then
    log "Container started successfully"
    log "MCP Gateway is now running"
    docker ps | grep mcp-gateway-container
else
    handle_error "Container failed to start properly"
fi

log "Deployment completed successfully"

# Follow container logs
log "Following container logs (press Ctrl+C to stop following logs without stopping the container):"
echo "---------- CONTAINER LOGS ----------"
docker logs -f mcp-gateway-container