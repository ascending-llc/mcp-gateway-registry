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

# Default values
RUN_INGRESS=true
RUN_EGRESS=true
EGRESS_PROVIDER="atlassian"
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
    ./oauth_creds.sh [OPTIONS]

OPTIONS:
    --ingress-only          Run only ingress authentication (Cognito M2M)
    --egress-only           Run only egress authentication (external providers)
    --both                  Run both ingress and egress (default behavior)
    --provider PROVIDER     Specify egress provider (default: atlassian)
                           Supported: atlassian, google, github, microsoft, etc.
    --force, -f             Force new token generation, ignore existing tokens
    --verbose, -v           Enable verbose debug logging
    --help, -h              Show this help message

EXAMPLES:
    ./oauth_creds.sh                        # Run both flows with Atlassian
    ./oauth_creds.sh --ingress-only         # Only MCP Gateway authentication
    ./oauth_creds.sh --egress-only          # Only external provider authentication
    ./oauth_creds.sh --provider google      # Both flows with Google as egress
    ./oauth_creds.sh --force --verbose      # Force new tokens with debug output

BEHAVIOR:
    - Default: Runs both ingress and egress authentication
    - If both are requested and ingress fails → script stops
    - If only egress is requested and fails → continues to generate configs
    - Generates separate VS Code and Roocode MCP configuration files
    - Combines ingress and egress tokens when both are available

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
            shift
            ;;
        --egress-only)
            RUN_INGRESS=false
            RUN_EGRESS=true
            shift
            ;;
        --both)
            RUN_INGRESS=true
            RUN_EGRESS=true
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
    
    local cmd="python '$SCRIPT_DIR/ingress_oauth.py'"
    
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
    
    local cmd="python '$SCRIPT_DIR/egress_oauth.py' --provider '$EGRESS_PROVIDER'"
    
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

# Function to generate MCP configuration files
generate_mcp_configs() {
    log_info "🔧 Generating MCP configuration files..."
    
    local token_dir="$(pwd)/.oauth-tokens"
    local ingress_file="$token_dir/ingress.json"
    local egress_file="$token_dir/egress.json"
    
    # Check which token files exist
    local has_ingress=false
    local has_egress=false
    
    if [ -f "$ingress_file" ]; then
        has_ingress=true
        log_debug "Found ingress tokens: $ingress_file"
    fi
    
    if [ -f "$egress_file" ]; then
        has_egress=true
        log_debug "Found egress tokens: $egress_file"
    fi
    
    if [ "$has_ingress" = false ] && [ "$has_egress" = false ]; then
        log_warn "No token files found, skipping MCP configuration generation"
        return 0
    fi
    
    # Generate VS Code MCP configuration
    generate_vscode_config "$has_ingress" "$has_egress" "$ingress_file" "$egress_file"
    
    # Generate Roocode MCP configuration  
    generate_roocode_config "$has_ingress" "$has_egress" "$ingress_file" "$egress_file"
    
    log_info "✅ MCP configuration files generated successfully"
}

# Function to generate VS Code MCP configuration
generate_vscode_config() {
    local has_ingress=$1
    local has_egress=$2
    local ingress_file=$3
    local egress_file=$4
    
    local config_file="$(pwd)/.oauth-tokens/vscode_mcp.json"
    local temp_file=$(mktemp)
    
    log_debug "Generating VS Code MCP config: $config_file"
    
    # Start JSON
    echo '{' > "$temp_file"
    echo '  "mcp": {' >> "$temp_file"
    echo '    "servers": {' >> "$temp_file"
    
    local first_server=true
    
    # Add ingress MCP server configuration if available
    if [ "$has_ingress" = true ]; then
        if [ "$first_server" = false ]; then
            echo ',' >> "$temp_file"
        fi
        
        # Extract ingress token data
        local ingress_token=$(python3 -c "
import json
with open('$ingress_file') as f:
    data = json.load(f)
    print(data.get('access_token', ''))
")
        
        local user_pool_id=$(python3 -c "
import json
with open('$ingress_file') as f:
    data = json.load(f)
    print(data.get('user_pool_id', ''))
")
        
        local client_id=$(python3 -c "
import json
with open('$ingress_file') as f:
    data = json.load(f)
    print(data.get('client_id', ''))
")
        
        local region=$(python3 -c "
import json
with open('$ingress_file') as f:
    data = json.load(f)
    print(data.get('region', 'us-east-1'))
")
        
        cat >> "$temp_file" << EOF
      "mcp_gateway": {
        "url": "\${REGISTRY_URL:-https://mcpgateway.ddns.net}/sse",
        "headers": {
          "X-Authorization": "Bearer $ingress_token",
          "X-User-Pool-Id": "$user_pool_id",
          "X-Client-Id": "$client_id",
          "X-Region": "$region"
        }
      }
EOF
        first_server=false
    fi
    
    # Add egress provider configuration if available
    if [ "$has_egress" = true ]; then
        if [ "$first_server" = false ]; then
            echo ',' >> "$temp_file"
        fi
        
        # Extract egress token data
        local egress_provider=$(python3 -c "
import json
with open('$egress_file') as f:
    data = json.load(f)
    print(data.get('provider', ''))
")
        
        local egress_token=$(python3 -c "
import json
with open('$egress_file') as f:
    data = json.load(f)
    print(data.get('access_token', ''))
")
        
        local cloud_id=$(python3 -c "
import json
with open('$egress_file') as f:
    data = json.load(f)
    print(data.get('cloud_id', ''))
")
        
        # Generate provider-specific configuration
        if [ "$egress_provider" = "atlassian" ]; then
            cat >> "$temp_file" << EOF
      "atlassian": {
        "url": "\${REGISTRY_URL:-https://mcpgateway.ddns.net}/atlassian/mcp",
        "headers": {
          "Authorization": "Bearer $egress_token",
          "X-Atlassian-Cloud-Id": "$cloud_id"
        }
      }
EOF
        else
            # Generic external provider configuration
            cat >> "$temp_file" << EOF
      "$egress_provider": {
        "url": "\${REGISTRY_URL:-https://mcpgateway.ddns.net}/$egress_provider/mcp",
        "headers": {
          "Authorization": "Bearer $egress_token"
        }
      }
EOF
        fi
        
        first_server=false
    fi
    
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
    local has_egress=$2
    local ingress_file=$3
    local egress_file=$4
    
    local config_file="$(pwd)/.oauth-tokens/mcp.json"
    local temp_file=$(mktemp)
    
    log_debug "Generating Roocode MCP config: $config_file"
    
    # Start JSON
    echo '{' > "$temp_file"
    echo '  "mcpServers": {' >> "$temp_file"
    
    local first_server=true
    
    # Add ingress MCP server configuration if available
    if [ "$has_ingress" = true ]; then
        if [ "$first_server" = false ]; then
            echo ',' >> "$temp_file"
        fi
        
        # Extract ingress token data
        local ingress_token=$(python3 -c "
import json
with open('$ingress_file') as f:
    data = json.load(f)
    print(data.get('access_token', ''))
")
        
        local user_pool_id=$(python3 -c "
import json
with open('$ingress_file') as f:
    data = json.load(f)
    print(data.get('user_pool_id', ''))
")
        
        local client_id=$(python3 -c "
import json
with open('$ingress_file') as f:
    data = json.load(f)
    print(data.get('client_id', ''))
")
        
        local region=$(python3 -c "
import json
with open('$ingress_file') as f:
    data = json.load(f)
    print(data.get('region', 'us-east-1'))
")
        
        cat >> "$temp_file" << EOF
    "mcp_gateway": {
      "type": "streamable-http",
      "url": "\${REGISTRY_URL:-https://mcpgateway.ddns.net}/sse",
      "headers": {
        "X-Authorization": "Bearer $ingress_token",
        "X-User-Pool-Id": "$user_pool_id",
        "X-Client-Id": "$client_id",
        "X-Region": "$region"
      },
      "disabled": false,
      "alwaysAllow": []
    }
EOF
        first_server=false
    fi
    
    # Add egress provider configuration if available
    if [ "$has_egress" = true ]; then
        if [ "$first_server" = false ]; then
            echo ',' >> "$temp_file"
        fi
        
        # Extract egress token data
        local egress_provider=$(python3 -c "
import json
with open('$egress_file') as f:
    data = json.load(f)
    print(data.get('provider', ''))
")
        
        local egress_token=$(python3 -c "
import json
with open('$egress_file') as f:
    data = json.load(f)
    print(data.get('access_token', ''))
")
        
        local cloud_id=$(python3 -c "
import json
with open('$egress_file') as f:
    data = json.load(f)
    print(data.get('cloud_id', ''))
")
        
        # Generate provider-specific configuration
        if [ "$egress_provider" = "atlassian" ]; then
            cat >> "$temp_file" << EOF
    "atlassian": {
      "type": "streamable-http",
      "url": "\${REGISTRY_URL:-https://mcpgateway.ddns.net}/atlassian/mcp",
      "headers": {
        "Authorization": "Bearer $egress_token",
        "X-Atlassian-Cloud-Id": "$cloud_id"
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
      "url": "\${REGISTRY_URL:-https://mcpgateway.ddns.net}/$egress_provider/mcp",
      "headers": {
        "Authorization": "Bearer $egress_token"
      },
      "disabled": false,
      "alwaysAllow": []
    }
EOF
        fi
        
        first_server=false
    fi
    
    # Close JSON
    echo '' >> "$temp_file"
    echo '  }' >> "$temp_file"
    echo '}' >> "$temp_file"
    
    # Move temp file to final location
    mv "$temp_file" "$config_file"
    chmod 600 "$config_file"
    
    log_info "📋 Generated Roocode MCP config: $config_file"
}

# Main execution
main() {
    log_info "🚀 Starting OAuth Credentials Orchestrator"
    log_info "Configuration: ingress=$RUN_INGRESS, egress=$RUN_EGRESS, provider=$EGRESS_PROVIDER"
    
    local ingress_success=false
    local egress_success=false
    
    # Run ingress authentication if requested
    if [ "$RUN_INGRESS" = true ]; then
        if run_ingress_auth; then
            ingress_success=true
        else
            # If both are requested and ingress fails, stop here
            if [ "$RUN_EGRESS" = true ]; then
                log_error "Ingress authentication failed. Stopping before egress (as both were requested)."
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
    
    log_info "🎉 OAuth credentials orchestration completed!"
    log_info "💡 Check ./.oauth-tokens/ for generated token and config files"
}

# Run main function
main "$@"