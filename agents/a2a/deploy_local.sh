#!/bin/bash

set -e

# Find the agents/a2a directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
A2A_DIR="$SCRIPT_DIR"

# If running from repo root, adjust the path
if [ ! -f "$A2A_DIR/docker-compose.local.yml" ]; then
    A2A_DIR="$SCRIPT_DIR/agents/a2a"
fi

# Verify we found the agents/a2a directory
if [ ! -f "$A2A_DIR/docker-compose.local.yml" ]; then
    echo "❌ Error: docker-compose.local.yml not found"
    echo ""
    echo "This script must be run from either:"
    echo "  - The agents/a2a directory: ./deploy_local.sh"
    echo "  - The repository root: agents/a2a/deploy_local.sh"
    exit 1
fi

# Change to agents/a2a directory for the deployment
cd "$A2A_DIR"

# Parse command line arguments
COMPOSE_FILE="docker-compose.local.yml"
ARCHITECTURE=""
TARGETPLATFORM=""

for arg in "$@"; do
    case "$arg" in
        --arm64)
            COMPOSE_FILE="docker-compose.arm.yml"
            ARCHITECTURE="ARM64"
            TARGETPLATFORM="linux/arm64"
            ;;
        --x86_64)
            COMPOSE_FILE="docker-compose.local.yml"
            ARCHITECTURE="x86_64"
            TARGETPLATFORM="linux/amd64"
            ;;
        --help)
            echo "Usage: ./deploy_local.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --arm64     Use ARM64 docker-compose file (for Apple Silicon Macs)"
            echo "  --x86_64    Use x86_64 docker-compose file (default for Intel/AMD)"
            echo "  --help      Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./deploy_local.sh                    # Auto-detect architecture"
            echo "  ./deploy_local.sh --arm64            # Force ARM64 (Apple Silicon)"
            echo "  ./deploy_local.sh --x86_64           # Force x86_64 (Intel/AMD)"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Auto-detect architecture if not specified
if [ -z "$ARCHITECTURE" ]; then
    SYSTEM_ARCH=$(uname -m)
    if [ "$SYSTEM_ARCH" = "arm64" ] || [ "$SYSTEM_ARCH" = "aarch64" ]; then
        COMPOSE_FILE="docker-compose.arm.yml"
        ARCHITECTURE="ARM64 (auto-detected)"
        TARGETPLATFORM="linux/arm64"
    else
        COMPOSE_FILE="docker-compose.local.yml"
        ARCHITECTURE="x86_64 (auto-detected)"
        TARGETPLATFORM="linux/amd64"
    fi
fi

# Export TARGETPLATFORM for docker-compose to use
export TARGETPLATFORM

echo "Deploying agents for: $ARCHITECTURE"
echo ""

echo "Validating AWS credentials..."

# Check if AWS credentials are available through the credential chain
# This checks: explicit env vars, AWS_PROFILE, EC2 IAM role, ~/.aws/credentials, etc.
IDENTITY_OUTPUT=$(aws sts get-caller-identity 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ Error: Unable to retrieve AWS credentials"
    echo ""
    echo "AWS credentials not found. Please provide credentials using one of these methods:"
    echo ""
    echo "1. AWS Profile (recommended):"
    echo "   export AWS_PROFILE=your_profile_name"
    echo ""
    echo "2. EC2 IAM Role (automatic when running on EC2 instance)"
    echo ""
    echo "Debug info:"
    echo "$IDENTITY_OUTPUT"
    exit 1
fi

# Extract and display credential information
ACCOUNT_ID=$(echo "$IDENTITY_OUTPUT" | grep -o '"Account": "[^"]*"' | cut -d'"' -f4)
ARN=$(echo "$IDENTITY_OUTPUT" | grep -o '"Arn": "[^"]*"' | cut -d'"' -f4)

echo "✅ AWS credentials validated"
echo "   Account ID: $ACCOUNT_ID"
echo "   Principal: $ARN"

echo "Stopping existing containers and removing volumes..."
docker compose -f "$COMPOSE_FILE" down -v

echo "Building images..."

# Copy dependency files to .tmp directories for build
echo "Copying dependency files to .tmp directories..."
mkdir -p src/flight-booking-agent/.tmp src/travel-assistant-agent/.tmp
cp pyproject.toml uv.lock src/flight-booking-agent/.tmp/
cp pyproject.toml uv.lock src/travel-assistant-agent/.tmp/

# Build images
docker compose -f "$COMPOSE_FILE" build --no-cache

# Clean up .tmp directories
echo "Cleaning up .tmp directories..."
rm -rf src/flight-booking-agent/.tmp
rm -rf src/travel-assistant-agent/.tmp

echo "Starting containers..."
docker compose -f "$COMPOSE_FILE" up -d

echo "✅ Deployment complete!"
echo ""
echo "Waiting for containers to be ready and starting to display live logs..."
echo "Press Ctrl+C to stop viewing logs (containers will continue running)"
echo ""

# Wait a moment for containers to start
sleep 2

# Display live logs
docker compose -f "$COMPOSE_FILE" logs -f
