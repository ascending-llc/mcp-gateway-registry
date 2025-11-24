#!/bin/bash

################################################################################
# Initialize Scopes on EFS
#
# This script:
# 1. Builds and pushes the scopes-init Docker image to ECR
# 2. Reads terraform outputs from terraform-outputs.json
# 3. Creates an ECS task definition for scopes-init container
# 4. Runs the task on the ECS cluster
# 5. Waits for task completion
# 6. Displays logs from CloudWatch
#
# Usage:
#   ./scripts/run-scopes-init-task.sh [OPTIONS]
#
# Options:
#   --skip-build               Skip building and pushing Docker image
#   --aws-region REGION        AWS region (default: us-west-2)
#   --aws-profile PROFILE      AWS profile to use (default: default)
#   --wait-timeout SECONDS     Timeout waiting for task (default: 300)
#   --help                     Show this help message
#
# Examples:
#   # Build image and run task (default)
#   ./scripts/run-scopes-init-task.sh
#
#   # Skip build and run task only
#   ./scripts/run-scopes-init-task.sh --skip-build
#
#   # With custom timeout
#   ./scripts/run-scopes-init-task.sh --wait-timeout 600
#
################################################################################

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration with defaults
AWS_REGION="${AWS_REGION:-us-west-2}"
AWS_PROFILE="${AWS_PROFILE:-default}"
WAIT_TIMEOUT=300
SKIP_BUILD=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TERRAFORM_DIR="$REPO_ROOT/terraform/aws-ecs"
OUTPUTS_FILE="$SCRIPT_DIR/terraform-outputs.json"
BUILD_SCRIPT="$SCRIPT_DIR/build-and-push-scopes-init.sh"

# Functions
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
    grep '^#' "$0" | tail -n +2 | sed 's/^# //' | sed 's/^#//'
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --aws-region)
            AWS_REGION="$2"
            shift 2
            ;;
        --aws-profile)
            AWS_PROFILE="$2"
            shift 2
            ;;
        --wait-timeout)
            WAIT_TIMEOUT="$2"
            shift 2
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

log_info "=========================================="
log_info "Scopes Init ECS Task Runner"
log_info "=========================================="
log_info "AWS Region: $AWS_REGION"
log_info "AWS Profile: $AWS_PROFILE"
log_info "Skip Build: $SKIP_BUILD"
log_info "Wait Timeout: $WAIT_TIMEOUT seconds"
log_info "=========================================="

# Step 0: Build and push Docker image (optional)
if [[ "$SKIP_BUILD" == "false" ]]; then
    log_info "Step 0/7: Building and pushing scopes-init Docker image..."
    if [[ ! -f "$BUILD_SCRIPT" ]]; then
        log_error "Build script not found: $BUILD_SCRIPT"
        exit 1
    fi

    if AWS_REGION="$AWS_REGION" bash "$BUILD_SCRIPT"; then
        log_success "Docker image built and pushed successfully"
        # Extract image URI from the build output by getting the latest image
        IMAGE_URI="$(aws ecr describe-images \
            --repository-name mcp-gateway-scopes-init \
            --region "$AWS_REGION" \
            --query 'sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]' \
            --output text 2>/dev/null)"
        ACCOUNT_ID="$(aws sts get-caller-identity --region "$AWS_REGION" --query Account --output text 2>/dev/null)"
        IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/mcp-gateway-scopes-init:${IMAGE_URI}"
        log_success "Image URI: $IMAGE_URI"
    else
        log_error "Failed to build Docker image"
        exit 1
    fi
else
    log_info "Skipping Docker image build as requested"
    # Get the latest image from ECR
    IMAGE_TAG="$(aws ecr describe-images \
        --repository-name mcp-gateway-scopes-init \
        --region "$AWS_REGION" \
        --query 'sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]' \
        --output text 2>/dev/null)"
    ACCOUNT_ID="$(aws sts get-caller-identity --region "$AWS_REGION" --query Account --output text 2>/dev/null)"
    IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/mcp-gateway-scopes-init:${IMAGE_TAG}"
    log_success "Using existing image: $IMAGE_URI"
fi

# Step 1: Check terraform outputs file
log_info "Step 1/6: Validating terraform outputs..."
if [[ ! -f "$OUTPUTS_FILE" ]]; then
    log_error "terraform-outputs.json not found at $OUTPUTS_FILE"
    log_info "Run this command first to generate outputs:"
    log_info "  cd $TERRAFORM_DIR"
    log_info "  terraform output -json > $OUTPUTS_FILE"
    exit 1
fi
log_success "Found terraform outputs file"

# Step 2: Extract parameters from terraform outputs
log_info "Step 2/6: Extracting parameters from terraform outputs..."

CLUSTER_NAME=$(jq -r '.ecs_cluster_name.value // empty' "$OUTPUTS_FILE" 2>/dev/null)
if [[ -z "$CLUSTER_NAME" ]]; then
    log_error "Could not extract ecs_cluster_name from terraform outputs"
    exit 1
fi
log_success "Cluster: $CLUSTER_NAME"

EFS_ID=$(jq -r '.mcp_gateway_efs_id.value // empty' "$OUTPUTS_FILE" 2>/dev/null)
if [[ -z "$EFS_ID" ]]; then
    log_error "Could not extract mcp_gateway_efs_id from terraform outputs"
    log_info "Make sure terraform outputs are up to date by running:"
    log_info "  cd $TERRAFORM_DIR && terraform output -json > $OUTPUTS_FILE"
    exit 1
fi
log_success "EFS ID: $EFS_ID"

ACCESS_POINT_ID=$(jq -r '.mcp_gateway_efs_access_points.value.auth_config // empty' "$OUTPUTS_FILE" 2>/dev/null)
if [[ -z "$ACCESS_POINT_ID" ]]; then
    log_error "Could not extract mcp_gateway_efs_access_points.auth_config from terraform outputs"
    exit 1
fi
log_success "Access Point ID: $ACCESS_POINT_ID"

# Get VPC configuration from registry service
log_info "Step 3/6: Fetching VPC configuration from registry service..."

SUBNET_IDS=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "mcp-gateway-v2-registry" \
    --region "$AWS_REGION" \
    --query 'services[0].networkConfiguration.awsvpcConfiguration.subnets[*]' \
    --output text 2>/dev/null)

if [[ -z "$SUBNET_IDS" ]]; then
    log_error "Could not get subnet IDs from registry service"
    exit 1
fi
log_success "Subnets: $SUBNET_IDS"

SECURITY_GROUP_IDS=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "mcp-gateway-v2-registry" \
    --region "$AWS_REGION" \
    --query 'services[0].networkConfiguration.awsvpcConfiguration.securityGroups[*]' \
    --output text 2>/dev/null)

if [[ -z "$SECURITY_GROUP_IDS" ]]; then
    log_error "Could not get security group IDs from registry service"
    exit 1
fi
log_success "Security Groups: $SECURITY_GROUP_IDS"

# Get AWS account ID
if [[ -z "$AWS_PROFILE" || "$AWS_PROFILE" == "default" ]]; then
    AWS_ACCOUNT=$(aws sts get-caller-identity \
        --region "$AWS_REGION" \
        --query Account \
        --output text 2>/dev/null)
else
    AWS_ACCOUNT=$(aws sts get-caller-identity \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE" \
        --query Account \
        --output text 2>/dev/null)
fi

if [[ -z "$AWS_ACCOUNT" ]]; then
    log_error "Could not get AWS account ID"
    exit 1
fi
log_success "AWS Account: $AWS_ACCOUNT"

# Get execution role from existing auth-server task
EXECUTION_ROLE=$(aws ecs describe-task-definition \
    --task-definition mcp-gateway-v2-auth \
    --region "$AWS_REGION" \
    --query 'taskDefinition.executionRoleArn' \
    --output text 2>/dev/null)

if [[ -z "$EXECUTION_ROLE" ]]; then
    log_error "Could not get execution role from auth-server task"
    exit 1
fi
log_success "Execution Role: $EXECUTION_ROLE"

# Step 4: Create task definition
log_info "Step 4/6: Registering ECS task definition..."

TASK_DEF=$(cat <<EOF
{
  "family": "mcp-gateway-scopes-init",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "$EXECUTION_ROLE",
  "containerDefinitions": [
    {
      "name": "scopes-init",
      "image": "$IMAGE_URI",
      "essential": true,
      "mountPoints": [
        {
          "sourceVolume": "auth-config",
          "containerPath": "/mnt",
          "readOnly": false
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/mcp-gateway-scopes-init",
          "awslogs-region": "$AWS_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "volumes": [
    {
      "name": "auth-config",
      "efsVolumeConfiguration": {
        "fileSystemId": "$EFS_ID",
        "transitEncryption": "ENABLED",
        "authorizationConfig": {
          "accessPointId": "$ACCESS_POINT_ID"
        }
      }
    }
  ]
}
EOF
)

# Write task definition to temp file
TASK_DEF_FILE="/tmp/mcp-gateway-scopes-init-taskdef-$$.json"
echo "$TASK_DEF" > "$TASK_DEF_FILE"

if [[ -z "$AWS_PROFILE" || "$AWS_PROFILE" == "default" ]]; then
    TASK_DEF_ARN=$(aws ecs register-task-definition \
        --cli-input-json "file://$TASK_DEF_FILE" \
        --region "$AWS_REGION" \
        --query 'taskDefinition.taskDefinitionArn' \
        --output text 2>/dev/null)
else
    TASK_DEF_ARN=$(aws ecs register-task-definition \
        --cli-input-json "file://$TASK_DEF_FILE" \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE" \
        --query 'taskDefinition.taskDefinitionArn' \
        --output text 2>/dev/null)
fi

# Clean up temp file
rm -f "$TASK_DEF_FILE"

if [[ -z "$TASK_DEF_ARN" ]]; then
    log_error "Failed to register task definition"
    exit 1
fi
log_success "Task definition registered: $TASK_DEF_ARN"

# Step 5: Create CloudWatch log group if needed
log_info "Step 5/6: Checking CloudWatch log group..."

LOG_CHECK_CMD="aws logs describe-log-groups --log-group-name-prefix /ecs/mcp-gateway-scopes-init --region $AWS_REGION"
if [[ -n "$AWS_PROFILE" && "$AWS_PROFILE" != "default" ]]; then
    LOG_CHECK_CMD="$LOG_CHECK_CMD --profile $AWS_PROFILE"
fi

if ! $LOG_CHECK_CMD --query 'logGroups[0].logGroupName' 2>/dev/null | grep -q "mcp-gateway-scopes-init"; then
    log_info "Creating CloudWatch log group..."
    if [[ -z "$AWS_PROFILE" || "$AWS_PROFILE" == "default" ]]; then
        aws logs create-log-group \
            --log-group-name "/ecs/mcp-gateway-scopes-init" \
            --region "$AWS_REGION" 2>/dev/null || true
    else
        aws logs create-log-group \
            --log-group-name "/ecs/mcp-gateway-scopes-init" \
            --region "$AWS_REGION" \
            --profile "$AWS_PROFILE" 2>/dev/null || true
    fi
    log_success "Log group created"
else
    log_success "Log group already exists"
fi

# Step 6: Run the task
log_info "Step 6/6: Running ECS task..."

# Convert space-separated values to JSON arrays
SUBNET_JSON=$(echo "$SUBNET_IDS" | awk '{for(i=1;i<=NF;i++) print "\""$i"\""}' | paste -sd ',' -)
SG_JSON=$(echo "$SECURITY_GROUP_IDS" | awk '{for(i=1;i<=NF;i++) print "\""$i"\""}' | paste -sd ',' -)

if [[ -z "$AWS_PROFILE" || "$AWS_PROFILE" == "default" ]]; then
    TASK_ARN=$(aws ecs run-task \
        --cluster "$CLUSTER_NAME" \
        --task-definition "mcp-gateway-scopes-init" \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_JSON],securityGroups=[$SG_JSON],assignPublicIp=DISABLED}" \
        --region "$AWS_REGION" \
        --query 'tasks[0].taskArn' \
        --output text 2>/dev/null)
else
    TASK_ARN=$(aws ecs run-task \
        --cluster "$CLUSTER_NAME" \
        --task-definition "mcp-gateway-scopes-init" \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_JSON],securityGroups=[$SG_JSON],assignPublicIp=DISABLED}" \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE" \
        --query 'tasks[0].taskArn' \
        --output text 2>/dev/null)
fi

if [[ -z "$TASK_ARN" ]]; then
    log_error "Failed to run task"
    exit 1
fi

TASK_ID=$(echo "$TASK_ARN" | awk -F'/' '{print $NF}')
log_success "Task started: $TASK_ARN"

# Wait for task completion
log_info "Waiting for task to complete (timeout: $WAIT_TIMEOUT seconds)..."

ELAPSED=0
INTERVAL=5

while [[ $ELAPSED -lt $WAIT_TIMEOUT ]]; do
    if [[ -z "$AWS_PROFILE" || "$AWS_PROFILE" == "default" ]]; then
        TASK_STATUS=$(aws ecs describe-tasks \
            --cluster "$CLUSTER_NAME" \
            --tasks "$TASK_ARN" \
            --region "$AWS_REGION" \
            --query 'tasks[0].{lastStatus:lastStatus,exitCode:containers[0].exitCode}' \
            --output json 2>/dev/null)
    else
        TASK_STATUS=$(aws ecs describe-tasks \
            --cluster "$CLUSTER_NAME" \
            --tasks "$TASK_ARN" \
            --region "$AWS_REGION" \
            --profile "$AWS_PROFILE" \
            --query 'tasks[0].{lastStatus:lastStatus,exitCode:containers[0].exitCode}' \
            --output json 2>/dev/null)
    fi

    LAST_STATUS=$(echo "$TASK_STATUS" | jq -r '.lastStatus // "UNKNOWN"')
    EXIT_CODE=$(echo "$TASK_STATUS" | jq -r '.exitCode // "null"')

    log_info "Task status: $LAST_STATUS (elapsed: ${ELAPSED}s)"

    if [[ "$LAST_STATUS" == "STOPPED" ]]; then
        if [[ "$EXIT_CODE" == "0" ]]; then
            log_success "Task completed successfully!"
            break
        else
            log_error "Task failed with exit code: $EXIT_CODE"
            break
        fi
    fi

    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [[ $ELAPSED -ge $WAIT_TIMEOUT ]]; then
    log_warning "Task did not complete within timeout period"
fi

# Display task logs
log_info "Retrieving task logs from CloudWatch..."
echo ""

LOG_STREAM="ecs/scopes-init/$TASK_ID"

# Wait a moment for logs to appear
sleep 2

if [[ -z "$AWS_PROFILE" || "$AWS_PROFILE" == "default" ]]; then
    LOGS=$(aws logs get-log-events \
        --log-group-name "/ecs/mcp-gateway-scopes-init" \
        --log-stream-name "$LOG_STREAM" \
        --region "$AWS_REGION" \
        --query 'events[*].message' \
        --output text 2>/dev/null || echo "")
else
    LOGS=$(aws logs get-log-events \
        --log-group-name "/ecs/mcp-gateway-scopes-init" \
        --log-stream-name "$LOG_STREAM" \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE" \
        --query 'events[*].message' \
        --output text 2>/dev/null || echo "")
fi

if [[ -n "$LOGS" ]]; then
    log_info "CloudWatch Logs:"
    echo "$LOGS" | while read -r line; do
        echo "  $line"
    done
else
    log_warning "No logs found (they may take a moment to appear)"
fi

echo ""
log_success "=========================================="
log_success "Scopes Init Task Complete!"
log_success "=========================================="
log_info "Task ARN: $TASK_ARN"
log_info "Exit Code: $EXIT_CODE"
log_info ""
log_info "The scopes.yml file should now be available on the EFS mount"
log_info "at /auth_config/scopes.yml for registry and auth-server containers."
log_info ""

if [[ "$EXIT_CODE" != "0" ]]; then
    log_error "Task failed. Check the logs above for details."
    exit 1
fi

exit 0
