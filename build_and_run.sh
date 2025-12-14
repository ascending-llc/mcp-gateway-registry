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

# Parse command line arguments
USE_PREBUILT=false
DOCKER_COMPOSE_FILE="docker-compose.yml"

while [[ $# -gt 0 ]]; do
  case $1 in
    --prebuilt)
      USE_PREBUILT=true
      DOCKER_COMPOSE_FILE="docker-compose.prebuilt.yml"
      shift
      ;;
    --help)
      echo "Usage: $0 [--prebuilt] [--help]"
      echo ""
      echo "Options:"
      echo "  --prebuilt    Use pre-built container images (faster startup)"
      echo "  --help        Show this help message"
      echo ""
      echo "Examples:"
      echo "  $0                # Build containers locally (default)"
      echo "  $0 --prebuilt    # Use pre-built images from registry"
      echo ""
      echo "Benefits of --prebuilt:"
      echo "  - Instant deployment (no build time)"
      echo "  - Reduced friction (eliminate build environment issues)"
      echo "  - Consistent experience (all users get the same tested images)"
      echo "  - Bandwidth efficient (pull optimized, compressed images)"
      exit 0
      ;;
    *)
      echo "Unknown option $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

echo "MCP Gateway Registry Deployment"
echo "==============================="

if [ "$USE_PREBUILT" = true ]; then
    log "🚀 Using pre-built container images for fast deployment"
    log "📥 Will pull latest images from container registry during startup..."
else
    log "🔨 Building containers locally (this may take several minutes)"
fi

log "Using Docker Compose file: $DOCKER_COMPOSE_FILE"
log "Starting MCP Gateway Docker Compose deployment script"

# Only check Node.js and build frontend when building locally
if [ "$USE_PREBUILT" = false ]; then
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
else
    log "Skipping frontend build (using pre-built images)"
fi

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

# Check if docker compose is installed
if ! docker compose version &> /dev/null; then
    log "ERROR: docker compose is not available"
    log "Please install Docker Compose v2: https://docs.docker.com/compose/install/"
    exit 1
fi

# Stop and remove existing services if they exist
log "Stopping existing services (if any)..."
docker compose -f "$DOCKER_COMPOSE_FILE" down --remove-orphans || log "No existing services to stop"
log "Existing services stopped"

# Clean up FAISS index files to force registry to recreate them
log "Checking FAISS index files..."
MCPGATEWAY_SERVERS_DIR="${HOME}/mcp-gateway/servers"
FAISS_FILES=("service_index.faiss" "service_index_metadata.json")

# Check if FAISS index files exist
FAISS_EXISTS=false
for file in "${FAISS_FILES[@]}"; do
    file_path="$MCPGATEWAY_SERVERS_DIR/$file"
    if [ -f "$file_path" ]; then
        FAISS_EXISTS=true
        break
    fi
done

if [ "$FAISS_EXISTS" = true ]; then
    echo ""
    echo "╔════════════════════════════════════════════════════════════════════════════╗"
    echo "║                       ⚠️  FAISS INDEX FILES EXIST  ⚠️                       ║"
    echo "╠════════════════════════════════════════════════════════════════════════════╣"
    echo "║                                                                            ║"
    echo "║  Existing FAISS index files were found in:                                ║"
    echo "║  $MCPGATEWAY_SERVERS_DIR/"
    echo "║                                                                            ║"
    echo "║  These files contain your server registry and search index.               ║"
    echo "║  To preserve your registered servers, these files will NOT be deleted.    ║"
    echo "║                                                                            ║"
    echo "║  If you need to regenerate the FAISS index (e.g., after corruption):      ║"
    echo "║  1. Delete the existing files:                                            ║"
    echo "║     rm $MCPGATEWAY_SERVERS_DIR/service_index*"
    echo "║  2. The registry will automatically rebuild the index on startup          ║"
    echo "║                                                                            ║"
    echo "╚════════════════════════════════════════════════════════════════════════════╝"
    echo ""
    log "Keeping existing FAISS index files - NOT deleting"
else
    log "No existing FAISS index files found - will be created on first startup"
fi

# Copy JSON files from registry/servers to ${HOME}/mcp-gateway/servers with environment variable substitution
log "Copying JSON files from registry/servers to $MCPGATEWAY_SERVERS_DIR..."
if [ -d "registry/servers" ]; then
    # Create the target directory if it doesn't exist
    mkdir -p "$MCPGATEWAY_SERVERS_DIR"

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
            envsubst < "$json_file" > "$MCPGATEWAY_SERVERS_DIR/$filename"
        done
        log "JSON files copied successfully with environment variable substitution"

        # Verify atlassian.json was copied
        if [ -f "$MCPGATEWAY_SERVERS_DIR/atlassian.json" ]; then
            log "atlassian.json copied successfully"
        else
            log "WARNING: atlassian.json not found in copied files"
        fi
    else
        log "No JSON files found in registry/servers"
    fi
else
    log "WARNING: registry/servers directory not found"
fi

# Copy seed agent JSON files from cli/examples to ${HOME}/mcp-gateway/agents
AGENTS_DIR="${HOME}/mcp-gateway/agents"
log "Copying seed agent files from cli/examples to $AGENTS_DIR..."
if [ -d "cli/examples" ]; then
    # Create the target directory if it doesn't exist
    mkdir -p "$AGENTS_DIR"

    # Copy all agent JSON files from cli/examples
    if ls cli/examples/*agent*.json 1> /dev/null 2>&1; then
        for json_file in cli/examples/*agent*.json; do
            filename=$(basename "$json_file")
            log "Copying seed agent $filename..."

            # Copy agent file to target directory
            cp "$json_file" "$AGENTS_DIR/$filename"
        done
        log "Seed agent files copied successfully"
    else
        log "No seed agent files found in cli/examples"
    fi
else
    log "WARNING: cli/examples directory not found - seed agents will not be copied"
fi

# Copy scopes.yml to ${HOME}/mcp-gateway/auth_server
AUTH_SERVER_DIR="${HOME}/mcp-gateway/auth_server"
TARGET_SCOPES_FILE="$AUTH_SERVER_DIR/scopes.yml"

log "Checking scopes.yml configuration..."
if [ -f "auth_server/scopes.yml" ]; then
    # Create the target directory if it doesn't exist
    mkdir -p "$AUTH_SERVER_DIR"

    # Check if scopes.yml already exists in the target directory
    if [ -f "$TARGET_SCOPES_FILE" ]; then
        echo ""
        echo "╔════════════════════════════════════════════════════════════════════════════╗"
        echo "║                          ⚠️  SCOPES.YML EXISTS  ⚠️                          ║"
        echo "╠════════════════════════════════════════════════════════════════════════════╣"
        echo "║                                                                            ║"
        echo "║  An existing scopes.yml file was found at:                                ║"
        echo "║  $TARGET_SCOPES_FILE"
        echo "║                                                                            ║"
        echo "║  This file contains your custom groups and server configurations.         ║"
        echo "║  To preserve your settings, this file will NOT be overwritten.            ║"
        echo "║                                                                            ║"
        echo "║  If you need to restore the default scopes.yml from the codebase:         ║"
        echo "║  1. Delete the existing file:                                             ║"
        echo "║     rm $TARGET_SCOPES_FILE"
        echo "║  2. Re-run this script                                                    ║"
        echo "║                                                                            ║"
        echo "╚════════════════════════════════════════════════════════════════════════════╝"
        echo ""
        log "Keeping existing scopes.yml - NOT overwriting"
    else
        # Copy scopes.yml for first-time setup
        cp auth_server/scopes.yml "$AUTH_SERVER_DIR/"
        log "scopes.yml copied successfully to $AUTH_SERVER_DIR (initial setup)"
    fi
else
    log "WARNING: auth_server/scopes.yml not found in codebase"
fi

# Setup SSL certificate directory structure
SSL_DIR="${HOME}/mcp-gateway/ssl"
log "Setting up SSL certificate directory structure..."
mkdir -p "$SSL_DIR/certs"
mkdir -p "$SSL_DIR/private"

# Check if SSL certificates exist and are properly located
if [ -f "$SSL_DIR/certs/fullchain.pem" ] && [ -f "$SSL_DIR/private/privkey.pem" ]; then
    log "SSL certificates found - HTTPS will be enabled"
    chmod 644 "$SSL_DIR/certs/fullchain.pem"
    chmod 600 "$SSL_DIR/private/privkey.pem"
else
    log "No SSL certificates found - HTTP-only mode will be used"
    log "To enable HTTPS, place certificates at:"
    log "  - $SSL_DIR/certs/fullchain.pem"
    log "  - $SSL_DIR/private/privkey.pem"
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

# Determine BUILD_VERSION from git
log "Determining version from git..."
if command -v git &> /dev/null && [ -d .git ]; then
    # Get the current git tag
    GIT_TAG=$(git describe --tags --exact-match 2>/dev/null || echo "")

    if [ -n "$GIT_TAG" ]; then
        # We're on a tagged commit - use just the tag (remove 'v' prefix)
        export BUILD_VERSION="${GIT_TAG#v}"
        log "Building release version: $BUILD_VERSION"
    else
        # Not on a tag - include branch name and commit info
        GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
        GIT_DESCRIBE=$(git describe --tags --always 2>/dev/null || echo "dev")

        # Format: version-branch or describe-branch
        if [[ "$GIT_DESCRIBE" =~ ^[0-9] ]]; then
            # Starts with version number from describe
            export BUILD_VERSION="${GIT_DESCRIBE#v}-${GIT_BRANCH}"
        else
            # No version tags found, use commit hash
            export BUILD_VERSION="${GIT_DESCRIBE}-${GIT_BRANCH}"
        fi

        log "Building development version: $BUILD_VERSION"
    fi
else
    export BUILD_VERSION="1.0.0-dev"
    log "Git not available, using default version: $BUILD_VERSION"
fi

# Build or pull Docker images
if [ "$USE_PREBUILT" = true ]; then
    log "Pulling pre-built Docker images..."
    docker compose -f "$DOCKER_COMPOSE_FILE" pull || handle_error "Docker Compose pull failed"
    log "Pre-built Docker images pulled successfully"
else
    log "Building Docker images with optimization..."
    # Enable BuildKit for better caching and parallel builds
    export DOCKER_BUILDKIT=1
    export COMPOSE_DOCKER_CLI_BUILD=1

    # Build with parallel jobs and build cache
    docker compose -f "$DOCKER_COMPOSE_FILE" build --parallel --progress=auto || handle_error "Docker Compose build failed"
    log "Docker images built successfully with optimization"
fi

# Start metrics service first to generate API keys
log "Starting metrics service first..."
docker compose -f "$DOCKER_COMPOSE_FILE" up -d metrics-service || handle_error "Failed to start metrics service"

# Wait for metrics service to be ready
log "Waiting for metrics service to be ready..."
max_retries=30
retry_count=0
while [ $retry_count -lt $max_retries ]; do
    if curl -f http://localhost:8890/health &>/dev/null; then
        log "Metrics service is ready"
        break
    fi
    sleep 2
    retry_count=$((retry_count + 1))
    log "Waiting for metrics service... ($retry_count/$max_retries)"
done

if [ $retry_count -eq $max_retries ]; then
    handle_error "Metrics service did not become ready within expected time"
fi

# Generate dynamic pre-shared tokens for metrics authentication
log "Setting up dynamic pre-shared tokens for services..."

# Get all services from docker-compose that might need metrics (exclude monitoring services)
METRICS_SERVICES=$(docker compose config --services 2>/dev/null | grep -v -E "(prometheus|grafana|metrics-db)" | sort | uniq)

if [ -z "$METRICS_SERVICES" ]; then
    log "WARNING: No services found for metrics configuration"
else
    log "Found services for metrics: $(echo $METRICS_SERVICES | tr '\n' ' ')"
fi

# Check if tokens already exist in .env
source .env 2>/dev/null || true

# Generate tokens for each service dynamically
for service in $METRICS_SERVICES; do
    # Convert service name to environment variable format
    # auth-server -> METRICS_API_KEY_AUTH_SERVER
    # metrics-service -> METRICS_API_KEY_METRICS_SERVICE (will be skipped as it's the metrics service itself)
    ENV_VAR_NAME="METRICS_API_KEY_$(echo "$service" | tr '[:lower:]-' '[:upper:]_')"
    
    # Skip the metrics service itself and non-metrics services
    if [ "$service" = "metrics-service" ] || [ "$service" = "prometheus" ] || [ "$service" = "grafana" ]; then
        continue
    fi
    
    # Get current value
    CURRENT_VALUE=$(eval echo "\$$ENV_VAR_NAME")
    
    # Generate token only if it doesn't exist or is empty
    if [ -z "$CURRENT_VALUE" ] || [ "$CURRENT_VALUE" = "" ]; then
        NEW_TOKEN="mcp_metrics_$(openssl rand -hex 16)"
        
        # Remove any existing line for this variable
        sed -i "/^$ENV_VAR_NAME=/d" .env 2>/dev/null || true
        
        # Add new token
        echo "$ENV_VAR_NAME=$NEW_TOKEN" >> .env
        log "Generated new $service token: ${NEW_TOKEN:0:20}..."
    else
        log "Using existing $service token: ${CURRENT_VALUE:0:20}..."
    fi
done

log "Dynamic metrics API tokens configured successfully"

# Now start all other services with the API keys in environment
log "Starting remaining Docker Compose services..."
docker compose -f "$DOCKER_COMPOSE_FILE" up -d || handle_error "Failed to start remaining services"

# Wait a moment for services to initialize
log "Waiting for services to initialize..."
sleep 10

# Check service status
log "Checking service status..."
docker compose -f "$DOCKER_COMPOSE_FILE" ps

# Verify key services are running
log "Verifying services are healthy..."

# Check registry service
if curl -f http://localhost:7860/health &>/dev/null; then
    log "Registry service is healthy"
else
    log "WARNING: Registry service may still be starting up..."
fi

# Check auth service
if curl -f http://localhost:8888/health &>/dev/null; then
    log "Auth service is healthy"
else
    log "WARNING: Auth service may still be starting up..."
fi

# Check nginx is responding
if curl -f http://localhost:80 &>/dev/null || curl -k -f https://localhost:443 &>/dev/null; then
    log "Nginx is responding"
else
    log "WARNING: Nginx may still be starting up..."
fi

# Verify FAISS index creation
log "Verifying FAISS index creation..."
sleep 5  # Give registry service time to create the index

if [ -f "$MCPGATEWAY_SERVERS_DIR/service_index.faiss" ]; then
    log "FAISS index created successfully at $MCPGATEWAY_SERVERS_DIR/service_index.faiss"
    
    # Check if metadata file also exists
    if [ -f "$MCPGATEWAY_SERVERS_DIR/service_index_metadata.json" ]; then
        log "FAISS index metadata created successfully"
    else
        log "WARNING: FAISS index metadata file not found"
    fi
else
    log "WARNING: FAISS index not yet created. The registry service will create it on first access."
fi

# Verify server list includes Atlassian
log "Verifying server list..."
if [ -f "$MCPGATEWAY_SERVERS_DIR/atlassian.json" ]; then
    log "Atlassian server configuration present"
fi

# List all available server JSON files
log "Available server configurations in $MCPGATEWAY_SERVERS_DIR:"
if ls "$MCPGATEWAY_SERVERS_DIR"/*.json 2>/dev/null | head -n 10; then
    TOTAL_SERVERS=$(ls "$MCPGATEWAY_SERVERS_DIR"/*.json 2>/dev/null | wc -l)
    log "Total server configurations: $TOTAL_SERVERS"
else
    log "WARNING: No server configurations found in $MCPGATEWAY_SERVERS_DIR"
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
log "To view logs for all services: docker compose -f $DOCKER_COMPOSE_FILE logs -f"
log "To view logs for a specific service: docker compose -f $DOCKER_COMPOSE_FILE logs -f <service-name>"
log "To stop services: docker compose -f $DOCKER_COMPOSE_FILE down"
log ""

# Ask if user wants to follow logs
read -p "Do you want to follow the logs? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log "Following container logs (press Ctrl+C to stop following logs without stopping the services):"
    echo "---------- DOCKER COMPOSE LOGS ----------"
    docker compose -f "$DOCKER_COMPOSE_FILE" logs -f
else
    log "Services are running in the background. Use 'docker compose -f $DOCKER_COMPOSE_FILE logs -f' to view logs."
fi