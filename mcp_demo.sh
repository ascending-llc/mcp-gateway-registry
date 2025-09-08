#!/bin/bash

# MCP Agent Demo Script - Mimics the agent.py workflow
# Based on: mcp_cmds.sh
# 
# This script demonstrates the agent workflow:
# 1. Call intelligent_tool_finder to find servers that can get current time
# 2. Parse the response to identify the appropriate server and tool
# 3. Call the identified tool to get the current time

# Set script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse gateway URL from environment variable or default
# Use the main MCP gateway which has intelligent_tool_finder, not the individual server
GATEWAY_URL="${GATEWAY_URL:-http://localhost/mcpgw/mcp}"

# Load authentication credentials from environment variables or JSON files
load_auth_credentials() {
    local token_file="${SCRIPT_DIR}/../.oauth-tokens/ingress.json"
    local user_token_file="${SCRIPT_DIR}/../.oauth-tokens/user-token.json"
    
    # First priority: Check environment variables for registry token
    if [ -n "$USER_ACCESS_TOKEN" ]; then
        echo "User token found in environment variable USER_ACCESS_TOKEN"
        AUTH_TOKEN="Bearer $USER_ACCESS_TOKEN"
        USER_POOL_ID="dummy-pool-id"
        CLIENT_ID="dummy-client-id"
        REGION="us-east-1"
        
        echo "Successfully loaded registry token from environment variables (using dummy Cognito headers)"
        echo
        return 0
    fi
    
    # Second priority: Check if user token file exists
    if [ -f "$user_token_file" ]; then
        echo "User token file detected: $user_token_file"
        echo "Loading user-generated token credentials..."
        
        # Check if jq is available
        if ! command -v jq &> /dev/null; then
            echo "ERROR: jq command not found. Please install jq to parse JSON credentials."
            exit 1
        fi
        
        # Extract credentials from user token JSON file
        AUTH_TOKEN="Bearer $(jq -r '.access_token' "$user_token_file")"
        USER_POOL_ID=$(jq -r '.user_pool_id // "dummy-pool-id"' "$user_token_file")
        CLIENT_ID=$(jq -r '.client_id // "dummy-client-id"' "$user_token_file")
        REGION=$(jq -r '.region // "us-east-1"' "$user_token_file")
        
        # Validate that access token was extracted
        if [ "$AUTH_TOKEN" = "Bearer null" ] || [ "$AUTH_TOKEN" = "Bearer " ]; then
            echo "ERROR: Failed to read access_token from $user_token_file"
            echo "Required field: access_token"
            echo "Optional fields (only needed for non-registry tokens): user_pool_id, client_id, region"
            exit 1
        fi
        
        echo "Successfully loaded user token credentials from $user_token_file"
        echo "User Pool ID: $USER_POOL_ID"
        echo "Client ID: $CLIENT_ID"
        echo "Region: $REGION"
        echo
        return 0
    fi
    
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
        echo "Checking for user token credentials..."
        
        # For localhost, still check if user token exists and load it
        local user_token_file="${SCRIPT_DIR}/../.oauth-tokens/user-token.json"
        if [ -f "$user_token_file" ]; then
            echo "User token file found, loading credentials for localhost..."
            
            # Check if jq is available
            if ! command -v jq &> /dev/null; then
                echo "ERROR: jq command not found. Please install jq to parse JSON credentials."
                exit 1
            fi
            
            # Extract credentials from user token JSON file
            AUTH_TOKEN="Bearer $(jq -r '.access_token' "$user_token_file")"
            USER_POOL_ID=$(jq -r '.user_pool_id // "dummy-pool-id"' "$user_token_file")
            CLIENT_ID=$(jq -r '.client_id // "dummy-client-id"' "$user_token_file")
            REGION=$(jq -r '.region // "us-east-1"' "$user_token_file")
            
            # Validate that access token was extracted
            if [ "$AUTH_TOKEN" = "Bearer null" ] || [ "$AUTH_TOKEN" = "Bearer " ]; then
                echo "ERROR: Failed to read access_token from $user_token_file"
                echo "Required field: access_token"
                echo "Optional fields (only needed for non-registry tokens): user_pool_id, client_id, region"
                exit 1
            fi
            
            echo "Successfully loaded user token credentials from $user_token_file"
            echo "User Pool ID: $USER_POOL_ID"
            echo "Client ID: $CLIENT_ID"
            echo "Region: $REGION"
        else
            echo "No user token file found, proceeding without authentication"
        fi
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
    
    # Add authentication headers only if available (user token or non-localhost)
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
    
    # Return the response for further processing
    echo "$response"
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
    
    # Add authentication headers only if available (user token or non-localhost)
    if [ -n "$AUTH_TOKEN" ]; then
        curl_cmd="$curl_cmd -H 'X-Authorization: $AUTH_TOKEN'"
        curl_cmd="$curl_cmd -H 'X-User-Pool-Id: $USER_POOL_ID'"
        curl_cmd="$curl_cmd -H 'X-Client-Id: $CLIENT_ID'"
        curl_cmd="$curl_cmd -H 'X-Region: $REGION'"
    fi
    
    curl_cmd="$curl_cmd -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"mcp-demo-client\",\"version\":\"1.0.0\"}}}'"
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
        
        # Add authentication headers only if available (user token or non-localhost)
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

# Step 1: Call intelligent_tool_finder to discover time-related tools
call_intelligent_tool_finder() {
    echo "🔍 Step 1: Calling intelligent_tool_finder to discover time-related tools..." >&2
    local query="$1"
    
    # Ensure session is established and auth is loaded
    if [ -z "$AUTH_LOADED" ]; then
        load_auth_credentials
        AUTH_LOADED=1
    fi
    
    if [ -z "$SESSION_ID" ]; then
        establish_session || return 1
    fi
    
    # Make a silent request (no output to console, just return the response)
    local curl_cmd="curl -sS --request POST"
    curl_cmd="$curl_cmd --header 'Content-Type: application/json'"
    curl_cmd="$curl_cmd --header 'Accept: application/json, text/event-stream'"
    curl_cmd="$curl_cmd --header 'mcp-session-id: $SESSION_ID'"
    
    # Add authentication headers only if available
    if [ -n "$AUTH_TOKEN" ]; then
        curl_cmd="$curl_cmd --header 'X-Authorization: $AUTH_TOKEN'"
        curl_cmd="$curl_cmd --header 'X-User-Pool-Id: $USER_POOL_ID'"
        curl_cmd="$curl_cmd --header 'X-Client-Id: $CLIENT_ID'"
        curl_cmd="$curl_cmd --header 'X-Region: $REGION'"
    fi
    
    curl_cmd="$curl_cmd --data '{\"jsonrpc\":\"2.0\",\"id\":10,\"method\":\"tools/call\",\"params\":{\"name\":\"intelligent_tool_finder\",\"arguments\":{\"natural_language_query\":\"$query\"}}}' '$GATEWAY_URL'"
    
    local response=$(eval "$curl_cmd")
    
    echo "$response"
}

# Step 2: Parse the intelligent_tool_finder response to extract server and tool info
parse_tool_finder_response() {
    local response="$1"
    
    # Extract JSON from SSE format if needed
    local json_data=$(echo "$response" | grep "^data: " | sed 's/^data: //')
    if [ -z "$json_data" ]; then
        json_data="$response"
    fi
    
    # Parse the response to extract server and tool information from the structured result
    local tool_name=$(echo "$json_data" | jq -r '.result.structuredContent.result[0].tool_name // empty' 2>/dev/null)
    local service_path=$(echo "$json_data" | jq -r '.result.structuredContent.result[0].service_path // empty' 2>/dev/null)
    
    # Extract server name from service path (remove leading/trailing slashes)
    local server_name=""
    if [ -n "$service_path" ]; then
        server_name=$(echo "$service_path" | sed 's|^/||' | sed 's|/$||')
    fi
    
    # If we still don't have the info, try parsing from text content as fallback
    if [ -z "$server_name" ] || [ -z "$tool_name" ]; then
        local content_text=$(echo "$json_data" | jq -r '.result.content[0].text // empty' 2>/dev/null)
        
        # Try to extract from JSON string in text content
        if [ -n "$content_text" ]; then
            local first_result=$(echo "$content_text" | jq -r '.[0] // empty' 2>/dev/null)
            if [ -n "$first_result" ] && [ "$first_result" != "null" ]; then
                tool_name=$(echo "$first_result" | jq -r '.tool_name // empty' 2>/dev/null)
                service_path=$(echo "$first_result" | jq -r '.service_path // empty' 2>/dev/null)
                if [ -n "$service_path" ]; then
                    server_name=$(echo "$service_path" | sed 's|^/||' | sed 's|/$||')
                fi
            fi
        fi
    fi
    
    # Debug output to stderr
    echo "DEBUG JSON: $json_data" >&2
    echo "DEBUG: Extracted server: $server_name" >&2
    echo "DEBUG: Extracted tool: $tool_name" >&2
    local result="$server_name|$tool_name"
    echo "DEBUG: Returning: '$result'" >&2
    echo >&2
    
    # Return the server and tool names as pipe-separated string (ONLY this goes to stdout)
    printf "%s" "$result"
}

# Step 3: Call the identified tool with appropriate arguments
call_identified_tool() {
    echo "🕒 Step 3: Calling the identified tool..." >&2
    local server_name="$1"
    local tool_name="$2"
    local timezone="${3:-America/New_York}"
    
    echo "Calling tool '$tool_name' on server '$server_name' with timezone '$timezone'" >&2
    
    # Switch to the specific server URL directly
    local original_url="$GATEWAY_URL"
    GATEWAY_URL="http://localhost/$server_name/mcp"
    echo "Switching to server-specific URL: $GATEWAY_URL" >&2
    
    # Reset session for new server
    SESSION_ID=""
    AUTH_LOADED=""
    
    # Establish session and auth for the specific server
    if [ -z "$AUTH_LOADED" ]; then
        load_auth_credentials
        AUTH_LOADED=1
    fi
    
    if [ -z "$SESSION_ID" ]; then
        establish_session || return 1
    fi
    
    # Make a silent request to call the tool directly on the specific server
    local curl_cmd="curl -sS --request POST"
    curl_cmd="$curl_cmd --header 'Content-Type: application/json'"
    curl_cmd="$curl_cmd --header 'Accept: application/json, text/event-stream'"
    curl_cmd="$curl_cmd --header 'mcp-session-id: $SESSION_ID'"
    
    # Add authentication headers only if available
    if [ -n "$AUTH_TOKEN" ]; then
        curl_cmd="$curl_cmd --header 'X-Authorization: $AUTH_TOKEN'"
        curl_cmd="$curl_cmd --header 'X-User-Pool-Id: $USER_POOL_ID'"
        curl_cmd="$curl_cmd --header 'X-Client-Id: $CLIENT_ID'"
        curl_cmd="$curl_cmd --header 'X-Region: $REGION'"
    fi
    
    curl_cmd="$curl_cmd --data '{\"jsonrpc\":\"2.0\",\"id\":20,\"method\":\"tools/call\",\"params\":{\"name\":\"$tool_name\",\"arguments\":{\"tz_name\":\"$timezone\"}}}' '$GATEWAY_URL'"
    
    local response=$(eval "$curl_cmd")
    
    # Restore original URL
    GATEWAY_URL="$original_url"
    
    echo "$response"
}

# Extract final result from tool response
extract_final_result() {
    echo "📋 Step 4: Extracting final result..." >&2
    local response="$1"
    
    # Extract JSON from SSE format if needed
    local json_data=$(echo "$response" | grep "^data: " | sed 's/^data: //')
    if [ -z "$json_data" ]; then
        json_data="$response"
    fi
    
    # Extract the actual time result
    local time_result=$(echo "$json_data" | jq -r '.result.structuredContent.result // .result.content[0].text // empty' 2>/dev/null)
    
    if [ -n "$time_result" ]; then
        echo "🎉 Final Result: $time_result"
    else
        echo "⚠️  Could not extract time result from response" >&2
        echo "Raw response: $json_data" >&2
    fi
}

# Main demo function that orchestrates the entire workflow
run_agent_demo() {
    local query="${1:-What time is it now?}"
    local timezone="${2:-America/New_York}"
    
    echo "🤖 MCP Agent Demo - Mimicking agent.py workflow"
    echo "=================================="
    echo "Query: $query"
    echo "Timezone: $timezone"
    echo "Gateway URL: $GATEWAY_URL"
    echo "=================================="
    echo
    
    # Step 1: Call intelligent_tool_finder
    echo "🔍 Step 1: Calling intelligent_tool_finder to discover time-related tools..."
    local finder_response=$(call_intelligent_tool_finder "$query")
    
    # Step 2: Parse the response to identify server and tool
    echo "🔍 Step 2: Parsing intelligent_tool_finder response..."
    local server_tool=$(parse_tool_finder_response "$finder_response")
    # Clean up any extra newlines and take only the first line
    server_tool=$(echo "$server_tool" | head -1 | tr -d '\n\r')
    echo "DEBUG: server_tool='$server_tool'" >&2
    local server_name=$(echo "$server_tool" | cut -d'|' -f1 | tr -d ' ')
    local tool_name=$(echo "$server_tool" | cut -d'|' -f2 | tr -d ' ')
    echo "DEBUG: server_name='$server_name', tool_name='$tool_name'" >&2
    
    if [ -z "$server_name" ] || [ -z "$tool_name" ]; then
        echo "❌ Could not identify appropriate server and tool from intelligent_tool_finder response"
        echo "Response was:"
        echo "$finder_response"
        return 1
    fi
    
    # Step 3: Call the identified tool
    local tool_response=$(call_identified_tool "$server_name" "$tool_name" "$timezone")
    
    # Step 4: Extract and display the final result
    extract_final_result "$tool_response"
}

# Parse command line arguments
case "${1:-demo}" in
    "demo")
        shift
        run_agent_demo "$@"
        ;;
    "finder")
        shift
        call_intelligent_tool_finder "${1:-What time is it?}"
        ;;
    "help"|*)
        echo "MCP Agent Demo Script"
        echo "Usage: $0 <command> [args...]"
        echo
        echo "Commands:"
        echo "  demo [query] [timezone]  - Run full agent demo workflow (default)"
        echo "  finder <query>          - Just call intelligent_tool_finder"
        echo "  help                    - Show this help"
        echo
        echo "Environment Variables:"
        echo "  GATEWAY_URL              Gateway URL (default: http://localhost/currenttime/mcp)"
        echo "  USER_ACCESS_TOKEN        Your registry-generated access token"
        echo
        echo "Examples:"
        echo "  # Full demo with default query and timezone"
        echo "  USER_ACCESS_TOKEN=your_token $0 demo"
        echo
        echo "  # Custom query and timezone"
        echo "  USER_ACCESS_TOKEN=your_token $0 demo 'What is the current time?' 'Europe/London'"
        echo
        echo "  # Just test intelligent_tool_finder"
        echo "  USER_ACCESS_TOKEN=your_token $0 finder 'time tools'"
        ;;
esac