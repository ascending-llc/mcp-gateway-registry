#!/bin/bash

# Script to get M2M JWT token for a Keycloak client with smart caching
# Usage: ./get-m2m-token.sh [OPTIONS] [client-name]
#
# Options:
#   --aws-region REGION      AWS region (overrides AWS_REGION env var)
#   --keycloak-url URL       Keycloak base URL (overrides KEYCLOAK_URL env var)
#   --output-file FILE       Save token to file instead of printing to stdout
#   --help                   Show this help message
#
# Environment variables (used if command-line options not provided):
#   AWS_REGION - AWS region where Keycloak and SSM are deployed (e.g., us-east-1)
#   KEYCLOAK_URL - Keycloak base URL (e.g., https://kc.us-east-1.mycorp.click)
#
# This script implements smart token management:
# 1. First checks SSM Parameter Store for cached token
# 2. Validates token expiration (with 60 second buffer)
# 3. Only fetches new token from Keycloak if needed
# 4. Stores new tokens in SSM (but NOT in local files by default)
# 5. Outputs the token to stdout (or saves to file if --output-file is specified)

set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TERRAFORM_OUTPUTS="$SCRIPT_DIR/terraform-outputs.json"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Parse command-line arguments
CLIENT_NAME=""
CLI_AWS_REGION=""
CLI_KEYCLOAK_URL=""
OUTPUT_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --aws-region)
            CLI_AWS_REGION="$2"
            shift 2
            ;;
        --keycloak-url)
            CLI_KEYCLOAK_URL="$2"
            shift 2
            ;;
        --output-file)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS] [client-name]"
            echo ""
            echo "Options:"
            echo "  --aws-region REGION      AWS region (overrides AWS_REGION env var)"
            echo "  --keycloak-url URL       Keycloak base URL (overrides KEYCLOAK_URL env var)"
            echo "  --output-file FILE       Save token to file instead of printing to stdout"
            echo "  --help                   Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  AWS_REGION - AWS region where Keycloak and SSM are deployed"
            echo "  KEYCLOAK_URL - Keycloak base URL"
            exit 0
            ;;
        -*)
            echo -e "${RED}Error: Unknown option: $1${NC}" >&2
            exit 1
            ;;
        *)
            CLIENT_NAME="$1"
            shift
            ;;
    esac
done

# Command-line args override environment variables
AWS_REGION="${CLI_AWS_REGION:-$AWS_REGION}"
KEYCLOAK_URL="${CLI_KEYCLOAK_URL:-$KEYCLOAK_URL}"

# Configuration - require mandatory parameters
if [ -z "$AWS_REGION" ]; then
    echo -e "${RED}Error: AWS_REGION is required${NC}" >&2
    echo -e "${RED}Set via environment variable or --aws-region option:${NC}" >&2
    echo -e "${RED}  export AWS_REGION=us-east-1${NC}" >&2
    echo -e "${RED}  OR${NC}" >&2
    echo -e "${RED}  $0 --aws-region us-east-1 <client-name>${NC}" >&2
    exit 1
fi

if [ -z "$KEYCLOAK_URL" ]; then
    echo -e "${RED}Error: KEYCLOAK_URL is required${NC}" >&2
    echo -e "${RED}Set via environment variable or --keycloak-url option:${NC}" >&2
    echo -e "${RED}  export KEYCLOAK_URL=https://kc.us-east-1.mycorp.click${NC}" >&2
    echo -e "${RED}  OR${NC}" >&2
    echo -e "${RED}  $0 --keycloak-url https://kc.us-east-1.mycorp.click <client-name>${NC}" >&2
    exit 1
fi

REALM="mcp-gateway"
CLIENT_NAME="${CLIENT_NAME:-registry-admin-bot}"
ORIGINAL_CLIENT_NAME="${CLIENT_NAME}"
SSM_TOKEN_PARAM="/keycloak/clients/${CLIENT_NAME}/jwt_token"
EXPIRATION_BUFFER=60  # Refresh token if expires within 60 seconds

echo -e "${YELLOW}Getting JWT token for client: $CLIENT_NAME${NC}" >&2
echo -e "${YELLOW}Using AWS region: $AWS_REGION${NC}" >&2
echo -e "${YELLOW}Using Keycloak URL: $KEYCLOAK_URL${NC}" >&2
echo "" >&2

# Function to check if token is expired
is_token_expired() {
    local expires_at=$1
    local current_time=$(date +%s)
    local time_until_expiry=$((expires_at - current_time))

    if [ $time_until_expiry -le $EXPIRATION_BUFFER ]; then
        return 0  # Token is expired or will expire soon
    else
        return 1  # Token is still valid
    fi
}

# Step 1: Try to get cached token from SSM Parameter Store
echo -e "${YELLOW}Step 1: Checking SSM Parameter Store for cached token...${NC}" >&2

# Get the SSM parameter value (which is a JSON string)
# Try the original client name first
SSM_PARAM_VALUE=$(aws ssm get-parameter \
    --name "$SSM_TOKEN_PARAM" \
    --with-decryption \
    --region "$AWS_REGION" 2>/dev/null | jq -r '.Parameter.Value // empty' 2>/dev/null || echo "")

# If not found, try with service-account- prefix
if [ -z "$SSM_PARAM_VALUE" ] || [ "$SSM_PARAM_VALUE" = "null" ]; then
    SSM_TOKEN_PARAM_ALT="/keycloak/clients/service-account-${ORIGINAL_CLIENT_NAME}/jwt_token"
    SSM_PARAM_VALUE=$(aws ssm get-parameter \
        --name "$SSM_TOKEN_PARAM_ALT" \
        --with-decryption \
        --region "$AWS_REGION" 2>/dev/null | jq -r '.Parameter.Value // empty' 2>/dev/null || echo "")
    if [ -n "$SSM_PARAM_VALUE" ] && [ "$SSM_PARAM_VALUE" != "null" ]; then
        # Use the alternate parameter name for storing the token later
        SSM_TOKEN_PARAM="$SSM_TOKEN_PARAM_ALT"
    fi
fi

if [ -n "$SSM_PARAM_VALUE" ] && [ "$SSM_PARAM_VALUE" != "null" ]; then
    echo -e "${GREEN}Found cached token in SSM at $SSM_TOKEN_PARAM${NC}" >&2

    # Parse the JSON value (Parameter.Value is itself a JSON string)
    CACHED_ACCESS_TOKEN=$(echo "$SSM_PARAM_VALUE" | jq -r '.access_token // empty' 2>/dev/null)
    CACHED_EXPIRES_AT=$(echo "$SSM_PARAM_VALUE" | jq -r '.expires_at // empty' 2>/dev/null)
    CACHED_EXPIRES_IN=$(echo "$SSM_PARAM_VALUE" | jq -r '.expires_in // 300' 2>/dev/null)

    if [ -n "$CACHED_ACCESS_TOKEN" ] && [ -n "$CACHED_EXPIRES_AT" ]; then
        # Check if token is still valid
        if ! is_token_expired "$CACHED_EXPIRES_AT"; then
            CURRENT_TIME=$(date +%s)
            TIME_UNTIL_EXPIRY=$((CACHED_EXPIRES_AT - CURRENT_TIME))

            echo -e "${GREEN}Cached token is still valid (expires in ${TIME_UNTIL_EXPIRY} seconds)${NC}" >&2
            echo -e "${GREEN}Using cached token from SSM${NC}" >&2
            echo "" >&2
            echo -e "${GREEN}Successfully retrieved cached token!${NC}" >&2

            # Output token to stdout and exit
            echo "$CACHED_ACCESS_TOKEN"
            exit 0
        else
            echo -e "${YELLOW}Cached token is expired or will expire soon${NC}" >&2
            echo -e "${YELLOW}Will fetch new token from Keycloak...${NC}" >&2
        fi
    else
        echo -e "${YELLOW}Invalid cached token format${NC}" >&2
        echo -e "${YELLOW}Will fetch new token from Keycloak...${NC}" >&2
    fi
else
    echo -e "${YELLOW}No cached token found in SSM${NC}" >&2
    echo -e "${YELLOW}Will fetch new token from Keycloak...${NC}" >&2
fi

echo "" >&2

# Step 2: Get new token from Keycloak
echo -e "${YELLOW}Step 2: Fetching new token from Keycloak...${NC}" >&2
echo "Keycloak URL: $KEYCLOAK_URL" >&2

# Get Keycloak admin password from SSM
KEYCLOAK_ADMIN_PASSWORD=$(aws ssm get-parameter \
    --name "/keycloak/admin_password" \
    --with-decryption \
    --region "$AWS_REGION" 2>/dev/null | jq -r '.Parameter.Value // empty' 2>/dev/null)

if [ -z "$KEYCLOAK_ADMIN_PASSWORD" ] || [ "$KEYCLOAK_ADMIN_PASSWORD" = "null" ]; then
    echo -e "${RED}Error: Could not retrieve Keycloak admin password from SSM${NC}" >&2
    exit 1
fi

# Get admin token
echo "Getting admin token..." >&2
ADMIN_TOKEN=$(curl -s -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=admin" \
    -d "password=${KEYCLOAK_ADMIN_PASSWORD}" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" 2>/dev/null | jq -r '.access_token // empty' 2>/dev/null)

if [ -z "$ADMIN_TOKEN" ] || [ "$ADMIN_TOKEN" = "null" ]; then
    echo -e "${RED}Error: Failed to get admin token${NC}" >&2
    exit 1
fi

echo -e "${GREEN}Admin token obtained${NC}" >&2

# Get client UUID
# Try with the provided name first, then try with service-account- prefix
echo "Looking up client UUID..." >&2
CLIENT_UUID=$(curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=${CLIENT_NAME}" 2>/dev/null | \
    jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)

# If not found, try with service-account- prefix (Keycloak's naming convention for service accounts)
if [ -z "$CLIENT_UUID" ]; then
    echo "Client '${CLIENT_NAME}' not found, trying 'service-account-${CLIENT_NAME}'..." >&2
    CLIENT_NAME="service-account-${CLIENT_NAME}"
    # Update SSM parameter path to match the actual client name
    SSM_TOKEN_PARAM="/keycloak/clients/${CLIENT_NAME}/jwt_token"
    CLIENT_UUID=$(curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=${CLIENT_NAME}" 2>/dev/null | \
        jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)
fi

if [ -z "$CLIENT_UUID" ]; then
    echo -e "${RED}Error: Client '${CLIENT_NAME}' not found${NC}" >&2
    exit 1
fi

echo -e "${GREEN}Client UUID: ${CLIENT_UUID}${NC}" >&2

# Get client secret
echo "Retrieving client secret..." >&2
CLIENT_SECRET=$(curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/client-secret" 2>/dev/null | \
    jq -r '.value // empty' 2>/dev/null)

if [ -z "$CLIENT_SECRET" ]; then
    echo -e "${RED}Error: Could not retrieve client secret${NC}" >&2
    exit 1
fi

echo -e "${GREEN}Client secret retrieved${NC}" >&2

# Get M2M token using client credentials
echo "Requesting M2M access token..." >&2

TOKEN_RESPONSE=$(curl -s -X POST "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "client_id=${CLIENT_NAME}" \
    -d "client_secret=${CLIENT_SECRET}" \
    -d "grant_type=client_credentials" 2>/dev/null)

ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token // empty' 2>/dev/null)

if [ -z "$ACCESS_TOKEN" ]; then
    echo -e "${RED}Error: Failed to get access token${NC}" >&2
    ERROR_MSG=$(echo "$TOKEN_RESPONSE" | jq -r '.error_description // .error // "Unknown error"' 2>/dev/null)
    echo -e "${RED}Error details: $ERROR_MSG${NC}" >&2
    exit 1
fi

# Calculate expiration time
EXPIRES_IN=$(echo "$TOKEN_RESPONSE" | jq -r '.expires_in // 300' 2>/dev/null)
CURRENT_TIME=$(date +%s)
EXPIRES_AT=$((CURRENT_TIME + EXPIRES_IN))

echo -e "${GREEN}Successfully obtained new access token!${NC}" >&2
echo "Expires in: ${EXPIRES_IN} seconds" >&2

# Step 3: Store token in SSM Parameter Store
echo "" >&2
echo -e "${YELLOW}Step 3: Storing token in SSM Parameter Store...${NC}" >&2

TOKEN_JSON=$(cat <<EOF
{
  "access_token": "$ACCESS_TOKEN",
  "expires_in": $EXPIRES_IN,
  "expires_at": $EXPIRES_AT,
  "token_type": "Bearer",
  "client_id": "$CLIENT_NAME"
}
EOF
)

# Store in SSM (overwrite if exists)
aws ssm put-parameter \
    --name "$SSM_TOKEN_PARAM" \
    --value "$TOKEN_JSON" \
    --type "SecureString" \
    --overwrite \
    --region "$AWS_REGION" >/dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Token stored in SSM: $SSM_TOKEN_PARAM${NC}" >&2
else
    echo -e "${YELLOW}Warning: Failed to store token in SSM (continuing anyway)${NC}" >&2
fi

echo "" >&2
echo -e "${GREEN}=== Token Management Complete ===${NC}" >&2
echo "" >&2
echo "Token details:" >&2
echo "  Client: $CLIENT_NAME" >&2
echo "  Expires in: ${EXPIRES_IN} seconds" >&2
echo "  Expires at: $(date -d @${EXPIRES_AT} 2>/dev/null || date -r ${EXPIRES_AT} 2>/dev/null || echo $EXPIRES_AT)" >&2
echo "  SSM location: $SSM_TOKEN_PARAM" >&2

# Output the token to stdout or save to file
if [ -n "$OUTPUT_FILE" ]; then
    echo "$ACCESS_TOKEN" > "$OUTPUT_FILE"
    echo "  Token saved to: $OUTPUT_FILE" >&2
    echo "" >&2
else
    echo "" >&2
    # Output the token to stdout for consumption by other scripts
    echo "$ACCESS_TOKEN"
fi
