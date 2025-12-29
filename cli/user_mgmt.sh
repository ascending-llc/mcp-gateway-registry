#!/bin/bash
# DEPRECATED: This script is deprecated in favor of the Registry Management API
# Use: uv run python api/registry_management.py OR cli/registry_cli_wrapper.py
# See: api/README.md for documentation
#
# User Management Script for MCP Gateway Registry
# This script manages both M2M (machine-to-machine) service accounts and human users

echo "WARNING: This script is DEPRECATED. Please use the Registry Management API instead:"
echo "  uv run python api/registry_management.py --help"
echo "  OR cli/registry_cli_wrapper.py --help"
echo "See api/README.md for full documentation."
echo ""

set -e

# Configuration
ADMIN_URL="http://localhost:8080"
REALM="mcp-gateway"
ADMIN_USER="admin"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OAUTH_TOKENS_DIR="$SCRIPT_DIR/../.oauth-tokens"
CLIENT_SECRETS_FILE="$OAUTH_TOKENS_DIR/keycloak-client-secrets.txt"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'


# Usage function
usage() {
    echo "Usage: $0 {create-m2m|create-human|delete-user|list-users|list-groups} [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  create-m2m              - Create M2M service account for machine-to-machine authentication"
    echo "  create-human            - Create human user with Keycloak login capabilities"
    echo "  delete-user             - Delete a user (M2M or human)"
    echo "  list-users              - List all users in the realm"
    echo "  list-groups             - List all available groups"
    echo ""
    echo "M2M Service Account Options:"
    echo "  -n, --name NAME         - Service account name (required)"
    echo "  -g, --groups GROUPS     - Comma-separated list of groups (required)"
    echo "  -d, --description DESC  - Description of the service account"
    echo ""
    echo "Human User Options:"
    echo "  -u, --username USERNAME - Username (required)"
    echo "  -e, --email EMAIL       - Email address (required)"
    echo "  -f, --firstname NAME    - First name (required)"
    echo "  -l, --lastname NAME     - Last name (required)"
    echo "  -g, --groups GROUPS     - Comma-separated list of groups (required)"
    echo "  -p, --password PASS     - Initial password (optional, will prompt if not provided)"
    echo ""
    echo "Delete User Options:"
    echo "  -u, --username USERNAME - Username to delete (required)"
    echo ""
    echo "Examples:"
    echo "  # Create M2M service account"
    echo "  $0 create-m2m --name agent-finance-bot --groups 'mcp-servers-finance/read,mcp-servers-finance/execute'"
    echo ""
    echo "  # Create human user"
    echo "  $0 create-human --username jdoe --email jdoe@example.com --firstname John --lastname Doe --groups 'mcp-servers-restricted/read'"
    echo ""
    echo "  # Delete user"
    echo "  $0 delete-user --username agent-finance-bot"
    echo ""
    echo "  # List all users"
    echo "  $0 list-users"
    echo ""
    echo "  # List all groups"
    echo "  $0 list-groups"
}


# Function to get admin token
get_admin_token() {
    if [ -z "$ADMIN_PASS" ]; then
        echo -e "${RED}Error: KEYCLOAK_ADMIN_PASSWORD environment variable is required${NC}"
        echo "Please set it before running this script:"
        echo "export KEYCLOAK_ADMIN_PASSWORD=\"your-secure-password\""
        exit 1
    fi

    TOKEN=$(curl -s -X POST "$ADMIN_URL/realms/master/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=$ADMIN_USER" \
        -d "password=$ADMIN_PASS" \
        -d "grant_type=password" \
        -d "client_id=admin-cli" | jq -r '.access_token // empty')

    if [ -z "$TOKEN" ]; then
        echo -e "${RED}Failed to get admin token${NC}"
        exit 1
    fi
}


# Function to list all groups
list_groups() {
    echo -e "${BLUE}Listing all groups in realm '$REALM'${NC}"
    echo "=============================================="

    get_admin_token

    GROUPS=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "$ADMIN_URL/admin/realms/$REALM/groups")

    echo "$GROUPS" | jq -r '.[] | "\(.name) (ID: \(.id))"'

    echo ""
    echo -e "${GREEN}Total groups: $(echo "$GROUPS" | jq '. | length')${NC}"
}


# Function to list all users
list_users() {
    echo -e "${BLUE}Listing all users in realm '$REALM'${NC}"
    echo "=============================================="

    get_admin_token

    USERS=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "$ADMIN_URL/admin/realms/$REALM/users")

    echo "$USERS" | jq -r '.[] | "Username: \(.username), Email: \(.email // "N/A"), Enabled: \(.enabled), ID: \(.id)"'

    echo ""
    echo -e "${GREEN}Total users: $(echo "$USERS" | jq '. | length')${NC}"
}


# Function to check if group exists
check_group_exists() {
    local group_name="$1"

    GROUP_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "$ADMIN_URL/admin/realms/$REALM/groups" | \
        jq -r ".[] | select(.name==\"$group_name\") | .id")

    if [ -z "$GROUP_ID" ] || [ "$GROUP_ID" = "null" ]; then
        return 1
    fi
    return 0
}


# Function to validate groups
validate_groups() {
    local groups_input="$1"
    IFS=',' read -ra GROUPS_ARRAY <<< "$groups_input"

    local invalid_groups=()

    for group in "${GROUPS_ARRAY[@]}"; do
        group=$(echo "$group" | xargs) # trim whitespace
        if ! check_group_exists "$group"; then
            invalid_groups+=("$group")
        fi
    done

    if [ ${#invalid_groups[@]} -gt 0 ]; then
        echo -e "${RED}Error: The following groups do not exist:${NC}"
        for group in "${invalid_groups[@]}"; do
            echo "  - $group"
        done
        echo ""
        echo -e "${YELLOW}Available groups:${NC}"
        curl -s -H "Authorization: Bearer $TOKEN" \
            "$ADMIN_URL/admin/realms/$REALM/groups" | \
            jq -r '.[].name' | sed 's/^/  - /'
        return 1
    fi

    return 0
}


# Function to create M2M client
create_m2m_client() {
    local client_id="$1"
    local description="$2"

    echo "Creating M2M client: $client_id"

    # Check if client already exists
    EXISTING_CLIENT=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "$ADMIN_URL/admin/realms/$REALM/clients?clientId=$client_id" | \
        jq -r '.[0].id // empty')

    if [ -n "$EXISTING_CLIENT" ]; then
        echo -e "${YELLOW}Client '$client_id' already exists, using existing client${NC}"
        CLIENT_UUID="$EXISTING_CLIENT"
        return 0
    fi

    # Create the client
    CLIENT_JSON="{
        \"clientId\": \"$client_id\",
        \"name\": \"$client_id\",
        \"description\": \"$description\",
        \"enabled\": true,
        \"clientAuthenticatorType\": \"client-secret\",
        \"serviceAccountsEnabled\": true,
        \"standardFlowEnabled\": false,
        \"directAccessGrantsEnabled\": false,
        \"publicClient\": false,
        \"protocol\": \"openid-connect\"
    }"

    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$ADMIN_URL/admin/realms/$REALM/clients" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$CLIENT_JSON")

    if [ "$RESPONSE" = "201" ]; then
        echo -e "${GREEN}✓ M2M client created successfully${NC}"

        # Get the client UUID
        CLIENT_UUID=$(curl -s -H "Authorization: Bearer $TOKEN" \
            "$ADMIN_URL/admin/realms/$REALM/clients?clientId=$client_id" | \
            jq -r '.[0].id')

        echo "Client UUID: $CLIENT_UUID"
    else
        echo -e "${RED}Failed to create M2M client. HTTP: $RESPONSE${NC}"
        exit 1
    fi
}


# Function to get client secret
get_client_secret() {
    local client_uuid="$1"

    CLIENT_SECRET=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "$ADMIN_URL/admin/realms/$REALM/clients/$client_uuid/client-secret" | \
        jq -r '.value')

    if [ -z "$CLIENT_SECRET" ] || [ "$CLIENT_SECRET" = "null" ]; then
        echo -e "${RED}Failed to retrieve client secret${NC}"
        exit 1
    fi
}


# Function to add groups mapper to client
add_groups_mapper() {
    local client_uuid="$1"

    echo "Adding groups mapper to client..."

    # Check if groups mapper already exists
    EXISTING_MAPPER=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "$ADMIN_URL/admin/realms/$REALM/clients/$client_uuid/protocol-mappers/models" | \
        jq -r '.[] | select(.name=="groups") | .id')

    if [ -n "$EXISTING_MAPPER" ] && [ "$EXISTING_MAPPER" != "null" ]; then
        echo -e "${GREEN}✓ Groups mapper already exists${NC}"
        return 0
    fi

    GROUPS_MAPPER='{
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

    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$ADMIN_URL/admin/realms/$REALM/clients/$client_uuid/protocol-mappers/models" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$GROUPS_MAPPER")

    if [ "$RESPONSE" = "201" ] || [ "$RESPONSE" = "409" ]; then
        echo -e "${GREEN}✓ Groups mapper configured${NC}"
    else
        echo -e "${RED}Failed to add groups mapper. HTTP: $RESPONSE${NC}"
        exit 1
    fi
}


# Function to get service account user ID
get_service_account_user() {
    local client_uuid="$1"

    SERVICE_ACCOUNT_USER=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "$ADMIN_URL/admin/realms/$REALM/clients/$client_uuid/service-account-user" | \
        jq -r '.id')

    if [ -z "$SERVICE_ACCOUNT_USER" ] || [ "$SERVICE_ACCOUNT_USER" = "null" ]; then
        echo -e "${RED}Failed to retrieve service account user${NC}"
        exit 1
    fi
}


# Function to assign user to groups
assign_user_to_groups() {
    local user_id="$1"
    local groups_input="$2"

    IFS=',' read -ra GROUPS_ARRAY <<< "$groups_input"

    for group in "${GROUPS_ARRAY[@]}"; do
        group=$(echo "$group" | xargs) # trim whitespace

        # Get group ID
        GROUP_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
            "$ADMIN_URL/admin/realms/$REALM/groups" | \
            jq -r ".[] | select(.name==\"$group\") | .id")

        if [ -z "$GROUP_ID" ] || [ "$GROUP_ID" = "null" ]; then
            echo -e "${RED}Group '$group' not found${NC}"
            continue
        fi

        # Assign to group
        RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
            -X PUT "$ADMIN_URL/admin/realms/$REALM/users/$user_id/groups/$GROUP_ID" \
            -H "Authorization: Bearer $TOKEN")

        if [ "$RESPONSE" = "204" ]; then
            echo -e "${GREEN}✓ Assigned to group: $group${NC}"
        else
            echo -e "${RED}Failed to assign to group '$group'. HTTP: $RESPONSE${NC}"
        fi
    done
}


# Function to refresh all credentials using get-all-client-credentials.sh
refresh_all_credentials() {
    echo "Refreshing all client credentials..."

    # Call the existing script to regenerate all credential files
    # Run from project root so it saves to .oauth-tokens/ at the root
    PROJECT_ROOT="$SCRIPT_DIR/.."
    KEYCLOAK_SETUP_SCRIPT="$PROJECT_ROOT/keycloak/setup/get-all-client-credentials.sh"

    if [ -f "$KEYCLOAK_SETUP_SCRIPT" ]; then
        (cd "$PROJECT_ROOT" && ./keycloak/setup/get-all-client-credentials.sh)
        echo -e "${GREEN}✓ All credentials refreshed${NC}"
    else
        echo -e "${RED}Error: get-all-client-credentials.sh not found at $KEYCLOAK_SETUP_SCRIPT${NC}"
        exit 1
    fi
}


# Function to generate access token for M2M client
generate_access_token() {
    local client_id="$1"

    echo "Generating access token for: $client_id"

    # Call the existing script to generate token and .env files
    PROJECT_ROOT="$SCRIPT_DIR/.."
    GENERATE_TOKEN_SCRIPT="$PROJECT_ROOT/keycloak/setup/generate-agent-token.sh"

    if [ -f "$GENERATE_TOKEN_SCRIPT" ]; then
        (cd "$PROJECT_ROOT/keycloak/setup" && ./generate-agent-token.sh "$client_id")
        echo -e "${GREEN}✓ Access token generated${NC}"
    else
        echo -e "${RED}Error: generate-agent-token.sh not found at $GENERATE_TOKEN_SCRIPT${NC}"
        exit 1
    fi
}


# Function to create M2M service account
create_m2m_account() {
    local name=""
    local groups=""
    local description=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -n|--name)
                name="$2"
                shift 2
                ;;
            -g|--groups)
                groups="$2"
                shift 2
                ;;
            -d|--description)
                description="$2"
                shift 2
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                usage
                exit 1
                ;;
        esac
    done

    # Validate required parameters
    if [ -z "$name" ]; then
        echo -e "${RED}Error: Service account name is required${NC}"
        usage
        exit 1
    fi

    if [ -z "$groups" ]; then
        echo -e "${RED}Error: Groups are required${NC}"
        usage
        exit 1
    fi

    if [ -z "$description" ]; then
        description="M2M service account for $name"
    fi

    CLIENT_ID="$name"

    echo -e "${BLUE}Creating M2M Service Account${NC}"
    echo "=============================================="
    echo "Name: $name"
    echo "Groups: $groups"
    echo "Description: $description"
    echo ""

    # Get admin token
    get_admin_token

    # Validate groups
    if ! validate_groups "$groups"; then
        exit 1
    fi

    # Create M2M client
    create_m2m_client "$CLIENT_ID" "$description"

    # Add groups mapper
    add_groups_mapper "$CLIENT_UUID"

    # Get service account user
    get_service_account_user "$CLIENT_UUID"

    # Assign to groups
    assign_user_to_groups "$SERVICE_ACCOUNT_USER" "$groups"

    # Get client secret
    get_client_secret "$CLIENT_UUID"

    # Refresh all credentials using the existing script
    echo ""
    refresh_all_credentials

    # Generate access token and .env file
    echo ""
    generate_access_token "$CLIENT_ID"

    echo ""
    echo -e "${GREEN}SUCCESS! M2M service account created${NC}"
    echo "=============================================="
    echo "Client ID: $CLIENT_ID"
    echo "Client Secret: $CLIENT_SECRET"
    echo "Groups: $groups"
    echo ""
    echo -e "${YELLOW}Credentials saved to:${NC}"
    echo "  $OAUTH_TOKENS_DIR/${CLIENT_ID}.json (client credentials)"
    echo "  $OAUTH_TOKENS_DIR/${CLIENT_ID}-token.json (access token)"
    echo "  $OAUTH_TOKENS_DIR/${CLIENT_ID}.env (environment variables)"
    echo "  $OAUTH_TOKENS_DIR/keycloak-client-secrets.txt (all client secrets)"
    echo ""
    echo -e "${YELLOW}Test the account:${NC}"
    echo "curl -X POST '$ADMIN_URL/realms/$REALM/protocol/openid-connect/token' \\"
    echo "  -H 'Content-Type: application/x-www-form-urlencoded' \\"
    echo "  -d 'grant_type=client_credentials' \\"
    echo "  -d 'client_id=$CLIENT_ID' \\"
    echo "  -d 'client_secret=$CLIENT_SECRET'"
}


# Function to create human user
create_human_user() {
    local username=""
    local email=""
    local firstname=""
    local lastname=""
    local groups=""
    local password=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -u|--username)
                username="$2"
                shift 2
                ;;
            -e|--email)
                email="$2"
                shift 2
                ;;
            -f|--firstname)
                firstname="$2"
                shift 2
                ;;
            -l|--lastname)
                lastname="$2"
                shift 2
                ;;
            -g|--groups)
                groups="$2"
                shift 2
                ;;
            -p|--password)
                password="$2"
                shift 2
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                usage
                exit 1
                ;;
        esac
    done

    # Validate required parameters
    if [ -z "$username" ]; then
        echo -e "${RED}Error: Username is required${NC}"
        usage
        exit 1
    fi

    if [ -z "$email" ]; then
        echo -e "${RED}Error: Email is required${NC}"
        usage
        exit 1
    fi

    if [ -z "$firstname" ]; then
        echo -e "${RED}Error: First name is required${NC}"
        usage
        exit 1
    fi

    if [ -z "$lastname" ]; then
        echo -e "${RED}Error: Last name is required${NC}"
        usage
        exit 1
    fi

    if [ -z "$groups" ]; then
        echo -e "${RED}Error: Groups are required${NC}"
        usage
        exit 1
    fi

    # Prompt for password if not provided
    if [ -z "$password" ]; then
        echo -n "Enter password for user: "
        read -s password
        echo ""
        echo -n "Confirm password: "
        read -s password_confirm
        echo ""

        if [ "$password" != "$password_confirm" ]; then
            echo -e "${RED}Error: Passwords do not match${NC}"
            exit 1
        fi
    fi

    echo -e "${BLUE}Creating Human User${NC}"
    echo "=============================================="
    echo "Username: $username"
    echo "Email: $email"
    echo "Name: $firstname $lastname"
    echo "Groups: $groups"
    echo ""

    # Get admin token
    get_admin_token

    # Validate groups
    if ! validate_groups "$groups"; then
        exit 1
    fi

    # Check if user already exists
    EXISTING_USER=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "$ADMIN_URL/admin/realms/$REALM/users?username=$username" | \
        jq -r '.[0].id // empty')

    if [ -n "$EXISTING_USER" ]; then
        echo -e "${RED}Error: User '$username' already exists${NC}"
        exit 1
    fi

    # Create user
    USER_JSON="{
        \"username\": \"$username\",
        \"email\": \"$email\",
        \"firstName\": \"$firstname\",
        \"lastName\": \"$lastname\",
        \"enabled\": true,
        \"emailVerified\": true,
        \"credentials\": [{
            \"type\": \"password\",
            \"value\": \"$password\",
            \"temporary\": false
        }]
    }"

    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$ADMIN_URL/admin/realms/$REALM/users" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$USER_JSON")

    if [ "$RESPONSE" = "201" ]; then
        echo -e "${GREEN}✓ User created successfully${NC}"

        # Get the user ID
        USER_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
            "$ADMIN_URL/admin/realms/$REALM/users?username=$username" | \
            jq -r '.[0].id')

        echo "User ID: $USER_ID"

        # Assign to groups
        assign_user_to_groups "$USER_ID" "$groups"

        echo ""
        echo -e "${GREEN}SUCCESS! Human user created${NC}"
        echo "=============================================="
        echo "Username: $username"
        echo "Email: $email"
        echo "Groups: $groups"
        echo ""
        echo -e "${YELLOW}User can login to Keycloak at:${NC}"
        echo "$ADMIN_URL/realms/$REALM/account"
        echo ""
        echo -e "${YELLOW}Or authenticate via API:${NC}"
        echo "curl -X POST '$ADMIN_URL/realms/$REALM/protocol/openid-connect/token' \\"
        echo "  -H 'Content-Type: application/x-www-form-urlencoded' \\"
        echo "  -d 'grant_type=password' \\"
        echo "  -d 'client_id=mcp-gateway-m2m' \\"
        echo "  -d 'username=$username' \\"
        echo "  -d 'password=YOUR_PASSWORD'"
    else
        echo -e "${RED}Failed to create user. HTTP: $RESPONSE${NC}"
        exit 1
    fi
}


# Function to delete user
delete_user() {
    local username=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -u|--username)
                username="$2"
                shift 2
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                usage
                exit 1
                ;;
        esac
    done

    # Validate required parameters
    if [ -z "$username" ]; then
        echo -e "${RED}Error: Username is required${NC}"
        usage
        exit 1
    fi

    echo -e "${BLUE}Deleting User${NC}"
    echo "=============================================="
    echo "Username: $username"
    echo ""

    # Get admin token
    get_admin_token

    # Find user
    USER_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
        "$ADMIN_URL/admin/realms/$REALM/users?username=$username" | \
        jq -r '.[0].id // empty')

    if [ -z "$USER_ID" ]; then
        echo -e "${RED}Error: User '$username' not found${NC}"
        exit 1
    fi

    # Delete user
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
        -X DELETE "$ADMIN_URL/admin/realms/$REALM/users/$USER_ID" \
        -H "Authorization: Bearer $TOKEN")

    if [ "$RESPONSE" = "204" ]; then
        echo -e "${GREEN}✓ User deleted successfully${NC}"

        # Refresh all credentials to update files
        echo ""
        refresh_all_credentials

        echo ""
        echo -e "${GREEN}✓ Credential files updated${NC}"
    else
        echo -e "${RED}Failed to delete user. HTTP: $RESPONSE${NC}"
        exit 1
    fi
}


# Main execution
main() {
    if [ $# -eq 0 ]; then
        usage
        exit 1
    fi

    COMMAND=$1
    shift

    case $COMMAND in
        create-m2m)
            create_m2m_account "$@"
            ;;
        create-human)
            create_human_user "$@"
            ;;
        delete-user)
            delete_user "$@"
            ;;
        list-users)
            list_users
            ;;
        list-groups)
            list_groups
            ;;
        -h|--help|help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown command: $COMMAND${NC}"
            usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
