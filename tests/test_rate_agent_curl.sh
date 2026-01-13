#!/bin/bash

################################################################################
# Test script for the rate_agent function in agent_routes.py
#
# This script demonstrates how to test the rate_agent endpoint using curl
#
# Usage:
#   bash test_rate_agent_curl.sh
#   bash test_rate_agent_curl.sh /path/to/token.json
#   TOKEN_FILE=/path/to/token.json bash test_rate_agent_curl.sh
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
AGENT_PATH="test-reviewer"  # Using existing agent from the registry
USERNAME="admin"
PASSWORD="anrwangAdminPassword"

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
    exit 1
fi

# Extract token from file
TOKEN=$(jq -r '.access_token' "$TOKEN_FILE" 2>/dev/null)

# Validate token exists and is not empty
if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo ""
    echo -e "${RED}✗ ERROR: Failed to extract token from: $TOKEN_FILE${NC}"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ Using token from: $TOKEN_FILE${NC}"
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
# STEP 0: Get authentication token (if token file doesn't exist)
################################################################################
if [ ! -f "$TOKEN_FILE" ]; then
    section "STEP 0: Get Authentication Token"
    
    echo -e "${YELLOW}Token file not found. Attempting to authenticate with credentials...${NC}"
    echo ""
    
    print_cmd "POST /auth/token"
    
    AUTH_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST \
      "$HOST/auth/token" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "username=$USERNAME&password=$PASSWORD")
    
    HTTP_CODE=$(echo "$AUTH_RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
    BODY=$(echo "$AUTH_RESPONSE" | grep -v "HTTP_CODE")
    
    echo -e "${YELLOW}◀ Response (HTTP $HTTP_CODE):${NC}"
    echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
    echo ""
    
    if [ "$HTTP_CODE" = "200" ]; then
        TOKEN=$(echo "$BODY" | jq -r '.access_token' 2>/dev/null)
        if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
            echo -e "${GREEN}✓ Authentication successful!${NC}"
            echo ""
        else
            echo -e "${RED}✗ Failed to extract token from response${NC}"
            echo ""
            exit 1
        fi
    else
        echo -e "${RED}✗ Authentication failed (HTTP $HTTP_CODE)${NC}"
        echo ""
        exit 1
    fi
fi

################################################################################
# STEP 1: List available agents
################################################################################
section "STEP 1: List Available Agents"

print_cmd "GET /api/agents"

RESPONSE=$(curl -s -X GET \
  "$HOST/api/agents" \
  -H "Authorization: Bearer $TOKEN")

print_response "$RESPONSE"

echo -e "${GREEN}Available agents:${NC}"
echo "$RESPONSE" | jq -r '.agents[]? | "  - \(.name) (path: \(.path))"' 2>/dev/null || echo "  No agents found"
echo ""

################################################################################
# STEP 2: Get agent details before rating
################################################################################
section "STEP 2: Get Agent Details (Before Rating)"

print_cmd "GET /api/agents/$AGENT_PATH"

RESPONSE=$(curl -s -X GET \
  "$HOST/api/agents/$AGENT_PATH" \
  -H "Authorization: Bearer $TOKEN")

print_response "$RESPONSE"

CURRENT_RATING=$(echo "$RESPONSE" | jq -r '.num_stars // 0' 2>/dev/null)
echo -e "${GREEN}Current rating: $CURRENT_RATING stars${NC}"
echo ""

################################################################################
# STEP 3: Rate the agent with 5 stars
################################################################################
section "STEP 3: Rate Agent (5 stars)"

print_cmd "POST /api/agents/$AGENT_PATH/rate"

RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST \
  "$HOST/api/agents/$AGENT_PATH/rate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"rating": 5}')

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE")

echo -e "${YELLOW}◀ Response (HTTP $HTTP_CODE):${NC}"
echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ Rating submitted successfully!${NC}"
else
    echo -e "${RED}✗ Failed to submit rating (HTTP $HTTP_CODE)${NC}"
fi

################################################################################
# STEP 4: Get agent rating details
################################################################################
section "STEP 4: Get Agent Rating Details"

print_cmd "GET /api/agents/$AGENT_PATH/rating"

RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X GET \
  "$HOST/api/agents/$AGENT_PATH/rating" \
  -H "Authorization: Bearer $TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE")

echo -e "${YELLOW}◀ Response (HTTP $HTTP_CODE):${NC}"
echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ Rating details retrieved successfully!${NC}"
else
    echo -e "${RED}✗ Failed to get rating details (HTTP $HTTP_CODE)${NC}"
fi

################################################################################
# STEP 5: Rate the agent with 3 stars (update rating)
################################################################################
section "STEP 5: Update Rating (3 stars)"

print_cmd "POST /api/agents/$AGENT_PATH/rate"

RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST \
  "$HOST/api/agents/$AGENT_PATH/rate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"rating": 3}')

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE")

echo -e "${YELLOW}◀ Response (HTTP $HTTP_CODE):${NC}"
echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ Rating updated successfully!${NC}"
else
    echo -e "${RED}✗ Failed to update rating (HTTP $HTTP_CODE)${NC}"
fi

################################################################################
# STEP 6: Verify updated rating
################################################################################
section "STEP 6: Verify Updated Rating"

print_cmd "GET /api/agents/$AGENT_PATH"

RESPONSE=$(curl -s -X GET \
  "$HOST/api/agents/$AGENT_PATH" \
  -H "Authorization: Bearer $TOKEN")

print_response "$RESPONSE"

NEW_RATING=$(echo "$RESPONSE" | jq -r '.num_stars // 0' 2>/dev/null)
echo -e "${GREEN}Updated rating: $NEW_RATING stars${NC}"
echo ""

################################################################################
# STEP 7: Test invalid rating (out of range)
################################################################################
section "STEP 7: Test Invalid Rating (Out of Range)"

print_cmd "POST /api/agents/$AGENT_PATH/rate (rating: 10)"

RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST \
  "$HOST/api/agents/$AGENT_PATH/rate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"rating": 10}')

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE")

echo -e "${YELLOW}◀ Response (HTTP $HTTP_CODE):${NC}"
echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
echo ""

if [ "$HTTP_CODE" = "422" ] || [ "$HTTP_CODE" = "400" ] || [ "$HTTP_CODE" = "500" ]; then
    echo -e "${GREEN}✓ Invalid rating correctly rejected!${NC}"
else
    echo -e "${RED}✗ Invalid rating should have been rejected (HTTP $HTTP_CODE)${NC}"
fi

################################################################################
# STEP 8: Test rating non-existent agent
################################################################################
section "STEP 8: Test Rating Non-Existent Agent"

print_cmd "POST /api/agents/non-existent-agent/rate"

RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST \
  "$HOST/api/agents/non-existent-agent/rate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"rating": 5}')

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE")

echo -e "${YELLOW}◀ Response (HTTP $HTTP_CODE):${NC}"
echo "$BODY" | jq . 2>/dev/null || echo "$BODY"
echo ""

if [ "$HTTP_CODE" = "404" ]; then
    echo -e "${GREEN}✓ Non-existent agent correctly returned 404!${NC}"
else
    echo -e "${RED}✗ Should have returned 404 for non-existent agent (HTTP $HTTP_CODE)${NC}"
fi

################################################################################
# Summary
################################################################################
section "Rate Agent Test Summary"

cat << 'EOF'
What we tested:

1. LIST      - Listed all available agents
2. GET       - Retrieved agent details before rating
3. RATE      - Submitted a 5-star rating
4. GET       - Retrieved rating details
5. UPDATE    - Updated rating to 3 stars
6. VERIFY    - Verified the updated rating
7. INVALID   - Tested invalid rating (out of range)
8. NOT FOUND - Tested rating non-existent agent

Expected behaviors:
✓ Valid ratings (1-5) should return HTTP 200
✓ Invalid ratings should return HTTP 422/400/500
✓ Non-existent agents should return HTTP 404
✓ Ratings should be stored and retrievable
✓ Users can update their own ratings

EOF

echo ""
echo -e "${GREEN}✓ Rate Agent Test Complete!${NC}"
echo ""