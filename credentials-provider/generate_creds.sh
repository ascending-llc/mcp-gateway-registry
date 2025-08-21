#!/bin/bash
#
# OAuth Credentials Orchestrator Script
#
# This script orchestrates OAuth authentication for both ingress and egress flows,
# and generates MCP configuration files for VS Code and Roocode.
#
# Default behavior: Run both ingress and egress authentication flows
# - ingress: Cognito M2M authentication for MCP Gateway
# - egress: External provider authentication (default: Atlassian)
#
# If both are requested and ingress fails, the script stops (egress won't run).
# If only egress is requested and it fails, the script continues to generate configs.
#
# Usage:
#   ./oauth_creds.sh                    # Run both ingress and egress (default)
#   ./oauth_creds.sh --ingress-only     # Run only ingress authentication
#   ./oauth_creds.sh --egress-only      # Run only egress authentication  
#   ./oauth_creds.sh --both             # Explicitly run both (same as default)
#   ./oauth_creds.sh --provider google  # Run both with Google as egress provider
#   ./oauth_creds.sh --verbose          # Enable verbose logging
#   ./oauth_creds.sh --force            # Force new token generation
#   ./oauth_creds.sh --help             # Show this help

set -e  # Exit on error

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env file if it exists (check both oauth and main auth directories)
if [ -f "$SCRIPT_DIR/oauth/.env" ]; then
    source "$SCRIPT_DIR/oauth/.env"
elif [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
fi

# Default values
RUN_INGRESS=true
RUN_EGRESS=true
RUN_AGENTCORE=true
# Read provider and server name from environment variables with defaults
EGRESS_PROVIDER="${EGRESS_PROVIDER_NAME:-atlassian}"
EGRESS_MCP_SERVER_NAME="${EGRESS_MCP_SERVER_NAME:-}"
VERBOSE=false
FORCE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

show_help() {
    cat << EOF
OAuth Credentials Orchestrator Script

This script manages OAuth authentication for both ingress (MCP Gateway) and 
egress (external services) flows, and generates MCP configuration files.

USAGE:
    ./generate_creds.sh [OPTIONS]

OPTIONS:
    --ingress-only          Run only ingress authentication (Cognito M2M)
    --egress-only           Run only egress authentication (external providers)
    --agentcore-only        Run only AgentCore token generation
    --both                  Run only ingress and egress (excludes agentcore)
    --all                   Run ingress, egress, and agentcore authentication
    --provider PROVIDER     Specify egress provider (default: atlassian)
                           Supported: atlassian, google, github, microsoft, etc.
    --force, -f             Force new token generation, ignore existing tokens
    --verbose, -v           Enable verbose debug logging
    --help, -h              Show this help message

EXAMPLES:
    ./generate_creds.sh                        # Run all flows (ingress, egress, agentcore)
    ./generate_creds.sh --ingress-only         # Only MCP Gateway authentication
    ./generate_creds.sh --egress-only          # Only external provider authentication
    ./generate_creds.sh --agentcore-only       # Only AgentCore token generation
    ./generate_creds.sh --both                 # Run only ingress and egress (no agentcore)
    ./generate_creds.sh --provider google      # All flows with Google as egress
    ./generate_creds.sh --force --verbose      # Force new tokens with debug output

BEHAVIOR:
    - Default: Runs all three authentication types (ingress, egress, and agentcore)
    - If multiple are requested and ingress fails → script stops
    - If egress or agentcore fails → continues with remaining tasks and config generation
    - Always attempts to generate MCP configuration files with available tokens
    - Summary shows clear pass/fail status for each authentication type

ENVIRONMENT VARIABLES:
    For ingress (Cognito M2M):
        INGRESS_OAUTH_USER_POOL_ID     # Required
        INGRESS_OAUTH_CLIENT_ID        # Required  
        INGRESS_OAUTH_CLIENT_SECRET    # Required
        AWS_REGION                     # Optional (default: us-east-1)

    For egress (external providers):
        EGRESS_OAUTH_CLIENT_ID         # Required
        EGRESS_OAUTH_CLIENT_SECRET     # Required
        EGRESS_OAUTH_REDIRECT_URI      # Required
        EGRESS_OAUTH_SCOPE             # Optional (uses provider defaults)

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --ingress-only)
            RUN_INGRESS=true
            RUN_EGRESS=false
            RUN_AGENTCORE=false
            shift
            ;;
        --egress-only)
            RUN_INGRESS=false
            RUN_EGRESS=true
            RUN_AGENTCORE=false
            shift
            ;;
        --agentcore-only)
            RUN_INGRESS=false
            RUN_EGRESS=false
            RUN_AGENTCORE=true
            shift
            ;;
        --both)
            RUN_INGRESS=true
            RUN_EGRESS=true
            RUN_AGENTCORE=false
            shift
            ;;
        --all)
            RUN_INGRESS=true
            RUN_EGRESS=true
            RUN_AGENTCORE=true
            shift
            ;;
        --provider)
            EGRESS_PROVIDER="$2"
            shift 2
            ;;
        --force|-f)
            FORCE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Function to run ingress authentication
run_ingress_auth() {
    log_info "🔐 Running INGRESS OAuth authentication (Cognito M2M)..."
    
    local cmd="python '$SCRIPT_DIR/oauth/ingress_oauth.py'"
    
    if [ "$FORCE" = true ]; then
        cmd="$cmd --force"
    fi
    
    if [ "$VERBOSE" = true ]; then
        cmd="$cmd --verbose"
    fi
    
    log_debug "Executing: $cmd"
    
    if eval "$cmd"; then
        log_info "✅ INGRESS authentication completed successfully"
        return 0
    else
        log_error "❌ INGRESS authentication failed"
        return 1
    fi
}

# Function to run egress authentication
run_egress_auth() {
    log_info "🔐 Running EGRESS OAuth authentication for: $EGRESS_PROVIDER"
    
    local cmd="python '$SCRIPT_DIR/oauth/egress_oauth.py' --provider '$EGRESS_PROVIDER'"
    
    # Add MCP server name if provided
    if [ -n "$EGRESS_MCP_SERVER_NAME" ]; then
        cmd="$cmd --mcp-server-name '$EGRESS_MCP_SERVER_NAME'"
    fi
    
    if [ "$FORCE" = true ]; then
        cmd="$cmd --force"
    fi
    
    if [ "$VERBOSE" = true ]; then
        cmd="$cmd --verbose"
    fi
    
    log_debug "Executing: $cmd"
    
    if eval "$cmd"; then
        log_info "✅ EGRESS authentication completed successfully for $EGRESS_PROVIDER"
        return 0
    else
        log_error "❌ EGRESS authentication failed for $EGRESS_PROVIDER"
        return 1
    fi
}

# Function to run AgentCore authentication
run_agentcore_auth() {
    log_info "🔐 Running AgentCore token generation..."
    
    local cmd="python '$SCRIPT_DIR/agentcore-auth/generate_access_token.py'"
    
    if [ "$FORCE" = true ]; then
        cmd="$cmd --force"
    fi
    
    if [ "$VERBOSE" = true ]; then
        cmd="$cmd --debug"
    fi
    
    log_debug "Executing: $cmd"
    
    if eval "$cmd"; then
        log_info "✅ AgentCore token generation completed successfully"
        return 0
    else
        log_error "❌ AgentCore token generation failed"
        return 1
    fi
}

# Function to generate MCP configuration files
generate_mcp_configs() {
    log_info "🔧 Generating MCP configuration files..."
    
    local token_dir="$(pwd)/.oauth-tokens"
    local ingress_file="$token_dir/ingress.json"
    
    # Check which token files exist
    local has_ingress=false
    
    if [ -f "$ingress_file" ]; then
        has_ingress=true
        log_debug "Found ingress tokens: $ingress_file"
    fi
    
    # Find all egress token files
    local egress_files=()
    for file in "$token_dir"/*-egress.json; do
        if [ -f "$file" ]; then
            egress_files+=("$file")
            log_debug "Found egress tokens: $file"
        fi
    done
    
    if [ "$has_ingress" = false ] && [ ${#egress_files[@]} -eq 0 ]; then
        log_warn "No token files found, skipping MCP configuration generation"
        return 0
    fi
    
    # Generate VS Code MCP configuration
    generate_vscode_config "$has_ingress" "$ingress_file" "${egress_files[@]}"
    
    # Generate Roocode MCP configuration  
    generate_roocode_config "$has_ingress" "$ingress_file" "${egress_files[@]}"
    
    # Add no-auth services to MCP configurations
    add_noauth_services
    
    log_info "✅ MCP configuration files generated successfully"
}

# Function to generate VS Code MCP configuration
generate_vscode_config() {
    local has_ingress=$1
    local ingress_file=$2
    shift 2
    local egress_files=("$@")
    
    local config_file="$(pwd)/.oauth-tokens/vscode_mcp.json"
    local temp_file=$(mktemp)
    
    # Expand REGISTRY_URL variable once at the beginning
    local registry_url="${REGISTRY_URL:-https://mcpgateway.ddns.net}"
    
    log_debug "Generating VS Code MCP config: $config_file"
    
    # Start JSON
    echo '{' > "$temp_file"
    echo '  "mcp": {' >> "$temp_file"
    echo '    "servers": {' >> "$temp_file"
    
    local first_server=true
    
    # Skip adding ingress MCP server configuration here - now handled by add_noauth_services.py
    
    # Get ingress auth headers if available (to include in all servers)
    local ing_token=""
    local ing_user_pool=""
    local ing_client=""
    local ing_region=""
    if [ "$has_ingress" = true ]; then
        ing_token=$(jq -r '.access_token // empty' "$ingress_file")
        ing_user_pool=$(jq -r '.user_pool_id // empty' "$ingress_file")
        ing_client=$(jq -r '.client_id // empty' "$ingress_file")
        ing_region=$(jq -r '.region // "us-east-1"' "$ingress_file")
    fi
    
    # Add all egress provider configurations
    for egress_file in "${egress_files[@]}"; do
        if [ "$first_server" = false ]; then
            echo ',' >> "$temp_file"
        fi
        
        # Extract egress token data using jq
        local egress_provider=$(jq -r '.provider // empty' "$egress_file")
        local egress_token=$(jq -r '.access_token // empty' "$egress_file")
        local cloud_id=$(jq -r '.cloud_id // empty' "$egress_file")
        
        # Generate provider-specific configuration
        if [ "$egress_provider" = "atlassian" ]; then
            cat >> "$temp_file" << EOF
      "atlassian": {
        "url": "${registry_url}/atlassian",
        "headers": {
          "Authorization": "Bearer $egress_token"$([ -n "$cloud_id" ] && echo ",
          \"X-Atlassian-Cloud-Id\": \"$cloud_id\"" || echo "")$([ "$has_ingress" = true ] && echo ",
          \"X-Authorization\": \"Bearer $ing_token\",
          \"X-User-Pool-Id\": \"$ing_user_pool\",
          \"X-Client-Id\": \"$ing_client\",
          \"X-Region\": \"$ing_region\"" || echo "")
        }
      }
EOF
        elif [ "$egress_provider" = "bedrock-agentcore" ]; then
            # Extract server name from filename if present
            local server_name=$(basename "$egress_file" | sed -n 's/^bedrock-agentcore-\(.*\)-egress\.json$/\1/p')
            if [ -z "$server_name" ]; then
                server_name="sre-gateway"
            fi
            cat >> "$temp_file" << EOF
      "$server_name": {
        "url": "${registry_url}/$server_name/mcp",
        "headers": {
          "Authorization": "Bearer $egress_token"$([ "$has_ingress" = true ] && echo ",
          \"X-Authorization\": \"Bearer $ing_token\",
          \"X-User-Pool-Id\": \"$ing_user_pool\",
          \"X-Client-Id\": \"$ing_client\",
          \"X-Region\": \"$ing_region\"" || echo "")
        }
      }
EOF
        else
            # Generic external provider configuration
            cat >> "$temp_file" << EOF
      "$egress_provider": {
        "url": "${registry_url}/$egress_provider/mcp",
        "headers": {
          "Authorization": "Bearer $egress_token"$([ "$has_ingress" = true ] && echo ",
          \"X-Authorization\": \"Bearer $ing_token\",
          \"X-User-Pool-Id\": \"$ing_user_pool\",
          \"X-Client-Id\": \"$ing_client\",
          \"X-Region\": \"$ing_region\"" || echo "")
        }
      }
EOF
        fi
        
        first_server=false
    done
    
    # Close JSON
    echo '' >> "$temp_file"
    echo '    }' >> "$temp_file"
    echo '  }' >> "$temp_file"
    echo '}' >> "$temp_file"
    
    # Move temp file to final location
    mv "$temp_file" "$config_file"
    chmod 600 "$config_file"
    
    log_info "📋 Generated VS Code MCP config: $config_file"
}

# Function to generate Roocode MCP configuration
generate_roocode_config() {
    local has_ingress=$1
    local ingress_file=$2
    shift 2
    local egress_files=("$@")
    
    local config_file="$(pwd)/.oauth-tokens/mcp.json"
    local temp_file=$(mktemp)
    
    # Expand REGISTRY_URL variable once at the beginning
    local registry_url="${REGISTRY_URL:-https://mcpgateway.ddns.net}"
    
    log_debug "Generating Roocode MCP config: $config_file"
    
    # Start JSON
    echo '{' > "$temp_file"
    echo '  "mcpServers": {' >> "$temp_file"
    
    local first_server=true
    
    # Skip adding ingress MCP server configuration here - now handled by add_noauth_services.py
    
    # Get ingress auth headers if available (to include in all servers)
    local ing_token=""
    local ing_user_pool=""
    local ing_client=""
    local ing_region=""
    if [ "$has_ingress" = true ]; then
        ing_token=$(jq -r '.access_token // empty' "$ingress_file")
        ing_user_pool=$(jq -r '.user_pool_id // empty' "$ingress_file")
        ing_client=$(jq -r '.client_id // empty' "$ingress_file")
        ing_region=$(jq -r '.region // "us-east-1"' "$ingress_file")
    fi
    
    # Add all egress provider configurations
    for egress_file in "${egress_files[@]}"; do
        if [ "$first_server" = false ]; then
            echo ',' >> "$temp_file"
        fi
        
        # Extract egress token data using jq
        local egress_provider=$(jq -r '.provider // empty' "$egress_file")
        local egress_token=$(jq -r '.access_token // empty' "$egress_file")
        local cloud_id=$(jq -r '.cloud_id // empty' "$egress_file")
        
        # Generate provider-specific configuration
        if [ "$egress_provider" = "atlassian" ]; then
            cat >> "$temp_file" << EOF
    "atlassian": {
      "type": "streamable-http",
      "url": "${registry_url}/atlassian",
      "headers": {
        "Authorization": "Bearer $egress_token"$([ -n "$cloud_id" ] && echo ",
        \"X-Atlassian-Cloud-Id\": \"$cloud_id\"" || echo "")$([ "$has_ingress" = true ] && echo ",
        \"X-Authorization\": \"Bearer $ing_token\",
        \"X-User-Pool-Id\": \"$ing_user_pool\",
        \"X-Client-Id\": \"$ing_client\",
        \"X-Region\": \"$ing_region\"" || echo "")
      },
      "disabled": false,
      "alwaysAllow": []
    }
EOF
        elif [ "$egress_provider" = "bedrock-agentcore" ]; then
            # Extract server name from filename if present
            local server_name=$(basename "$egress_file" | sed -n 's/^bedrock-agentcore-\(.*\)-egress\.json$/\1/p')
            if [ -z "$server_name" ]; then
                server_name="sre-gateway"
            fi
            cat >> "$temp_file" << EOF
    "$server_name": {
      "type": "streamable-http",
      "url": "${registry_url}/$server_name/mcp",
      "headers": {
        "Authorization": "Bearer $egress_token"$([ "$has_ingress" = true ] && echo ",
        \"X-Authorization\": \"Bearer $ing_token\",
        \"X-User-Pool-Id\": \"$ing_user_pool\",
        \"X-Client-Id\": \"$ing_client\",
        \"X-Region\": \"$ing_region\"" || echo "")
      },
      "disabled": false,
      "alwaysAllow": []
    }
EOF
        else
            # Generic external provider configuration
            cat >> "$temp_file" << EOF
    "$egress_provider": {
      "type": "streamable-http", 
      "url": "${registry_url}/$egress_provider/mcp",
      "headers": {
        "Authorization": "Bearer $egress_token"$([ "$has_ingress" = true ] && echo ",
        \"X-Authorization\": \"Bearer $ing_token\",
        \"X-User-Pool-Id\": \"$ing_user_pool\",
        \"X-Client-Id\": \"$ing_client\",
        \"X-Region\": \"$ing_region\"" || echo "")
      },
      "disabled": false,
      "alwaysAllow": []
    }
EOF
        fi
        
        first_server=false
    done
    
    # Close JSON
    echo '' >> "$temp_file"
    echo '  }' >> "$temp_file"
    echo '}' >> "$temp_file"
    
    # Move temp file to final location
    mv "$temp_file" "$config_file"
    chmod 600 "$config_file"
    
    log_info "📋 Generated Roocode MCP config: $config_file"
}

# Function to add no-auth services to MCP configurations
add_noauth_services() {
    log_info "🔧 Adding no-auth services to MCP configurations..."
    
    local cmd="python '$SCRIPT_DIR/add_noauth_services.py'"
    
    if [ "$VERBOSE" = true ]; then
        cmd="$cmd --verbose"
    fi
    
    log_debug "Executing: $cmd"
    
    if eval "$cmd"; then
        log_info "✅ No-auth services added to MCP configurations"
        return 0
    else
        log_warn "⚠️ Failed to add no-auth services, but continuing"
        return 1
    fi
}

# Main execution
main() {
    log_info "🚀 Starting OAuth Credentials Orchestrator"
    log_info "Configuration: ingress=$RUN_INGRESS, egress=$RUN_EGRESS (provider=$EGRESS_PROVIDER), agentcore=$RUN_AGENTCORE"
    
    local ingress_success=false
    local egress_success=false
    local agentcore_success=false
    
    # Run ingress authentication if requested
    if [ "$RUN_INGRESS" = true ]; then
        if run_ingress_auth; then
            ingress_success=true
        else
            # If multiple are requested and ingress fails, stop here
            if [ "$RUN_EGRESS" = true ] || [ "$RUN_AGENTCORE" = true ]; then
                log_error "Ingress authentication failed. Stopping before other authentication types (as multiple were requested)."
                exit 1
            fi
        fi
    fi
    
    # Run egress authentication if requested
    if [ "$RUN_EGRESS" = true ]; then
        if run_egress_auth; then
            egress_success=true
        else
            log_warn "Egress authentication failed, but continuing to generate configs"
        fi
    fi
    
    # Run AgentCore authentication if requested
    if [ "$RUN_AGENTCORE" = true ]; then
        if run_agentcore_auth; then
            agentcore_success=true
        else
            log_warn "AgentCore authentication failed, but continuing to generate configs"
        fi
    fi
    
    # Generate MCP configuration files
    generate_mcp_configs
    
    # Summary
    log_info "📊 Summary:"
    if [ "$RUN_INGRESS" = true ]; then
        if [ "$ingress_success" = true ]; then
            log_info "  ✅ Ingress authentication: SUCCESS"
        else
            log_info "  ❌ Ingress authentication: FAILED"
        fi
    fi
    
    if [ "$RUN_EGRESS" = true ]; then
        if [ "$egress_success" = true ]; then
            log_info "  ✅ Egress authentication ($EGRESS_PROVIDER): SUCCESS"
        else
            log_info "  ❌ Egress authentication ($EGRESS_PROVIDER): FAILED"
        fi
    fi
    
    if [ "$RUN_AGENTCORE" = true ]; then
        if [ "$agentcore_success" = true ]; then
            log_info "  ✅ AgentCore authentication: SUCCESS"
        else
            log_info "  ❌ AgentCore authentication: FAILED"
        fi
    fi
    
    log_info "🎉 OAuth credentials orchestration completed!"
    log_info "💡 Check ./.oauth-tokens/ for generated token and config files"
}

# Run main function
main "$@"