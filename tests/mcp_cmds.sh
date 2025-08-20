#!/bin/bash

# MCP Commands Script for MCPGateway Testing
# Based on: https://github.com/awslabs/amazon-bedrock-agentcore-samples/blob/main/02-use-cases/SRE-agent/gateway/mcp_cmds.sh

# Set script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse gateway URL from environment variable or default
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8003/mcp}"

# Load authentication credentials from JSON file
load_auth_credentials() {
    local token_file="${SCRIPT_DIR}/../.oauth-tokens/ingress.json"
    
    # Check if running against non-localhost URL
    if [[ "$GATEWAY_URL" != *"http://localhost"* ]]; then
        echo "Non-localhost URL detected: $GATEWAY_URL"
        echo "Checking for authentication credentials..."
        
        # Check if token file exists
        if [ ! -f "$token_file" ]; then
            echo "ERROR: Token file not found at $token_file"
            echo "Cannot proceed with non-localhost URL without authentication credentials"
            exit 1
        fi
        
        # Check if jq is available
        if ! command -v jq &> /dev/null; then
            echo "ERROR: jq command not found. Please install jq to parse JSON credentials."
            exit 1
        fi
        
        # Extract credentials from JSON file
        AUTH_TOKEN="Bearer $(jq -r '.access_token' "$token_file")"
        USER_POOL_ID=$(jq -r '.user_pool_id' "$token_file")
        CLIENT_ID=$(jq -r '.client_id' "$token_file")
        REGION=$(jq -r '.region' "$token_file")
        
        # Validate that all required fields were extracted
        if [ "$AUTH_TOKEN" = "Bearer null" ] || [ "$USER_POOL_ID" = "null" ] || [ "$CLIENT_ID" = "null" ] || [ "$REGION" = "null" ]; then
            echo "ERROR: Failed to read required credentials from $token_file"
            echo "Required fields: access_token, user_pool_id, client_id, region"
            exit 1
        fi
        
        echo "Successfully loaded authentication credentials from $token_file"
        echo "User Pool ID: $USER_POOL_ID"
        echo "Client ID: $CLIENT_ID"
        echo "Region: $REGION"
        echo
    else
        echo "Localhost URL detected: $GATEWAY_URL"
        echo "Authentication credentials not required for localhost"
        echo
    fi
}

# Helper function to make authenticated curl requests
make_request() {
    local method="$1"
    local data="$2"
    local description="$3"
    
    echo "=== $description ==="
    
    # Load authentication credentials if needed
    if [ -z "$AUTH_LOADED" ]; then
        load_auth_credentials
        AUTH_LOADED=1
    fi
    
    # Establish session if not already done
    if [ -z "$SESSION_ID" ]; then
        establish_session || return 1
    fi
    
    # Build curl command with conditional authentication headers
    local curl_cmd="curl -sS --request $method"
    curl_cmd="$curl_cmd --header 'Content-Type: application/json'"
    curl_cmd="$curl_cmd --header 'Accept: application/json, text/event-stream'"
    curl_cmd="$curl_cmd --header 'mcp-session-id: $SESSION_ID'"
    
    # Add authentication headers only if available (non-localhost)
    if [ -n "$AUTH_TOKEN" ]; then
        curl_cmd="$curl_cmd --header 'X-Authorization: $AUTH_TOKEN'"
        curl_cmd="$curl_cmd --header 'X-User-Pool-Id: $USER_POOL_ID'"
        curl_cmd="$curl_cmd --header 'X-Client-Id: $CLIENT_ID'"
        curl_cmd="$curl_cmd --header 'X-Region: $REGION'"
    fi
    
    curl_cmd="$curl_cmd --data '$data' '$GATEWAY_URL'"
    
    local response=$(eval "$curl_cmd")
    
    echo "Raw response:"
    echo "$response"
    echo
    echo "Formatted response:"
    # Extract JSON from SSE format (lines starting with "data: ")
    local json_data=$(echo "$response" | grep "^data: " | sed 's/^data: //')
    if [ -n "$json_data" ]; then
        echo "$json_data" | jq . 2>/dev/null || echo "Failed to parse JSON: $json_data"
    else
        echo "$response" | jq . 2>/dev/null || echo "Failed to parse JSON or extract from SSE"
    fi
    echo
}

# Test basic connectivity without authentication
test_basic_connectivity() {
    echo "Testing basic gateway connectivity..."
    echo "URL: $GATEWAY_URL"
    echo
    echo "=== Basic HTTP Test ==="
    curl -v "$GATEWAY_URL" 2>&1 | head -20
    echo
}

# Global variables
SESSION_ID=""
AUTH_LOADED=""

# Establish session and get session ID
establish_session() {
    echo "Establishing session..."
    
    # Load authentication credentials if needed
    if [ -z "$AUTH_LOADED" ]; then
        load_auth_credentials
        AUTH_LOADED=1
    fi
    
    # Build curl command with conditional authentication headers
    local curl_cmd="curl -v -X POST"
    curl_cmd="$curl_cmd -H 'Content-Type: application/json'"
    curl_cmd="$curl_cmd -H 'Accept: application/json, text/event-stream'"
    
    # Add authentication headers only if available (non-localhost)
    if [ -n "$AUTH_TOKEN" ]; then
        curl_cmd="$curl_cmd -H 'X-Authorization: $AUTH_TOKEN'"
        curl_cmd="$curl_cmd -H 'X-User-Pool-Id: $USER_POOL_ID'"
        curl_cmd="$curl_cmd -H 'X-Client-Id: $CLIENT_ID'"
        curl_cmd="$curl_cmd -H 'X-Region: $REGION'"
    fi
    
    curl_cmd="$curl_cmd -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test-client\",\"version\":\"1.0.0\"}}}'"
    curl_cmd="$curl_cmd '$GATEWAY_URL'"
    
    # Step 1: Initialize and get session ID
    SESSION_ID=$(eval "$curl_cmd" 2>&1 >/dev/null | grep '< mcp-session-id:' | sed 's/< mcp-session-id: //' | tr -d '\r')
    
    if [ -n "$SESSION_ID" ]; then
        echo "Session established with ID: $SESSION_ID"
        
        # Step 2: Send initialized notification to complete handshake
        echo "Completing initialization handshake..."
        
        # Build curl command for initialized notification
        local init_cmd="curl -sS -X POST"
        init_cmd="$init_cmd -H 'Content-Type: application/json'"
        init_cmd="$init_cmd -H 'Accept: application/json, text/event-stream'"
        init_cmd="$init_cmd -H 'mcp-session-id: $SESSION_ID'"
        
        # Add authentication headers only if available (non-localhost)
        if [ -n "$AUTH_TOKEN" ]; then
            init_cmd="$init_cmd -H 'X-Authorization: $AUTH_TOKEN'"
            init_cmd="$init_cmd -H 'X-User-Pool-Id: $USER_POOL_ID'"
            init_cmd="$init_cmd -H 'X-Client-Id: $CLIENT_ID'"
            init_cmd="$init_cmd -H 'X-Region: $REGION'"
        fi
        
        init_cmd="$init_cmd -d '{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}'"
        init_cmd="$init_cmd '$GATEWAY_URL'"
        
        eval "$init_cmd" >/dev/null
            
        echo "Initialization complete"
    else
        echo "Failed to establish session or extract session ID"
        return 1
    fi
}

# Test MCP connectivity
test_connectivity() {
    echo "Testing MCP Gateway connectivity..."
    establish_session
    make_request "POST" '{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "ping"
    }' "Ping Test"
}

# List available tools
list_tools() {
    echo "Listing available tools..."
    make_request "POST" '{
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list"
    }' "List Tools"
}

# Call a specific tool
call_tool() {
    local tool_name="$1"
    local arguments="$2"
    local description="${3:-Call tool $tool_name}"
    
    if [ -z "$tool_name" ]; then
        echo "Usage: call_tool <tool_name> <arguments_json> [description]"
        return 1
    fi
    
    if [ -z "$arguments" ]; then
        arguments="{}"
    fi
    
    make_request "POST" "{
        \"jsonrpc\": \"2.0\",
        \"id\": 3,
        \"method\": \"tools/call\",
        \"params\": {
            \"name\": \"$tool_name\",
            \"arguments\": $arguments
        }
    }" "$description"
}


# Parse command line arguments for gateway URL
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --url)
                GATEWAY_URL="$2"
                shift 2
                ;;
            --url=*)
                GATEWAY_URL="${1#*=}"
                shift
                ;;
            *)
                # Return remaining arguments
                echo "$@"
                return
                ;;
        esac
    done
}

# Parse arguments and get remaining command
REMAINING_ARGS=$(parse_args "$@")
eval set -- "$REMAINING_ARGS"

# Main script logic
case "${1:-help}" in
    "basic")
        test_basic_connectivity
        ;;
    "connectivity"|"ping")
        test_connectivity
        ;;
    "list"|"tools")
        list_tools
        ;;
    "call")
        shift
        call_tool "$@"
        ;;
    "help"|*)
        echo "MCP Gateway Commands Script"
        echo "Usage: $0 [--url <gateway_url>] <command> [args...]"
        echo
        echo "Options:"
        echo "  --url <gateway_url>      Gateway URL (default: http://localhost:8003/mcp)"
        echo "  --url=<gateway_url>      Alternative syntax for gateway URL"
        echo
        echo "Environment Variables:"
        echo "  GATEWAY_URL              Can also be set via environment variable"
        echo
        echo "Authentication:"
        echo "  - For localhost URLs: No authentication required"
        echo "  - For external URLs: Automatically loads credentials from ../.oauth-tokens/ingress.json"
        echo
        echo "Commands:"
        echo "  basic                - Test basic HTTP connectivity"
        echo "  connectivity|ping    - Test MCP connectivity"
        echo "  list|tools           - List available tools"
        echo "  call <tool> <args>   - Call a specific tool"
        echo "  help                 - Show this help"
        echo
        echo "Examples:"
        echo "  $0 basic"
        echo "  $0 list"
        echo "  $0 call debug_auth_context '{}'"
        echo "  $0 call intelligent_tool_finder '{\"natural_language_query\": \"quantum\"}'"
        echo "  $0 ping"
        echo "  $0 --url https://example.com/mcp list"
        echo "  GATEWAY_URL=https://example.com/mcp $0 ping"
        ;;
esac