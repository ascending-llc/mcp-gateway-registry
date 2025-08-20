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

# Update auth tokens from .oauth-tokens files
update_auth_tokens() {
    log "Updating auth tokens from .oauth-tokens directory..."
    
    OAUTH_TOKENS_DIR="$PWD/.oauth-tokens"
    if [ ! -d "$OAUTH_TOKENS_DIR" ]; then
        log "No .oauth-tokens directory found at $OAUTH_TOKENS_DIR - skipping token updates"
        return
    fi
    
    # Create backup of .env (overwrite previous backup)
    cp .env .env.backup
    
    # Process each egress.json file
    for egress_file in "$OAUTH_TOKENS_DIR"/*egress.json; do
        if [ ! -f "$egress_file" ]; then
            continue
        fi
        
        # Extract server name from filename (remove egress.json suffix)
        filename=$(basename "$egress_file")
        server_name=$(echo "$filename" | sed 's/egress\.json$//')
        
        # Map specific server names to expected environment variable names
        case "$server_name" in
            "atlassian-atlassian-")
                env_var_name="ATLASSIAN_AUTH_TOKEN"
                ;;
            "bedrock-agentcore-sre-gateway-")
                env_var_name="SRE_GATEWAY_AUTH_TOKEN"
                ;;
            *)
                # Generic conversion: convert to uppercase and replace hyphens with underscores
                env_var_name=$(echo "${server_name}" | sed 's/-$//' | tr '[:lower:]' '[:upper:]' | tr '-' '_')_AUTH_TOKEN
                ;;
        esac
        
        # Extract access_token from JSON file
        if command -v jq &> /dev/null; then
            access_token=$(jq -r '.access_token // empty' "$egress_file" 2>/dev/null)
        else
            # Fallback method without jq
            access_token=$(grep -o '"access_token"[[:space:]]*:[[:space:]]*"[^"]*"' "$egress_file" | sed 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
        fi
        
        if [ -n "$access_token" ] && [ "$access_token" != "null" ]; then
            log "Found token for $server_name -> $env_var_name"
            
            # Remove existing token line if present
            sed -i "/^${env_var_name}=/d" .env
            
            # Add new token
            echo "${env_var_name}=\"${access_token}\"" >> .env
            log "✓ Updated $env_var_name in .env"
        else
            log "⚠ No valid access_token found in $egress_file"
        fi
    done
}

log "Starting MCP Gateway Docker Compose deployment script"

# Check if Node.js and npm are installed
if ! command -v node &> /dev/null; then
    log "ERROR: Node.js is not installed"
    log "Please install Node.js (version 16 or higher): https://nodejs.org/"
    exit 1
fi

if ! command -v npm &> /dev/null; then
    log "ERROR: npm is not installed"
    log "Please install npm (usually comes with Node.js): https://nodejs.org/"
    exit 1
fi

# Check Node.js version
NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 16 ]; then
    log "ERROR: Node.js version $NODE_VERSION is too old. Please install Node.js 16 or higher."
    exit 1
fi

log "Node.js $(node -v) and npm $(npm -v) are available"

# Build the React frontend
log "Building React frontend..."
if [ ! -d "frontend" ]; then
    handle_error "Frontend directory not found"
fi

cd frontend

# Install frontend dependencies
log "Installing frontend dependencies..."
npm install || handle_error "Failed to install frontend dependencies"

# Build the React application
log "Building React application for production..."
npm run build || handle_error "Failed to build React application"

log "Frontend build completed successfully"
cd ..

# Check if .env file exists
if [ ! -f .env ]; then
    log "ERROR: .env file not found"
    log "Please create a .env file with your configuration values:"
    log "Example .env file:"
    log "SECRET_KEY=your_secret_key_here"
    log "ADMIN_USER=admin"
    log "ADMIN_PASSWORD=your_secure_password"
    log "# For Financial Info server API keys, see servers/fininfo/README_SECRETS.md"
    exit 1
fi

log "Found .env file"

# Update auth tokens from .oauth-tokens files
update_auth_tokens

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    log "ERROR: docker-compose is not installed"
    log "Please install docker-compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# Stop and remove existing services if they exist
log "Stopping existing services (if any)..."
docker-compose down --remove-orphans || log "No existing services to stop"
log "Existing services stopped"

# Clean up FAISS index files to force registry to recreate them
log "Cleaning up FAISS index files..."
MCPGATEWAY_SERVERS_DIR="/opt/mcp-gateway/servers"
FAISS_FILES=("service_index.faiss" "service_index_metadata.json")

for file in "${FAISS_FILES[@]}"; do
    file_path="$MCPGATEWAY_SERVERS_DIR/$file"
    if [ -f "$file_path" ]; then
        sudo rm -f "$file_path"
        log "Deleted $file_path"
    else
        log "$file not found (already clean)"
    fi
done
log "FAISS index cleanup completed"

# Copy JSON files from registry/servers to /opt/mcp-gateway/servers with environment variable substitution
log "Copying JSON files from registry/servers to $MCPGATEWAY_SERVERS_DIR..."
if [ -d "registry/servers" ]; then
    # Create the target directory if it doesn't exist
    sudo mkdir -p "$MCPGATEWAY_SERVERS_DIR"
    
    # Copy all JSON files with environment variable substitution
    if ls registry/servers/*.json 1> /dev/null 2>&1; then
        # Export all environment variables from .env file for envsubst
        set -a  # Automatically export all variables
        source .env
        set +a  # Turn off automatic export
        
        for json_file in registry/servers/*.json; do
            filename=$(basename "$json_file")
            log "Processing $filename with environment variable substitution..."
            
            # Use envsubst to substitute environment variables, then copy to target
            envsubst < "$json_file" | sudo tee "$MCPGATEWAY_SERVERS_DIR/$filename" > /dev/null
        done
        log "JSON files copied successfully with environment variable substitution"
        
        # Verify atlassian.json was copied
        if [ -f "$MCPGATEWAY_SERVERS_DIR/atlassian.json" ]; then
            log "✓ atlassian.json copied successfully"
        else
            log "⚠ atlassian.json not found in copied files"
        fi
    else
        log "No JSON files found in registry/servers"
    fi
else
    log "WARNING: registry/servers directory not found"
fi

# Copy scopes.yml to /opt/mcp-gateway/auth_server
AUTH_SERVER_DIR="/opt/mcp-gateway/auth_server"
log "Copying scopes.yml to $AUTH_SERVER_DIR..."
if [ -f "auth_server/scopes.yml" ]; then
    # Create the target directory if it doesn't exist
    sudo mkdir -p "$AUTH_SERVER_DIR"
    
    # Copy scopes.yml
    sudo cp auth_server/scopes.yml "$AUTH_SERVER_DIR/"
    log "✓ scopes.yml copied successfully to $AUTH_SERVER_DIR"
else
    log "WARNING: auth_server/scopes.yml not found"
fi

# Generate a random SECRET_KEY if not already in .env
if ! grep -q "SECRET_KEY=" .env || grep -q "SECRET_KEY=$" .env || grep -q "SECRET_KEY=\"\"" .env; then
    log "Generating SECRET_KEY..."
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))') || handle_error "Failed to generate SECRET_KEY"
    
    # Remove any existing empty SECRET_KEY line
    sed -i '/^SECRET_KEY=$/d' .env 2>/dev/null || true
    sed -i '/^SECRET_KEY=""$/d' .env 2>/dev/null || true
    
    # Add new SECRET_KEY
    echo "SECRET_KEY=$SECRET_KEY" >> .env
    log "SECRET_KEY added to .env"
else
    log "SECRET_KEY already exists in .env"
fi

# Validate required environment variables
log "Validating required environment variables..."
source .env

if [ -z "$ADMIN_PASSWORD" ] || [ "$ADMIN_PASSWORD" = "your_secure_password" ]; then
    log "ERROR: ADMIN_PASSWORD must be set to a secure value in .env file"
    exit 1
fi

# Build the Docker images
log "Building Docker images..."
docker-compose build || handle_error "Docker Compose build failed"
log "Docker images built successfully"

# Start the services
log "Starting Docker Compose services..."
docker-compose up -d || handle_error "Failed to start services"

# Wait a moment for services to initialize
log "Waiting for services to initialize..."
sleep 10

# Check service status
log "Checking service status..."
docker-compose ps

# Verify key services are running
log "Verifying services are healthy..."

# Check registry service
if curl -f http://localhost:7860/health &>/dev/null; then
    log "✓ Registry service is healthy"
else
    log "⚠ Registry service may still be starting up..."
fi

# Check auth service
if curl -f http://localhost:8888/health &>/dev/null; then
    log "✓ Auth service is healthy"
else
    log "⚠ Auth service may still be starting up..."
fi

# Check nginx is responding
if curl -f http://localhost:80 &>/dev/null || curl -k -f https://localhost:443 &>/dev/null; then
    log "✓ Nginx is responding"
else
    log "⚠ Nginx may still be starting up..."
fi

# Verify FAISS index creation
log "Verifying FAISS index creation..."
sleep 5  # Give registry service time to create the index

if [ -f "$MCPGATEWAY_SERVERS_DIR/service_index.faiss" ]; then
    log "✓ FAISS index created successfully at $MCPGATEWAY_SERVERS_DIR/service_index.faiss"
    
    # Check if metadata file also exists
    if [ -f "$MCPGATEWAY_SERVERS_DIR/service_index_metadata.json" ]; then
        log "✓ FAISS index metadata created successfully"
    else
        log "⚠ FAISS index metadata file not found"
    fi
else
    log "⚠ FAISS index not yet created. The registry service will create it on first access."
fi

# Verify server list includes Atlassian
log "Verifying server list..."
if [ -f "$MCPGATEWAY_SERVERS_DIR/atlassian.json" ]; then
    log "✓ Atlassian server configuration present"
fi

# List all available server JSON files
log "Available server configurations in $MCPGATEWAY_SERVERS_DIR:"
if ls "$MCPGATEWAY_SERVERS_DIR"/*.json 2>/dev/null | head -n 10; then
    TOTAL_SERVERS=$(ls "$MCPGATEWAY_SERVERS_DIR"/*.json 2>/dev/null | wc -l)
    log "Total server configurations: $TOTAL_SERVERS"
else
    log "⚠ No server configurations found in $MCPGATEWAY_SERVERS_DIR"
fi

log "Deployment completed successfully"
log ""
log "Services are available at:"
log "  - Main interface: http://localhost or https://localhost"
log "  - Registry API: http://localhost:7860"
log "  - Auth service: http://localhost:8888"
log "  - Current Time MCP: http://localhost:8000"
log "  - Financial Info MCP: http://localhost:8001"
log "  - Real Server Fake Tools MCP: http://localhost:8002"
log "  - MCP Gateway MCP: http://localhost:8003"
log "  - Atlassian MCP: http://localhost:8005"
log ""
log "To view logs for all services: docker-compose logs -f"
log "To view logs for a specific service: docker-compose logs -f <service-name>"
log "To stop services: docker-compose down"
log ""

# Ask if user wants to follow logs
read -p "Do you want to follow the logs? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log "Following container logs (press Ctrl+C to stop following logs without stopping the services):"
    echo "---------- DOCKER COMPOSE LOGS ----------"
    docker-compose logs -f
else
    log "Services are running in the background. Use 'docker-compose logs -f' to view logs."
fi