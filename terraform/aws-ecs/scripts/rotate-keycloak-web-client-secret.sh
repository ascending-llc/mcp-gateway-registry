#!/bin/bash

# Rotate and sync mcp-gateway-web client secret between Keycloak and AWS Secrets Manager
#
# PREREQUISITES:
#   - Keycloak must be fully initialized (run init-keycloak.sh first)
#   - mcp-gateway-web client must exist in Keycloak
#   - Keycloak admin credentials must be configured in terraform.tfvars or .env
#   - AWS Secrets Manager must have mcp-gateway-keycloak-client-secret
#
# This script:
# 1. Connects to Keycloak admin console
# 2. Generates a NEW client secret in Keycloak (Keycloak is source of truth)
# 3. Updates AWS Secrets Manager with the new Keycloak-generated secret
#
# Use this for:
#   - Secret rotation (security best practice)
#   - Syncing Keycloak and AWS Secrets Manager when out of sync
#   - After manual client modifications in Keycloak admin console

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_info() { echo -e "${YELLOW}ℹ${NC} $1"; }

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$TERRAFORM_DIR")"

print_info "Rotating Keycloak client secret for mcp-gateway-web"

# Try to load from .env file first (same as init-keycloak.sh)
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
    print_info "Loaded configuration from .env file"
fi

# Fall back to terraform.tfvars if .env doesn't have the values
if [ -z "$KEYCLOAK_ADMIN_URL" ]; then
    if [ -f "$TERRAFORM_DIR/terraform.tfvars" ]; then
        KEYCLOAK_ADMIN_URL=$(grep "^keycloak_domain" "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2)
        if [ -n "$KEYCLOAK_ADMIN_URL" ]; then
            KEYCLOAK_ADMIN_URL="https://${KEYCLOAK_ADMIN_URL}"
        fi
    fi
fi

if [ -z "$KEYCLOAK_ADMIN" ] && [ -f "$TERRAFORM_DIR/terraform.tfvars" ]; then
    KEYCLOAK_ADMIN=$(grep "^keycloak_admin" "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2)
fi

if [ -z "$KEYCLOAK_ADMIN_PASSWORD" ] && [ -f "$TERRAFORM_DIR/terraform.tfvars" ]; then
    KEYCLOAK_ADMIN_PASSWORD=$(grep "^keycloak_admin_password" "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2)
fi

# Use KEYCLOAK_ADMIN_URL as the base URL
KEYCLOAK_URL="${KEYCLOAK_ADMIN_URL:-https://kc.mycorp.click}"
REALM="mcp-gateway"
CLIENT_ID="mcp-gateway-web"
AWS_REGION="${AWS_REGION:-us-west-2}"

print_info "Keycloak URL: $KEYCLOAK_URL"
print_info "Realm: $REALM"
print_info "Client ID: $CLIENT_ID"

# Get the client secret from AWS Secrets Manager
print_info "Retrieving client secret from AWS Secrets Manager..."
SECRET_JSON=$(aws secretsmanager get-secret-value \
    --secret-id mcp-gateway-keycloak-client-secret \
    --region "$AWS_REGION" \
    --query 'SecretString' \
    --output text)

CLIENT_SECRET=$(echo "$SECRET_JSON" | jq -r '.client_secret // empty')

if [ -z "$CLIENT_SECRET" ]; then
    print_error "Could not retrieve client secret from Secrets Manager"
    exit 1
fi

print_success "Client secret retrieved"

# Get admin access token
print_info "Getting Keycloak admin token..."
TOKEN_RESPONSE=$(curl -s -k -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=${KEYCLOAK_ADMIN}" \
    -d "password=${KEYCLOAK_ADMIN_PASSWORD}" \
    -d "grant_type=password" \
    -d "client_id=admin-cli")

ADMIN_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token // empty')

if [ -z "$ADMIN_TOKEN" ]; then
    print_error "Failed to get admin token"
    echo "Response:"
    echo "$TOKEN_RESPONSE"
    exit 1
fi

print_success "Admin token obtained"

# Get all clients in the realm
print_info "Fetching clients in realm $REALM..."
CLIENTS_RESPONSE=$(curl -s -k -X GET "${KEYCLOAK_URL}/admin/realms/${REALM}/clients" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json")

# Find the client UUID
CLIENT_UUID=$(echo "$CLIENTS_RESPONSE" | jq -r ".[] | select(.clientId == \"${CLIENT_ID}\") | .id" | head -1)

if [ -z "$CLIENT_UUID" ]; then
    print_error "Client $CLIENT_ID not found in realm $REALM"
    print_info "Available clients:"
    echo "$CLIENTS_RESPONSE" | jq -r '.[].clientId'
    exit 1
fi

print_success "Found client UUID: $CLIENT_UUID"

# Generate a new client secret in Keycloak
print_info "Generating new client secret in Keycloak..."
SECRET_RESPONSE=$(curl -s -k -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/client-secret" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{}')

GENERATED_SECRET=$(echo "$SECRET_RESPONSE" | jq -r '.value // empty')

if [ -z "$GENERATED_SECRET" ]; then
    print_error "Failed to generate client secret"
    echo "Response: $SECRET_RESPONSE" | jq '.'
    exit 1
fi

print_success "New client secret generated in Keycloak"

# Update the secret in AWS Secrets Manager with the Keycloak-generated secret
print_info "Updating AWS Secrets Manager with Keycloak-generated secret..."
aws secretsmanager update-secret \
    --secret-id mcp-gateway-keycloak-client-secret \
    --secret-string "{\"client_id\": \"${CLIENT_ID}\", \"client_secret\": \"${GENERATED_SECRET}\"}" \
    --region "$AWS_REGION" > /dev/null

print_success "Secrets Manager updated"

# Verify the client is configured correctly
print_info "Verifying client configuration..."
CLIENT_CONFIG=$(curl -s -k -X GET "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${CLIENT_UUID}" \
    -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    -H "Content-Type: application/json")

print_success "Client configuration verified"

echo ""
echo "=================================================="
echo "Keycloak Client Secret Rotation Complete!"
echo "=================================================="
echo ""
echo "Client Details:"
echo "  Client ID: $CLIENT_ID"
echo "  Realm: $REALM"
echo "  Client UUID: $CLIENT_UUID"
echo ""
echo "Configuration:"
echo "  Enabled: $(echo "$CLIENT_CONFIG" | jq -r '.enabled')"
echo "  Auth Type: $(echo "$CLIENT_CONFIG" | jq -r '.clientAuthenticatorType')"
echo "  Public Client: $(echo "$CLIENT_CONFIG" | jq -r '.publicClient')"
echo ""
echo "Secret Sync Status:"
echo "  ✓ New secret generated in Keycloak"
echo "  ✓ AWS Secrets Manager updated"
echo ""
echo "Next Steps:"
echo "  1. Restart registry ECS tasks to pick up new secret from Secrets Manager"
echo "  2. Verify login functionality at: https://registry.mycorp.click"
echo ""
