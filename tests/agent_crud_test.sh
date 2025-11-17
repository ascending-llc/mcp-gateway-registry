#!/bin/bash

################################################################################
# Simple A2A Agent CRUD Test Script
#
# This script demonstrates basic CRUD operations on a single agent
# Easy to run and see output for learning purposes
#
# Usage:
#   bash tests/agent_crud_test.sh
#   bash tests/agent_crud_test.sh /path/to/token.json
#   TOKEN_FILE=/path/to/token.json bash tests/agent_crud_test.sh
#
# Token Resolution (in order of precedence):
#   1. Command-line argument (first parameter)
#   2. TOKEN_FILE environment variable
#   3. Default: .oauth-tokens/admin-bot-token.json
#
# Note: Requires Docker containers running (docker-compose up -d)
#       API accessible via Nginx reverse proxy on port 80
################################################################################

# Configuration
HOST="http://localhost"
AGENT_PATH="code-reviewer"
FULL_PATH="/code-reviewer"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

################################################################################
# Token Resolution and Validation
################################################################################

TOKEN=""
TOKEN_FILE=""

# Check command-line argument first
if [ -n "$1" ]; then
    TOKEN_FILE="$1"
# Check environment variable second
elif [ -n "$TOKEN_FILE" ]; then
    TOKEN_FILE="$TOKEN_FILE"
# Use default
else
    TOKEN_FILE=".oauth-tokens/admin-bot-token.json"
fi

# Verify token file exists
if [ ! -f "$TOKEN_FILE" ]; then
    echo ""
    echo -e "${RED}✗ ERROR: Token file not found!${NC}"
    echo ""
    echo "Looked for: $TOKEN_FILE"
    echo ""
    echo -e "${YELLOW}To generate a token, run:${NC}"
    echo "  ./keycloak/setup/generate-agent-token.sh admin-bot"
    echo ""
    echo "Then either:"
    echo "  bash tests/agent_crud_test.sh                              # Uses default .oauth-tokens/admin-bot-token.json"
    echo "  bash tests/agent_crud_test.sh /path/to/token.json         # With custom path"
    echo "  TOKEN_FILE=/path/to/token.json bash tests/agent_crud_test.sh  # With env variable"
    echo ""
    echo "Note: Tokens expire after 5 minutes and must be regenerated before testing"
    echo ""
    exit 1
fi

# Extract token from file
TOKEN=$(jq -r '.access_token' "$TOKEN_FILE" 2>/dev/null)

# Validate token exists and is not empty
if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo ""
    echo -e "${RED}✗ ERROR: Failed to extract token from: $TOKEN_FILE${NC}"
    echo ""
    echo "The file exists but does not contain a valid 'access_token' field"
    echo ""
    echo -e "${YELLOW}To generate a fresh token, run:${NC}"
    echo "  ./keycloak/setup/generate-agent-token.sh admin-bot"
    echo ""
    echo "Note: Tokens expire after 5 minutes and must be regenerated before testing"
    echo ""
    exit 1
fi

# Decode JWT token to check expiration
# JWT format: header.payload.signature
PAYLOAD=$(echo "$TOKEN" | cut -d'.' -f2)

# Add padding if needed for base64 decoding
padding=$((${#PAYLOAD} % 4))
if [ $padding -gt 0 ]; then
    PAYLOAD="${PAYLOAD}$(printf '%*s' $((4 - padding)) | tr ' ' '=')"
fi

# Decode the payload
DECODED=$(echo "$PAYLOAD" | base64 -d 2>/dev/null)

if [ -z "$DECODED" ]; then
    echo ""
    echo -e "${RED}✗ ERROR: Failed to decode JWT token!${NC}"
    echo ""
    echo "This usually means the token is malformed or corrupted."
    echo ""
    echo -e "${YELLOW}To generate a fresh token, run:${NC}"
    echo "  ./keycloak/setup/generate-agent-token.sh admin-bot"
    echo ""
    exit 1
fi

# Extract expiration time (exp claim in seconds since epoch)
EXP=$(echo "$DECODED" | jq -r '.exp' 2>/dev/null)

if [ -z "$EXP" ] || [ "$EXP" = "null" ]; then
    echo ""
    echo -e "${RED}✗ ERROR: Token does not contain expiration info!${NC}"
    echo ""
    echo -e "${YELLOW}To generate a fresh token, run:${NC}"
    echo "  ./keycloak/setup/generate-agent-token.sh admin-bot"
    echo ""
    exit 1
fi

# Check if token is expired
CURRENT_TIME=$(date +%s)
TIME_REMAINING=$((EXP - CURRENT_TIME))

if [ $TIME_REMAINING -lt 0 ]; then
    echo ""
    echo -e "${RED}✗ ERROR: Authentication token has EXPIRED!${NC}"
    echo ""
    echo "Token expired $((-TIME_REMAINING)) seconds ago"
    echo ""
    echo -e "${YELLOW}To generate a fresh token, run:${NC}"
    echo "  ./keycloak/setup/generate-agent-token.sh admin-bot"
    echo ""
    echo "Note: Tokens expire after 5 minutes and must be regenerated before testing"
    echo ""
    exit 1
fi

# Warn if token is expiring soon (less than 30 seconds)
if [ $TIME_REMAINING -lt 30 ]; then
    echo ""
    echo -e "${YELLOW}⚠ WARNING: Token expires in $TIME_REMAINING seconds!${NC}"
    echo ""
    echo "Consider regenerating the token:"
    echo "  ./keycloak/setup/generate-agent-token.sh admin-bot"
    echo ""
fi

echo -e "${GREEN}✓ Using token from: $TOKEN_FILE${NC}"
echo -e "${GREEN}✓ Token valid for $TIME_REMAINING more seconds${NC}"
echo ""

# Helper function to print sections
section() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║ $1${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Helper function to print commands
print_cmd() {
    echo -e "${YELLOW}▶ Command:${NC}"
    echo "  $1"
    echo ""
}

# Helper function to print responses
print_response() {
    echo -e "${YELLOW}◀ Response:${NC}"
    echo "$1" | jq . 2>/dev/null || echo "$1"
    echo ""
}

################################################################################
# STEP 1: CREATE (Register) an Agent
################################################################################
section "STEP 1: CREATE - Register an Agent"

print_cmd "POST /api/agents/register"

RESPONSE=$(curl -s -X POST \
  "$HOST/api/agents/register" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "protocol_version": "1.0",
    "name": "Code Reviewer Agent",
    "description": "Reviews code for quality and best practices",
    "url": "https://code-reviewer.example.com",
    "path": "'"$FULL_PATH"'",
    "skills": [
      {
        "id": "review-python",
        "name": "Python Code Review",
        "description": "Reviews Python code",
        "parameters": {
          "code_snippet": {"type": "string"}
        },
        "tags": ["python", "review"]
      }
    ],
    "security_schemes": {
      "bearer": {"type": "bearer", "description": "Bearer token"}
    },
    "security": ["bearer"],
    "tags": ["code-review", "qa"],
    "visibility": "public",
    "trust_level": "verified"
  }')

print_response "$RESPONSE"

# Check if successful
if echo "$RESPONSE" | jq -e '.path' >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Agent created successfully!${NC}"
else
    echo -e "${RED}✗ Failed to create agent${NC}"
fi

################################################################################
# STEP 2: READ (Retrieve) the Agent
################################################################################
section "STEP 2: READ - Retrieve the Agent"

print_cmd "GET /api/agents/$AGENT_PATH"

RESPONSE=$(curl -s -X GET \
  "$HOST/api/agents/$AGENT_PATH" \
  -H "Authorization: Bearer $TOKEN")

print_response "$RESPONSE"

if echo "$RESPONSE" | jq -e '.name' >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Agent retrieved successfully!${NC}"
else
    echo -e "${RED}✗ Failed to retrieve agent${NC}"
fi

################################################################################
# STEP 3: UPDATE the Agent
################################################################################
section "STEP 3: UPDATE - Modify the Agent"

print_cmd "PUT /api/agents/$AGENT_PATH"

RESPONSE=$(curl -s -X PUT \
  "$HOST/api/agents/$AGENT_PATH" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "description": "Reviews code for quality, style, and security issues",
    "tags": ["code-review", "qa", "security"]
  }')

print_response "$RESPONSE"

if echo "$RESPONSE" | jq -e '.description' >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Agent updated successfully!${NC}"
else
    echo -e "${RED}✗ Failed to update agent${NC}"
fi

################################################################################
# STEP 4: LIST (Read all) Agents
################################################################################
section "STEP 4: LIST - Get All Agents"

print_cmd "GET /api/agents"

RESPONSE=$(curl -s -X GET \
  "$HOST/api/agents" \
  -H "Authorization: Bearer $TOKEN")

print_response "$RESPONSE"

if echo "$RESPONSE" | jq -e '.' >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Agents listed successfully!${NC}"
else
    echo -e "${RED}✗ Failed to list agents${NC}"
fi

################################################################################
# STEP 5: DISABLE the Agent
################################################################################
section "STEP 5: TOGGLE - Disable the Agent"

print_cmd "POST /api/agents/$AGENT_PATH/toggle"

RESPONSE=$(curl -s -X POST \
  "$HOST/api/agents/$AGENT_PATH/toggle" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"enabled": false}')

print_response "$RESPONSE"

echo -e "${GREEN}✓ Agent disabled!${NC}"

################################################################################
# STEP 6: RE-ENABLE the Agent
################################################################################
section "STEP 6: TOGGLE - Re-enable the Agent"

print_cmd "POST /api/agents/$AGENT_PATH/toggle"

RESPONSE=$(curl -s -X POST \
  "$HOST/api/agents/$AGENT_PATH/toggle" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"enabled": true}')

print_response "$RESPONSE"

echo -e "${GREEN}✓ Agent re-enabled!${NC}"

################################################################################
# STEP 7: DELETE the Agent
################################################################################
section "STEP 7: DELETE - Remove the Agent"

print_cmd "DELETE /api/agents/$AGENT_PATH"

RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X DELETE \
  "$HOST/api/agents/$AGENT_PATH" \
  -H "Authorization: Bearer $TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE")

echo -e "${YELLOW}◀ Response (HTTP $HTTP_CODE):${NC}"
if [ -z "$BODY" ] || [ "$BODY" = "" ]; then
    echo "  (No response body - expected for DELETE)"
else
    echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
fi
echo ""

if [ "$HTTP_CODE" = "204" ]; then
    echo -e "${GREEN}✓ Agent deleted successfully! (HTTP 204)${NC}"
else
    echo -e "${RED}✗ Delete may have failed (HTTP $HTTP_CODE)${NC}"
fi

################################################################################
# STEP 8: VERIFY Deletion
################################################################################
section "STEP 8: VERIFY - Confirm Deletion"

print_cmd "GET /api/agents/$AGENT_PATH (should return 404)"

RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X GET \
  "$HOST/api/agents/$AGENT_PATH" \
  -H "Authorization: Bearer $TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE")

echo -e "${YELLOW}◀ Response (HTTP $HTTP_CODE):${NC}"
echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
echo ""

if [ "$HTTP_CODE" = "404" ]; then
    echo -e "${GREEN}✓ Agent confirmed deleted! (HTTP 404 - Not Found)${NC}"
else
    echo -e "${RED}✗ Agent still exists (HTTP $HTTP_CODE)${NC}"
fi

################################################################################
# STEP 9: RE-CREATE the Agent (Restore to Clean State)
################################################################################
section "STEP 9: RE-CREATE - Restore Agent to Clean State"

print_cmd "POST /api/agents/register"

RESPONSE=$(curl -s -X POST \
  "$HOST/api/agents/register" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{\n    "protocol_version": "1.0",\n    "name": "Code Reviewer Agent",\n    "description": "Reviews code for quality and best practices",\n    "url": "https://code-reviewer.example.com",\n    "path": "'"$FULL_PATH"'",\n    "skills": [\n      {\n        "id": "review-python",\n        "name": "Python Code Review",\n        "description": "Reviews Python code",\n        "parameters": {\n          "code_snippet": {"type": "string"}\n        },\n        "tags": ["python", "review"]\n      }\n    ],\n    "security_schemes": {\n      "bearer": {"type": "bearer", "description": "Bearer token"}\n    },\n    "security": ["bearer"],\n    "tags": ["code-review", "qa"],\n    "visibility": "public",\n    "trust_level": "verified"\n  }')

print_response "$RESPONSE"

if echo "$RESPONSE" | jq -e '.path' >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Agent re-created successfully!${NC}"
else
    echo -e "${RED}✗ Failed to re-create agent${NC}"
fi

################################################################################
# Summary
################################################################################
section "CRUD Operations Summary"

cat << 'EOF'
What we just did:

1. CREATE    - Registered a new agent (/agents/code-reviewer)
2. READ      - Retrieved the agent details
3. UPDATE    - Modified the agent description and tags
4. LIST      - Listed all agents
5. TOGGLE    - Disabled the agent
6. TOGGLE    - Re-enabled the agent
7. DELETE    - Removed the agent
8. VERIFY    - Confirmed the agent no longer exists
9. RE-CREATE - Restored the agent to clean state

All operations shown with actual HTTP requests and responses!
The agent is now registered and ready for use.

Next steps:
- Check files: cat registry/agents/agent_state.json | jq .
- Run tests: uv run pytest tests/unit/agents/test_agent_endpoints.py -v
- Start app: python -m uvicorn registry.main:app --reload

EOF

echo ""
echo -e "${GREEN}✓ CRUD Test Complete!${NC}"
echo ""
