#!/bin/bash

# Script to refresh any M2M (machine-to-machine) token
# Usage: ./scripts/refresh_m2m_token.sh <client_name>
# Example: ./scripts/refresh_m2m_token.sh bot-008

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OAUTH_DIR="$PROJECT_ROOT/.oauth-tokens"

# Check if client name provided
if [ -z "$1" ]; then
    echo "Error: Client name required"
    echo ""
    echo "Usage: $0 <client_name>"
    echo ""
    echo "Example: $0 bot-008"
    echo ""
    echo "Available clients:"
    find "$OAUTH_DIR" -name "*.json" -type f ! -name "*-token.json" ! -name "*-m2m-token.json" -exec basename {} .json \; | sort
    exit 1
fi

CLIENT_NAME="$1"
CLIENT_FILE="$OAUTH_DIR/${CLIENT_NAME}.json"
TOKEN_FILE="$OAUTH_DIR/${CLIENT_NAME}-token.json"

# Check if client file exists
if [ ! -f "$CLIENT_FILE" ]; then
    echo "Error: Client file not found: $CLIENT_FILE"
    echo ""
    echo "Available clients:"
    find "$OAUTH_DIR" -name "*.json" -type f ! -name "*-token.json" ! -name "*-m2m-token.json" -exec basename {} .json \; | sort
    exit 1
fi

# Extract client credentials
CLIENT_ID=$(jq -r '.client_id' "$CLIENT_FILE")
CLIENT_SECRET=$(jq -r '.client_secret' "$CLIENT_FILE")

if [ -z "$CLIENT_ID" ] || [ "$CLIENT_ID" = "null" ]; then
    echo "Error: Invalid client_id in $CLIENT_FILE"
    exit 1
fi

if [ -z "$CLIENT_SECRET" ] || [ "$CLIENT_SECRET" = "null" ]; then
    echo "Error: Invalid client_secret in $CLIENT_FILE"
    exit 1
fi

# Keycloak configuration
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
REALM="${REALM:-mcp-gateway}"
TOKEN_ENDPOINT="${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token"

echo "Refreshing token for client: $CLIENT_NAME"
echo "Keycloak URL: $KEYCLOAK_URL"
echo "Realm: $REALM"
echo ""

# Request new token from Keycloak
RESPONSE=$(curl -s -X POST "$TOKEN_ENDPOINT" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=client_credentials" \
    -d "client_id=$CLIENT_ID" \
    -d "client_secret=$CLIENT_SECRET")

# Check if request was successful
if echo "$RESPONSE" | jq -e '.access_token' > /dev/null 2>&1; then
    ACCESS_TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')
    REFRESH_TOKEN=$(echo "$RESPONSE" | jq -r '.refresh_token // empty')
    EXPIRES_IN=$(echo "$RESPONSE" | jq -r '.expires_in')
    TOKEN_TYPE=$(echo "$RESPONSE" | jq -r '.token_type')
    SCOPE=$(echo "$RESPONSE" | jq -r '.scope // empty')

    # Calculate expiration timestamp
    CURRENT_TIME=$(date +%s)
    EXPIRES_AT=$((CURRENT_TIME + EXPIRES_IN))

    # Build token JSON
    TOKEN_JSON=$(jq -n \
        --arg access_token "$ACCESS_TOKEN" \
        --arg token_type "$TOKEN_TYPE" \
        --arg expires_in "$EXPIRES_IN" \
        --arg expires_at "$EXPIRES_AT" \
        --arg scope "$SCOPE" \
        --arg refresh_token "$REFRESH_TOKEN" \
        '{
            access_token: $access_token,
            token_type: $token_type,
            expires_in: ($expires_in | tonumber),
            expires_at: ($expires_at | tonumber),
            scope: $scope
        } + (if $refresh_token != "" then {refresh_token: $refresh_token} else {} end)')

    # Save to file
    echo "$TOKEN_JSON" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"

    echo "✓ Token refreshed successfully!"
    echo ""
    echo "Token file: $TOKEN_FILE"
    echo "Expires in: $EXPIRES_IN seconds ($(($EXPIRES_IN / 60)) minutes)"
    echo "Expires at: $(date -d @$EXPIRES_AT)"
    echo ""
    echo "To use this token:"
    echo "  export TOKEN=\$(jq -r '.access_token' $TOKEN_FILE)"
    echo "  curl -H \"Authorization: Bearer \$TOKEN\" http://localhost/v0/servers"
    echo ""

    # Also print first 50 chars for verification
    echo "Token preview: ${ACCESS_TOKEN:0:50}..."

else
    echo "✗ Failed to refresh token"
    echo ""
    echo "Error response:"
    echo "$RESPONSE" | jq '.'
    exit 1
fi
