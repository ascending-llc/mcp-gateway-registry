#!/bin/bash
#
# Comprehensive Test Suite for MCP Gateway Registry
#
# This script runs all critical tests before PR merge.
# Tests are run against both localhost and production URLs.
#
# Usage:
#   ./run_all_tests.sh [--skip-production]
#
# Options:
#   --skip-production    Skip production URL tests (for local development only)
#
# Exit Codes:
#   0 - All tests passed
#   1 - One or more tests failed
#

# Note: We don't use 'set -e' because we want to continue running all tests
# even if some fail. We track failures manually and exit at the end.

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0

# Configuration
SKIP_PRODUCTION=false
LOCALHOST_URL="http://localhost"
PRODUCTION_URL="https://mcpgateway.ddns.net"
TEST_GROUP_NAME="test-group-$$"
TEST_SERVER_NAME="test-server-$$"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


# Output functions
print_header() {
    echo ""
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_test() {
    echo -e "${YELLOW}[TEST]${NC} $1"
    ((TOTAL_TESTS++))
}

print_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED_TESTS++))
}

print_failure() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED_TESTS++))
}

print_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
    ((SKIPPED_TESTS++))
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}


# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-production)
            SKIP_PRODUCTION=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--skip-production]"
            echo ""
            echo "Options:"
            echo "  --skip-production    Skip production URL tests (for local development)"
            echo "  --help, -h           Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done


print_header "MCP Gateway Registry - Comprehensive Test Suite"
print_info "Started at: $(date)"
print_info "Working directory: $SCRIPT_DIR"
print_info "Skip production: $SKIP_PRODUCTION"


# Test 1: Docker Containers Running
print_header "1. Infrastructure Health Checks"

print_test "Docker containers are running"
if docker ps --filter "name=mcp-gateway-registry" --format "{{.Names}}" | grep -q "registry"; then
    print_success "Docker containers are running"
else
    print_failure "Docker containers are not running"
fi

print_test "Registry service is responding"
if curl -sf http://localhost/health > /dev/null 2>&1; then
    print_success "Registry service is healthy"
else
    print_failure "Registry service is not responding"
fi

print_test "Auth server is responding"
if curl -sf http://localhost:8888/health > /dev/null 2>&1; then
    print_success "Auth server is healthy"
else
    print_failure "Auth server is not responding"
fi


# Test 2: Credentials Generation
print_header "2. Credentials Generation Tests"

print_test "Generate credentials"
if ./credentials-provider/generate_creds.sh > /tmp/creds_output.log 2>&1; then
    print_success "Credentials generated successfully"
else
    print_failure "Failed to generate credentials"
    cat /tmp/creds_output.log
fi

print_test "Verify ingress.json exists"
if [ -f ".oauth-tokens/ingress.json" ]; then
    print_success "ingress.json exists"
else
    print_failure "ingress.json not found"
fi

print_test "Verify ingress.json has valid structure"
if python3 -c "
import json
with open('.oauth-tokens/ingress.json') as f:
    data = json.load(f)
    assert data.get('access_token'), 'No access_token found'
    assert len(data['access_token']) > 100, 'Token too short'
" 2>/dev/null; then
    print_success "ingress.json has valid structure"
else
    print_failure "ingress.json has invalid structure"
fi

print_test "Verify token is not expired"
if python3 -c "
import json, base64, time
from datetime import datetime, timezone
with open('.oauth-tokens/ingress.json') as f:
    token = json.load(f)['access_token']
    parts = token.split('.')
    payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(payload))
    exp = decoded.get('exp', 0)
    assert time.time() < exp, 'Token expired'
" 2>/dev/null; then
    print_success "Token is valid and not expired"
else
    print_failure "Token is expired or invalid"
fi


# Test 3: MCP Client Tests (Localhost)
print_header "3. MCP Client Tests (Localhost)"

print_test "List tools from mcpgw"
if uv run cli/mcp_client.py --url "$LOCALHOST_URL/mcpgw/mcp" list > /tmp/mcp_list.log 2>&1; then
    print_success "Successfully listed tools"
else
    print_failure "Failed to list tools"
    cat /tmp/mcp_list.log
fi

print_test "List all services"
if uv run cli/mcp_client.py --url "$LOCALHOST_URL/mcpgw/mcp" call --tool list_services --args '{}' > /tmp/mcp_list_services.log 2>&1; then
    print_success "Successfully listed services"
else
    print_failure "Failed to list services"
    cat /tmp/mcp_list_services.log
fi

print_test "Health check"
if uv run cli/mcp_client.py --url "$LOCALHOST_URL/mcpgw/mcp" call --tool healthcheck --args '{}' > /tmp/mcp_health.log 2>&1; then
    print_success "Health check passed"
else
    print_failure "Health check failed"
    cat /tmp/mcp_health.log
fi


# Test 4: Agent Tests (Localhost)
print_header "4. Agent Tests (Localhost)"

print_test "Run agent with simple prompt"
if timeout 30 uv run agents/agent.py --prompt "What is the current time?" --model claude-sonnet-4 > /tmp/agent_output.log 2>&1; then
    print_success "Agent executed successfully"
else
    print_failure "Agent execution failed"
    cat /tmp/agent_output.log
fi


# Test 5: Anthropic Registry API v0 Tests (Localhost)
print_header "5. Anthropic Registry API v0 Tests (Localhost)"

print_test "List servers"
if uv run python cli/test_anthropic_api.py --token-file .oauth-tokens/ingress.json --base-url "$LOCALHOST_URL" --test list-servers --limit 5 > /tmp/anthropic_list.log 2>&1; then
    print_success "Successfully listed servers via Anthropic API"
else
    print_failure "Failed to list servers via Anthropic API"
    grep -E "ERROR|FAIL" /tmp/anthropic_list.log | head -10
fi


# Test 6: Service Management CRUD Tests
print_header "6. Service Management CRUD Tests"

# Note: These tests require implementing group/user management commands
# For now, we'll test basic service operations

print_test "Import from Anthropic Registry (dry-run)"
if ./cli/import_from_anthropic_registry.sh --dry-run > /tmp/import_dryrun.log 2>&1; then
    print_success "Import dry-run succeeded"
else
    print_failure "Import dry-run failed"
    tail -20 /tmp/import_dryrun.log
fi


# Test 7: Code Quality Tests
print_header "7. Code Quality Tests"

print_test "Python syntax validation (anthropic_transformer.py)"
if uv run python -m py_compile cli/anthropic_transformer.py 2>/dev/null; then
    print_success "anthropic_transformer.py has valid syntax"
else
    print_failure "anthropic_transformer.py has syntax errors"
fi

print_test "Python syntax validation (test_anthropic_api.py)"
if uv run python -m py_compile cli/test_anthropic_api.py 2>/dev/null; then
    print_success "test_anthropic_api.py has valid syntax"
else
    print_failure "test_anthropic_api.py has syntax errors"
fi

print_test "Bash syntax validation (import_from_anthropic_registry.sh)"
if bash -n cli/import_from_anthropic_registry.sh 2>/dev/null; then
    print_success "import_from_anthropic_registry.sh has valid syntax"
else
    print_failure "import_from_anthropic_registry.sh has syntax errors"
fi

print_test "Bash syntax validation (service_mgmt.sh)"
if bash -n cli/service_mgmt.sh 2>/dev/null; then
    print_success "service_mgmt.sh has valid syntax"
else
    print_failure "service_mgmt.sh has syntax errors"
fi


# Test 8: Production URL Tests (if not skipped)
if [ "$SKIP_PRODUCTION" = false ]; then
    print_header "8. Production URL Tests (MANDATORY FOR PR MERGE)"

    print_test "MCP Client list tools (production)"
    if GATEWAY_URL="$PRODUCTION_URL" timeout 30 uv run cli/mcp_client.py --url "$PRODUCTION_URL/mcpgw/mcp" list > /tmp/prod_mcp_list.log 2>&1; then
        print_success "Successfully listed tools from production"
    else
        print_failure "Failed to list tools from production"
        cat /tmp/prod_mcp_list.log
    fi

    print_test "List services (production)"
    if GATEWAY_URL="$PRODUCTION_URL" timeout 30 uv run cli/mcp_client.py --url "$PRODUCTION_URL/mcpgw/mcp" call --tool list_services --args '{}' > /tmp/prod_services.log 2>&1; then
        print_success "Successfully listed services from production"
    else
        print_failure "Failed to list services from production"
        cat /tmp/prod_services.log
    fi

    print_test "Anthropic API list servers (production)"
    if uv run python cli/test_anthropic_api.py --token-file .oauth-tokens/ingress.json --base-url "$PRODUCTION_URL" --test list-servers --limit 5 > /tmp/prod_anthropic.log 2>&1; then
        print_success "Successfully listed servers via Anthropic API (production)"
    else
        print_failure "Failed to list servers via Anthropic API (production)"
        grep -E "ERROR|FAIL|expired" /tmp/prod_anthropic.log | head -10
    fi

    print_test "Agent execution (production)"
    if GATEWAY_URL="$PRODUCTION_URL" timeout 30 uv run agents/agent.py --prompt "What is 2+2?" --model claude-sonnet-4 > /tmp/prod_agent.log 2>&1; then
        print_success "Agent executed successfully (production)"
    else
        print_failure "Agent execution failed (production)"
        tail -20 /tmp/prod_agent.log
    fi
else
    print_header "8. Production URL Tests"
    print_skip "Production tests skipped (--skip-production flag used)"
    print_info "WARNING: Production tests are MANDATORY for PR merge!"
fi


# Test 9: Configuration Validation
print_header "9. Configuration Validation"

print_test "Nginx configuration is valid"
if docker exec mcp-gateway-registry-registry-1 nginx -t > /tmp/nginx_test.log 2>&1; then
    print_success "Nginx configuration is valid"
else
    print_failure "Nginx configuration has errors"
    cat /tmp/nginx_test.log
fi

print_test "Required environment files exist"
if [ -f ".env" ] || [ -f "docker/.env" ]; then
    print_success "Environment files exist"
else
    print_failure "Environment files not found"
fi


# Final Summary
print_header "Test Summary"

echo ""
echo "Total Tests:   $TOTAL_TESTS"
echo -e "${GREEN}Passed Tests:  $PASSED_TESTS${NC}"
echo -e "${RED}Failed Tests:  $FAILED_TESTS${NC}"
echo -e "${YELLOW}Skipped Tests: $SKIPPED_TESTS${NC}"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}ALL TESTS PASSED!${NC}"
    echo -e "${GREEN}============================================================${NC}"
    if [ "$SKIP_PRODUCTION" = true ]; then
        echo -e "${YELLOW}WARNING: Production tests were skipped.${NC}"
        echo -e "${YELLOW}Run without --skip-production flag for PR merge.${NC}"
    fi
    exit 0
else
    echo -e "${RED}============================================================${NC}"
    echo -e "${RED}TESTS FAILED!${NC}"
    echo -e "${RED}============================================================${NC}"
    echo ""
    echo "Please fix the failing tests before merging PR."
    echo ""
    echo "Log files available in /tmp:"
    echo "  - /tmp/creds_output.log"
    echo "  - /tmp/mcp_*.log"
    echo "  - /tmp/agent_output.log"
    echo "  - /tmp/anthropic_*.log"
    echo "  - /tmp/prod_*.log"
    echo ""
    exit 1
fi
