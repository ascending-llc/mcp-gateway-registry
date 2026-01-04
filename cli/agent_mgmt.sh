#!/bin/bash

# DEPRECATED: This script is deprecated in favor of the Registry Management API
# Use: uv run python api/registry_management.py OR cli/registry_cli_wrapper.py
# See: api/README.md for documentation
#
# Agent Management Script for MCP Gateway Registry
# Usage: ./cli/agent_mgmt.sh {register|list|get|test|test-all} [args...]

echo "WARNING: This script is DEPRECATED. Please use the Registry Management API instead:"
echo "  uv run python api/registry_management.py agent-register --help"
echo "  uv run python api/registry_management.py agent-list --help"
echo "See api/README.md for full documentation."
echo ""

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment variables from .env file if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Default values
BASE_URL="${BASE_URL:-http://localhost}"  # Goes through nginx (port 80), not direct :7860
TOKEN_FILE="${TOKEN_FILE:-.oauth-tokens/ingress.json}"
DEBUG="${DEBUG:-false}"

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

show_usage() {
    cat << EOF
Agent Management Script for MCP Gateway Registry

Usage: $0 {command} [options]

Commands:
  register            Register agent from JSON file
  list                List all agents
  get                 Get agent details
  update              Update agent from JSON file
  delete              Delete agent
  toggle              Enable/disable agent
  test                Test agent accessibility
  test-all            Test all agents
  search              Search agents using semantic query

Options:
  --base-url URL        Base URL for API (default: $BASE_URL)
  --token-file FILE     Path to token JSON file (default: $TOKEN_FILE)
  --debug               Enable debug logging

Examples:
  # Register an agent from JSON file
  $0 register cli/examples/test_code_reviewer_agent.json

  # List all agents
  $0 list

  # Get agent details
  $0 get /test-reviewer

  # Update an agent
  $0 update /test-reviewer cli/examples/updated_agent.json

  # Enable an agent
  $0 toggle /test-reviewer true

  # Disable an agent
  $0 toggle /test-reviewer false

  # Delete an agent
  $0 delete /test-reviewer

  # Test agent accessibility
  $0 test /test-reviewer

  # Test all agents
  $0 test-all

  # Search agents with semantic query
  $0 search "code review tool"

Prerequisites:
  Ensure the registry and nginx services are running:
    1. Registry service (port 7860)
    2. Nginx reverse proxy (port 80)

  Docker setup:
    docker-compose up -d

For more information, run:
  uv run python cli/agent_mgmt.py --help
  cat cli/examples/README.md
EOF
}

# Check if no arguments provided
if [ $# -eq 0 ]; then
    show_usage
    exit 1
fi

# Parse command
command="$1"
shift

# Check if help is requested
if [ "$command" = "-h" ] || [ "$command" = "--help" ]; then
    show_usage
    exit 0
fi

# Build Python command with arguments
python_args=("--base-url" "$BASE_URL" "--token-file" "$TOKEN_FILE")

if [ "$DEBUG" = "true" ]; then
    python_args+=("--debug")
fi

python_args+=("$command")

# Add remaining arguments
while [ $# -gt 0 ]; do
    python_args+=("$1")
    shift
done

print_info "Running: uv run python cli/agent_mgmt.py ${python_args[@]}"

# Execute Python script
cd "$PROJECT_ROOT"
if uv run python cli/agent_mgmt.py "${python_args[@]}"; then
    exit 0
else
    print_error "Agent management command failed"
    exit 1
fi
