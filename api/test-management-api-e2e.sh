#!/bin/bash

# Exit on error
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Usage function
usage() {
    echo "Usage: $0 --token-file <path-to-token-file> [--registry-url <url>] [--aws-region <region>] [--keycloak-url <url>] [--quiet]"
    echo ""
    echo "Required arguments:"
    echo "  --token-file <path>      Path to the OAuth token file (e.g., .oauth-tokens/ingress.json)"
    echo ""
    echo "Optional arguments:"
    echo "  --registry-url <url>     Registry URL (default: http://localhost)"
    echo "  --aws-region <region>    AWS region (e.g., us-east-1)"
    echo "  --keycloak-url <url>     Keycloak base URL (e.g., https://kc.us-east-1.aroraai.people.aws.dev)"
    echo "  --quiet                  Suppress verbose output (verbose is enabled by default)"
    echo ""
    echo "Examples:"
    echo "  # Local testing with verbose output (default)"
    echo "  $0 --token-file .oauth-tokens/ingress.json"
    echo ""
    echo "  # Remote testing with all parameters"
    echo "  $0 --token-file api/.token --registry-url https://registry.us-east-1.aroraai.people.aws.dev --aws-region us-east-1 --keycloak-url https://kc.us-east-1.aroraai.people.aws.dev"
    exit 1
}

# Parse command line arguments
TOKEN_FILE=""
REGISTRY_URL="http://localhost"
AWS_REGION=""
KEYCLOAK_URL=""
VERBOSE=true  # Verbose by default

while [[ $# -gt 0 ]]; do
    case $1 in
        --token-file)
            TOKEN_FILE="$2"
            shift 2
            ;;
        --registry-url)
            REGISTRY_URL="$2"
            shift 2
            ;;
        --aws-region)
            AWS_REGION="$2"
            shift 2
            ;;
        --keycloak-url)
            KEYCLOAK_URL="$2"
            shift 2
            ;;
        --quiet)
            VERBOSE=false
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Error: Unknown argument $1"
            usage
            ;;
    esac
done

# Validate required arguments
if [ -z "$TOKEN_FILE" ]; then
    echo -e "${RED}Error: --token-file is required${NC}"
    echo ""
    usage
fi

# Validate token file exists
if [ ! -f "$TOKEN_FILE" ]; then
    echo -e "${RED}Error: Token file not found: $TOKEN_FILE${NC}"
    echo ""
    echo "To generate tokens for local testing:"
    echo "  cd credentials-provider && ./generate_creds.sh && cd .."
    exit 1
fi

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

# Validate token is not expired
echo "Validating token..."
TOKEN_CONTENT=$(cat "$TOKEN_FILE")

# Detect token format and extract access_token
# Format 1: JSON with access_token field (from generate_creds.sh)
# Format 2: Raw JWT token (from get-m2m-token.sh)
if echo "$TOKEN_CONTENT" | grep -q "^eyJ"; then
    # Format 2: Raw JWT token (starts with eyJ which is base64 for '{"')
    ACCESS_TOKEN="$TOKEN_CONTENT"
else
    # Format 1: JSON format - extract the access_token field
    if command -v jq &> /dev/null; then
        # Use jq if available
        ACCESS_TOKEN=$(echo "$TOKEN_CONTENT" | jq -r '.access_token // empty')
    else
        # Fallback to grep/sed if jq is not available
        ACCESS_TOKEN=$(echo "$TOKEN_CONTENT" | grep -o '"access_token":"[^"]*"' | sed 's/"access_token":"\([^"]*\)"/\1/')
    fi
fi

if [ -z "$ACCESS_TOKEN" ]; then
    echo -e "${RED}Error: Could not extract access_token from token file${NC}"
    echo "Token file may be corrupted or in wrong format"
    echo ""
    echo "Supported formats:"
    echo "  1. JSON format: {\"access_token\": \"...\"}"
    echo "  2. Raw JWT token: eyJ..."
    echo ""
    echo "To regenerate tokens:"
    echo "  cd credentials-provider && ./generate_creds.sh && cd .."
    exit 1
fi

# Decode JWT to check expiration (JWT format: header.payload.signature)
# Extract payload (second part)
PAYLOAD=$(echo "$ACCESS_TOKEN" | cut -d. -f2)

# Add padding if needed for base64 decoding
case $((${#PAYLOAD} % 4)) in
    2) PAYLOAD="${PAYLOAD}==" ;;
    3) PAYLOAD="${PAYLOAD}=" ;;
esac

# Decode payload
if command -v base64 &> /dev/null; then
    DECODED_PAYLOAD=$(echo "$PAYLOAD" | base64 -d 2>/dev/null || echo "{}")

    # Extract exp field
    if command -v jq &> /dev/null; then
        EXP=$(echo "$DECODED_PAYLOAD" | jq -r '.exp // empty')
    else
        EXP=$(echo "$DECODED_PAYLOAD" | grep -o '"exp":[0-9]*' | sed 's/"exp"://')
    fi

    if [ -n "$EXP" ]; then
        CURRENT_TIME=$(date +%s)
        if [ "$EXP" -lt "$CURRENT_TIME" ]; then
            echo -e "${RED}Error: Token has expired${NC}"
            echo "Token expired at: $(date -d @$EXP 2>/dev/null || date -r $EXP 2>/dev/null)"
            echo "Current time: $(date)"
            echo ""
            echo "To regenerate tokens:"
            echo "  cd credentials-provider && ./generate_creds.sh && cd .."
            exit 1
        else
            TIME_LEFT=$((EXP - CURRENT_TIME))
            MINUTES_LEFT=$((TIME_LEFT / 60))
            echo -e "${GREEN}Token is valid (expires in $MINUTES_LEFT minutes)${NC}"
        fi
    else
        echo -e "${YELLOW}Warning: Could not verify token expiration${NC}"
    fi
else
    echo -e "${YELLOW}Warning: base64 command not found, skipping token expiration check${NC}"
fi
echo ""

# Test data with timestamp for uniqueness
TIMESTAMP="$(date +%s)"
GROUP_NAME="test-team-${TIMESTAMP}"
HUMAN_USERNAME="test.user.${TIMESTAMP}"
HUMAN_EMAIL="${HUMAN_USERNAME}@example.com"
M2M_NAME="test-service-bot-${TIMESTAMP}"
SERVER_NAME="Cloudflare Documentation MCP Server"
AGENT_NAME="Flight Booking Agent"

# Generate random password for human user
HUMAN_USER_PASSWORD="$(openssl rand -base64 16 | tr -d '/+=' | head -c 20)Aa1!"

# Unique paths with timestamp
SERVER_PATH="/cloudflare-docs-${TIMESTAMP}"
AGENT_PATH="/flight-booking-${TIMESTAMP}"

# Temporary files for JSON payloads
SERVER_JSON_FILE="${SCRIPT_DIR}/cloudflare-docs-server-config-${TIMESTAMP}.json"
AGENT_JSON_FILE="${SCRIPT_DIR}/flight_booking_agent_card-${TIMESTAMP}.json"

# Variables to store created resource info
M2M_CLIENT_ID=""
M2M_CLIENT_SECRET=""

# Arrays to track test results
declare -a TEST_NAMES
declare -a TEST_RESULTS
TEST_COUNT=0

# Function to record test result
record_result() {
    local test_name="$1"
    local result="$2"  # PASS or FAIL
    TEST_NAMES[$TEST_COUNT]="$test_name"
    TEST_RESULTS[$TEST_COUNT]="$result"
    TEST_COUNT=$((TEST_COUNT + 1))
}

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Management API End-to-End Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Registry URL: ${REGISTRY_URL}"
echo "  Token File: ${TOKEN_FILE}"
[ -n "$AWS_REGION" ] && echo "  AWS Region: ${AWS_REGION}"
[ -n "$KEYCLOAK_URL" ] && echo "  Keycloak URL: ${KEYCLOAK_URL}"
echo "  Group Name: ${GROUP_NAME}"
echo "  Human User: ${HUMAN_USERNAME}"
echo "  M2M Account: ${M2M_NAME}"
echo ""

# Set up management command
MGMT_CMD="uv run python ${SCRIPT_DIR}/registry_management.py --debug --registry-url ${REGISTRY_URL} --token-file ${TOKEN_FILE}"
[ -n "$AWS_REGION" ] && MGMT_CMD="$MGMT_CMD --aws-region ${AWS_REGION}"
[ -n "$KEYCLOAK_URL" ] && MGMT_CMD="$MGMT_CMD --keycloak-url ${KEYCLOAK_URL}"

# Function to cleanup on exit
cleanup() {
    # Display test results summary first (before cleanup)
    if [ $TEST_COUNT -gt 0 ]; then
        echo ""
        echo -e "${BLUE}========================================${NC}"
        echo -e "${BLUE}Test Results Summary${NC}"
        echo -e "${BLUE}========================================${NC}"
        echo ""

        # Print table header
        printf "%-40s | %-10s\n" "Test Name" "Result"
        printf "%-40s-+-%-10s\n" "----------------------------------------" "----------"

        # Calculate pass/fail counts
        PASS_COUNT=0
        FAIL_COUNT=0
        SKIP_COUNT=0

        # Print each result
        for ((i=0; i<TEST_COUNT; i++)); do
            test_name="${TEST_NAMES[$i]}"
            result="${TEST_RESULTS[$i]}"

            # Count results
            if [ "$result" = "PASS" ]; then
                PASS_COUNT=$((PASS_COUNT + 1))
                result_colored="${GREEN}PASS${NC}"
            elif [ "$result" = "SKIP" ]; then
                SKIP_COUNT=$((SKIP_COUNT + 1))
                result_colored="${YELLOW}SKIP${NC}"
            else
                FAIL_COUNT=$((FAIL_COUNT + 1))
                result_colored="${RED}FAIL${NC}"
            fi

            printf "%-40s | " "$test_name"
            echo -e "$result_colored"
        done

        echo ""
        printf "%-40s | %-10s\n" "----------------------------------------" "----------"
        printf "%-40s | ${GREEN}%-10s${NC}\n" "Total Passed" "$PASS_COUNT"
        printf "%-40s | ${RED}%-10s${NC}\n" "Total Failed" "$FAIL_COUNT"
        printf "%-40s | ${YELLOW}%-10s${NC}\n" "Total Skipped" "$SKIP_COUNT"
        printf "%-40s | %-10s\n" "Total Tests" "$TEST_COUNT"
        echo ""
    fi

    echo ""
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}Cleanup: Deleting resources${NC}"
    echo -e "${YELLOW}========================================${NC}"
    echo ""

    # Delete agent
    if [ -n "${AGENT_PATH}" ]; then
        echo -e "${BLUE}[Step 11] Deleting agent: ${AGENT_NAME}${NC}"
        ${MGMT_CMD} agent-delete --path "${AGENT_PATH}" --force || echo -e "${RED}Failed to delete agent${NC}"
    fi

    # Delete server
    if [ -n "${SERVER_PATH}" ]; then
        echo -e "${BLUE}[Step 12] Deleting server: ${SERVER_NAME}${NC}"
        ${MGMT_CMD} remove --path "${SERVER_PATH}" --force || echo -e "${RED}Failed to delete server${NC}"
    fi

    # Delete M2M account
    if [ -n "${M2M_CLIENT_ID}" ]; then
        echo -e "${BLUE}[Step 13] Deleting M2M account: ${M2M_NAME}${NC}"
        ${MGMT_CMD} user-delete --username "${M2M_NAME}" --force || echo -e "${RED}Failed to delete M2M account${NC}"
    fi

    # Delete human user
    echo -e "${BLUE}[Step 14] Deleting human user: ${HUMAN_USERNAME}${NC}"
    ${MGMT_CMD} user-delete --username "${HUMAN_USERNAME}" --force || echo -e "${RED}Failed to delete human user${NC}"

    # Delete group
    echo -e "${BLUE}[Step 15] Deleting group: ${GROUP_NAME}${NC}"
    ${MGMT_CMD} group-delete --name "${GROUP_NAME}" --force || echo -e "${RED}Failed to delete group${NC}"

    # Delete temporary JSON files
    echo -e "${BLUE}[Step 16] Cleaning up temporary JSON files${NC}"
    if [ -f "${SERVER_JSON_FILE}" ]; then
        rm -f "${SERVER_JSON_FILE}"
        echo -e "${GREEN}Deleted ${SERVER_JSON_FILE}${NC}"
    fi
    if [ -f "${AGENT_JSON_FILE}" ]; then
        rm -f "${AGENT_JSON_FILE}"
        echo -e "${GREEN}Deleted ${AGENT_JSON_FILE}${NC}"
    fi

    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Cleanup complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
}

# Register cleanup function to run on exit
trap cleanup EXIT

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Phase 1: Resource Creation${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Create IAM group
echo -e "${BLUE}[Step 1] Creating IAM group: ${GROUP_NAME}${NC}"
if [ "$VERBOSE" = true ]; then
    ${MGMT_CMD} group-create \
        --name "${GROUP_NAME}" \
        --description "Test group for end-to-end testing"
    CREATE_STATUS=$?
else
    ${MGMT_CMD} group-create \
        --name "${GROUP_NAME}" \
        --description "Test group for end-to-end testing" > /dev/null 2>&1
    CREATE_STATUS=$?
fi

if [ $CREATE_STATUS -eq 0 ]; then
    echo -e "${GREEN}Group created successfully${NC}"
    record_result "Create IAM Group" "PASS"

    # Wait for group to be available in Keycloak
    echo -e "${YELLOW}Waiting for group to be available in Keycloak...${NC}"
    GROUP_AVAILABLE=false
    for i in {1..10}; do
        # Use a simple command without --debug to avoid confusion
        # Store output and check separately to avoid set -e issues
        GROUP_LIST_OUTPUT=$(uv run python ${SCRIPT_DIR}/registry_management.py --registry-url ${REGISTRY_URL} --token-file ${TOKEN_FILE} group-list 2>/dev/null || true)
        if echo "${GROUP_LIST_OUTPUT}" | grep -q "${GROUP_NAME}"; then
            echo -e "${GREEN}Group is now available${NC}"
            GROUP_AVAILABLE=true
            break
        else
            echo -e "${YELLOW}Group not yet available, waiting 10 seconds (attempt $i/10)...${NC}"
            sleep 10
        fi
    done

    if [ "$GROUP_AVAILABLE" = false ]; then
        echo -e "${RED}Group did not become available after 100 seconds${NC}"
        exit 1
    fi
else
    echo -e "${RED}Group creation failed${NC}"
    record_result "Create IAM Group" "FAIL"
fi
echo ""

# Step 2: Create human user
echo -e "${BLUE}[Step 2] Creating human user: ${HUMAN_USERNAME}${NC}"
if [ "$VERBOSE" = true ]; then
    ${MGMT_CMD} user-create-human \
        --username "${HUMAN_USERNAME}" \
        --email "${HUMAN_EMAIL}" \
        --first-name "Test" \
        --last-name "User" \
        --groups "${GROUP_NAME}" \
        --password "${HUMAN_USER_PASSWORD}"
    CREATE_STATUS=$?
else
    ${MGMT_CMD} user-create-human \
        --username "${HUMAN_USERNAME}" \
        --email "${HUMAN_EMAIL}" \
        --first-name "Test" \
        --last-name "User" \
        --groups "${GROUP_NAME}" \
        --password "${HUMAN_USER_PASSWORD}" > /dev/null 2>&1
    CREATE_STATUS=$?
fi

if [ $CREATE_STATUS -eq 0 ]; then
    echo -e "${GREEN}Human user created successfully${NC}"
    record_result "Create Human User" "PASS"
else
    echo -e "${RED}Human user creation failed${NC}"
    record_result "Create Human User" "FAIL"
fi
echo ""

# Step 3: Create M2M service account
echo -e "${BLUE}[Step 3] Creating M2M service account: ${M2M_NAME}${NC}"
if [ "$VERBOSE" = true ]; then
    M2M_OUTPUT=$(${MGMT_CMD} user-create-m2m \
        --name "${M2M_NAME}" \
        --groups "${GROUP_NAME}" \
        --description "Test service account for end-to-end testing" 2>&1)
    CREATE_STATUS=$?
else
    M2M_OUTPUT=$(${MGMT_CMD} user-create-m2m \
        --name "${M2M_NAME}" \
        --groups "${GROUP_NAME}" \
        --description "Test service account for end-to-end testing" 2>&1)
    CREATE_STATUS=$?
fi

if [ $CREATE_STATUS -eq 0 ]; then
    echo "${M2M_OUTPUT}"
    # Extract client ID and secret (these are shown in the output)
    M2M_CLIENT_ID="${M2M_NAME}"
    echo -e "${GREEN}M2M service account created successfully${NC}"
    echo -e "${YELLOW}Note: Save the client secret from the output above - it will not be shown again!${NC}"
    record_result "Create M2M Account" "PASS"
else
    echo -e "${RED}M2M account creation failed${NC}"
    record_result "Create M2M Account" "FAIL"
fi
echo ""

# Step 4: Register server
echo -e "${BLUE}[Step 4] Registering server: ${SERVER_NAME} at ${SERVER_PATH}${NC}"
# Create the JSON file with timestamped path
cat > "${SERVER_JSON_FILE}" <<EOF
{
  "server_name": "Cloudflare Documentation MCP Server ${TIMESTAMP}",
  "description": "Search Cloudflare documentation and get migration guides (test)",
  "path": "${SERVER_PATH}",
  "proxy_pass_url": "https://docs.mcp.cloudflare.com/mcp",
  "supported_transports": ["streamable-http"]
}
EOF

if [ "$VERBOSE" = true ]; then
    ${MGMT_CMD} register --config "${SERVER_JSON_FILE}"
    CREATE_STATUS=$?
else
    ${MGMT_CMD} register --config "${SERVER_JSON_FILE}" > /dev/null 2>&1
    CREATE_STATUS=$?
fi

if [ $CREATE_STATUS -eq 0 ]; then
    echo -e "${GREEN}Server registered successfully at ${SERVER_PATH}${NC}"
    record_result "Register Server" "PASS"
else
    echo -e "${RED}Server registration failed${NC}"
    record_result "Register Server" "FAIL"
fi
echo ""

# Step 5: Register agent
echo -e "${BLUE}[Step 5] Registering agent: ${AGENT_NAME} at ${AGENT_PATH}${NC}"
# Create the JSON file with timestamped path
cat > "${AGENT_JSON_FILE}" <<EOF
{
  "protocolVersion": "0.3.0",
  "name": "Flight Booking Agent ${TIMESTAMP}",
  "description": "Flight booking and reservation management agent (test)",
  "url": "http://flight-booking-agent:9000/",
  "version": "0.0.1",
  "capabilities": {
    "streaming": true
  },
  "defaultInputModes": ["text/plain", "application/json"],
  "defaultOutputModes": ["text/plain", "application/json"],
  "provider": {
    "organization": "Example Corp",
    "url": "https://example-corp.com"
  },
  "skills": [
    {
      "id": "check_availability",
      "name": "Check Availability",
      "description": "Check seat availability for a specific flight.",
      "tags": ["flight", "availability", "booking"]
    },
    {
      "id": "reserve_flight",
      "name": "Reserve Flight",
      "description": "Reserve seats on a flight for passengers.",
      "tags": ["flight", "reservation", "booking"]
    },
    {
      "id": "confirm_booking",
      "name": "Confirm Booking",
      "description": "Confirm and finalize a flight booking.",
      "tags": ["flight", "confirmation", "booking"]
    },
    {
      "id": "process_payment",
      "name": "Process Payment",
      "description": "Process payment for a booking (simulated).",
      "tags": ["payment", "processing", "booking"]
    },
    {
      "id": "manage_reservation",
      "name": "Manage Reservation",
      "description": "Update, view, or cancel existing reservations.",
      "tags": ["reservation", "management", "booking"]
    }
  ],
  "tags": ["travel", "flight-booking", "reservation"],
  "visibility": "public",
  "license": "MIT",
  "path": "${AGENT_PATH}"
}
EOF

if [ "$VERBOSE" = true ]; then
    ${MGMT_CMD} agent-register --config "${AGENT_JSON_FILE}"
    CREATE_STATUS=$?
else
    ${MGMT_CMD} agent-register --config "${AGENT_JSON_FILE}" > /dev/null 2>&1
    CREATE_STATUS=$?
fi

if [ $CREATE_STATUS -eq 0 ]; then
    echo -e "${GREEN}Agent registered successfully at ${AGENT_PATH}${NC}"
    record_result "Register Agent" "PASS"
else
    echo -e "${RED}Agent registration failed${NC}"
    record_result "Register Agent" "FAIL"
fi
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Phase 2: Verification${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 6: List users
echo -e "${BLUE}[Step 6] Listing all users (should include ${HUMAN_USERNAME} and ${M2M_NAME})${NC}"
if [ "$VERBOSE" = true ]; then
    USER_LIST_OUTPUT=$(${MGMT_CMD} user-list 2>&1)
    CREATE_STATUS=$?
    echo "$USER_LIST_OUTPUT"
else
    USER_LIST_OUTPUT=$(${MGMT_CMD} user-list 2>&1)
    CREATE_STATUS=$?
fi

if [ $CREATE_STATUS -eq 0 ]; then
    # Verify our created users are in the list
    if echo "$USER_LIST_OUTPUT" | grep -q "${HUMAN_USERNAME}" && echo "$USER_LIST_OUTPUT" | grep -q "${M2M_NAME}"; then
        echo -e "${GREEN}User list retrieved successfully - verified both test users present${NC}"
        record_result "List Users" "PASS"
    else
        echo -e "${RED}User list retrieved but test users not found${NC}"
        echo -e "${RED}Expected users: ${HUMAN_USERNAME}, ${M2M_NAME}${NC}"
        record_result "List Users" "FAIL"
    fi
else
    echo -e "${RED}User list failed${NC}"
    record_result "List Users" "FAIL"
fi
echo ""

# Step 7: List groups
echo -e "${BLUE}[Step 7] Listing all groups (should include ${GROUP_NAME})${NC}"
if [ "$VERBOSE" = true ]; then
    GROUP_LIST_OUTPUT=$(${MGMT_CMD} group-list 2>&1)
    CREATE_STATUS=$?
    echo "$GROUP_LIST_OUTPUT"
else
    GROUP_LIST_OUTPUT=$(${MGMT_CMD} group-list 2>&1)
    CREATE_STATUS=$?
fi

if [ $CREATE_STATUS -eq 0 ]; then
    # Verify our created group is in the list
    if echo "$GROUP_LIST_OUTPUT" | grep -q "${GROUP_NAME}"; then
        echo -e "${GREEN}Group list retrieved successfully - verified test group present${NC}"
        record_result "List Groups" "PASS"
    else
        echo -e "${RED}Group list retrieved but test group not found${NC}"
        echo -e "${RED}Expected group: ${GROUP_NAME}${NC}"
        record_result "List Groups" "FAIL"
    fi
else
    echo -e "${RED}Group list failed${NC}"
    record_result "List Groups" "FAIL"
fi
echo ""

# Step 8: List servers
echo -e "${BLUE}[Step 8] Listing all servers (should include ${SERVER_NAME})${NC}"
if [ "$VERBOSE" = true ]; then
    SERVER_LIST_OUTPUT=$(${MGMT_CMD} list 2>&1)
    CREATE_STATUS=$?
    echo "$SERVER_LIST_OUTPUT"
else
    SERVER_LIST_OUTPUT=$(${MGMT_CMD} list 2>&1)
    CREATE_STATUS=$?
fi

if [ $CREATE_STATUS -eq 0 ]; then
    # Verify our registered server is in the list (check for the path)
    if echo "$SERVER_LIST_OUTPUT" | grep -q "${SERVER_PATH}"; then
        echo -e "${GREEN}Server list retrieved successfully - verified test server present${NC}"
        record_result "List Servers" "PASS"
    else
        echo -e "${RED}Server list retrieved but test server not found${NC}"
        echo -e "${RED}Expected server path: ${SERVER_PATH}${NC}"
        record_result "List Servers" "FAIL"
    fi
else
    echo -e "${RED}Server list failed${NC}"
    record_result "List Servers" "FAIL"
fi
echo ""

# Step 9: List agents
echo -e "${BLUE}[Step 9] Listing all agents (should include ${AGENT_NAME})${NC}"
if [ "$VERBOSE" = true ]; then
    AGENT_LIST_OUTPUT=$(${MGMT_CMD} agent-list 2>&1)
    CREATE_STATUS=$?
    echo "$AGENT_LIST_OUTPUT"
else
    AGENT_LIST_OUTPUT=$(${MGMT_CMD} agent-list 2>&1)
    CREATE_STATUS=$?
fi

if [ $CREATE_STATUS -eq 0 ]; then
    # Verify our registered agent is in the list (check for the path)
    if echo "$AGENT_LIST_OUTPUT" | grep -q "${AGENT_PATH}"; then
        echo -e "${GREEN}Agent list retrieved successfully - verified test agent present${NC}"
        record_result "List Agents" "PASS"
    else
        echo -e "${RED}Agent list retrieved but test agent not found${NC}"
        echo -e "${RED}Expected agent path: ${AGENT_PATH}${NC}"
        record_result "List Agents" "FAIL"
    fi
else
    echo -e "${RED}Agent list failed${NC}"
    record_result "List Agents" "FAIL"
fi
echo ""

# Step 10: Search for test users
echo -e "${BLUE}[Step 10] Searching for test users${NC}"
if [ "$VERBOSE" = true ]; then
    ${MGMT_CMD} user-list --search "test" --limit 50
    CREATE_STATUS=$?
else
    ${MGMT_CMD} user-list --search "test" --limit 50 > /dev/null 2>&1
    CREATE_STATUS=$?
fi

if [ $CREATE_STATUS -eq 0 ]; then
    echo -e "${GREEN}User search successful${NC}"
    record_result "Search Users" "PASS"
else
    echo -e "${RED}User search failed${NC}"
    record_result "Search Users" "FAIL"
fi
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}All verification steps completed!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Cleanup will run automatically via trap EXIT and display summary
