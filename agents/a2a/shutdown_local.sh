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
    echo "  - The agents/a2a directory: ./shutdown_local.sh"
    echo "  - The repository root: agents/a2a/shutdown_local.sh"
    exit 1
fi

# Change to agents/a2a directory for the shutdown
cd "$A2A_DIR"

echo "Stopping and removing local agents..."
echo ""

# Determine which compose file to use based on architecture (same logic as deploy_local.sh)
COMPOSE_FILE="docker-compose.local.yml"
SYSTEM_ARCH=$(uname -m)

if [ "$SYSTEM_ARCH" = "arm64" ] || [ "$SYSTEM_ARCH" = "aarch64" ]; then
    COMPOSE_FILE="docker-compose.arm.yml"
    echo "Detected ARM64 architecture"
else
    echo "Detected x86_64 architecture"
fi

echo ""
echo "Using docker-compose file: $COMPOSE_FILE"
echo ""

# Stop and remove containers, networks, and volumes
docker compose -f "$COMPOSE_FILE" down -v

echo ""
echo "✅ Shutdown complete!"
echo "All containers, networks, and volumes have been removed."
echo ""
echo "To restart the agents, run: ./deploy_local.sh"
