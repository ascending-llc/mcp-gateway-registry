#!/bin/bash

################################################################################
# Save Terraform Outputs to JSON File
#
# This script:
# 1. Runs terraform output to get all deployed resource information
# 2. Saves output as JSON to terraform-outputs.json in the scripts directory
# 3. Creates a backup of previous outputs in terraform/.terraform/ directory
#
# Usage:
#   ./save-terraform-outputs.sh [OPTIONS]
#
# Options:
#   --output-file FILE         Output file name (default: terraform-outputs.json)
#   --terraform-dir DIR        Terraform directory (default: aws-ecs)
#   --no-backup                Don't create backup of previous output
#   --help                     Show this help message
#
# Examples:
#   # Save outputs with default filename (to scripts directory)
#   ./save-terraform-outputs.sh
#
#   # Save to custom filename (to scripts directory)
#   ./save-terraform-outputs.sh --output-file my-outputs.json
#
#   # Disable backups
#   ./save-terraform-outputs.sh --no-backup
#
# Note: Backups are stored in terraform/aws-ecs/.terraform/ which is gitignored
#
################################################################################

set -euo pipefail

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
OUTPUT_FILE="terraform-outputs.json"
TERRAFORM_DIR="terraform/aws-ecs"
CREATE_BACKUP=true
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="$SCRIPT_DIR"  # Save outputs to scripts directory
BACKUP_DIR=""  # Will be set to .terraform directory after validation

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

show_help() {
    grep '^#' "$0" | tail -n +2 | sed 's/^# //' | sed 's/^#//'\
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --output-file)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --terraform-dir)
            TERRAFORM_DIR="$2"
            shift 2
            ;;
        --no-backup)
            CREATE_BACKUP=false
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

# Validate terraform directory
TERRAFORM_PATH="$REPO_ROOT/$TERRAFORM_DIR"
if [[ ! -d "$TERRAFORM_PATH" ]]; then
    log_error "Terraform directory not found: $TERRAFORM_PATH"
    exit 1
fi

# Set backup directory to .terraform within terraform directory
BACKUP_DIR="$TERRAFORM_PATH/.terraform"

# Create .terraform directory if it doesn't exist
if [[ ! -d "$BACKUP_DIR" ]]; then
    log_info "Creating .terraform directory for backups: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
fi

# Get absolute output path
if [[ "$OUTPUT_FILE" != /* ]]; then
    OUTPUT_FILE="$OUTPUT_DIR/$OUTPUT_FILE"
fi

log_info "=========================================="
log_info "Terraform Outputs Export Script"
log_info "=========================================="
log_info "Terraform Directory: $TERRAFORM_PATH"
log_info "Output File: $OUTPUT_FILE"
log_info "Backup Directory: $BACKUP_DIR"
log_info "Create Backup: $CREATE_BACKUP"
log_info "=========================================="

# Create backup if file exists
if [[ -f "$OUTPUT_FILE" && "$CREATE_BACKUP" == "true" ]]; then
    BACKUP_FILE="$BACKUP_DIR/terraform-outputs.json.backup-${TIMESTAMP}"
    log_info "Creating backup of previous outputs..."
    cp "$OUTPUT_FILE" "$BACKUP_FILE"
    log_success "Backup created: $BACKUP_FILE"
fi

# Run terraform output
log_info "Running terraform output..."
cd "$TERRAFORM_PATH"

log_info "Exporting as JSON..."
if terraform output -json > "$OUTPUT_FILE" 2>/dev/null; then
    log_success "JSON outputs exported successfully"
else
    log_error "Failed to export JSON outputs"
    exit 1
fi

# Verify file was created
if [[ -f "$OUTPUT_FILE" ]]; then
    FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    log_success "Output file created successfully"
    log_info "File: $OUTPUT_FILE"
    log_info "Size: $FILE_SIZE"
    echo ""

    log_success "=========================================="
    log_success "Terraform outputs saved to:"
    log_success "$OUTPUT_FILE"
    log_success "=========================================="
else
    log_error "Failed to create output file"
    exit 1
fi

exit 0
