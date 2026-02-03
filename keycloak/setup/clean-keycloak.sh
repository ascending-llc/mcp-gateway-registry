#!/bin/bash
# Clean Keycloak configuration and data
# This script removes all Keycloak configuration and database data for a fresh start

set -e

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
REALM="mcp-gateway"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Keycloak cleanup script for MCP Gateway Registry${NC}"
echo "=============================================="

# Get script directory and find .env file
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
ENV_FILE="$PROJECT_ROOT/.env"

# Load environment variables from .env file if it exists
if [ -f "$ENV_FILE" ]; then
    echo "Loading environment variables from $ENV_FILE..."
    set -a  # Automatically export all variables
    source "$ENV_FILE"
    set +a  # Turn off automatic export
    echo "Environment variables loaded successfully"
else
    echo -e "${YELLOW}No .env file found at $ENV_FILE${NC}"
fi

# Function to get admin token
get_admin_token() {
    local response=$(curl -s -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=${KEYCLOAK_ADMIN}" \
        -d "password=${KEYCLOAK_ADMIN_PASSWORD}" \
        -d "grant_type=password" \
        -d "client_id=admin-cli")

    echo "$response" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4
}

# Function to check if Keycloak is accessible
check_keycloak_accessible() {
    if curl -f -s "${KEYCLOAK_URL}/admin/" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to delete realm via API
delete_realm_via_api() {
    echo -e "${BLUE}Attempting to delete realm via Keycloak Admin API...${NC}"

    if ! check_keycloak_accessible; then
        echo -e "${YELLOW}Keycloak is not accessible. Skipping API cleanup.${NC}"
        return 1
    fi

    # Check if admin password is set
    if [ -z "$KEYCLOAK_ADMIN_PASSWORD" ]; then
        echo -e "${YELLOW}KEYCLOAK_ADMIN_PASSWORD not set. Skipping API cleanup.${NC}"
        return 1
    fi

    # Get admin token
    echo "Getting admin token..."
    TOKEN=$(get_admin_token)

    if [ -z "$TOKEN" ]; then
        echo -e "${YELLOW}Failed to get admin token. Skipping API cleanup.${NC}"
        return 1
    fi

    # Check if realm exists
    local response=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${TOKEN}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}")

    if [ "$response" = "200" ]; then
        echo "Deleting ${REALM} realm..."
        local delete_response=$(curl -s -o /dev/null -w "%{http_code}" \
            -X DELETE "${KEYCLOAK_URL}/admin/realms/${REALM}" \
            -H "Authorization: Bearer ${TOKEN}")

        if [ "$delete_response" = "204" ]; then
            echo -e "${GREEN}Realm '${REALM}' deleted successfully via API!${NC}"
            return 0
        else
            echo -e "${YELLOW}Failed to delete realm via API (HTTP ${delete_response})${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}Realm '${REALM}' does not exist or is not accessible${NC}"
        return 0
    fi
}

# Function to stop and remove containers
stop_containers() {
    echo -e "${BLUE}Stopping Keycloak containers...${NC}"

    cd "$PROJECT_ROOT"

    # Stop Keycloak and database containers specifically
    if docker-compose ps | grep -q keycloak; then
        echo "Stopping keycloak container..."
        docker-compose stop keycloak || echo "Keycloak container was not running"
    fi

    if docker-compose ps | grep -q keycloak-db; then
        echo "Stopping keycloak-db container..."
        docker-compose stop keycloak-db || echo "Keycloak-db container was not running"
    fi

    # Remove the containers (but keep volumes for now)
    echo "Removing keycloak containers..."
    docker-compose rm -f keycloak keycloak-db 2>/dev/null || echo "Containers already removed"

    echo -e "${GREEN}Containers stopped and removed${NC}"
}

# Function to remove database volume
remove_database_volume() {
    echo -e "${BLUE}Removing Keycloak database volume...${NC}"

    cd "$PROJECT_ROOT"

    # Get the volume name (it will be prefixed with the project name)
    local volume_name=$(docker volume ls | grep keycloak_db_data | awk '{print $2}')

    if [ ! -z "$volume_name" ]; then
        echo "Removing volume: $volume_name"
        docker volume rm "$volume_name" 2>/dev/null || {
            echo -e "${YELLOW}Volume might be in use. Forcing removal...${NC}"
            docker volume rm -f "$volume_name" 2>/dev/null || echo -e "${YELLOW}Could not remove volume $volume_name${NC}"
        }
        echo -e "${GREEN}Database volume removed${NC}"
    else
        echo -e "${YELLOW}Keycloak database volume not found${NC}"
    fi
}

# Function to clean environment variables from .env
clean_env_secrets() {
    echo -e "${BLUE}Cleaning Keycloak secrets from .env file...${NC}"

    if [ -f "$ENV_FILE" ]; then
        # Reset client secrets to placeholder values
        sed -i 's/^KEYCLOAK_CLIENT_SECRET=.*/KEYCLOAK_CLIENT_SECRET=your-keycloak-client-secret/' "$ENV_FILE" 2>/dev/null || true
        sed -i 's/^KEYCLOAK_M2M_CLIENT_SECRET=.*/KEYCLOAK_M2M_CLIENT_SECRET=your-keycloak-m2m-secret/' "$ENV_FILE" 2>/dev/null || true

        echo -e "${GREEN}Client secrets reset to placeholder values in .env${NC}"
    else
        echo -e "${YELLOW}.env file not found, skipping secret cleanup${NC}"
    fi
}

# Main cleanup function
main() {
    echo -e "${RED}WARNING: This will completely remove all Keycloak configuration and data!${NC}"
    echo "This includes:"
    echo "  - All realms, clients, and users"
    echo "  - All groups and group assignments"
    echo "  - All client secrets and configuration"
    echo "  - Database volume with all persistent data"
    echo ""

    read -p "Are you sure you want to proceed? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cleanup cancelled"
        exit 0
    fi

    echo ""
    echo -e "${BLUE}Starting Keycloak cleanup...${NC}"

    # Step 1: Try to delete realm via API (graceful cleanup)
    delete_realm_via_api || echo -e "${YELLOW}API cleanup failed or skipped${NC}"

    # Step 2: Stop and remove containers
    stop_containers

    # Step 3: Remove database volume (nuclear option)
    remove_database_volume

    # Step 4: Clean environment secrets
    clean_env_secrets

    echo ""
    echo -e "${GREEN}Keycloak cleanup completed!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Run 'docker-compose up -d keycloak keycloak-db' to start fresh containers"
    echo "2. Wait for Keycloak to initialize (check with 'docker-compose logs keycloak')"
    echo "3. Run './keycloak/setup/init-keycloak.sh' to set up fresh configuration"
    echo ""
    echo -e "${YELLOW}Note: You'll need to update your .env file with new client secrets after running init-keycloak.sh${NC}"
}

# Run main function
main
