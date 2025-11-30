#!/bin/bash
#
# Pre-Destroy Cleanup Script
# Run this before 'terraform destroy' to clean up resources that may block deletion
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

AWS_REGION="${AWS_REGION:-us-east-1}"

echo "============================================"
echo "MCP Gateway Pre-Destroy Cleanup"
echo "Region: $AWS_REGION"
echo "============================================"
echo ""

# Function to log messages
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}


# Step 1: Scale down and delete ECS services
echo ""
echo "Step 1: Cleaning up ECS Services"
echo "--------------------------------"

# MCP Gateway ECS Cluster services
MCP_CLUSTER="mcp-gateway-ecs-cluster"
SERVICES=$(aws ecs list-services --cluster "$MCP_CLUSTER" --region "$AWS_REGION" --query 'serviceArns[*]' --output text 2>/dev/null || echo "")

if [[ -n "$SERVICES" ]]; then
    for service_arn in $SERVICES; do
        service_name=$(echo "$service_arn" | awk -F'/' '{print $NF}')
        log_info "Scaling down and deleting service: $service_name"
        aws ecs update-service --cluster "$MCP_CLUSTER" --service "$service_name" --desired-count 0 --region "$AWS_REGION" --output text --query 'service.serviceName' 2>/dev/null || true
        aws ecs delete-service --cluster "$MCP_CLUSTER" --service "$service_name" --force --region "$AWS_REGION" --output text --query 'service.serviceName' 2>/dev/null || true
    done
else
    log_info "No services found in $MCP_CLUSTER"
fi

# Keycloak cluster services
KC_CLUSTER="keycloak"
KC_SERVICES=$(aws ecs list-services --cluster "$KC_CLUSTER" --region "$AWS_REGION" --query 'serviceArns[*]' --output text 2>/dev/null || echo "")

if [[ -n "$KC_SERVICES" ]]; then
    for service_arn in $KC_SERVICES; do
        service_name=$(echo "$service_arn" | awk -F'/' '{print $NF}')
        log_info "Scaling down and deleting service: $service_name (keycloak cluster)"
        aws ecs update-service --cluster "$KC_CLUSTER" --service "$service_name" --desired-count 0 --region "$AWS_REGION" --output text --query 'service.serviceName' 2>/dev/null || true
        aws ecs delete-service --cluster "$KC_CLUSTER" --service "$service_name" --force --region "$AWS_REGION" --output text --query 'service.serviceName' 2>/dev/null || true
    done
else
    log_info "No services found in $KC_CLUSTER"
fi


# Step 2: Wait for tasks to stop
echo ""
echo "Step 2: Waiting for ECS tasks to stop"
echo "--------------------------------------"

sleep 10

for cluster in "$MCP_CLUSTER" "$KC_CLUSTER"; do
    TASKS=$(aws ecs list-tasks --cluster "$cluster" --region "$AWS_REGION" --query 'taskArns[*]' --output text 2>/dev/null || echo "")
    if [[ -n "$TASKS" ]]; then
        log_info "Waiting for tasks in $cluster to stop..."
        for i in {1..12}; do
            TASKS=$(aws ecs list-tasks --cluster "$cluster" --region "$AWS_REGION" --query 'taskArns[*]' --output text 2>/dev/null || echo "")
            if [[ -z "$TASKS" ]]; then
                log_info "All tasks in $cluster stopped"
                break
            fi
            log_info "Still waiting... ($i/12)"
            sleep 10
        done
    else
        log_info "No running tasks in $cluster"
    fi
done


# Step 3: Clean up Service Discovery namespaces
echo ""
echo "Step 3: Cleaning up Service Discovery Namespaces"
echo "-------------------------------------------------"

NAMESPACES=$(aws servicediscovery list-namespaces --region "$AWS_REGION" --query 'Namespaces[?contains(Name, `mcp-gateway`)].{Id:Id,Name:Name}' --output json 2>/dev/null || echo "[]")

if [[ "$NAMESPACES" != "[]" ]]; then
    echo "$NAMESPACES" | jq -r '.[] | "\(.Id) \(.Name)"' | while read -r ns_id ns_name; do
        log_info "Processing namespace: $ns_name ($ns_id)"

        # Delete services in the namespace first
        NS_SERVICES=$(aws servicediscovery list-services --filters Name=NAMESPACE_ID,Values="$ns_id" --region "$AWS_REGION" --query 'Services[*].Id' --output text 2>/dev/null || echo "")

        if [[ -n "$NS_SERVICES" ]]; then
            for svc_id in $NS_SERVICES; do
                log_info "  Deleting service: $svc_id"
                aws servicediscovery delete-service --id "$svc_id" --region "$AWS_REGION" 2>/dev/null || log_warn "  Failed to delete service $svc_id"
            done
        fi

        # Now delete the namespace
        log_info "  Deleting namespace: $ns_name"
        aws servicediscovery delete-namespace --id "$ns_id" --region "$AWS_REGION" 2>/dev/null || log_warn "  Failed to delete namespace $ns_name (may require additional IAM permissions)"
    done
else
    log_info "No MCP Gateway service discovery namespaces found"
fi


# Step 4: ECR Repositories - PRESERVED (not deleted)
echo ""
echo "Step 4: ECR Repositories"
echo "------------------------"
echo ""
log_warn "============================================================"
log_warn "ECR REPOSITORIES ARE NOT DELETED BY THIS SCRIPT"
log_warn "============================================================"
log_warn ""
log_warn "Container images are preserved to avoid expensive rebuilds."
log_warn "Images can be reused after terraform apply without rebuilding."
log_warn ""
log_warn "If you want to delete ECR repositories manually, run:"
log_warn ""
log_warn "  aws ecr delete-repository --repository-name keycloak --force --region $AWS_REGION"
log_warn "  aws ecr delete-repository --repository-name mcp-gateway-registry --force --region $AWS_REGION"
log_warn "  aws ecr delete-repository --repository-name mcp-gateway-auth-server --force --region $AWS_REGION"
log_warn "  aws ecr delete-repository --repository-name mcp-gateway-currenttime --force --region $AWS_REGION"
log_warn "  aws ecr delete-repository --repository-name mcp-gateway-mcpgw --force --region $AWS_REGION"
log_warn "  aws ecr delete-repository --repository-name mcp-gateway-realserverfaketools --force --region $AWS_REGION"
log_warn "  aws ecr delete-repository --repository-name mcp-gateway-flight-booking-agent --force --region $AWS_REGION"
log_warn "  aws ecr delete-repository --repository-name mcp-gateway-travel-assistant-agent --force --region $AWS_REGION"
log_warn ""
log_warn "============================================================"
echo ""


# Step 5: Force delete Secrets Manager secrets
echo ""
echo "Step 5: Cleaning up Secrets Manager Secrets"
echo "--------------------------------------------"

SECRETS=(
    "keycloak/database"
    "mcp-gateway-keycloak-client-secret"
    "mcp-gateway-keycloak-m2m-client-secret"
)

for secret in "${SECRETS[@]}"; do
    if aws secretsmanager describe-secret --secret-id "$secret" --region "$AWS_REGION" &>/dev/null; then
        log_info "Force deleting secret: $secret"
        aws secretsmanager delete-secret --secret-id "$secret" --force-delete-without-recovery --region "$AWS_REGION" 2>/dev/null || log_warn "Failed to delete $secret"
    else
        log_info "Secret not found (already deleted): $secret"
    fi
done


# Step 6: Clean up any orphaned load balancers
echo ""
echo "Step 6: Checking for orphaned resources"
echo "----------------------------------------"

# Check for target groups that might block ALB deletion
TGS=$(aws elbv2 describe-target-groups --region "$AWS_REGION" --query 'TargetGroups[?contains(TargetGroupName, `keycloak`) || contains(TargetGroupName, `mcp-gateway`)].TargetGroupArn' --output text 2>/dev/null || echo "")

if [[ -n "$TGS" ]]; then
    log_warn "Found target groups that may need manual cleanup:"
    for tg in $TGS; do
        echo "  - $tg"
    done
fi


echo ""
echo "============================================"
echo "Pre-Destroy Cleanup Complete"
echo "============================================"
echo ""
echo "You can now run: terraform destroy"
echo ""
