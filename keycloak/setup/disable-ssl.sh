#!/bin/bash

# Script to disable SSL requirement for Keycloak realms
# This allows both HTTP and HTTPS connections without requiring HTTPS
#
# Usage:
#   ./disable-ssl.sh                          # Uses AWS Secrets Manager to fetch password
#   ./disable-ssl.sh "your-password"          # Uses provided password
#   KEYCLOAK_URL=http://custom:8080 ./disable-ssl.sh
#   VERBOSE=1 ./disable-ssl.sh               # Enable verbose logging with password display
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - jq installed for JSON processing
#   - curl installed for API requests
#   - Keycloak running and accessible

set -e

# Configure logging with basicConfig
logging_format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
AWS_REGION="${AWS_REGION:-us-east-1}"
KEYCLOAK_ADMIN_PASSWORD="${1:-}"
VERBOSE="${VERBOSE:-0}"

log_info() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

log_debug() {
    if [[ "$VERBOSE" == "1" ]]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

log_trace() {
    if [[ "$VERBOSE" == "1" ]]; then
        echo -e "${BLUE}[TRACE]${NC} $1"
    fi
}

_fetch_keycloak_password_from_secrets_manager() {
    local secret_name
    local secret_value
    local raw_response

    log_info "Fetching Keycloak admin password from AWS Secrets Manager..." >&2
    log_debug "AWS Region: $AWS_REGION" >&2
    log_debug "Searching for secrets matching pattern: mcp-gateway-keycloak-admin-password" >&2

    # Get the secret name that matches the pattern
    log_trace "Executing: aws secretsmanager list-secrets --region $AWS_REGION --filters Key=name,Values=mcp-gateway-keycloak-admin-password" >&2
    secret_name=$(aws secretsmanager list-secrets \
        --region "$AWS_REGION" \
        --filters Key=name,Values="mcp-gateway-keycloak-admin-password" \
        --query 'SecretList[0].Name' \
        --output text)

    log_debug "Secret name lookup result: $secret_name" >&2

    if [[ -z "$secret_name" || "$secret_name" == "None" ]]; then
        log_error "Could not find Keycloak admin password secret in AWS Secrets Manager" >&2
        echo "Searched for secrets matching pattern: mcp-gateway-keycloak-admin-password" >&2
        echo "" >&2
        echo "Available secrets:" >&2
        log_trace "Executing: aws secretsmanager list-secrets --region $AWS_REGION" >&2
        aws secretsmanager list-secrets --region "$AWS_REGION" --query 'SecretList[].Name' --output text >&2
        return 1
    fi

    log_info "Found secret: $secret_name" >&2
    log_debug "Retrieving secret value from: $secret_name" >&2

    # Get the secret value directly using jq query
    if [[ "$VERBOSE" == "1" ]]; then
        log_trace "Executing: aws secretsmanager get-secret-value --secret-id $secret_name --region $AWS_REGION --query SecretString --output text" >&2
    fi

    secret_value=$(aws secretsmanager get-secret-value \
        --secret-id "$secret_name" \
        --region "$AWS_REGION" \
        --query 'SecretString' \
        --output text)

    # Remove any trailing newlines or whitespace
    secret_value="$(echo -n "$secret_value")"

    log_debug "Secret value retrieved (length: ${#secret_value} characters)" >&2

    if [[ -z "$secret_value" ]]; then
        log_error "Failed to retrieve SecretString from AWS response" >&2
        log_error "Secret name was: $secret_name" >&2
        return 1
    fi

    if [[ "$VERBOSE" == "1" ]]; then
        echo "[TRACE] Keycloak admin password (first 4 chars): ${secret_value:0:4}***" >&2
        echo "[TRACE] Keycloak admin password (full): $secret_value" >&2
        echo "[TRACE] Password length verified: ${#secret_value} characters" >&2
    fi

    echo "$secret_value"
}

_extract_hostname_from_url() {
    local url="$1"
    # Extract hostname from URL like http://mcp-gateway-kc-alb-xxx.us-east-1.elb.amazonaws.com:8080
    # Remove protocol
    url="${url#*://}"
    # Remove port
    url="${url%%:*}"
    echo "$url"
}

_get_admin_token() {
    local keycloak_url="$1"
    local admin_user="$2"
    local admin_password="$3"
    local token
    local token_url
    local http_code
    local response

    log_info "Getting admin token from Keycloak..."
    log_debug "Keycloak URL: $keycloak_url"
    log_debug "Admin User: $admin_user"

    token_url="$keycloak_url/realms/master/protocol/openid-connect/token"
    log_trace "Token URL: $token_url"

    if [[ "$VERBOSE" == "1" ]]; then
        log_trace "Admin password (first 4 chars): ${admin_password:0:4}***"
    fi

    log_trace "Executing token request..."
    if [[ "$VERBOSE" == "1" ]]; then
        echo "[TRACE] Full curl command:" >&2
        echo "[TRACE] curl -s -w \"\\n%{http_code}\" -X POST \"$token_url\" -H \"Content-Type: application/x-www-form-urlencoded\" -d \"username=$admin_user\" -d \"password=***\" -d \"grant_type=password\" -d \"client_id=admin-cli\"" >&2
    fi

    response=$(curl -s -w "\n%{http_code}" -X POST "$token_url" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=$admin_user" \
        -d "password=$admin_password" \
        -d "grant_type=password" \
        -d "client_id=admin-cli")

    if [[ "$VERBOSE" == "1" ]]; then
        echo "[TRACE] Raw curl response length: ${#response}" >&2
        echo "[TRACE] Raw curl response (first 500 chars): ${response:0:500}" >&2
    fi

    http_code=$(echo "$response" | tail -1)
    log_debug "HTTP Status Code: $http_code"

    if [[ "$VERBOSE" == "1" ]]; then
        echo "[TRACE] Response body (without http code):" >&2
        echo "$response" | sed '$d' >&2
    fi

    token=$(echo "$response" | sed '$d' | jq -r '.access_token // .error // "unknown"')
    log_debug "Token extraction result: $token"
    log_debug "Token response status: $(echo "$response" | sed '$d' | jq -r '.access_token // .error // "unknown"')"

    if [[ -z "$token" || "$token" == "null" || "$token" == "unknown" ]]; then
        log_error "Failed to obtain admin token"
        log_debug "Full response: $(echo "$response" | sed '$d' | jq '.')"
        log_error "Check that Keycloak is running and credentials are correct"
        return 1
    fi

    log_debug "Token obtained (length: ${#token} characters)"
    log_trace "Admin token (first 50 chars): ${token:0:50}..."

    echo "$token"
}

_configure_hostname() {
    local keycloak_url="$1"
    local admin_token="$2"
    local hostname="$3"

    log_info "Configuring Keycloak hostname to: $hostname"
    log_debug "Setting frontendUrl in realm attributes to: http://$hostname:8080"

    local api_url="$keycloak_url/admin/realms/master"
    log_trace "API URL: $api_url"
    log_trace "Request body: {\"attributes\": {\"frontendUrl\": \"http://$hostname:8080\"}}"

    log_trace "Executing API request to configure hostname..."
    local response
    response=$(curl -s -w "\n%{http_code}" -X PUT "$api_url" \
        -H "Authorization: Bearer $admin_token" \
        -H "Content-Type: application/json" \
        -d "{\"attributes\": {\"frontendUrl\": \"http://$hostname:8080\"}}")

    local http_code
    http_code=$(echo "$response" | tail -1)
    log_debug "HTTP Status Code: $http_code"

    if [[ "$http_code" == "204" ]]; then
        log_info "Successfully configured hostname: $hostname"
        return 0
    else
        log_error "Failed to configure hostname (HTTP $http_code)"
        log_trace "Full response: $(echo "$response" | sed '$d')"
        log_debug "Note: Frontend URL configuration may not be supported via REST API in all Keycloak versions"
        return 1
    fi
}

_disable_ssl_for_realm() {
    local keycloak_url="$1"
    local admin_token="$2"
    local realm_name="$3"
    local http_code
    local api_url
    local response

    log_info "Disabling SSL requirement for realm: $realm_name"
    log_debug "Realm Name: $realm_name"

    api_url="$keycloak_url/admin/realms/$realm_name"
    log_trace "API URL: $api_url"
    log_trace "Request method: PUT"
    log_trace "Request body: {\"sslRequired\": \"none\"}"

    if [[ "$VERBOSE" == "1" ]]; then
        log_trace "Admin token (first 50 chars): ${admin_token:0:50}..."
    fi

    log_trace "Executing API request to disable SSL..."
    response=$(curl -s -w "\n%{http_code}" -X PUT "$api_url" \
        -H "Authorization: Bearer $admin_token" \
        -H "Content-Type: application/json" \
        -d '{"sslRequired": "none"}')

    http_code=$(echo "$response" | tail -1)
    log_debug "HTTP Status Code: $http_code"
    log_debug "Response body: $(echo "$response" | sed '$d')"

    if [[ "$http_code" == "204" ]]; then
        log_info "Successfully disabled SSL requirement for realm: $realm_name"
        return 0
    else
        log_error "Failed to disable SSL for realm: $realm_name (HTTP $http_code)"
        log_trace "Full response: $(echo "$response" | sed '$d')"
        return 1
    fi
}

_verify_ssl_disabled() {
    local keycloak_url="$1"
    local admin_token="$2"
    local realm_name="$3"
    local ssl_required
    local api_url
    local response
    local http_code

    log_info "Verifying SSL requirement is disabled for realm: $realm_name"
    log_debug "Realm Name: $realm_name"

    api_url="$keycloak_url/admin/realms/$realm_name"
    log_trace "Verification API URL: $api_url"
    log_trace "Request method: GET"

    log_trace "Executing API request to verify SSL configuration..."
    response=$(curl -s -w "\n%{http_code}" -X GET "$api_url" \
        -H "Authorization: Bearer $admin_token")

    http_code=$(echo "$response" | tail -1)
    log_debug "HTTP Status Code: $http_code"

    ssl_required=$(echo "$response" | sed '$d' | jq -r '.sslRequired')
    log_debug "Current sslRequired value: $ssl_required"
    log_trace "Full realm config: $(echo "$response" | sed '$d' | jq '.')"

    if [[ "$ssl_required" == "none" ]]; then
        log_info "Verified: SSL requirement is disabled (sslRequired = 'none')"
        return 0
    else
        log_warn "Current sslRequired value: $ssl_required"
        log_warn "Expected: 'none', Got: '$ssl_required'"
        return 1
    fi
}

main() {
    echo "=========================================="
    echo "Keycloak SSL Configuration Script"
    echo "=========================================="
    echo ""

    if [[ "$VERBOSE" == "1" ]]; then
        log_debug "VERBOSE mode enabled"
        log_debug "Passwords will be partially displayed for debugging"
    fi

    echo ""

    # Get password from argument or fetch from Secrets Manager
    if [[ -z "$KEYCLOAK_ADMIN_PASSWORD" ]]; then
        log_info "No password provided as argument"
        log_debug "Attempting to fetch from AWS Secrets Manager..."
        # Capture only stdout (password), send logs to stderr
        KEYCLOAK_ADMIN_PASSWORD=$(_fetch_keycloak_password_from_secrets_manager)
        if [[ -z "$KEYCLOAK_ADMIN_PASSWORD" ]]; then
            log_error "Failed to fetch password from AWS Secrets Manager"
            exit 1
        fi
        log_info "Password fetched successfully from AWS Secrets Manager"
    else
        log_info "Using provided password"
        log_debug "Password provided as argument"
    fi

    if [[ "$VERBOSE" == "1" ]]; then
        echo "[TRACE] Password length: ${#KEYCLOAK_ADMIN_PASSWORD} characters" >&2
        echo "[TRACE] Password first 4 chars: ${KEYCLOAK_ADMIN_PASSWORD:0:4}***" >&2
        echo "[TRACE] Full password: $KEYCLOAK_ADMIN_PASSWORD" >&2
    fi

    # Extract hostname from KEYCLOAK_URL if not explicitly provided
    local KEYCLOAK_HOSTNAME
    KEYCLOAK_HOSTNAME=$(_extract_hostname_from_url "$KEYCLOAK_URL")
    log_debug "Extracted hostname from URL: $KEYCLOAK_HOSTNAME"

    echo ""
    echo "Configuration:"
    echo "  Keycloak URL: $KEYCLOAK_URL"
    echo "  Keycloak Hostname: $KEYCLOAK_HOSTNAME"
    echo "  Admin User: $KEYCLOAK_ADMIN"
    echo "  AWS Region: $AWS_REGION"
    if [[ "$VERBOSE" == "1" ]]; then
        echo "  Verbose Mode: ENABLED"
    fi
    echo ""

    log_debug "Starting Keycloak SSL and hostname configuration process..."
    log_trace "Step 1: Obtaining admin token"

    # Get admin token
    local admin_token
    admin_token=$(_get_admin_token "$KEYCLOAK_URL" "$KEYCLOAK_ADMIN" "$KEYCLOAK_ADMIN_PASSWORD")
    if [[ $? -ne 0 ]]; then
        log_error "Failed to obtain admin token. Aborting."
        exit 1
    fi

    echo ""
    log_trace "Step 2: Configuring hostname"

    # Configure hostname for master realm (fixes HTTPS redirect loop)
    if _configure_hostname "$KEYCLOAK_URL" "$admin_token" "$KEYCLOAK_HOSTNAME"; then
        log_info "Hostname configuration successful"
    else
        log_warn "Failed to configure hostname, continuing..."
    fi

    echo ""
    log_trace "Step 3: Processing master realm"

    # Disable SSL for master realm
    if _disable_ssl_for_realm "$KEYCLOAK_URL" "$admin_token" "master"; then
        _verify_ssl_disabled "$KEYCLOAK_URL" "$admin_token" "master"
    else
        log_warn "Failed to disable SSL for master realm, continuing..."
    fi

    echo ""
    log_trace "Step 4: Processing mcp-gateway realm"

    # Disable SSL for mcp-gateway realm
    if _disable_ssl_for_realm "$KEYCLOAK_URL" "$admin_token" "mcp-gateway"; then
        _verify_ssl_disabled "$KEYCLOAK_URL" "$admin_token" "mcp-gateway"
    else
        log_warn "Failed to disable SSL for mcp-gateway realm"
        log_warn "Make sure the mcp-gateway realm exists before running this script"
    fi

    echo ""
    echo "=========================================="
    log_info "Keycloak SSL and hostname configuration completed"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "1. Clear your browser cache/cookies for the Keycloak domain"
    echo "2. Try accessing Keycloak at: $KEYCLOAK_URL"
    echo "3. If still seeing HTTPS error, restart Keycloak container:"
    echo "   docker-compose restart keycloak"
    echo ""
    log_debug "Script exit status: $?"
}

main "$@"
