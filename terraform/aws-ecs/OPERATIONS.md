# Operations and Maintenance

This document covers day-to-day operations and maintenance tasks for the MCP Gateway ECS deployment.

## Accessing ECS Tasks

### SSH into Running Tasks

Use the provided script to get shell access to any running ECS task:

```bash
cd terraform/aws-ecs

# Connect to Registry task
./scripts/ecs-ssh.sh registry

# Connect to Auth Server task
./scripts/ecs-ssh.sh auth-server

# Connect to Keycloak task
./scripts/ecs-ssh.sh keycloak

# Specify custom cluster or region
./scripts/ecs-ssh.sh registry mcp-gateway-ecs-cluster us-east-1
```

The script automatically:
- Finds the first running task for the specified service
- Establishes an interactive session using AWS Systems Manager
- No SSH keys or bastion hosts required

**Requirements:**
- Session Manager plugin installed: `aws ssm install-plugin`
- IAM permissions for `ecs:ExecuteCommand` and `ssm:StartSession`
- ECS tasks must have `enableExecuteCommand` enabled (already configured)

### Manual ECS Access

```bash
# List all tasks in cluster
aws ecs list-tasks --cluster mcp-gateway-ecs-cluster --region us-east-1

# Get specific task details
aws ecs describe-tasks \
  --cluster mcp-gateway-ecs-cluster \
  --tasks TASK_ARN \
  --region us-east-1

# Execute command in running task
aws ecs execute-command \
  --cluster mcp-gateway-ecs-cluster \
  --task TASK_ARN \
  --container registry \
  --interactive \
  --command "/bin/bash" \
  --region us-east-1
```

## Viewing Logs

### Using CloudWatch Logs Script

```bash
cd terraform/aws-ecs

# Basic usage - last 30 minutes, all components
./scripts/view-cloudwatch-logs.sh

# Component-specific logs
./scripts/view-cloudwatch-logs.sh --component keycloak
./scripts/view-cloudwatch-logs.sh --component registry
./scripts/view-cloudwatch-logs.sh --component auth-server

# Custom time range
./scripts/view-cloudwatch-logs.sh --minutes 60  # Last hour
./scripts/view-cloudwatch-logs.sh --minutes 5   # Last 5 minutes

# Live tail (real-time streaming)
./scripts/view-cloudwatch-logs.sh --follow

# Filter by pattern (regex)
./scripts/view-cloudwatch-logs.sh --filter "ERROR|WARN"
./scripts/view-cloudwatch-logs.sh --filter "database connection"

# Specific time range
./scripts/view-cloudwatch-logs.sh \
  --start-time 2024-01-15T10:00:00Z \
  --end-time 2024-01-15T11:00:00Z

# Combine options
./scripts/view-cloudwatch-logs.sh \
  --component registry \
  --minutes 15 \
  --filter "ERROR"
```

### Direct CloudWatch Access

```bash
# List log groups
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/ecs/mcp-gateway" \
  --region us-east-1

# Get specific log streams
aws logs describe-log-streams \
  --log-group-name "/aws/ecs/mcp-gateway-registry" \
  --order-by LastEventTime \
  --descending \
  --max-items 5 \
  --region us-east-1

# Tail logs in real-time
aws logs tail "/aws/ecs/mcp-gateway-registry" \
  --follow \
  --region us-east-1

# Filter and query logs
aws logs filter-log-events \
  --log-group-name "/aws/ecs/mcp-gateway-registry" \
  --start-time $(date -u -d '30 minutes ago' +%s)000 \
  --filter-pattern "ERROR" \
  --region us-east-1
```

## Container Build and Deployment

### Understanding the Build System

The repository uses a unified container build system with `build-config.yaml` as the **single source of truth**.

**All Container Images:**

| Image Name | Purpose | Size | Build Time |
|------------|---------|------|------------|
| `registry` | MCP Gateway with nginx, FAISS, ML models | ~4.6GB | ~8 min |
| `mcpgw` | MCP Gateway core server | ~4.1GB | ~7 min |
| `auth_server` | OAuth2/OIDC authentication server | ~244MB | ~3 min |
| `currenttime` | Example MCP server (current time) | ~230MB | ~2 min |
| `realserverfaketools` | Testing MCP server | ~230MB | ~2 min |
| `flight_booking_agent` | A2A agent for flight booking | ~170MB | ~2 min |
| `travel_assistant_agent` | A2A agent for travel assistance | ~170MB | ~2 min |

**Total:** ~9.8GB across 7 images, ~25-30 minutes for complete build.

### Building Container Images

**Prerequisites:**
```bash
# Verify Docker is running
docker ps

# Set target region
export AWS_REGION=us-east-1

# Verify AWS credentials
aws sts get-caller-identity
```

**Build Commands:**

```bash
# From repository root
cd /path/to/mcp-gateway-registry

# ==============================================================================
# BUILD ONLY (Local Testing)
# ==============================================================================
# Build all 12 images locally (no push)
make build

# Build specific image
make build IMAGE=registry
make build IMAGE=auth_server
make build IMAGE=keycloak

# Build multiple specific images
make build IMAGE=registry && make build IMAGE=auth_server

# ==============================================================================
# PUSH ONLY (After Local Build)
# ==============================================================================
# Push all built images to ECR
make push

# Push specific image
make push IMAGE=registry

# ==============================================================================
# BUILD + PUSH (Recommended for Deployment)
# ==============================================================================
# Build and push all images (full deployment)
make build-push

# Build and push specific image (faster updates)
make build-push IMAGE=registry
make build-push IMAGE=auth_server
make build-push IMAGE=metrics_service

# ==============================================================================
# AGENT-SPECIFIC BUILDS
# ==============================================================================
# Build both A2A agents
make build-agents

# Push both A2A agents
make push-agents
```

**What Happens During `make build-push`:**

```
1. Reads build-config.yaml for image definitions
2. Authenticates with ECR: aws ecr get-login-password
3. Creates ECR repositories (if don't exist)
4. For each image:
   a. Builds Docker image with specified dockerfile and context
   b. Tags with latest and optional custom tags
   c. Pushes to ECR repository
5. Displays summary with all ECR URIs
```

**Example Output:**
```
[INFO] AWS Account: 123456789012
[INFO] ECR Registry: 123456789012.dkr.ecr.us-east-1.amazonaws.com
[INFO] AWS Region: us-east-1
[INFO] Build Action: build-push
[INFO] Processing all 12 images...

[INFO] ==========================================
[INFO] Processing: registry (mcp-gateway-registry)
[INFO] ==========================================
[INFO] Building registry...
[+] Building 480.2s (20/20) FINISHED
 => [internal] load build definition
 => [internal] load .dockerignore
 => [internal] load metadata for docker.io/library/python:3.12-slim
 ...
[INFO] Successfully built registry
[INFO] Pushing registry to ECR...
[INFO] Successfully pushed: 123456789012.dkr.ecr.us-east-1.amazonaws.com/mcp-gateway-registry:latest

...
[INFO] ==========================================
[INFO] Build Summary
[INFO] ==========================================
[INFO] Successfully processed 12/12 images
[INFO] Total build time: 28 minutes 15 seconds
```

### Updating Running Services

After pushing a new container image to ECR, trigger a deployment to update running ECS tasks.

**Service Deployment Mapping:**

| Service Name | ECS Cluster | Container Image | Typical Update Reason |
|--------------|-------------|-----------------|----------------------|
| `mcp-gateway-v2-registry` | `mcp-gateway-ecs-cluster` | `registry` | API changes, bug fixes |
| `mcp-gateway-v2-auth` | `mcp-gateway-ecs-cluster` | `auth_server` | Auth logic updates |
| `keycloak` | `keycloak` | `keycloak` | Custom Keycloak config |

**Update Commands:**

```bash
# Set region
export AWS_REGION=us-east-1

# ============================================================================
# UPDATE REGISTRY SERVICE
# ============================================================================
aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --force-new-deployment \
  --region $AWS_REGION \
  --output table

# ============================================================================
# UPDATE AUTH SERVER SERVICE
# ============================================================================
aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-auth \
  --force-new-deployment \
  --region $AWS_REGION \
  --output table

# ============================================================================
# UPDATE KEYCLOAK SERVICE
# ============================================================================
aws ecs update-service \
  --cluster keycloak \
  --service keycloak \
  --force-new-deployment \
  --region $AWS_REGION \
  --output table
```

**What `--force-new-deployment` does:**
1. Stops existing tasks gracefully (30 second drain period)
2. Pulls latest image from ECR (even if tag is same)
3. Starts new tasks with new container
4. Waits for health checks to pass
5. Continues rolling deployment until all tasks updated

**Monitor Deployment Progress:**

```bash
# Method 1: Watch service status (auto-refreshing)
watch -n 5 'aws ecs describe-services \
  --cluster mcp-gateway-ecs-cluster \
  --services mcp-gateway-v2-registry \
  --region us-east-1 \
  --query "services[0].{Running:runningCount,Desired:desiredCount,Status:status,Deployment:deployments[0].status}" \
  --output table'

# Exit watch with Ctrl+C when Running = Desired

# Method 2: Check deployment status once
aws ecs describe-services \
  --cluster mcp-gateway-ecs-cluster \
  --services mcp-gateway-v2-registry \
  --region $AWS_REGION \
  --query 'services[0].{ServiceName:serviceName,Status:status,RunningCount:runningCount,DesiredCount:desiredCount,Deployments:deployments[*].{Status:status,Running:runningCount,Desired:desiredCount,TaskDef:taskDefinition}}' \
  --output json

# Method 3: View recent service events
aws ecs describe-services \
  --cluster mcp-gateway-ecs-cluster \
  --services mcp-gateway-v2-registry \
  --region $AWS_REGION \
  --query 'services[0].events[:10]' \
  --output table

# Method 4: List all running tasks
aws ecs list-tasks \
  --cluster mcp-gateway-ecs-cluster \
  --service-name mcp-gateway-v2-registry \
  --region $AWS_REGION

# Method 5: Get specific task details
aws ecs describe-tasks \
  --cluster mcp-gateway-ecs-cluster \
  --tasks TASK_ARN \
  --region $AWS_REGION \
  --query 'tasks[0].{TaskArn:taskArn,Status:lastStatus,Health:healthStatus,StartedAt:startedAt,Containers:containers[*].{Name:name,Status:lastStatus,Health:healthStatus}}'
```

### Complete Developer Workflow

**Scenario:** You fixed a bug in the Registry API and want to deploy it.

```bash
# ============================================================================
# STEP 1: Make Code Changes
# ============================================================================
cd /path/to/mcp-gateway-registry
vim registry/api/server_routes.py  # Fix bug

# ============================================================================
# STEP 2: Test Locally (Optional but Recommended)
# ============================================================================
# Build image locally
docker build -f docker/Dockerfile.registry -t registry:test .

# Run locally
docker run -p 7860:7860 registry:test

# Test endpoint
curl http://localhost:7860/health

# Stop test container
docker stop $(docker ps -q --filter ancestor=registry:test)

# ============================================================================
# STEP 3: Build and Push to ECR
# ============================================================================
export AWS_REGION=us-east-1
make build-push IMAGE=registry

# Verify push succeeded
aws ecr describe-images \
  --repository-name mcp-gateway-registry \
  --region $AWS_REGION \
  --query 'imageDetails[0].{Tags:imageTags,Pushed:imagePushedAt,Size:imageSizeInBytes}'

# ============================================================================
# STEP 4: Deploy to ECS
# ============================================================================
aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --force-new-deployment \
  --region $AWS_REGION

# ============================================================================
# STEP 5: Monitor Deployment
# ============================================================================
# Watch logs in real-time
cd terraform/aws-ecs
./scripts/view-cloudwatch-logs.sh --component registry --follow

# In another terminal, check service status
watch -n 10 'aws ecs describe-services \
  --cluster mcp-gateway-ecs-cluster \
  --services mcp-gateway-v2-registry \
  --region us-east-1 \
  --query "services[0].{Running:runningCount,Desired:desiredCount}" \
  --output table'

# ============================================================================
# STEP 6: Verify Deployment
# ============================================================================
# Test health endpoint
curl https://registry.us-east-1.your.domain/health

# Test your specific fix
curl https://registry.us-east-1.your.domain/api/your-fixed-endpoint

# Check for errors in logs (last 5 minutes)
./scripts/view-cloudwatch-logs.sh --component registry --minutes 5 --filter "ERROR"
```

### Deployment Troubleshooting

**Deployment stuck / tasks not starting:**
```bash
# Check service events for errors
aws ecs describe-services \
  --cluster mcp-gateway-ecs-cluster \
  --services mcp-gateway-v2-registry \
  --region $AWS_REGION \
  --query 'services[0].events[:15]' \
  --output table

# Common issues:
# - "Ecouldn't pull image" -> ECR permissions or wrong image URI
# - "CannotPullContainerError" -> Image doesn't exist in ECR
# - "Task failed container health checks" -> Application not starting correctly
# - "Service is unable to place a task" -> No capacity or resource constraints

# Check stopped tasks for failure reason
aws ecs list-tasks \
  --cluster mcp-gateway-ecs-cluster \
  --service-name mcp-gateway-v2-registry \
  --desired-status STOPPED \
  --region $AWS_REGION \
  --max-items 5

aws ecs describe-tasks \
  --cluster mcp-gateway-ecs-cluster \
  --tasks STOPPED_TASK_ARN \
  --region $AWS_REGION \
  --query 'tasks[0].{StoppedReason:stoppedReason,Containers:containers[*].{Name:name,Reason:reason,ExitCode:exitCode}}'
```

### Rolling Back Deployments

**Quick rollback to previous working version:**

```bash
# Method 1: Rollback to specific task definition revision
# List recent task definitions
aws ecs list-task-definitions \
  --family-prefix mcp-gateway-registry \
  --sort DESC \
  --max-items 10 \
  --region $AWS_REGION

# Deploy specific (previous) revision
aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --task-definition mcp-gateway-registry:42 \
  --region $AWS_REGION

# Method 2: Redeploy current task definition (if image was bad)
# First, rebuild and push fixed image with same tag
make build-push IMAGE=registry

# Then force new deployment to pull updated image
aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --force-new-deployment \
  --region $AWS_REGION

# Method 3: Emergency rollback script
cat > rollback-registry.sh << 'EOF'
#!/bin/bash
set -e
export AWS_REGION=us-east-1

echo "Rolling back registry service..."
PREVIOUS_REVISION=$(aws ecs describe-services \
  --cluster mcp-gateway-ecs-cluster \
  --services mcp-gateway-v2-registry \
  --region $AWS_REGION \
  --query 'services[0].deployments[1].taskDefinition' \
  --output text)

aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --task-definition $PREVIOUS_REVISION \
  --region $AWS_REGION

echo "Rollback initiated to: $PREVIOUS_REVISION"
EOF

chmod +x rollback-registry.sh
./rollback-registry.sh
```

### Blue/Green Deployment Strategy

For zero-downtime updates with instant rollback capability:

```bash
# 1. Update service with new task definition (auto blue/green)
aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --force-new-deployment \
  --region $AWS_REGION

# ECS automatically performs rolling update:
# - Starts new task (green)
# - Waits for health check
# - Drains old task (blue)
# - Removes old task
# - Repeats for remaining tasks

# 2. Monitor health during deployment
watch -n 5 'curl -s https://registry.us-east-1.your.domain/health | jq .'

# 3. If issues detected, rollback immediately
aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --task-definition <PREVIOUS_REVISION> \
  --region $AWS_REGION
```
