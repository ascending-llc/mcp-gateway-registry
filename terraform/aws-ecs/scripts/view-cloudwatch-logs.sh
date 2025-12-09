#!/bin/bash

################################################################################
# View CloudWatch Logs for ECS Tasks
#
# This script:
# 1. Reads Terraform outputs to find ECS log groups
# 2. Displays logs from the last N minutes
# 3. Supports live tailing with --follow flag
# 4. Supports filtering by component (keycloak, registry, auth-server, alb)
#
# Usage:
#   ./scripts/view-cloudwatch-logs.sh [OPTIONS]
#
# Options:
#   --minutes N                Number of minutes to look back (default: 30)
#   --follow                   Follow logs in real-time (like tail -f)
#   --component COMP           View logs for specific component:
#                              keycloak, registry, auth-server, all (default: all)
#   --start-time TIME          Start time (format: 2024-01-15T10:00:00Z)
#   --end-time TIME            End time (format: 2024-01-15T10:30:00Z)
#   --filter PATTERN           Filter logs by pattern (regex)
#   --help                     Show this help message
#
# Examples:
#   # View logs from last 30 minutes for all components
#   ./scripts/view-cloudwatch-logs.sh
#
#   # Follow Keycloak logs in real-time
#   ./scripts/view-cloudwatch-logs.sh --component keycloak --follow
#
#   # View registry logs from last 5 minutes
#   ./scripts/view-cloudwatch-logs.sh --component registry --minutes 5
#
#   # View logs with pattern filter
#   ./scripts/view-cloudwatch-logs.sh --filter "ERROR"
#
#   # View auth-server logs excluding health checks (default)
#   ./scripts/view-cloudwatch-logs.sh --component auth-server
#
#   # View auth-server logs including health check logs
#   ./scripts/view-cloudwatch-logs.sh --component auth-server --include-health
#
################################################################################

set -euo pipefail

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
MINUTES=30
FOLLOW=false
COMPONENT="all"
FILTER_PATTERN=""
EXCLUDE_HEALTH_CHECKS=true
START_TIME=""
END_TIME=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TERRAFORM_DIR="$REPO_ROOT/terraform/aws-ecs"
OUTPUTS_FILE="$SCRIPT_DIR/terraform-outputs.json"

# Log groups mapping - will be populated dynamically
declare -A LOG_GROUPS=()

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

log_component() {
    echo -e "${CYAN}[$1]${NC} $2"
}

show_help() {
    grep '^#' "$0" | tail -n +2 | sed 's/^# //' | sed 's/^#//'\
    exit 0
}

_discover_ecs_log_groups() {
    log_info "Discovering ECS services and log groups..."

    # Get all log groups matching ECS patterns
    local ecs_logs=$(aws logs describe-log-groups \
        --log-group-name-prefix "/ecs/" \
        --region "$AWS_REGION" \
        --query 'logGroups[*].logGroupName' \
        --output text 2>/dev/null || true)

    if [[ -z "$ecs_logs" ]]; then
        ecs_logs=$(aws logs describe-log-groups \
            --log-group-name-prefix "/aws/ecs/" \
            --region "$AWS_REGION" \
            --query 'logGroups[*].logGroupName' \
            --output text 2>/dev/null || true)
    fi

    # Also add ALB logs
    local alb_logs=$(aws logs describe-log-groups \
        --log-group-name-prefix "/aws/alb" \
        --region "$AWS_REGION" \
        --query 'logGroups[*].logGroupName' \
        --output text 2>/dev/null || true)

    # Combine all logs
    local all_logs="$ecs_logs $alb_logs"

    # Populate the LOG_GROUPS array
    for log_group in $all_logs; do
        # Extract service name from log group
        local service_name=$(basename "$log_group")

        # Clean up common prefixes
        service_name=$(echo "$service_name" | sed 's/^mcp-gateway-v2-//' | sed 's/^mcp-gateway-//')
        service_name=$(echo "$service_name" | sed 's/-server$//' | sed 's/-init$//')

        # Use full name if empty after cleanup
        if [[ -z "$service_name" ]]; then
            service_name=$(basename "$log_group")
        fi

        LOG_GROUPS[$service_name]="$log_group"
    done

    if [[ ${#LOG_GROUPS[@]} -eq 0 ]]; then
        log_warning "No ECS log groups found in region $AWS_REGION"
        return 1
    fi

    log_success "Found ${#LOG_GROUPS[@]} log groups"

    # Debug: Show discovered components
    log_info "Available components: ${!LOG_GROUPS[@]}"
}

_validate_outputs_file() {
    if [[ ! -f "$OUTPUTS_FILE" ]]; then
        log_warning "Terraform outputs file not found: $OUTPUTS_FILE"
        log_info "Discovering services from AWS instead..."
        return 1
    fi
    return 0
}

_get_log_groups() {
    local comp="$1"

    if [[ "$comp" == "all" ]]; then
        echo "${!LOG_GROUPS[@]}"
    else
        if [[ -z "${LOG_GROUPS[$comp]:-}" ]]; then
            log_error "Unknown component: $comp" >&2
            log_info "Available components: ${!LOG_GROUPS[@]}" >&2
            return 1
        fi
        echo "$comp"
    fi
}

_calculate_start_time() {
    if [[ -n "$START_TIME" ]]; then
        echo "$START_TIME"
    else
        # Calculate timestamp from N minutes ago
        if command -v date &> /dev/null; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                # macOS
                date -u -v-${MINUTES}M +%s000
            else
                # Linux
                date -u -d "$MINUTES minutes ago" +%s000
            fi
        fi
    fi
}

_calculate_end_time() {
    if [[ -n "$END_TIME" ]]; then
        echo "$END_TIME"
    else
        # Current timestamp in milliseconds
        if command -v date &> /dev/null; then
            date -u +%s000
        fi
    fi
}

_check_log_group_exists() {
    local log_group="$1"

    if aws logs describe-log-groups \
        --log-group-name-prefix "$log_group" \
        --region "$AWS_REGION" \
        &>/dev/null; then
        return 0
    else
        return 1
    fi
}

_should_exclude_log() {
    local message="$1"

    # Exclude health check logs
    if [[ "$EXCLUDE_HEALTH_CHECKS" == "true" ]]; then
        # Health check patterns to exclude
        if [[ "$message" =~ GET\ /health\ HTTP ]]; then
            return 0  # Should exclude
        fi
    fi

    return 1  # Don't exclude
}

_tail_logs() {
    local log_group="$1"
    local follow="${2:-false}"

    log_component "$log_group" "Fetching logs..."

    # Check if log group exists
    if ! _check_log_group_exists "$log_group"; then
        log_warning "Log group not found: $log_group"
        return 1
    fi

    if [[ "$follow" == "true" ]]; then
        # Real-time tailing
        aws logs tail "$log_group" \
            --follow \
            --since "${MINUTES}m" \
            --region "$AWS_REGION" \
            $(if [[ -n "$FILTER_PATTERN" ]]; then echo "--filter-pattern $FILTER_PATTERN"; fi) \
            2>&1 | while read -r message; do
            if ! _should_exclude_log "$message"; then
                echo "$message"
            fi
        done
    else
        # Display logs from the past N minutes
        local start_time=$(_calculate_start_time)
        local end_time=$(_calculate_end_time)

        aws logs filter-log-events \
            --log-group-name "$log_group" \
            --start-time "$start_time" \
            --end-time "$end_time" \
            --region "$AWS_REGION" \
            $(if [[ -n "$FILTER_PATTERN" ]]; then echo "--filter-pattern $FILTER_PATTERN"; fi) \
            --query 'events[*].[timestamp, message]' \
            --output text \
            2>/dev/null | while read -r timestamp message; do
            if [[ -n "$timestamp" && -n "$message" ]]; then
                # Skip health check logs if enabled
                if _should_exclude_log "$message"; then
                    continue
                fi

                # Convert timestamp from milliseconds to readable format
                if command -v date &> /dev/null; then
                    if [[ "$OSTYPE" == "darwin"* ]]; then
                        formatted_time=$(date -u -r $((timestamp / 1000)) +"%Y-%m-%d %H:%M:%S")
                    else
                        formatted_time=$(date -u -d @$((timestamp / 1000)) +"%Y-%m-%d %H:%M:%S")
                    fi
                else
                    formatted_time=$(echo "scale=0; $timestamp / 1000" | bc)
                fi
                echo "[${formatted_time}] $message"
            fi
        done || true
    fi
}

_view_all_logs() {
    local follow="${1:-false}"
    local components

    # Get components and check for errors
    if ! components=$(_get_log_groups "$COMPONENT"); then
        exit 1
    fi

    echo ""
    log_info "=========================================="
    log_info "CloudWatch Logs Viewer"
    log_info "=========================================="
    log_info "Components: $COMPONENT"
    log_info "Minutes back: $MINUTES"
    log_info "Follow mode: $follow"
    if [[ -n "$FILTER_PATTERN" ]]; then
        log_info "Filter pattern: $FILTER_PATTERN"
    fi
    log_info "=========================================="
    echo ""

    # If following, tail all logs concurrently
    if [[ "$follow" == "true" ]]; then
        # For follow mode, we'll tail each log group
        for comp in $components; do
            log_group="${LOG_GROUPS[$comp]}"
            echo ""
            echo "---[ $comp logs (live) ]---"
            _tail_logs "$log_group" "true" &
        done
        wait
    else
        # For non-follow mode, display logs sequentially
        for comp in $components; do
            log_group="${LOG_GROUPS[$comp]}"
            echo ""
            echo "---[ $comp logs ]---"
            _tail_logs "$log_group" "false"
        done
    fi

    echo ""
    log_success "=========================================="
    log_success "Log viewing complete"
    log_success "=========================================="
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --minutes)
            MINUTES="$2"
            shift 2
            ;;
        --follow)
            FOLLOW=true
            shift
            ;;
        --component)
            COMPONENT="$2"
            shift 2
            ;;
        --start-time)
            START_TIME="$2"
            shift 2
            ;;
        --end-time)
            END_TIME="$2"
            shift 2
            ;;
        --filter)
            FILTER_PATTERN="$2"
            shift 2
            ;;
        --include-health)
            EXCLUDE_HEALTH_CHECKS=false
            shift
            ;;
        --help)
            show_help
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            ;;
    esac
done

# Validate inputs
if ! [[ "$MINUTES" =~ ^[0-9]+$ ]]; then
    log_error "Minutes must be a number"
    exit 1
fi

# Verify AWS CLI is available
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI is not installed or not in PATH"
    exit 1
fi

# Check AWS_REGION is set
if [[ -z "${AWS_REGION:-}" ]]; then
    log_error "AWS_REGION environment variable is not set"
    log_info "Please set AWS_REGION before running this script:"
    log_info "  export AWS_REGION=us-east-1"
    exit 1
fi

log_info "Using AWS region: $AWS_REGION"

# Main execution
# Always try discovery first (more reliable than outputs file)
_discover_ecs_log_groups || {
    log_warning "Discovery from AWS failed, attempting to use Terraform outputs..."
    _validate_outputs_file || {
        log_error "Failed to discover ECS log groups and outputs file not found"
        exit 1
    }
}

_view_all_logs "$FOLLOW"

exit 0
