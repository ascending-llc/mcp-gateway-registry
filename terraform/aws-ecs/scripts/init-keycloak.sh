#!/bin/bash
# Initialize Keycloak with MCP Gateway configuration
# This script sets up the initial realm, clients, groups, and users
#
# Usage:
#   KEYCLOAK_ADMIN_URL=https://kc.mycorp.click \
#   KEYCLOAK_ADMIN=admin \
#   KEYCLOAK_ADMIN_PASSWORD=Keycloak@123456! \
#   AUTH_SERVER_EXTERNAL_URL=http://mcp-gateway-alb-xxx.us-west-2.elb.amazonaws.com:8888 \
#   REGISTRY_URL=http://mcp-gateway-alb-xxx.us-west-2.elb.amazonaws.com \
#   ./init-keycloak.sh
#
# Or set these in a .env file in the project root

set -e

# These will be set properly after loading .env in main()
KEYCLOAK_URL=""  # Will be overridden with KEYCLOAK_ADMIN_URL after .env is loaded
REALM="mcp-gateway"
KEYCLOAK_ADMIN=""
KEYCLOAK_ADMIN_PASSWORD=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Keycloak initialization script for MCP Gateway Registry${NC}"
echo "=============================================="

# Function to wait for Keycloak to be ready
wait_for_keycloak() {
    echo -n "Waiting for Keycloak to be ready..."
    local max_attempts=60
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        # Try to access the admin console which indicates Keycloak is ready
        if curl -f -s "${KEYCLOAK_URL}/admin/" > /dev/null 2>&1; then
            echo -e " ${GREEN}Ready!${NC}"
            return 0
        fi
        echo -n "."
        sleep 5
        attempt=$((attempt + 1))
    done
    
    echo -e " ${RED}Timeout!${NC}"
    echo "Keycloak did not become ready within 5 minutes"
    exit 1
}

# Function to get admin token
get_admin_token() {
    local response=$(curl -s -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=${KEYCLOAK_ADMIN}" \
        -d "password=${KEYCLOAK_ADMIN_PASSWORD}" \
        -d "grant_type=password" \
        -d "client_id=admin-cli")

    echo "$response" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4
}

# Function to refresh admin token (call before each major operation)
refresh_token() {
    TOKEN=$(get_admin_token)
    if [ -z "$TOKEN" ]; then
        echo -e "${RED}Error: Failed to refresh authentication token${NC}"
        exit 1
    fi
}

# Function to check if realm exists
realm_exists() {
    local token=$1
    local response=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}")
    
    [ "$response" = "200" ]
}

# Function to create realm step by step
create_realm() {
    local token=$1
    
    echo "Creating MCP Gateway realm..."
    
    # Check if realm already exists
    if realm_exists "$token"; then
        echo -e "${YELLOW}Realm already exists. Skipping creation...${NC}"
        return 0
    fi
    
    # Create basic realm
    local realm_json='{
        "realm": "mcp-gateway",
        "enabled": true,
        "registrationAllowed": false,
        "loginWithEmailAllowed": true,
        "duplicateEmailsAllowed": false,
        "resetPasswordAllowed": true,
        "editUsernameAllowed": false
    }'
    
    local response=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "${KEYCLOAK_URL}/admin/realms" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$realm_json")
    
    if [ "$response" = "201" ]; then
        echo -e "${GREEN}Realm created successfully!${NC}"
        return 0
    elif [ "$response" = "409" ]; then
        echo -e "${YELLOW}Realm already exists. Continuing...${NC}"
        return 0
    else
        echo -e "${RED}Failed to create realm. HTTP status: ${response}${NC}"
        echo "Response body:"
        curl -s -X POST "${KEYCLOAK_URL}/admin/realms" \
            -H "Authorization: Bearer ${token}" \
            -H "Content-Type: application/json" \
            -d "$realm_json"
        echo ""
        return 1
    fi
}

# Function to create clients
create_clients() {
    local token=$1
    
    echo "Creating OAuth2 clients..."
    
    # Create web client
    # Ensure we're using HTTPS URLs for redirect URIs
    local registry_url="${REGISTRY_URL:-http://localhost:7860}"
    local auth_callback_url="${registry_url}/oauth2/callback/keycloak"

    local web_client_json='{
        "clientId": "mcp-gateway-web",
        "name": "MCP Gateway Web Client",
        "enabled": true,
        "clientAuthenticatorType": "client-secret",
        "redirectUris": [
            "'${auth_callback_url}'",
            "'${registry_url}'/*",
            "http://localhost:7860/*",
            "http://localhost:8888/*"
        ],
        "webOrigins": [
            "'${registry_url}'",
            "http://localhost:7860",
            "+"
        ],
        "protocol": "openid-connect",
        "standardFlowEnabled": true,
        "implicitFlowEnabled": false,
        "directAccessGrantsEnabled": true,
        "serviceAccountsEnabled": false,
        "publicClient": false
    }'
    
    curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/clients" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$web_client_json" > /dev/null
    
    # Create M2M client
    local m2m_client_json='{
        "clientId": "mcp-gateway-m2m",
        "name": "MCP Gateway M2M Client",
        "enabled": true,
        "clientAuthenticatorType": "client-secret",
        "protocol": "openid-connect",
        "standardFlowEnabled": false,
        "implicitFlowEnabled": false,
        "directAccessGrantsEnabled": false,
        "serviceAccountsEnabled": true,
        "publicClient": false
    }'
    
    curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/clients" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$m2m_client_json" > /dev/null
    
    echo -e "${GREEN}Clients created successfully!${NC}"
}

# Function to create groups
create_groups() {
    local token=$1
    
    echo "Creating user groups..."

    local groups=(
        "mcp-registry-admin"
        "mcp-registry-user"
        "mcp-registry-developer"
        "mcp-registry-operator"
        "mcp-servers-unrestricted"
        "mcp-servers-restricted"
        "a2a-agent-admin"
        "a2a-agent-publisher"
        "a2a-agent-user"
        "registry-admins"
        "registry-users-lob1"
        "registry-users-lob2"
    )

    for group in "${groups[@]}"; do
        local group_json='{
            "name": "'$group'",
            "attributes": {
                "description": ["'$group' group for MCP Gateway access"]
            }
        }'

        curl -s -X POST "${KEYCLOAK_URL}/admin/realms/mcp-gateway/groups" \
            -H "Authorization: Bearer ${token}" \
            -H "Content-Type: application/json" \
            -d "$group_json" > /dev/null
    done

    echo -e "${GREEN}Groups created successfully!${NC}"
}

# Function to create custom scopes
create_scopes() {
    # Refresh token to ensure it's valid
    refresh_token
    local token=$TOKEN

    echo "Creating custom MCP scopes..."
    
    local scopes=("mcp-servers-unrestricted/read" "mcp-servers-unrestricted/execute" "mcp-servers-restricted/read" "mcp-servers-restricted/execute")
    
    for scope in "${scopes[@]}"; do
        local scope_json='{
            "name": "'$scope'",
            "description": "MCP Gateway scope for '$scope' access",
            "protocol": "openid-connect"
        }'
        
        local response=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/client-scopes" \
            -H "Authorization: Bearer ${token}" \
            -H "Content-Type: application/json" \
            -d "$scope_json")
        
        if [ "$response" = "201" ]; then
            echo "  - Created scope: $scope"
        elif [ "$response" = "409" ]; then
            echo "  - Scope already exists: $scope"
        else
            echo -e "${RED}  - Failed to create scope: $scope (HTTP $response)${NC}"
        fi
    done
    
    echo -e "${GREEN}Custom scopes created successfully!${NC}"
}

# Function to assign scopes to M2M client
setup_m2m_scopes() {
    # Refresh token to ensure it's valid
    refresh_token
    local token=$TOKEN

    echo "Setting up M2M client scopes..."
    
    # Get M2M client ID
    local m2m_client_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=mcp-gateway-m2m" 2>/dev/null | \
        jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)
    
    if [ -z "$m2m_client_id" ] || [ "$m2m_client_id" = "null" ]; then
        echo -e "${RED}Error: Could not find mcp-gateway-m2m client${NC}"
        return 1
    fi
    
    # Get all available client scopes
    local scopes=("mcp-servers-unrestricted/read" "mcp-servers-unrestricted/execute" "mcp-servers-restricted/read" "mcp-servers-restricted/execute")
    
    for scope in "${scopes[@]}"; do
        # Get scope ID
        local scope_id=$(curl -s -H "Authorization: Bearer ${token}" \
            "${KEYCLOAK_URL}/admin/realms/${REALM}/client-scopes" 2>/dev/null | \
            jq -r 'if type == "array" then (.[] | select(.name=="'$scope'") | .id) else empty end' 2>/dev/null)
        
        if [ ! -z "$scope_id" ] && [ "$scope_id" != "null" ]; then
            # Add scope as default client scope
            local response=$(curl -s -o /dev/null -w "%{http_code}" \
                -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${m2m_client_id}/default-client-scopes/${scope_id}" \
                -H "Authorization: Bearer ${token}")
            
            if [ "$response" = "204" ]; then
                echo "  - Assigned scope: $scope"
            else
                echo -e "${YELLOW}  - Warning: Could not assign scope $scope (HTTP $response)${NC}"
            fi
        else
            echo -e "${RED}  - Error: Could not find scope: $scope${NC}"
        fi
    done
    
    echo -e "${GREEN}M2M client scopes configured successfully!${NC}"
}

# Function to create service account user for M2M client
create_service_account_user() {
    # Refresh token to ensure it's valid
    refresh_token
    local token=$TOKEN
    local service_account_username="service-account-mcp-gateway-m2m"

    echo "Creating service account user: $service_account_username"
    
    # Check if user already exists
    local existing_user=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=$service_account_username" 2>/dev/null | \
        jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)
    
    if [ ! -z "$existing_user" ]; then
        echo -e "${YELLOW}Service account user already exists with ID: $existing_user${NC}"
        return 0
    fi
    
    # Create service account user
    local user_json='{
        "username": "'$service_account_username'",
        "enabled": true,
        "emailVerified": true,
        "serviceAccountClientId": "mcp-gateway-m2m"
    }'
    
    local response=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/users" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$user_json")
    
    if [ "$response" = "201" ]; then
        echo -e "${GREEN}Service account user created successfully!${NC}"
        
        # Get the newly created user ID
        local user_id=$(curl -s -H "Authorization: Bearer ${token}" \
            "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=$service_account_username" 2>/dev/null | \
            jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)
        
        echo "Created service account user with ID: $user_id"
        
        # Assign user to mcp-servers-unrestricted group
        local group_id=$(curl -s -H "Authorization: Bearer ${token}" \
            "${KEYCLOAK_URL}/admin/realms/${REALM}/groups" 2>/dev/null | \
            jq -r 'if type == "array" then (.[] | select(.name=="mcp-servers-unrestricted") | .id) else empty end' 2>/dev/null)

        if [ ! -z "$group_id" ] && [ "$group_id" != "null" ]; then
            local group_response=$(curl -s -o /dev/null -w "%{http_code}" \
                -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}/users/$user_id/groups/$group_id" \
                -H "Authorization: Bearer ${token}")

            if [ "$group_response" = "204" ]; then
                echo -e "${GREEN}Service account assigned to mcp-servers-unrestricted group!${NC}"
            else
                echo -e "${YELLOW}Warning: Could not assign service account to mcp-servers-unrestricted group (HTTP $group_response)${NC}"
            fi
        else
            echo -e "${RED}Error: Could not find mcp-servers-unrestricted group${NC}"
        fi

        # Assign user to a2a-agent-admin group for A2A agent access
        local a2a_group_id=$(curl -s -H "Authorization: Bearer ${token}" \
            "${KEYCLOAK_URL}/admin/realms/${REALM}/groups" 2>/dev/null | \
            jq -r 'if type == "array" then (.[] | select(.name=="a2a-agent-admin") | .id) else empty end' 2>/dev/null)

        if [ ! -z "$a2a_group_id" ] && [ "$a2a_group_id" != "null" ]; then
            local a2a_response=$(curl -s -o /dev/null -w "%{http_code}" \
                -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}/users/$user_id/groups/$a2a_group_id" \
                -H "Authorization: Bearer ${token}")

            if [ "$a2a_response" = "204" ]; then
                echo -e "${GREEN}Service account assigned to a2a-agent-admin group!${NC}"
            else
                echo -e "${YELLOW}Warning: Could not assign service account to a2a-agent-admin group (HTTP $a2a_response)${NC}"
            fi
        else
            echo -e "${YELLOW}Warning: a2a-agent-admin group not found. Create it manually if A2A agent support is needed.${NC}"
        fi

        return 0
    elif [ "$response" = "409" ]; then
        echo -e "${YELLOW}Service account user already exists. Continuing...${NC}"
        return 0
    else
        echo -e "${RED}Failed to create service account user. HTTP status: ${response}${NC}"
        return 1
    fi
}

# Function to create service account clients for A2A agents
create_service_account_clients() {
    # Refresh token to ensure it's valid
    refresh_token
    local token=$TOKEN

    echo "Creating service account clients for A2A agents..."

    # Define service account clients
    local clients=("registry-admin-bot" "lob1-bot" "lob2-bot")
    local groups=("registry-admins" "registry-users-lob1" "registry-users-lob2")

    for i in "${!clients[@]}"; do
        local client_name="${clients[$i]}"
        local group_name="${groups[$i]}"

        echo "  Creating client: $client_name"

        # Create M2M service account client
        local client_json='{
            "clientId": "'$client_name'",
            "name": "'$client_name' Service Account",
            "description": "Service account for '$client_name' operations",
            "enabled": true,
            "serviceAccountsEnabled": true,
            "standardFlowEnabled": false,
            "implicitFlowEnabled": false,
            "directAccessGrantsEnabled": false,
            "publicClient": false,
            "protocol": "openid-connect"
        }'

        local response=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/clients" \
            -H "Authorization: Bearer ${token}" \
            -H "Content-Type: application/json" \
            -d "$client_json")

        if [ "$response" = "201" ]; then
            echo "    - Client created successfully"
        elif [ "$response" = "409" ]; then
            echo "    - Client already exists"
        else
            echo -e "${RED}    - Failed to create client (HTTP $response)${NC}"
            continue
        fi

        # Get the client UUID
        local client_uuid=$(curl -s -H "Authorization: Bearer ${token}" \
            "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=${client_name}" 2>/dev/null | \
            jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)

        if [ -z "$client_uuid" ] || [ "$client_uuid" = "null" ]; then
            echo -e "${RED}    - Error: Could not find client UUID${NC}"
            continue
        fi

        # Get the service account user ID
        local service_account_user=$(curl -s -H "Authorization: Bearer ${token}" \
            "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${client_uuid}/service-account-user" 2>/dev/null | \
            jq -r '.id // empty' 2>/dev/null)

        if [ -z "$service_account_user" ] || [ "$service_account_user" = "null" ]; then
            echo -e "${RED}    - Error: Could not get service account user ID${NC}"
            continue
        fi

        # Get the group ID
        local group_id=$(curl -s -H "Authorization: Bearer ${token}" \
            "${KEYCLOAK_URL}/admin/realms/${REALM}/groups" 2>/dev/null | \
            jq -r 'if type == "array" then (.[] | select(.name=="'$group_name'") | .id) else empty end' 2>/dev/null)

        if [ -z "$group_id" ] || [ "$group_id" = "null" ]; then
            echo -e "${RED}    - Error: Could not find group: $group_name${NC}"
            continue
        fi

        # Assign service account to the group
        local group_response=$(curl -s -o /dev/null -w "%{http_code}" \
            -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}/users/${service_account_user}/groups/${group_id}" \
            -H "Authorization: Bearer ${token}")

        if [ "$group_response" = "204" ]; then
            echo "    - Service account assigned to group: $group_name"
        else
            echo -e "${YELLOW}    - Warning: Could not assign to group (HTTP $group_response)${NC}"
        fi

        # Add groups mapper to the client so groups appear in JWT token
        echo "    - Adding groups mapper to client..."
        local groups_mapper_json='{
            "name": "groups",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-group-membership-mapper",
            "consentRequired": false,
            "config": {
                "full.path": "false",
                "id.token.claim": "true",
                "access.token.claim": "true",
                "claim.name": "groups",
                "userinfo.token.claim": "true"
            }
        }'

        local mapper_response=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${client_uuid}/protocol-mappers/models" \
            -H "Authorization: Bearer ${token}" \
            -H "Content-Type: application/json" \
            -d "$groups_mapper_json")

        if [ "$mapper_response" = "201" ]; then
            echo "    - Groups mapper created successfully"
        elif [ "$mapper_response" = "409" ]; then
            echo "    - Groups mapper already exists"
        else
            echo -e "${YELLOW}    - Warning: Could not create groups mapper (HTTP $mapper_response)${NC}"
        fi
    done

    echo -e "${GREEN}Service account clients created successfully!${NC}"
}

# Function to create test users
create_users() {
    # Refresh token to ensure it's valid
    refresh_token
    local token=$TOKEN

    echo "Creating test users..."

    # Define usernames for consistency
    local admin_username="admin"
    local test_username="testuser"
    local lob1_username="lob1-user"
    local lob2_username="lob2-user"

    # Create admin user
    local admin_user_json='{
        "username": "'$admin_username'",
        "email": "'$admin_username'@example.com",
        "enabled": true,
        "emailVerified": true,
        "firstName": "Admin",
        "lastName": "User",
        "credentials": [
            {
                "type": "password",
                "value": "'${INITIAL_ADMIN_PASSWORD}'",
                "temporary": false
            }
        ]
    }'
    
    curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/users" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$admin_user_json" > /dev/null
    
    # Create test user
    local test_user_json='{
        "username": "'$test_username'",
        "email": "'$test_username'@example.com",
        "enabled": true,
        "emailVerified": true,
        "firstName": "Test",
        "lastName": "User",
        "credentials": [
            {
                "type": "password",
                "value": "'${INITIAL_USER_PASSWORD:-testpass}'",
                "temporary": false
            }
        ]
    }'
    
    curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/users" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$test_user_json" > /dev/null

    # Create lob1-user
    local lob1_user_json='{
        "username": "'$lob1_username'",
        "email": "'$lob1_username'@example.com",
        "enabled": true,
        "emailVerified": true,
        "firstName": "LOB1",
        "lastName": "User",
        "credentials": [
            {
                "type": "password",
                "value": "'${LOB1_USER_PASSWORD:-lob1pass}'",
                "temporary": false
            }
        ]
    }'

    curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/users" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$lob1_user_json" > /dev/null

    # Create lob2-user
    local lob2_user_json='{
        "username": "'$lob2_username'",
        "email": "'$lob2_username'@example.com",
        "enabled": true,
        "emailVerified": true,
        "firstName": "LOB2",
        "lastName": "User",
        "credentials": [
            {
                "type": "password",
                "value": "'${LOB2_USER_PASSWORD:-lob2pass}'",
                "temporary": false
            }
        ]
    }'

    curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/users" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$lob2_user_json" > /dev/null

    echo "Assigning users to groups..."
    
    # Get user IDs
    local admin_user_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=$admin_username" 2>/dev/null | \
        jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)

    local test_user_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=$test_username" 2>/dev/null | \
        jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)

    local lob1_user_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=$lob1_username" 2>/dev/null | \
        jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)

    local lob2_user_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=$lob2_username" 2>/dev/null | \
        jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)
    
    # Get all group IDs
    local admin_group_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/groups" 2>/dev/null | \
        jq -r 'if type == "array" then (.[] | select(.name=="mcp-registry-admin") | .id) else empty end' 2>/dev/null)

    local user_group_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/groups" 2>/dev/null | \
        jq -r 'if type == "array" then (.[] | select(.name=="mcp-registry-user") | .id) else empty end' 2>/dev/null)

    local developer_group_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/groups" 2>/dev/null | \
        jq -r 'if type == "array" then (.[] | select(.name=="mcp-registry-developer") | .id) else empty end' 2>/dev/null)

    local operator_group_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/groups" 2>/dev/null | \
        jq -r 'if type == "array" then (.[] | select(.name=="mcp-registry-operator") | .id) else empty end' 2>/dev/null)

    local unrestricted_group_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/groups" 2>/dev/null | \
        jq -r 'if type == "array" then (.[] | select(.name=="mcp-servers-unrestricted") | .id) else empty end' 2>/dev/null)

    local restricted_group_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/groups" 2>/dev/null | \
        jq -r 'if type == "array" then (.[] | select(.name=="mcp-servers-restricted") | .id) else empty end' 2>/dev/null)

    local lob1_group_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/groups" 2>/dev/null | \
        jq -r 'if type == "array" then (.[] | select(.name=="registry-users-lob1") | .id) else empty end' 2>/dev/null)

    local lob2_group_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/groups" 2>/dev/null | \
        jq -r 'if type == "array" then (.[] | select(.name=="registry-users-lob2") | .id) else empty end' 2>/dev/null)

    # Define usernames for consistent logging
    local admin_username="admin"
    local test_username="testuser"
    local lob1_username="lob1-user"
    local lob2_username="lob2-user"
    
    # Assign admin user to admin group and unrestricted servers group
    if [ ! -z "$admin_user_id" ] && [ ! -z "$admin_group_id" ]; then
        curl -s -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}/users/$admin_user_id/groups/$admin_group_id" \
            -H "Authorization: Bearer ${token}" > /dev/null
        echo "  - $admin_username assigned to mcp-registry-admin group"
    fi
    
    # Also assign admin to unrestricted servers group for full access
    if [ ! -z "$admin_user_id" ] && [ ! -z "$unrestricted_group_id" ]; then
        curl -s -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}/users/$admin_user_id/groups/$unrestricted_group_id" \
            -H "Authorization: Bearer ${token}" > /dev/null
        echo "  - $admin_username assigned to mcp-servers-unrestricted group"
    fi
    
    # Assign test user to all groups except admin
    if [ ! -z "$test_user_id" ]; then
        # Arrays of group IDs and names for loop processing
        local group_ids=("$user_group_id" "$developer_group_id" "$operator_group_id" "$unrestricted_group_id" "$restricted_group_id")
        local group_names=("mcp-registry-user" "mcp-registry-developer" "mcp-registry-operator" "mcp-servers-unrestricted" "mcp-servers-restricted")
        
        # Loop through groups and assign test user to each
        for i in "${!group_ids[@]}"; do
            local group_id="${group_ids[$i]}"
            local group_name="${group_names[$i]}"
            
            if [ ! -z "$group_id" ]; then
                curl -s -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}/users/$test_user_id/groups/$group_id" \
                    -H "Authorization: Bearer ${token}" > /dev/null
                echo "  - $test_username assigned to $group_name group"
            fi
        done
    fi

    # Assign lob1-user to registry-users-lob1 group
    if [ ! -z "$lob1_user_id" ] && [ ! -z "$lob1_group_id" ]; then
        curl -s -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}/users/$lob1_user_id/groups/$lob1_group_id" \
            -H "Authorization: Bearer ${token}" > /dev/null
        echo "  - $lob1_username assigned to registry-users-lob1 group"
    fi

    # Assign lob2-user to registry-users-lob2 group
    if [ ! -z "$lob2_user_id" ] && [ ! -z "$lob2_group_id" ]; then
        curl -s -X PUT "${KEYCLOAK_URL}/admin/realms/${REALM}/users/$lob2_user_id/groups/$lob2_group_id" \
            -H "Authorization: Bearer ${token}" > /dev/null
        echo "  - $lob2_username assigned to registry-users-lob2 group"
    fi

    echo -e "${GREEN}Users created and assigned to groups successfully!${NC}"
}

# Function to create client secrets
setup_client_secrets() {
    # Refresh token to ensure it's valid
    refresh_token
    local token=$TOKEN

    echo "Setting up client secrets..."

    # Get web client ID
    local web_client_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=mcp-gateway-web" 2>/dev/null | \
        jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)

    # Generate secret for web client
    curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${web_client_id}/client-secret" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" > /dev/null

    local web_secret_response=$(curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${web_client_id}/client-secret" \
        -H "Authorization: Bearer ${token}")
    web_secret=$(echo "$web_secret_response" | jq -r '.value // empty')

    # Get M2M client ID
    local m2m_client_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=mcp-gateway-m2m" 2>/dev/null | \
        jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)

    # Generate secret for M2M client
    curl -s -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${m2m_client_id}/client-secret" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" > /dev/null

    local m2m_secret_response=$(curl -s "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${m2m_client_id}/client-secret" \
        -H "Authorization: Bearer ${token}")
    m2m_secret=$(echo "$m2m_secret_response" | jq -r '.value // empty')

    echo -e "${GREEN}Client secrets generated!${NC}"

    # Save web client secret to AWS Secrets Manager
    if [ -n "$web_secret" ] && command -v aws &> /dev/null; then
        echo "Saving web client secret to AWS Secrets Manager..."
        if aws secretsmanager update-secret \
            --secret-id mcp-gateway-keycloak-client-secret \
            --secret-string "{\"client_id\": \"mcp-gateway-web\", \"client_secret\": \"${web_secret}\"}" \
            --region "${AWS_REGION:-us-west-2}" &>/dev/null; then
            echo -e "${GREEN}Web client secret saved to AWS Secrets Manager!${NC}"
        else
            echo -e "${YELLOW}Warning: Could not save web client secret to Secrets Manager${NC}"
            echo "You can manually update it with:"
            echo "  aws secretsmanager update-secret --secret-id mcp-gateway-keycloak-client-secret \\"
            echo "    --secret-string '{\"client_id\": \"mcp-gateway-web\", \"client_secret\": \"${web_secret}\"}' \\"
            echo "    --region \${AWS_REGION:-us-west-2}"
        fi
    fi

    # Save M2M client secret to AWS Secrets Manager
    if [ -n "$m2m_secret" ] && command -v aws &> /dev/null; then
        echo "Saving M2M client secret to AWS Secrets Manager..."
        if aws secretsmanager update-secret \
            --secret-id mcp-gateway-keycloak-m2m-client-secret \
            --secret-string "{\"client_id\": \"mcp-gateway-m2m\", \"client_secret\": \"${m2m_secret}\"}" \
            --region "${AWS_REGION:-us-west-2}" &>/dev/null; then
            echo -e "${GREEN}M2M client secret saved to AWS Secrets Manager!${NC}"
        else
            echo -e "${YELLOW}Warning: Could not save M2M client secret to Secrets Manager${NC}"
            echo "You can manually update it with:"
            echo "  aws secretsmanager update-secret --secret-id mcp-gateway-keycloak-m2m-client-secret \\"
            echo "    --secret-string '{\"client_id\": \"mcp-gateway-m2m\", \"client_secret\": \"${m2m_secret}\"}' \\"
            echo "    --region \${AWS_REGION:-us-west-2}"
        fi
    fi

    echo ""
    echo "=============================================="
    echo -e "${YELLOW}Client credentials have been created.${NC}"
    echo "=============================================="
    echo ""
    echo "Web Client:"
    echo "  Client ID: mcp-gateway-web"
    echo "  Secret: ${web_secret}"
    echo ""
    echo "M2M Client:"
    echo "  Client ID: mcp-gateway-m2m"
    echo "  Secret: ${m2m_secret}"
    echo ""
    echo -e "${GREEN}Note: Both client secrets have been saved to AWS Secrets Manager${NC}"
    echo "  - mcp-gateway-keycloak-client-secret (web client)"
    echo "  - mcp-gateway-keycloak-m2m-client-secret (M2M client)"
    echo "=============================================="
}

# Function to setup groups mapper for OAuth2 clients
setup_groups_mapper() {
    # Refresh token to ensure it's valid
    refresh_token
    local token=$TOKEN

    echo "Setting up groups mapper for OAuth2 clients..."

    # Create groups mapper JSON
    local groups_mapper_json='{
        "name": "groups",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-group-membership-mapper",
        "consentRequired": false,
        "config": {
            "full.path": "false",
            "id.token.claim": "true",
            "access.token.claim": "true",
            "claim.name": "groups",
            "userinfo.token.claim": "true"
        }
    }'

    # Setup groups mapper for mcp-gateway-web client
    echo "Setting up groups mapper for mcp-gateway-web client..."
    local web_client_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=mcp-gateway-web" 2>/dev/null | \
        jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)

    if [ -z "$web_client_id" ] || [ "$web_client_id" = "null" ]; then
        echo -e "${RED}Error: Could not find mcp-gateway-web client${NC}"
        return 1
    fi

    local response=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${web_client_id}/protocol-mappers/models" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$groups_mapper_json")

    if [ "$response" = "201" ]; then
        echo -e "${GREEN}Groups mapper created for mcp-gateway-web!${NC}"
    elif [ "$response" = "409" ]; then
        echo -e "${YELLOW}Groups mapper already exists for mcp-gateway-web. Continuing...${NC}"
    else
        echo -e "${RED}Failed to create groups mapper for mcp-gateway-web. HTTP status: ${response}${NC}"
        return 1
    fi

    # Setup groups mapper for mcp-gateway-m2m client
    echo "Setting up groups mapper for mcp-gateway-m2m client..."
    local m2m_client_id=$(curl -s -H "Authorization: Bearer ${token}" \
        "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=mcp-gateway-m2m" 2>/dev/null | \
        jq -r 'if type == "array" then (.[0].id // empty) else empty end' 2>/dev/null)

    if [ -z "$m2m_client_id" ] || [ "$m2m_client_id" = "null" ]; then
        echo -e "${RED}Error: Could not find mcp-gateway-m2m client${NC}"
        return 1
    fi

    local m2m_response=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${m2m_client_id}/protocol-mappers/models" \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -d "$groups_mapper_json")

    if [ "$m2m_response" = "201" ]; then
        echo -e "${GREEN}Groups mapper created for mcp-gateway-m2m!${NC}"
    elif [ "$m2m_response" = "409" ]; then
        echo -e "${YELLOW}Groups mapper already exists for mcp-gateway-m2m. Continuing...${NC}"
    else
        echo -e "${RED}Failed to create groups mapper for mcp-gateway-m2m. HTTP status: ${m2m_response}${NC}"
        return 1
    fi
}

# Function to load values from terraform-outputs.json
load_from_terraform_outputs() {
    local terraform_outputs="$SCRIPT_DIR/terraform-outputs.json"

    if [ ! -f "$terraform_outputs" ]; then
        echo -e "${YELLOW}Warning: terraform-outputs.json not found in $SCRIPT_DIR${NC}"
        return 1
    fi

    echo "Loading values from terraform-outputs.json..."

    # Extract values from JSON
    if command -v jq &> /dev/null; then
        # Load KEYCLOAK_ADMIN_URL if not set
        if [ -z "$KEYCLOAK_ADMIN_URL" ]; then
            local keycloak_url=$(jq -r '.keycloak_url.value // empty' "$terraform_outputs" 2>/dev/null)
            if [ -n "$keycloak_url" ] && [ "$keycloak_url" != "null" ]; then
                KEYCLOAK_ADMIN_URL="$keycloak_url"
                echo "  - Loaded KEYCLOAK_ADMIN_URL: $KEYCLOAK_ADMIN_URL"
            fi
        fi

        # Load AUTH_SERVER_EXTERNAL_URL if not set
        if [ -z "$AUTH_SERVER_EXTERNAL_URL" ]; then
            local auth_url=$(jq -r '.mcp_gateway_auth_url.value // empty' "$terraform_outputs" 2>/dev/null)
            if [ -n "$auth_url" ] && [ "$auth_url" != "null" ]; then
                AUTH_SERVER_EXTERNAL_URL="$auth_url"
                echo "  - Loaded AUTH_SERVER_EXTERNAL_URL: $AUTH_SERVER_EXTERNAL_URL"
            fi
        fi

        # Load REGISTRY_URL if not set
        if [ -z "$REGISTRY_URL" ]; then
            local registry_url=$(jq -r '.registry_url.value // empty' "$terraform_outputs" 2>/dev/null)
            if [ -n "$registry_url" ] && [ "$registry_url" != "null" ]; then
                REGISTRY_URL="$registry_url"
                echo "  - Loaded REGISTRY_URL: $REGISTRY_URL"
            fi
        fi

        # Check if we successfully loaded values
        if [ -n "$AUTH_SERVER_EXTERNAL_URL" ] || [ -n "$REGISTRY_URL" ] || [ -n "$KEYCLOAK_ADMIN_URL" ]; then
            return 0
        fi
    else
        echo -e "${YELLOW}Warning: jq not found. Skipping terraform-outputs.json parsing${NC}"
        return 1
    fi

    return 1
}

# Main execution
main() {
    # Get script directory and find .env file
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
    ENV_FILE="$PROJECT_ROOT/.env"

    # Load environment variables from .env file if it exists
    if [ -f "$ENV_FILE" ]; then
        echo "Loading environment variables from $ENV_FILE..."
        set -a  # Automatically export all variables
        source "$ENV_FILE"
        set +a  # Turn off automatic export
        echo "Environment variables loaded successfully"
    else
        echo "No .env file found at $ENV_FILE"
    fi

    # Try to load missing values from terraform-outputs.json
    if [ -z "$AUTH_SERVER_EXTERNAL_URL" ] || [ -z "$REGISTRY_URL" ] || [ -z "$KEYCLOAK_ADMIN_URL" ]; then
        echo "Attempting to load missing values from terraform-outputs.json..."
        load_from_terraform_outputs || true
    fi

    # Override KEYCLOAK_URL with KEYCLOAK_ADMIN_URL for API calls
    KEYCLOAK_URL="${KEYCLOAK_ADMIN_URL:-https://kc.mycorp.click}"
    KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
    echo "Using Keycloak API URL: $KEYCLOAK_URL"

    # Display loaded configuration
    echo ""
    echo "Configuration:"
    echo "  - KEYCLOAK_URL: $KEYCLOAK_URL"
    echo "  - AUTH_SERVER_EXTERNAL_URL: ${AUTH_SERVER_EXTERNAL_URL:-<not set>}"
    echo "  - REGISTRY_URL: ${REGISTRY_URL:-<not set>}"
    echo ""

    # Try to load admin credentials from SSM Parameter Store if not set
    if [ -z "$KEYCLOAK_ADMIN_PASSWORD" ]; then
        echo "Attempting to load KEYCLOAK_ADMIN_PASSWORD from SSM Parameter Store..."
        if command -v aws &> /dev/null; then
            SSM_PASSWORD=$(aws ssm get-parameter --name "/keycloak/admin_password" --with-decryption --query 'Parameter.Value' --output text --region "${AWS_REGION:-us-west-2}" 2>/dev/null)
            if [ -n "$SSM_PASSWORD" ] && [ "$SSM_PASSWORD" != "null" ]; then
                KEYCLOAK_ADMIN_PASSWORD="$SSM_PASSWORD"
                echo -e "${GREEN}Loaded KEYCLOAK_ADMIN_PASSWORD from SSM Parameter Store${NC}"
            fi
        fi
    fi

    # Check if admin password is set (from env var or SSM)
    if [ -z "$KEYCLOAK_ADMIN_PASSWORD" ]; then
        echo -e "${RED}Error: KEYCLOAK_ADMIN_PASSWORD not found${NC}"
        echo "Please either:"
        echo "  1. Export KEYCLOAK_ADMIN_PASSWORD environment variable"
        echo "  2. Ensure AWS credentials are configured and SSM parameter '/keycloak/admin_password' exists"
        exit 1
    fi

    # Check if initial admin password is set (for realm admin user creation)
    if [ -z "$INITIAL_ADMIN_PASSWORD" ]; then
        echo -e "${RED}Error: INITIAL_ADMIN_PASSWORD environment variable is required${NC}"
        echo "This password will be used for the 'admin' user in the mcp-gateway realm."
        echo "Please export INITIAL_ADMIN_PASSWORD before running this script:"
        echo "  export INITIAL_ADMIN_PASSWORD='YourSecurePassword123'"
        exit 1
    fi
    
    # Wait for Keycloak to be ready
    wait_for_keycloak
    
    # Get admin token
    echo "Authenticating with Keycloak..."
    TOKEN=$(get_admin_token)
    
    if [ -z "$TOKEN" ]; then
        echo -e "${RED}Error: Failed to authenticate with Keycloak${NC}"
        echo "Please check your admin credentials"
        exit 1
    fi
    
    echo -e "${GREEN}Authentication successful!${NC}"

    # Create realm and configure it step by step
    # Refresh token before each operation to prevent expiration
    if create_realm "$TOKEN"; then
        refresh_token
        create_clients "$TOKEN"

        refresh_token
        create_scopes "$TOKEN"

        refresh_token
        create_groups "$TOKEN"

        refresh_token
        create_users "$TOKEN"

        refresh_token
        create_service_account_user "$TOKEN"

        refresh_token
        create_service_account_clients "$TOKEN"

        refresh_token
        setup_client_secrets "$TOKEN"

        refresh_token
        setup_groups_mapper "$TOKEN"

        refresh_token
        setup_m2m_scopes "$TOKEN"
    else
        exit 1
    fi
    
    echo ""
    echo -e "${GREEN}Keycloak initialization complete!${NC}"
    echo ""
    echo "You can now access Keycloak at: ${KEYCLOAK_URL}"
    echo "Admin console: ${KEYCLOAK_URL}/admin"
    echo "Realm: ${REALM}"
    echo ""
    echo "Users created:"
    echo "  - admin/${INITIAL_ADMIN_PASSWORD} (realm admin - all groups including mcp-registry-admin)"
    echo "  - testuser/${INITIAL_USER_PASSWORD:-testpass} (test user - user/developer/operator groups)"
    echo "  - lob1-user/${LOB1_USER_PASSWORD:-lob1pass} (LOB1 user - registry-users-lob1 group)"
    echo "  - lob2-user/${LOB2_USER_PASSWORD:-lob2pass} (LOB2 user - registry-users-lob2 group)"
    echo "  - service-account-mcp-gateway-m2m (service account for M2M access)"
    echo ""
    echo "Service Account Clients (M2M):"
    echo "  - registry-admin-bot (in registry-admins group)"
    echo "  - lob1-bot (in registry-users-lob1 group)"
    echo "  - lob2-bot (in registry-users-lob2 group)"
    echo ""
    echo "Groups created:"
    echo "  - mcp-registry-admin, mcp-registry-user, mcp-registry-developer"
    echo "  - mcp-registry-operator, mcp-servers-unrestricted, mcp-servers-restricted"
    echo "  - a2a-agent-admin, a2a-agent-publisher, a2a-agent-user"
    echo "  - registry-admins, registry-users-lob1, registry-users-lob2"
    echo ""
    echo "OAuth2 Clients:"
    echo "  - mcp-gateway-web (for UI authentication)"
    echo "  - mcp-gateway-m2m (for service-to-service authentication)"
    echo ""
    echo -e "${YELLOW}Remember to change the default passwords!${NC}"
}

# Run main function
main