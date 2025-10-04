#!/bin/bash

# Service Management Script for MCP Gateway Registry
# Usage: ./cli/service_mgmt.sh {add|delete|monitor} [service_name]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Unicode symbols
CHECK_MARK="✓"
CROSS_MARK="✗"

# Get script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default service name
DEFAULT_SERVICE="example-server"

print_success() {
    echo -e "${GREEN}${CHECK_MARK} $1${NC}"
}

print_error() {
    echo -e "${RED}${CROSS_MARK} $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

check_prerequisites() {
    print_info "Checking prerequisites..."

    # Check and refresh credentials if needed
    if ! "$PROJECT_ROOT/credentials-provider/check_and_refresh_creds.sh"; then
        print_error "Failed to setup credentials"
        exit 1
    fi
    print_success "Credentials ready"
}

run_mcp_command() {
    local tool="$1"
    local args="$2"
    local description="$3"

    print_info "$description"

    # Print the exact command being executed
    echo "🔍 Executing: uv run cli/mcp_client.py --url http://localhost/mcpgw/mcp call --tool $tool --args '$args'"

    if output=$(cd "$PROJECT_ROOT" && uv run cli/mcp_client.py --url http://localhost/mcpgw/mcp call --tool "$tool" --args "$args" 2>&1); then
        print_success "$description completed"
        echo "$output"
        return 0
    else
        print_error "$description failed"
        echo "$output"
        return 1
    fi
}

verify_server_in_list() {
    local service_name="$1"
    local should_exist="$2"  # "true" or "false"

    print_info "Checking server in service list..."

    if output=$(cd "$PROJECT_ROOT" && uv run cli/mcp_client.py --url http://localhost/mcpgw/mcp call --tool list_services --args '{}' 2>&1); then
        if echo "$output" | grep -q "$service_name"; then
            if [ "$should_exist" = "true" ]; then
                print_success "Server found in service list"
                echo "$output" | grep -A2 -B2 "$service_name"
                return 0
            else
                print_error "Server still exists in service list (should be removed)"
                return 1
            fi
        else
            if [ "$should_exist" = "false" ]; then
                print_success "Server not found in service list (expected)"
                return 0
            else
                print_error "Server not found in service list"
                return 1
            fi
        fi
    else
        print_error "Failed to check service list"
        echo "$output"
        return 1
    fi
}

verify_scopes_yml() {
    local service_name="$1"
    local should_exist="$2"  # "true" or "false"

    print_info "Checking scopes.yml files..."

    # Check container scopes.yml
    local container_count
    container_count=$(docker exec mcp-gateway-registry_auth-server_1 grep -c "$service_name" /app/scopes.yml 2>/dev/null || echo "0")
    # Ensure we only get the last line if multiple lines are returned
    container_count=$(echo "$container_count" | tail -1)

    if [ "$should_exist" = "true" ] && [ "$container_count" -gt "0" ]; then
        print_success "Server found in container scopes.yml ($container_count occurrences)"
    elif [ "$should_exist" = "false" ] && [ "$container_count" -eq "0" ]; then
        print_success "Server not found in container scopes.yml (expected)"
    else
        if [ "$should_exist" = "true" ]; then
            print_error "Server not found in container scopes.yml"
        else
            print_error "Server still exists in container scopes.yml ($container_count occurrences)"
        fi
        return 1
    fi

    # Check host scopes.yml
    local host_count
    host_count=$(grep -c "$service_name" "${HOME}/mcp-gateway/auth_server/scopes.yml" 2>/dev/null || echo "0")
    # Ensure we only get the last line if multiple lines are returned
    host_count=$(echo "$host_count" | tail -1)

    if [ "$should_exist" = "true" ] && [ "$host_count" -gt "0" ]; then
        print_success "Server found in host scopes.yml ($host_count occurrences)"
    elif [ "$should_exist" = "false" ] && [ "$host_count" -eq "0" ]; then
        print_success "Server not found in host scopes.yml (expected)"
    else
        if [ "$should_exist" = "true" ]; then
            print_error "Server not found in host scopes.yml"
        else
            print_error "Server still exists in host scopes.yml ($host_count occurrences)"
        fi
        return 1
    fi
}

verify_faiss_metadata() {
    local service_name="$1"
    local should_exist="$2"  # "true" or "false"

    print_info "Checking FAISS index metadata..."

    local metadata_count
    metadata_count=$(docker exec mcp-gateway-registry_registry_1 grep -c "$service_name" /app/registry/servers/service_index_metadata.json 2>/dev/null || echo "0")
    # Ensure we only get the last line if multiple lines are returned
    metadata_count=$(echo "$metadata_count" | tail -1)

    if [ "$should_exist" = "true" ] && [ "$metadata_count" -gt "0" ]; then
        print_success "Server found in FAISS metadata ($metadata_count occurrences)"
    elif [ "$should_exist" = "false" ] && [ "$metadata_count" -eq "0" ]; then
        print_success "Server not found in FAISS metadata (expected)"
    else
        if [ "$should_exist" = "true" ]; then
            print_error "Server not found in FAISS metadata"
        else
            print_error "Server still exists in FAISS metadata ($metadata_count occurrences)"
        fi
        return 1
    fi
}

parse_health_output() {
    local json_output="$1"
    local service_filter="$2"

    # Write output to temp file to avoid shell escaping issues
    local temp_file=$(mktemp)
    echo "$json_output" > "$temp_file"

    # Use Python to parse JSON and format output
    python3 -c "
import json
import sys
from datetime import datetime, timezone
import re

try:
    # Read from temp file
    with open('$temp_file', 'r') as f:
        output = f.read()

    # Look for the main JSON response (starts after authentication message)
    json_start = output.find('{')
    if json_start == -1:
        print('No JSON found in output')
        sys.exit(1)

    # Find the matching closing brace
    brace_count = 0
    json_end = json_start
    for i, char in enumerate(output[json_start:], json_start):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break

    json_text = output[json_start:json_end]
    data = json.loads(json_text)

    # Extract health data from structuredContent if available, otherwise from top level
    if 'structuredContent' in data:
        health_data = data['structuredContent']
    else:
        # Fallback to top level if no structuredContent
        health_data = data

    current_time = datetime.now(timezone.utc)

    print('Health Check Results:')
    print('=' * 50)

    for service_path, info in health_data.items():
        # Skip if filtering for specific service and this doesn't match
        if '$service_filter' and '$service_filter' not in service_path:
            continue

        status = info.get('status', 'unknown')
        last_checked = info.get('last_checked_iso', '')
        num_tools = info.get('num_tools', 0)

        # Calculate time difference
        if last_checked:
            try:
                check_time = datetime.fromisoformat(last_checked.replace('Z', '+00:00'))
                time_diff = current_time - check_time
                seconds_ago = int(time_diff.total_seconds())
                time_str = f'{seconds_ago} seconds ago'
            except:
                time_str = 'unknown time'
        else:
            time_str = 'never checked'

        # Format status with color indicators
        if status == 'healthy':
            status_display = '✓ healthy'
        elif status == 'unhealthy':
            status_display = '✗ unhealthy'
        elif 'auth-expired' in status:
            status_display = '⚠ healthy-auth-expired'
        else:
            status_display = f'? {status}'

        print(f'Service: {service_path}')
        print(f'  Status: {status_display}')
        print(f'  Last checked: {time_str}')
        print(f'  Tools available: {num_tools}')
        print()

except json.JSONDecodeError as e:
    print(f'Error parsing JSON: {e}')
    with open('$temp_file', 'r') as f:
        print('Raw output:')
        print(f.read())
    sys.exit(1)
except Exception as e:
    print(f'Error processing health check: {e}')
    sys.exit(1)
"

    # Clean up temp file
    rm -f "$temp_file"
}

run_health_check() {
    local service_name="$1"

    print_info "Running health check..."

    if output=$(cd "$PROJECT_ROOT" && uv run cli/mcp_client.py --url http://localhost/mcpgw/mcp call --tool healthcheck --args '{}' 2>&1); then
        print_success "Health check completed"
        echo ""

        # Parse and display formatted output
        if ! parse_health_output "$output" "$service_name"; then
            print_error "Failed to parse health check output"
            echo "Raw output:"
            echo "$output"
            return 1
        fi
        return 0
    else
        print_error "Health check failed"
        echo "$output"
        return 1
    fi
}

validate_config() {
    local config_json="$1"

    # Use Python to validate fields according to register_service tool spec
    python3 -c "
import json
import sys

try:
    config = json.loads('''$config_json''')

    # Required fields (based on register_service tool spec)
    required_fields = ['server_name', 'path', 'proxy_pass_url']
    missing_fields = []

    for field in required_fields:
        if field not in config or not config[field]:
            missing_fields.append(field)

    if missing_fields:
        print(f'ERROR: Missing required fields in config: {missing_fields}')
        sys.exit(1)

    # Validate field types and constraints
    errors = []

    # server_name: must be string and non-empty
    if not isinstance(config['server_name'], str) or not config['server_name'].strip():
        errors.append('server_name must be a non-empty string')

    # path: must be string, start with '/', and be unique URL path prefix
    if not isinstance(config['path'], str):
        errors.append('path must be a string')
    elif not config['path'].startswith('/'):
        errors.append('path must start with \"/\"')
    elif len(config['path']) < 2:
        errors.append('path must be more than just \"/\"')

    # proxy_pass_url: must be string and valid URL format
    if not isinstance(config['proxy_pass_url'], str):
        errors.append('proxy_pass_url must be a string')
    elif not (config['proxy_pass_url'].startswith('http://') or config['proxy_pass_url'].startswith('https://')):
        errors.append('proxy_pass_url must start with http:// or https://')

    # Check for unknown fields (not part of tool spec)
    allowed_fields = {'server_name', 'path', 'proxy_pass_url', 'description', 'tags', 'num_tools', 'num_stars', 'is_python', 'license'}
    unknown_fields = set(config.keys()) - allowed_fields
    if unknown_fields:
        errors.append(f'Unknown fields not allowed by register_service tool spec: {sorted(unknown_fields)}')

    # Optional field validations
    if 'description' in config and config['description'] is not None:
        if not isinstance(config['description'], str):
            errors.append('description must be a string')

    if 'tags' in config and config['tags'] is not None:
        if not isinstance(config['tags'], list):
            errors.append('tags must be a list')
        elif not all(isinstance(tag, str) for tag in config['tags']):
            errors.append('all tags must be strings')

    if 'num_tools' in config and config['num_tools'] is not None:
        if not isinstance(config['num_tools'], int) or config['num_tools'] < 0:
            errors.append('num_tools must be a non-negative integer')

    if 'num_stars' in config and config['num_stars'] is not None:
        if not isinstance(config['num_stars'], int) or config['num_stars'] < 0:
            errors.append('num_stars must be a non-negative integer')

    if 'is_python' in config and config['is_python'] is not None:
        if not isinstance(config['is_python'], bool):
            errors.append('is_python must be a boolean')

    if 'license' in config and config['license'] is not None:
        if not isinstance(config['license'], str):
            errors.append('license must be a string')

    if errors:
        print('ERROR: Config validation failed:')
        for error in errors:
            print(f'  - {error}')
        sys.exit(1)

    # Extract service name from path for validation
    service_name = config['path'].lstrip('/')
    print(service_name)

except json.JSONDecodeError as e:
    print(f'ERROR: Invalid JSON in config: {e}')
    sys.exit(1)
except Exception as e:
    print(f'ERROR: Config validation failed: {e}')
    sys.exit(1)
"
}

add_service() {
    local config_file="${1}"

    if [ -z "$config_file" ]; then
        print_error "Usage: $0 add <config-file>"
        print_error "Example: $0 add cli/examples/example-server-config.json"
        exit 1
    fi

    if [ ! -f "$config_file" ]; then
        print_error "Config file not found: $config_file"
        print_error "Full path searched: $(pwd)/$config_file"
        exit 1
    fi

    print_info "Loading config from: $config_file"
    local config_json
    config_json="$(cat "$config_file")"

    # Validate config and extract service name
    local service_name
    if ! service_name=$(validate_config "$config_json"); then
        print_error "Config validation failed"
        echo "$service_name"  # This contains error message
        exit 1
    fi

    echo "=== Adding Service: $service_name ==="

    # Check prerequisites
    check_prerequisites

    # Register the service
    if ! run_mcp_command "register_service" "$config_json" "Registering service"; then
        exit 1
    fi

    # Verify registration
    echo ""
    echo "=== Verifying Registration ==="

    if ! verify_server_in_list "$service_path" "true"; then
        exit 1
    fi

    if ! verify_scopes_yml "$service_name" "true"; then
        exit 1
    fi

    if ! verify_faiss_metadata "$service_name" "true"; then
        exit 1
    fi

    # Run health check
    echo ""
    echo "=== Health Check ==="
    if ! run_health_check "$service_name"; then
        exit 1
    fi

    echo ""
    print_success "Service $service_name successfully added and verified!"
}

delete_service() {
    local config_file="${1}"

    if [ -z "$config_file" ]; then
        print_error "Usage: $0 delete <config-file>"
        print_error "Example: $0 delete cli/examples/example-server-config.json"
        exit 1
    fi

    if [ ! -f "$config_file" ]; then
        print_error "Config file not found: $config_file"
        print_error "Full path searched: $(pwd)/$config_file"
        exit 1
    fi

    print_info "Loading config from: $config_file"
    local config_json
    config_json="$(cat "$config_file")"

    # Validate config and extract service info
    local service_name
    if ! service_name=$(validate_config "$config_json"); then
        print_error "Config validation failed"
        echo "$service_name"  # This contains error message
        exit 1
    fi

    # Extract service path from config
    local service_path
    service_path=$(python3 -c "
import json
config = json.loads('''$config_json''')
print(config['path'])
")

    echo "=== Deleting Service: $service_name (path: $service_path) ==="

    # Check prerequisites
    check_prerequisites

    # Remove the service
    if ! run_mcp_command "remove_service" "{\"service_path\": \"$service_path\"}" "Removing service"; then
        exit 1
    fi

    # Verify deletion
    echo ""
    echo "=== Verifying Deletion ==="

    if ! verify_server_in_list "$service_path" "false"; then
        exit 1
    fi

    if ! verify_scopes_yml "$service_name" "false"; then
        exit 1
    fi

    if ! verify_faiss_metadata "$service_name" "false"; then
        exit 1
    fi

    echo ""
    print_success "Service $service_name successfully deleted and verified!"
}

test_service() {
    local config_file="${1}"

    if [ -z "$config_file" ]; then
        print_error "Usage: $0 test <config-file>"
        print_error "Example: $0 test cli/examples/example-server-config.json"
        exit 1
    fi

    if [ ! -f "$config_file" ]; then
        print_error "Config file not found: $config_file"
        print_error "Full path searched: $(pwd)/$config_file"
        exit 1
    fi

    print_info "Loading config from: $config_file"
    local config_json
    config_json="$(cat "$config_file")"

    # Validate config and extract service info
    local service_name
    if ! service_name=$(validate_config "$config_json"); then
        print_error "Config validation failed"
        echo "$service_name"  # This contains error message
        exit 1
    fi

    # Extract description and tags for testing
    local description tags_json
    description=$(python3 -c "
import json
config = json.loads('''$config_json''')
print(config.get('description', ''))
")
    tags_json=$(python3 -c "
import json
config = json.loads('''$config_json''')
tags = config.get('tags', [])
print(json.dumps(tags))
")

    echo "=== Testing Service: $service_name ==="

    # Check prerequisites
    check_prerequisites

    # Test intelligent tool finder with description
    if [ -n "$description" ]; then
        print_info "Testing search with description: \"$description\""
        if ! run_mcp_command "intelligent_tool_finder" "{\"natural_language_query\": \"$description\"}" "Searching with description"; then
            print_error "Failed to search with description"
        else
            print_success "Search with description completed"
        fi
        echo ""
    fi

    # Test intelligent tool finder with tags only
    if [ "$tags_json" != "[]" ]; then
        print_info "Testing search with tags: $tags_json"
        if ! run_mcp_command "intelligent_tool_finder" "{\"tags\": $tags_json}" "Searching with tags"; then
            print_error "Failed to search with tags"
        else
            print_success "Search with tags completed"
        fi
        echo ""
    fi

    # Test combined search
    if [ -n "$description" ] && [ "$tags_json" != "[]" ]; then
        print_info "Testing combined search with description and tags"
        if ! run_mcp_command "intelligent_tool_finder" "{\"natural_language_query\": \"$description\", \"tags\": $tags_json}" "Combined search"; then
            print_error "Failed combined search"
        else
            print_success "Combined search completed"
        fi
        echo ""
    fi

    echo ""
    print_success "Service testing completed!"
}


monitor_services() {
    local config_file="${1}"
    local service_name=""

    if [ -n "$config_file" ]; then
        if [ ! -f "$config_file" ]; then
            print_error "Config file not found: $config_file"
            exit 1
        fi

        print_info "Loading config from: $config_file"
        local config_json
        config_json="$(cat "$config_file")"

        # Validate config and extract service name
        service_name=$(validate_config "$config_json")
        if [ $? -ne 0 ]; then
            print_error "Config validation failed"
            echo "$service_name"  # This contains error message
            exit 1
        fi

        echo "=== Monitoring Service: $service_name ==="
    else
        echo "=== Monitoring All Services ==="
    fi

    # Check prerequisites
    check_prerequisites

    # Run health check
    if ! run_health_check "$service_name"; then
        exit 1
    fi

    echo ""
    print_success "Monitoring completed!"
}

show_usage() {
    echo "Usage: $0 {add|delete|monitor|test|add-to-groups|remove-from-groups} [config-file] [groups]"
    echo ""
    echo "Commands:"
    echo "  add <config-file>            - Add a service using JSON config and verify registration"
    echo "  delete <config-file>         - Delete a service using JSON config and verify removal"
    echo "  monitor [config-file]        - Run health check (all services or specific service from config)"
    echo "  test <config-file>           - Test service searchability using intelligent_tool_finder"
    echo "  add-to-groups <server-name> <groups> - Add server to specific scopes groups (comma-separated)"
    echo "  remove-from-groups <server-name> <groups> - Remove server from specific scopes groups (comma-separated)"
    echo ""
    echo "Config File Requirements:"
    echo "  Required fields: server_name, path, proxy_pass_url"
    echo "  Optional fields: description, tags, num_tools, num_stars, is_python, license"
    echo "  Constraints:"
    echo "    - path must start with '/' and be more than just '/'"
    echo "    - proxy_pass_url must start with http:// or https://"
    echo "    - server_name must be non-empty string"
    echo "    - tags must be array of strings"
    echo "    - num_tools/num_stars must be non-negative integers"
    echo "    - is_python must be boolean"
    echo ""
    echo "Examples:"
    echo "  $0 add cli/examples/example-server-config.json"
    echo "  $0 delete cli/examples/example-server-config.json"
    echo "  $0 monitor                                        # All services"
    echo "  $0 monitor cli/examples/example-server-config.json # Specific service"
    echo "  $0 test cli/examples/example-server-config.json    # Test searchability"
    echo "  $0 add-to-groups example-server 'mcp-servers-restricted/read,mcp-servers-restricted/execute'"
    echo "  $0 remove-from-groups example-server 'mcp-servers-restricted/read,mcp-servers-restricted/execute'"
}

add_to_groups() {
    local server_name="$1"
    local groups="$2"

    if [ -z "$server_name" ] || [ -z "$groups" ]; then
        print_error "Usage: $0 add-to-groups <server-name> <groups>"
        print_error "Example: $0 add-to-groups example-server 'mcp-servers-restricted/read,mcp-servers-restricted/execute'"
        exit 1
    fi

    echo "=== Adding Server to Scopes Groups: $server_name ==="

    # Check prerequisites
    check_prerequisites

    # Convert comma-separated groups to JSON array format
    local groups_json
    groups_json=$(echo "$groups" | sed 's/,/","/g' | sed 's/^/"/' | sed 's/$/"/')
    groups_json="[$groups_json]"

    print_info "Adding server '$server_name' to groups: $groups"

    # Call the MCP tool
    local response
    if response=$(run_mcp_command "add_server_to_scopes_groups" "{\"server_name\": \"$server_name\", \"group_names\": $groups_json}"); then
        # Check if the response indicates success
        if echo "$response" | grep -q '"success": true'; then
            print_success "Server successfully added to groups"

            # Extract and display details
            local server_path
            server_path=$(echo "$response" | grep -o '"server_path": "[^"]*"' | cut -d'"' -f4)
            if [ -n "$server_path" ]; then
                print_info "Server path: $server_path"
            fi

            print_info "Groups: $groups"
            print_success "Scopes groups updated and auth server reloaded"
        else
            # Extract error message if available
            local error_msg
            error_msg=$(echo "$response" | grep -o '"error": "[^"]*"' | cut -d'"' -f4)
            if [ -n "$error_msg" ]; then
                print_error "Failed to add server to groups: $error_msg"
            else
                print_error "Failed to add server to groups (unknown error)"
                echo "Response: $response"
            fi
            exit 1
        fi
    else
        print_error "Failed to call add_server_to_scopes_groups tool"
        exit 1
    fi

    echo ""
    print_success "Add to groups operation completed!"
}

remove_from_groups() {
    local server_name="$1"
    local groups="$2"

    if [ -z "$server_name" ] || [ -z "$groups" ]; then
        print_error "Usage: $0 remove-from-groups <server-name> <groups>"
        print_error "Example: $0 remove-from-groups example-server 'mcp-servers-restricted/read,mcp-servers-restricted/execute'"
        exit 1
    fi

    echo "=== Removing Server from Scopes Groups: $server_name ==="

    # Check prerequisites
    check_prerequisites

    # Convert comma-separated groups to JSON array format
    local groups_json
    groups_json=$(echo "$groups" | sed 's/,/","/g' | sed 's/^/"/' | sed 's/$/"/')
    groups_json="[$groups_json]"

    print_info "Removing server '$server_name' from groups: $groups"

    # Call the MCP tool
    local response
    if response=$(run_mcp_command "remove_server_from_scopes_groups" "{\"server_name\": \"$server_name\", \"group_names\": $groups_json}"); then
        # Check if the response indicates success
        if echo "$response" | grep -q '"success": true'; then
            print_success "Server successfully removed from groups"

            # Extract and display details
            local server_path
            server_path=$(echo "$response" | grep -o '"server_path": "[^"]*"' | cut -d'"' -f4)
            if [ -n "$server_path" ]; then
                print_info "Server path: $server_path"
            fi

            print_info "Groups: $groups"
            print_success "Scopes groups updated and auth server reloaded"
        else
            # Extract error message if available
            local error_msg
            error_msg=$(echo "$response" | grep -o '"error": "[^"]*"' | cut -d'"' -f4)
            if [ -n "$error_msg" ]; then
                print_error "Failed to remove server from groups: $error_msg"
            else
                print_error "Failed to remove server from groups (unknown error)"
                echo "Response: $response"
            fi
            exit 1
        fi
    else
        print_error "Failed to call remove_server_from_scopes_groups tool"
        exit 1
    fi

    echo ""
    print_success "Remove from groups operation completed!"
}

# Main script logic
case "${1:-}" in
    add)
        add_service "$2"
        ;;
    delete)
        delete_service "$2"
        ;;
    monitor)
        monitor_services "$2"
        ;;
    test)
        test_service "$2"
        ;;
    add-to-groups)
        add_to_groups "$2" "$3"
        ;;
    remove-from-groups)
        remove_from_groups "$2" "$3"
        ;;
    *)
        show_usage
        exit 1
        ;;
esac