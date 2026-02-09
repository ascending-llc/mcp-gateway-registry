#!/bin/bash

# Script to retrieve and save ALL client credentials from Keycloak
# Usage: ./get-all-client-credentials.sh
# This will fetch credentials for all clients in the mcp-gateway realm

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_info() { echo -e "${YELLOW}ℹ${NC} $1"; }

# Get the directory where the script is being run from (should be project root)
OUTPUT_DIR="$(pwd)/.oauth-tokens"

# Load environment variables
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Set Keycloak connection details
KEYCLOAK_URL="${KEYCLOAK_ADMIN_URL:-http://localhost:8080}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-mcp-gateway}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD}"

# Check if admin password is set
if [ -z "$KEYCLOAK_ADMIN_PASSWORD" ]; then
    print_error "KEYCLOAK_ADMIN_PASSWORD not set. Please export it or add it to .env file"
    exit 1
fi

print_info "Retrieving all client credentials from realm: $KEYCLOAK_REALM"

# Get admin access token
print_info "Getting admin token..."
TOKEN_RESPONSE=$(curl -s -X POST \
    "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=${KEYCLOAK_ADMIN}" \
    -d "password=${KEYCLOAK_ADMIN_PASSWORD}" \
    -d "grant_type=password" \
    -d "client_id=admin-cli")

ADMIN_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$ADMIN_TOKEN" == "null" ] || [ -z "$ADMIN_TOKEN" ]; then
    print_error "Failed to get admin token. Check your admin credentials."
    exit 1
fi
print_success "Admin token obtained"

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Create the main credentials file
OUTPUT_FILE="$OUTPUT_DIR/keycloak-client-secrets.txt"
echo "# Keycloak Client Credentials - Generated $(date)" > "$OUTPUT_FILE"
echo "# Realm: $KEYCLOAK_REALM" >> "$OUTPUT_FILE"
echo "# Keycloak URL: $KEYCLOAK_URL" >> "$OUTPUT_FILE"
echo "#" >> "$OUTPUT_FILE"
echo "# Add these to your .env file or use them in your applications" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Get all clients in the realm
print_info "Fetching all clients in realm..."
CLIENTS_RESPONSE=$(curl -s -X GET \
    "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/clients" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json")

# Parse client IDs and filter out system clients
CLIENT_COUNT=0
CREDENTIAL_COUNT=0

# First, specifically look for and process the main clients
print_info "Processing main clients..."
for MAIN_CLIENT in "mcp-gateway-web" "mcp-gateway-m2m"; do
    print_info "Looking for main client: $MAIN_CLIENT"

    # Get specific client by clientId
    CLIENT_DATA=$(echo "$CLIENTS_RESPONSE" | jq -r ".[] | select(.clientId == \"$MAIN_CLIENT\")")

    if [ -n "$CLIENT_DATA" ] && [ "$CLIENT_DATA" != "null" ]; then
        CLIENT_UUID=$(echo "$CLIENT_DATA" | jq -r '.id')

        # Get client secret
        SECRET_RESPONSE=$(curl -s -X GET \
            "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/clients/${CLIENT_UUID}/client-secret" \
            -H "Authorization: Bearer ${ADMIN_TOKEN}" \
            -H "Content-Type: application/json")

        CLIENT_SECRET=$(echo $SECRET_RESPONSE | jq -r '.value // "N/A"')

        if [ "$CLIENT_SECRET" != "N/A" ] && [ "$CLIENT_SECRET" != "null" ]; then
            if [[ "$MAIN_CLIENT" == "mcp-gateway-web" ]]; then
                echo "KEYCLOAK_CLIENT_ID=${MAIN_CLIENT}" >> "$OUTPUT_FILE"
                echo "KEYCLOAK_CLIENT_SECRET=${CLIENT_SECRET}" >> "$OUTPUT_FILE"
                echo "" >> "$OUTPUT_FILE"
                print_success "  Found and saved: $MAIN_CLIENT"
            elif [[ "$MAIN_CLIENT" == "mcp-gateway-m2m" ]]; then
                echo "KEYCLOAK_M2M_CLIENT_ID=${MAIN_CLIENT}" >> "$OUTPUT_FILE"
                echo "KEYCLOAK_M2M_CLIENT_SECRET=${CLIENT_SECRET}" >> "$OUTPUT_FILE"
                echo "" >> "$OUTPUT_FILE"
                print_success "  Found and saved: $MAIN_CLIENT"
            fi

            # Also create individual files for these
            CLIENT_JSON_FILE="$OUTPUT_DIR/${MAIN_CLIENT}.json"
            cat > "$CLIENT_JSON_FILE" <<EOF
{
  "client_id": "${MAIN_CLIENT}",
  "client_secret": "${CLIENT_SECRET}",
  "gateway_url": "http://localhost:8000",
  "keycloak_url": "${KEYCLOAK_URL}",
  "keycloak_realm": "${KEYCLOAK_REALM}",
  "auth_provider": "keycloak"
}
EOF
            CREDENTIAL_COUNT=$((CREDENTIAL_COUNT + 1))
        fi
    else
        print_info "  Client $MAIN_CLIENT not found"
    fi
done

print_info "Processing agent clients..."
# Process all other clients (agents, etc.)
# Use process substitution instead of pipe to preserve variables
while IFS= read -r client; do
    CLIENT_ID=$(echo "$client" | jq -r '.clientId')
    CLIENT_UUID=$(echo "$client" | jq -r '.id')
    CLIENT_AUTH_TYPE=$(echo "$client" | jq -r '.clientAuthenticatorType // "client-secret"')
    PUBLIC_CLIENT=$(echo "$client" | jq -r '.publicClient // false')

    # Skip system clients, public clients, and the main clients we already processed
    if [[ "$CLIENT_ID" == "realm-management" ]] || \
       [[ "$CLIENT_ID" == "security-admin-console" ]] || \
       [[ "$CLIENT_ID" == "admin-cli" ]] || \
       [[ "$CLIENT_ID" == "account-console" ]] || \
       [[ "$CLIENT_ID" == "broker" ]] || \
       [[ "$CLIENT_ID" == "account" ]] || \
       [[ "$CLIENT_ID" == "mcp-gateway-web" ]] || \
       [[ "$CLIENT_ID" == "mcp-gateway-m2m" ]] || \
       [[ "$PUBLIC_CLIENT" == "true" ]]; then
        continue
    fi

    print_info "Processing agent client: $CLIENT_ID"

    # Get client secret
    SECRET_RESPONSE=$(curl -s -X GET \
        "${KEYCLOAK_URL}/admin/realms/${KEYCLOAK_REALM}/clients/${CLIENT_UUID}/client-secret" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H "Content-Type: application/json")

    CLIENT_SECRET=$(echo $SECRET_RESPONSE | jq -r '.value // "N/A"')

    if [ "$CLIENT_SECRET" != "N/A" ] && [ "$CLIENT_SECRET" != "null" ]; then
        # For agent clients, use a different format
        echo "# Agent: $CLIENT_ID" >> "$OUTPUT_FILE"
        CLIENT_VAR_NAME=$(echo "$CLIENT_ID" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
        echo "${CLIENT_VAR_NAME}_CLIENT_ID=${CLIENT_ID}" >> "$OUTPUT_FILE"
        echo "${CLIENT_VAR_NAME}_CLIENT_SECRET=${CLIENT_SECRET}" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"

        # Create individual JSON file for each client
        CLIENT_JSON_FILE="$OUTPUT_DIR/${CLIENT_ID}.json"
        cat > "$CLIENT_JSON_FILE" <<EOF
{
  "client_id": "${CLIENT_ID}",
  "client_secret": "${CLIENT_SECRET}",
  "gateway_url": "http://localhost:8000",
  "keycloak_url": "${KEYCLOAK_URL}",
  "keycloak_realm": "${KEYCLOAK_REALM}",
  "auth_provider": "keycloak"
}
EOF


        print_success "  Saved credentials for: $CLIENT_ID"
        CREDENTIAL_COUNT=$((CREDENTIAL_COUNT + 1))
    fi

    CLIENT_COUNT=$((CLIENT_COUNT + 1))
done < <(echo "$CLIENTS_RESPONSE" | jq -c '.[] | select(.clientId != null)')

# Add summary to the main file
echo "" >> "$OUTPUT_FILE"
echo "# Summary" >> "$OUTPUT_FILE"
echo "# Total clients with credentials: $CREDENTIAL_COUNT" >> "$OUTPUT_FILE"
echo "# Generated on: $(date)" >> "$OUTPUT_FILE"

# Set secure permissions
chmod 600 "$OUTPUT_FILE"
chmod 600 "$OUTPUT_DIR"/*.json 2>/dev/null || true

print_success "All client credentials retrieved and saved"
echo ""
echo "==================== Summary ===================="
echo "Main credentials file: $OUTPUT_FILE"
echo "Individual JSON files: $OUTPUT_DIR/<client-id>.json"
echo ""
echo "Files created in: $OUTPUT_DIR/"
ls -la "$OUTPUT_DIR/" | grep -E "\.(txt|json)$"
echo "=================================================="
echo ""
print_info "Note: These files contain sensitive credentials. Keep them secure!"
