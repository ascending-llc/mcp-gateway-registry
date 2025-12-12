# MCP Gateway Registry Scripts

This directory contains utility scripts for building, testing, and deploying MCP Gateway Registry services.

## Keycloak Build & Push Script

### Overview

The `build-and-push-keycloak.sh` script automates the process of building a Keycloak Docker image and pushing it to AWS ECR (Elastic Container Registry).

### Quick Start

```bash
# Build and push with defaults (latest tag to us-west-2)
./scripts/build-and-push-keycloak.sh

# Build and push with custom tag
./scripts/build-and-push-keycloak.sh --image-tag v24.0.1

# Build only (don't push)
./scripts/build-and-push-keycloak.sh --no-push
```

### Using with Make

```bash
# Build Keycloak image locally
make build-keycloak

# Build and push to ECR
make build-and-push-keycloak

# Deploy to ECS (after push)
make deploy-keycloak

# Complete workflow: build, push, and deploy
make update-keycloak

# With custom parameters
make build-and-push-keycloak AWS_REGION=us-east-1 IMAGE_TAG=v24.0.1
```

### Options

- `--aws-region REGION` - AWS region (default: us-west-2)
- `--image-tag TAG` - Image tag (default: latest)
- `--aws-profile PROFILE` - AWS profile (default: default)
- `--dockerfile PATH` - Dockerfile path (default: docker/keycloak/Dockerfile)
- `--build-context PATH` - Build context (default: docker/keycloak)
- `--no-push` - Build only, don't push to ECR
- `--help` - Show help message

### Prerequisites

- Docker installed and running
- AWS CLI installed and configured
- AWS credentials with ECR access
- Permission to push to ECR repository `keycloak`

### Features

- Color-coded output for easy readability
- Step-by-step progress tracking
- Error handling with clear error messages
- ECR login automation
- Image verification after push
- Helpful commands for manual deployment

### Workflow Example

```bash
# Build and push image
./scripts/build-and-push-keycloak.sh --image-tag v24.0.1

# Deploy to ECS
aws ecs update-service \
  --cluster keycloak \
  --service keycloak \
  --force-new-deployment \
  --region us-west-2

# Monitor deployment
aws ecs describe-services \
  --cluster keycloak \
  --services keycloak \
  --region us-west-2 \
  --query 'services[0].[serviceName,status,runningCount,desiredCount]' \
  --output table
```

### Troubleshooting

#### "Failed to get AWS account ID"
- Check AWS credentials: `aws sts get-caller-identity`
- Verify AWS profile: `aws configure list --profile <profile-name>`

#### "Failed to login to ECR"
- Verify ECR permissions in IAM
- Check if repository exists: `aws ecr describe-repositories --repository-names keycloak`

#### "Failed to build Docker image"
- Check Docker is running: `docker ps`
- Verify Dockerfile exists: `ls -la docker/keycloak/Dockerfile`

### Further Reading

- [AWS ECR Documentation](https://docs.aws.amazon.com/ecr/)
- [Keycloak Docker Image](https://hub.docker.com/r/keycloak/keycloak)
- [ECS Service Updates](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/update-service.html)
