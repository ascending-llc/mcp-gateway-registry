#!/bin/bash
# Build and push Docker images from build-config.yaml to AWS ECR
# Usage: ./scripts/build-images.sh [build|push|build-push] [IMAGE=name]
# Example: ./scripts/build-images.sh build IMAGE=registry

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# CRITICAL: Check if AWS_REGION is set
if [[ -z "${AWS_REGION:-}" ]]; then
    echo -e "${RED}${BOLD}============================================${NC}"
    echo -e "${RED}${BOLD}ERROR: AWS_REGION environment variable is not set!${NC}"
    echo -e "${RED}${BOLD}============================================${NC}"
    echo ""
    echo "Please set AWS_REGION before running build/push commands:"
    echo "  export AWS_REGION=us-east-1"
    echo ""
    echo "This prevents accidentally pushing to the wrong region."
    echo ""
    exit 1
fi

# Display region in BIG BOLD LETTERS
echo ""
echo -e "${GREEN}${BOLD}============================================${NC}"
echo -e "${GREEN}${BOLD}AWS REGION: ${AWS_REGION}${NC}"
echo -e "${GREEN}${BOLD}============================================${NC}"
echo ""

# Configuration
CONFIG_FILE="${REPO_ROOT}/build-config.yaml"
ACTION="${1:-build-push}"
TARGET_IMAGE="${IMAGE:-}"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validate configuration file exists
if [ ! -f "$CONFIG_FILE" ]; then
    log_error "Configuration file not found: $CONFIG_FILE"
    exit 1
fi

# Parse AWS account ID and construct ECR registry dynamically based on AWS_REGION
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

if [ -z "$AWS_ACCOUNT_ID" ]; then
    log_error "Could not determine AWS Account ID"
    exit 1
fi

log_info "AWS Account: $AWS_ACCOUNT_ID"
log_info "ECR Registry: $ECR_REGISTRY"
log_info "AWS Region: $AWS_REGION"
log_info "Build Action: $ACTION"

# Parse images from YAML and build array
declare -A IMAGES
declare -a IMAGE_NAMES

# Single pass to parse config and collect image information
while IFS='|' read -r name repo_name dockerfile context; do
    if [ -n "$name" ]; then
        IMAGES["$name"]="$repo_name|$dockerfile|$context"
        IMAGE_NAMES+=("$name")
    fi
done <<< "$(python3 << PYEOF
import yaml
import sys

try:
    with open('$CONFIG_FILE') as f:
        config = yaml.safe_load(f)

    images = config.get('images', {})
    for name, image_config in images.items():
        repo_name = image_config.get('repo_name')
        dockerfile = image_config.get('dockerfile')
        context = image_config.get('context', '.')

        if not repo_name or not dockerfile:
            print(f"ERROR: Image '{name}' missing repo_name or dockerfile", file=sys.stderr)
            sys.exit(1)

        print(f"{name}|{repo_name}|{dockerfile}|{context}")

except Exception as e:
    print(f"ERROR: Failed to parse config: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
)"

# Function to setup A2A agent build dependencies
setup_a2a_agent() {
    local image_name="$1"
    local context="$2"
    local agent_dir=""
    local tmp_dir=""
    local deps_source_dir=""

    # Determine which agent this is and where to place .tmp files
    if [[ "$image_name" == "flight_booking_agent" ]]; then
        agent_dir="${REPO_ROOT}/${context}"
        tmp_dir="${REPO_ROOT}/${context}/.tmp"
        # Dependencies are at agents/a2a level
        deps_source_dir="${REPO_ROOT}/agents/a2a"
    elif [[ "$image_name" == "travel_assistant_agent" ]]; then
        agent_dir="${REPO_ROOT}/${context}"
        tmp_dir="${REPO_ROOT}/${context}/.tmp"
        # Dependencies are at agents/a2a level
        deps_source_dir="${REPO_ROOT}/agents/a2a"
    else
        return 0  # Not an A2A agent
    fi

    # Create .tmp directory in context root (where Dockerfile COPY command expects it)
    log_info "Setting up A2A agent dependencies for $image_name..."
    mkdir -p "$tmp_dir" || {
        log_error "Failed to create .tmp directory for $image_name"
        return 1
    }

    # Copy pyproject.toml and uv.lock from agents/a2a root to context/.tmp/
    if [ -f "${deps_source_dir}/pyproject.toml" ] && [ -f "${deps_source_dir}/uv.lock" ]; then
        cp "${deps_source_dir}/pyproject.toml" "$tmp_dir/" || {
            log_error "Failed to copy pyproject.toml for $image_name"
            return 1
        }
        cp "${deps_source_dir}/uv.lock" "$tmp_dir/" || {
            log_error "Failed to copy uv.lock for $image_name"
            return 1
        }
        log_success "Copied dependencies to $tmp_dir/"
    else
        log_error "Missing pyproject.toml or uv.lock in ${deps_source_dir}"
        return 1
    fi

    return 0
}

# Function to cleanup A2A agent build dependencies
cleanup_a2a_agent() {
    local image_name="$1"
    local context="$2"
    local tmp_dir=""

    # Determine which agent this is
    if [[ "$image_name" == "flight_booking_agent" ]]; then
        tmp_dir="${REPO_ROOT}/${context}/.tmp"
    elif [[ "$image_name" == "travel_assistant_agent" ]]; then
        tmp_dir="${REPO_ROOT}/${context}/.tmp"
    else
        return 0  # Not an A2A agent
    fi

    # Remove .tmp directory from context root
    if [ -d "$tmp_dir" ]; then
        log_info "Cleaning up A2A agent temporary files for $image_name..."
        rm -rf "$tmp_dir" || {
            log_warning "Failed to cleanup .tmp directory for $image_name"
        }
    fi

    return 0
}

# Function to build Docker image
build_image() {
    local image_name="$1"
    local repo_name="$2"
    local dockerfile="$3"
    local context="$4"

    log_info "Building $image_name..."

    # Validate dockerfile exists
    if [ ! -f "$REPO_ROOT/$dockerfile" ]; then
        log_error "Dockerfile not found: $REPO_ROOT/$dockerfile"
        return 1
    fi

    # Setup A2A agent dependencies if needed
    if ! setup_a2a_agent "$image_name" "$context"; then
        return 1
    fi

    # Determine if we need buildx for this image
    if [[ "$image_name" == *"_agent" ]] && [ -f "$REPO_ROOT/$dockerfile" ]; then
        # A2A agents need buildx for ARM64 support
        log_info "Building A2A agent with buildx for multi-platform support..."
        docker buildx build \
            --load \
            -f "$REPO_ROOT/$dockerfile" \
            -t "$repo_name:latest" \
            "$REPO_ROOT/$context" || {
            log_error "Failed to build $image_name"
            cleanup_a2a_agent "$image_name" "$context"
            return 1
        }
    else
        # Standard docker build for other images
        docker build \
            -f "$REPO_ROOT/$dockerfile" \
            -t "$repo_name:latest" \
            "$REPO_ROOT/$context" || {
            log_error "Failed to build $image_name"
            cleanup_a2a_agent "$image_name" "$context"
            return 1
        }
    fi

    log_success "Built $repo_name:latest"

    # Cleanup A2A agent dependencies after build
    cleanup_a2a_agent "$image_name" "$context"

    return 0
}

# Function to push image to ECR
push_image() {
    local image_name="$1"
    local repo_name="$2"

    local ecr_uri="${ECR_REGISTRY}/${repo_name}:latest"

    log_info "Pushing $image_name to ECR..."

    # Create ECR repository if it doesn't exist
    log_info "Checking ECR repository: $repo_name"
    aws ecr describe-repositories \
        --repository-names "$repo_name" \
        --region "$AWS_REGION" 2>/dev/null || {
        log_info "Repository doesn't exist, creating: $repo_name"
        aws ecr create-repository \
            --repository-name "$repo_name" \
            --region "$AWS_REGION"
        log_success "Created ECR repository: $repo_name"
    }

    # Login to ECR
    log_info "Authenticating with ECR..."
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "$ECR_REGISTRY" || {
        log_error "Failed to authenticate with ECR"
        return 1
    }

    # Tag image for ECR
    docker tag "$repo_name:latest" "$ecr_uri" || {
        log_error "Failed to tag image for ECR"
        return 1
    }

    # Push to ECR
    docker push "$ecr_uri" || {
        log_error "Failed to push image to ECR"
        return 1
    }

    log_success "Pushed $ecr_uri"
}

# Process images
if [ -z "$TARGET_IMAGE" ]; then
    # Process all images
    log_info "Processing all ${#IMAGE_NAMES[@]} images..."
    IMAGES_TO_PROCESS=("${IMAGE_NAMES[@]}")
else
    # Process specific image
    if [[ " ${IMAGE_NAMES[@]} " =~ " ${TARGET_IMAGE} " ]]; then
        log_info "Processing specific image: $TARGET_IMAGE"
        IMAGES_TO_PROCESS=("$TARGET_IMAGE")
    else
        log_error "Image not found: $TARGET_IMAGE"
        log_info "Available images: ${IMAGE_NAMES[*]}"
        exit 1
    fi
fi

# Execute actions
FAILED_IMAGES=()
SUCCESSFUL_IMAGES=()

for image_name in "${IMAGES_TO_PROCESS[@]}"; do
    IFS='|' read -r repo_name dockerfile context <<< "${IMAGES[$image_name]}"

    log_info "=========================================="
    log_info "Processing: $image_name ($repo_name)"
    log_info "=========================================="

    if [[ "$ACTION" == "build" ]] || [[ "$ACTION" == "build-push" ]]; then
        if ! build_image "$image_name" "$repo_name" "$dockerfile" "$context"; then
            FAILED_IMAGES+=("$image_name")
            continue
        fi
    fi

    if [[ "$ACTION" == "push" ]] || [[ "$ACTION" == "build-push" ]]; then
        if ! push_image "$image_name" "$repo_name"; then
            FAILED_IMAGES+=("$image_name")
            continue
        fi
    fi

    SUCCESSFUL_IMAGES+=("$image_name")
done

# Summary
log_info "=========================================="
log_info "Build Summary"
log_info "=========================================="
log_success "Successful: ${#SUCCESSFUL_IMAGES[@]}"
if [ ${#SUCCESSFUL_IMAGES[@]} -gt 0 ]; then
    for img in "${SUCCESSFUL_IMAGES[@]}"; do
        echo "  - $img"
    done
fi

if [ ${#FAILED_IMAGES[@]} -gt 0 ]; then
    log_error "Failed: ${#FAILED_IMAGES[@]}"
    for img in "${FAILED_IMAGES[@]}"; do
        echo "  - $img"
    done
    exit 1
fi

log_success "All images processed successfully!"
