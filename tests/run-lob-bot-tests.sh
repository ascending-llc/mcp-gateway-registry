#!/bin/bash

REPO="/home/ubuntu/repos/mcp-gateway-registry"
cd "$REPO"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

echo ""
echo "=========================================="
echo "LOB Bot Access Control Testing"
echo "=========================================="
echo ""

# Ensure we have the token files
if [ ! -f ".oauth-tokens/lob1-bot-token.json" ]; then
    echo -e "${RED}Error: LOB1 bot token not found at .oauth-tokens/lob1-bot-token.json${NC}"
    echo ""
    echo "Please regenerate the tokens using:"
    echo "  ./keycloak/setup/generate-agent-token.sh lob1-bot"
    echo "  ./keycloak/setup/generate-agent-token.sh lob2-bot"
    echo "  ./keycloak/setup/generate-agent-token.sh admin-bot"
    exit 1
fi

echo -e "${BLUE}=== PART 1: MCP SERVICE ACCESS TESTS (Tests 1-6) ===${NC}"
echo ""

# Test 1: LOB1 - Access Allowed (currenttime)
echo -e "${GREEN}Test 1: LOB1 Bot - Access currenttime (SHOULD SUCCEED)${NC}"
echo ""
if uv run python cli/mcp_client.py \
  --url http://localhost/currenttime/mcp \
  --token-file .oauth-tokens/lob1-bot-token.json \
  call \
  --tool current_time_by_timezone \
  --args '{"timezone": "America/New_York"}' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Test 1 PASSED${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ Test 1 FAILED${NC}"
    ((TESTS_FAILED++))
fi
echo ""
echo "=========================================="
echo ""

# Test 2: LOB1 - Access Allowed (mcpgw)
echo -e "${GREEN}Test 2: LOB1 Bot - Find tools via mcpgw (SHOULD SUCCEED)${NC}"
echo ""
if uv run python cli/mcp_client.py \
  --url http://localhost/mcpgw/mcp \
  --token-file .oauth-tokens/lob1-bot-token.json \
  call \
  --tool intelligent_tool_finder \
  --args '{"natural_language_query": "get current time in New York"}' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Test 2 PASSED${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ Test 2 FAILED${NC}"
    ((TESTS_FAILED++))
fi
echo ""
echo "=========================================="
echo ""

# Test 3: LOB1 - Access Denied (fininfo)
echo -e "${YELLOW}Test 3: LOB1 Bot - Access fininfo (SHOULD BE DENIED)${NC}"
echo ""
if uv run python cli/mcp_client.py \
  --url http://localhost/fininfo/mcp \
  --token-file .oauth-tokens/lob1-bot-token.json \
  call \
  --tool get_stock_aggregates \
  --args '{"ticker": "AAPL", "timespan": "day", "from": "2025-01-01", "to": "2025-01-31"}' > /dev/null 2>&1; then
    echo -e "${RED}✗ Test 3 FAILED - Access should have been denied!${NC}"
    ((TESTS_FAILED++))
else
    echo -e "${GREEN}✓ Test 3 PASSED - Access correctly denied${NC}"
    ((TESTS_PASSED++))
fi
echo ""
echo "=========================================="
echo ""

# Test 4: LOB1 - Access Denied (realserverfaketools)
echo -e "${YELLOW}Test 4: LOB1 Bot - Access realserverfaketools (SHOULD BE DENIED)${NC}"
echo ""
if uv run python cli/mcp_client.py \
  --url http://localhost/realserverfaketools/mcp \
  --token-file .oauth-tokens/lob1-bot-token.json \
  call \
  --tool quantum_flux_analyzer \
  --args '{"input_data": "test"}' > /dev/null 2>&1; then
    echo -e "${RED}✗ Test 4 FAILED - Access should have been denied!${NC}"
    ((TESTS_FAILED++))
else
    echo -e "${GREEN}✓ Test 4 PASSED - Access correctly denied${NC}"
    ((TESTS_PASSED++))
fi
echo ""
echo "=========================================="
echo ""

# Test 5: LOB2 - Access Allowed (fininfo)
if [ -f ".oauth-tokens/lob2-bot-token.json" ]; then
    echo -e "${GREEN}Test 5: LOB2 Bot - Access fininfo (SHOULD SUCCEED)${NC}"
    echo ""
    if uv run python cli/mcp_client.py \
      --url http://localhost/fininfo/mcp \
      --token-file .oauth-tokens/lob2-bot-token.json \
      call \
      --tool get_stock_aggregates \
      --args '{"ticker": "GOOGL", "timespan": "day", "from": "2025-01-01", "to": "2025-01-31"}' > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Test 5 PASSED${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ Test 5 FAILED${NC}"
        ((TESTS_FAILED++))
    fi
    echo ""
    echo "=========================================="
    echo ""

    # Test 6: LOB2 - Access Denied (currenttime)
    echo -e "${YELLOW}Test 6: LOB2 Bot - Access currenttime (SHOULD BE DENIED)${NC}"
    echo ""
    if uv run python cli/mcp_client.py \
      --url http://localhost/currenttime/mcp \
      --token-file .oauth-tokens/lob2-bot-token.json \
      call \
      --tool current_time_by_timezone \
      --args '{"timezone": "Europe/London"}' > /dev/null 2>&1; then
        echo -e "${RED}✗ Test 6 FAILED - Access should have been denied!${NC}"
        ((TESTS_FAILED++))
    else
        echo -e "${GREEN}✓ Test 6 PASSED - Access correctly denied${NC}"
        ((TESTS_PASSED++))
    fi
    echo ""
    echo "=========================================="
    echo ""
else
    echo -e "${YELLOW}Skipping Tests 5-6 (LOB2 token not found)${NC}"
    echo ""
fi

echo ""
echo -e "${BLUE}=== PART 2: AGENT REGISTRY API TESTS (Tests 7-14) ===${NC}"
echo ""

# Test 7: LOB1 - List Agents (Should only see assigned agents)
echo -e "${GREEN}Test 7: LOB1 Bot - List agents (SHOULD ONLY SEE /code-reviewer, /test-automation)${NC}"
echo ""
AGENTS=$(curl -s -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/lob1-bot-token.json)" \
  http://localhost/api/agents 2>/dev/null | jq -r '.agents[]? | .path' | sort)

if echo "$AGENTS" | grep -q "/code-reviewer" && echo "$AGENTS" | grep -q "/test-automation"; then
    if echo "$AGENTS" | grep -q "/data-analysis" || echo "$AGENTS" | grep -q "/security-analyzer"; then
        echo -e "${RED}✗ Test 7 FAILED - LOB1 can see agents they shouldn't${NC}"
        echo "Agents seen: $AGENTS"
        ((TESTS_FAILED++))
    else
        echo -e "${GREEN}✓ Test 7 PASSED - LOB1 sees only assigned agents${NC}"
        echo "Agents: $AGENTS"
        ((TESTS_PASSED++))
    fi
else
    echo -e "${RED}✗ Test 7 FAILED - LOB1 missing assigned agents${NC}"
    echo "Agents seen: $AGENTS"
    ((TESTS_FAILED++))
fi
echo ""
echo "=========================================="
echo ""

# Test 8: LOB1 - Get assigned agent (should succeed)
echo -e "${GREEN}Test 8: LOB1 Bot - Get assigned agent /code-reviewer (SHOULD SUCCEED)${NC}"
echo ""
HTTP_CODE=$(curl -s -w "%{http_code}" -o /tmp/test8_response.json \
  -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/lob1-bot-token.json)" \
  http://localhost/api/agents/code-reviewer 2>/dev/null)

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✓ Test 8 PASSED - LOB1 can access /code-reviewer (HTTP $HTTP_CODE)${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ Test 8 FAILED - Got HTTP $HTTP_CODE, expected 200${NC}"
    ((TESTS_FAILED++))
fi
echo ""
echo "=========================================="
echo ""

# Test 9: LOB1 - Get non-assigned agent (should fail)
echo -e "${YELLOW}Test 9: LOB1 Bot - Get non-assigned agent /data-analysis (SHOULD BE DENIED)${NC}"
echo ""
HTTP_CODE=$(curl -s -w "%{http_code}" -o /tmp/test9_response.json \
  -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/lob1-bot-token.json)" \
  http://localhost/api/agents/data-analysis 2>/dev/null)

if [ "$HTTP_CODE" = "403" ] || [ "$HTTP_CODE" = "404" ]; then
    echo -e "${GREEN}✓ Test 9 PASSED - LOB1 cannot access /data-analysis (HTTP $HTTP_CODE)${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ Test 9 FAILED - Got HTTP $HTTP_CODE, expected 403 or 404${NC}"
    ((TESTS_FAILED++))
fi
echo ""
echo "=========================================="
echo ""

# Test 10: LOB2 - List Agents (Should only see assigned agents)
if [ -f ".oauth-tokens/lob2-bot-token.json" ]; then
    echo -e "${GREEN}Test 10: LOB2 Bot - List agents (SHOULD ONLY SEE /data-analysis, /security-analyzer)${NC}"
    echo ""
    AGENTS=$(curl -s -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/lob2-bot-token.json)" \
      http://localhost/api/agents 2>/dev/null | jq -r '.agents[]? | .path' | sort)

    if echo "$AGENTS" | grep -q "/data-analysis" && echo "$AGENTS" | grep -q "/security-analyzer"; then
        if echo "$AGENTS" | grep -q "/code-reviewer" || echo "$AGENTS" | grep -q "/test-automation"; then
            echo -e "${RED}✗ Test 10 FAILED - LOB2 can see agents they shouldn't${NC}"
            echo "Agents seen: $AGENTS"
            ((TESTS_FAILED++))
        else
            echo -e "${GREEN}✓ Test 10 PASSED - LOB2 sees only assigned agents${NC}"
            echo "Agents: $AGENTS"
            ((TESTS_PASSED++))
        fi
    else
        echo -e "${RED}✗ Test 10 FAILED - LOB2 missing assigned agents${NC}"
        echo "Agents seen: $AGENTS"
        ((TESTS_FAILED++))
    fi
    echo ""
    echo "=========================================="
    echo ""

    # Test 11: LOB2 - Get assigned agent (should succeed)
    echo -e "${GREEN}Test 11: LOB2 Bot - Get assigned agent /data-analysis (SHOULD SUCCEED)${NC}"
    echo ""
    HTTP_CODE=$(curl -s -w "%{http_code}" -o /tmp/test11_response.json \
      -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/lob2-bot-token.json)" \
      http://localhost/api/agents/data-analysis 2>/dev/null)

    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓ Test 11 PASSED - LOB2 can access /data-analysis (HTTP $HTTP_CODE)${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ Test 11 FAILED - Got HTTP $HTTP_CODE, expected 200${NC}"
        ((TESTS_FAILED++))
    fi
    echo ""
    echo "=========================================="
    echo ""

    # Test 12: LOB2 - Get non-assigned agent (should fail)
    echo -e "${YELLOW}Test 12: LOB2 Bot - Get non-assigned agent /code-reviewer (SHOULD BE DENIED)${NC}"
    echo ""
    HTTP_CODE=$(curl -s -w "%{http_code}" -o /tmp/test12_response.json \
      -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/lob2-bot-token.json)" \
      http://localhost/api/agents/code-reviewer 2>/dev/null)

    if [ "$HTTP_CODE" = "403" ] || [ "$HTTP_CODE" = "404" ]; then
        echo -e "${GREEN}✓ Test 12 PASSED - LOB2 cannot access /code-reviewer (HTTP $HTTP_CODE)${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ Test 12 FAILED - Got HTTP $HTTP_CODE, expected 403 or 404${NC}"
        ((TESTS_FAILED++))
    fi
    echo ""
    echo "=========================================="
    echo ""
else
    echo -e "${YELLOW}Skipping Tests 10-12 (LOB2 token not found)${NC}"
    echo ""
fi

# Test 13: Admin - List Agents (Should see all agents)
if [ -f ".oauth-tokens/admin-bot-token.json" ]; then
    echo -e "${GREEN}Test 13: Admin Bot - List agents (SHOULD SEE ALL AGENTS)${NC}"
    echo ""
    AGENT_COUNT=$(curl -s -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/admin-bot-token.json)" \
      http://localhost/api/agents 2>/dev/null | jq '.agents | length')

    if [ "$AGENT_COUNT" -ge 2 ]; then
        echo -e "${GREEN}✓ Test 13 PASSED - Admin can see all agents (count: $AGENT_COUNT)${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ Test 13 FAILED - Admin should see all agents, got count: $AGENT_COUNT${NC}"
        ((TESTS_FAILED++))
    fi
    echo ""
    echo "=========================================="
    echo ""

    # Test 14: Admin - Get any agent (should succeed)
    echo -e "${GREEN}Test 14: Admin Bot - Get any agent (SHOULD SUCCEED)${NC}"
    echo ""
    HTTP_CODE=$(curl -s -w "%{http_code}" -o /tmp/test14_response.json \
      -H "Authorization: Bearer $(jq -r '.access_token' .oauth-tokens/admin-bot-token.json)" \
      http://localhost/api/agents/code-reviewer 2>/dev/null)

    if [ "$HTTP_CODE" = "200" ]; then
        echo -e "${GREEN}✓ Test 14 PASSED - Admin can access any agent (HTTP $HTTP_CODE)${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}✗ Test 14 FAILED - Got HTTP $HTTP_CODE, expected 200${NC}"
        ((TESTS_FAILED++))
    fi
    echo ""
    echo "=========================================="
    echo ""
else
    echo -e "${YELLOW}Skipping Tests 13-14 (Admin token not found)${NC}"
    echo "To test admin agent access, run: ./keycloak/setup/generate-agent-token.sh admin-bot"
    echo ""
fi

# Final summary
echo ""
echo -e "${BLUE}=========================================="
echo "Test Summary"
echo "==========================================${NC}"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests PASSED!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests FAILED!${NC}"
    exit 1
fi
