.PHONY: help test test-unit test-integration test-e2e test-fast test-coverage test-auth test-servers test-search test-health test-core install-dev lint format check-deps clean build-keycloak push-keycloak build-and-push-keycloak deploy-keycloak update-keycloak save-outputs view-logs view-logs-keycloak view-logs-registry view-logs-auth view-logs-follow list-images build push build-push generate-manifest validate-config publish-dockerhub publish-dockerhub-component publish-dockerhub-version publish-dockerhub-no-mirror publish-local compose-up-agents compose-down-agents compose-logs-agents build-agents push-agents

# Default target
help:
	@echo "🧪 MCP Registry Testing Commands"
	@echo ""
	@echo "Setup:"
	@echo "  install-dev     Install development dependencies"
	@echo "  check-deps      Check if test dependencies are installed"
	@echo ""
	@echo "Testing:"
	@echo "  test            Run full test suite with coverage"
	@echo "  test-unit       Run unit tests only"
	@echo "  test-integration Run integration tests only" 
	@echo "  test-e2e        Run end-to-end tests only"
	@echo "  test-fast       Run fast tests (exclude slow tests)"
	@echo "  test-coverage   Generate coverage reports"
	@echo ""
	@echo "Domain Testing:"
	@echo "  test-auth       Run authentication domain tests"
	@echo "  test-servers    Run server management domain tests"
	@echo "  test-search     Run search domain tests"
	@echo "  test-health     Run health monitoring domain tests"
	@echo "  test-core       Run core infrastructure tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint            Run linting checks"
	@echo "  format          Format code"
	@echo "  clean           Clean up test artifacts"
	@echo ""
	@echo "Keycloak Build & Deploy:"
	@echo "  build-keycloak              Build Keycloak Docker image locally"
	@echo "  build-and-push-keycloak     Build and push to ECR"
	@echo "  deploy-keycloak             Update ECS service (after push)"
	@echo "  update-keycloak             Build, push, and deploy in one command"
	@echo ""
	@echo "Infrastructure Documentation:"
	@echo "  save-outputs                Save Terraform outputs as JSON"
	@echo ""
	@echo "CloudWatch Logs Viewing:"
	@echo "  view-logs                   View logs from all components (last 30 min)"
	@echo "  view-logs-keycloak          View Keycloak logs (last 30 min)"
	@echo "  view-logs-registry          View Registry logs (last 30 min)"
	@echo "  view-logs-auth              View Auth Server logs (last 30 min)"
	@echo "  view-logs-follow            Follow logs in real-time for all components"
	@echo ""
	@echo "Container Build & Registry:"
	@echo "  list-images                 List all configured container images"
	@echo "  build                       Build all images locally"
	@echo "  build IMAGE=name            Build specific image (e.g., IMAGE=registry)"
	@echo "  push                        Push all images to ECR"
	@echo "  push IMAGE=name             Push specific image to ECR"
	@echo "  build-push                  Build and push all images"
	@echo "  build-push IMAGE=name       Build and push specific image"
	@echo "  generate-manifest           Generate image-manifest.json for Terraform"
	@echo "  validate-config             Validate build-config.yaml syntax"
	@echo ""
	@echo "DockerHub Publishing:"
	@echo "  publish-dockerhub           Publish all images to DockerHub"
	@echo "  publish-dockerhub-component Publish specific component (COMPONENT=name)"
	@echo "  publish-dockerhub-version   Publish with version tag (VERSION=v1.0.0)"
	@echo "  publish-dockerhub-no-mirror Publish without external images"
	@echo "  publish-local               Build locally without pushing"
	@echo ""
	@echo "Local A2A Agent Development:"
	@echo "  compose-up-agents           Start A2A agents with docker-compose"
	@echo "  compose-down-agents         Stop A2A agents"
	@echo "  compose-logs-agents         Follow A2A agent logs in real-time"
	@echo "  build-agents                Build both A2A agent images locally"
	@echo "  push-agents                 Push both A2A agent images to ECR"

# Installation
install-dev:
	@echo "📦 Installing development dependencies..."
	pip install -e .[dev]

check-deps:
	@python scripts/test.py check

# Full test suite
test:
	@python scripts/test.py full

# Test types
test-unit:
	@python scripts/test.py unit

test-integration:
	@python scripts/test.py integration

test-e2e:
	@python scripts/test.py e2e

test-fast:
	@python scripts/test.py fast

test-coverage:
	@python scripts/test.py coverage

# Domain-specific tests
test-auth:
	@python scripts/test.py auth

test-servers:
	@python scripts/test.py servers

test-search:
	@python scripts/test.py search

test-health:
	@python scripts/test.py health

test-core:
	@python scripts/test.py core

# Code quality
lint:
	@echo "🔍 Running linting checks..."
	@python -m bandit -r registry/ -f json || true
	@echo "✅ Linting complete"

format:
	@echo "🎨 Formatting code..."
	@python -m black registry/ tests/ --diff --color
	@echo "✅ Code formatting complete"

# Cleanup
clean:
	@echo "🧹 Cleaning up test artifacts..."
	@rm -rf htmlcov/
	@rm -rf tests/reports/
	@rm -rf .coverage
	@rm -rf coverage.xml
	@rm -rf .pytest_cache/
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Cleanup complete"

# Development workflow
dev-test: clean install-dev test-fast
	@echo "🚀 Development test cycle complete!"

# CI/CD workflow
ci-test: clean check-deps test test-coverage
	@echo "🏗️ CI/CD test cycle complete!"

# Keycloak Build & Deployment
# Variables
AWS_REGION ?= us-west-2
AWS_PROFILE ?= default
IMAGE_TAG ?= latest

build-keycloak:
	@echo "🐋 Building Keycloak Docker image..."
	@$(MAKE) build IMAGE=keycloak
	@echo "✅ Image built: keycloak:$(IMAGE_TAG)"

build-and-push-keycloak:
	@echo "📦 Building and pushing Keycloak to ECR..."
	@$(MAKE) build-push IMAGE=keycloak
	@echo "✅ Keycloak image built and pushed successfully"

deploy-keycloak:
	@echo "🚀 Deploying Keycloak ECS service..."
	aws ecs update-service \
		--cluster keycloak \
		--service keycloak \
		--force-new-deployment \
		--region $(AWS_REGION) \
		--profile $(AWS_PROFILE) \
		--output table
	@echo "✅ ECS service update initiated"

update-keycloak: build-and-push-keycloak deploy-keycloak
	@echo ""
	@echo "✅ Keycloak update complete!"
	@echo ""
	@echo "Service URLs:"
	@echo "  Admin Console: https://kc.mycorp.click/admin"
	@echo "  Service URL:   https://kc.mycorp.click"
	@echo ""
	@echo "Monitor deployment:"
	@echo "  aws ecs describe-services --cluster keycloak --services keycloak --region $(AWS_REGION) --query 'services[0].[serviceName,status,runningCount,desiredCount]' --output table"

save-outputs:
	@echo "💾 Saving Terraform outputs as JSON..."
	./terraform/aws-ecs/scripts/save-terraform-outputs.sh
	@echo ""
	@echo "✅ Outputs saved to terraform/aws-ecs/terraform-outputs.json"

view-logs:
	@echo "📋 Viewing CloudWatch logs from last 30 minutes for all components..."
	./terraform/aws-ecs/scripts/view-cloudwatch-logs.sh

view-logs-keycloak:
	@echo "📋 Viewing Keycloak CloudWatch logs from last 30 minutes..."
	./terraform/aws-ecs/scripts/view-cloudwatch-logs.sh --component keycloak --minutes 30

view-logs-registry:
	@echo "📋 Viewing Registry CloudWatch logs from last 30 minutes..."
	./terraform/aws-ecs/scripts/view-cloudwatch-logs.sh --component registry --minutes 30

view-logs-auth:
	@echo "📋 Viewing Auth Server CloudWatch logs from last 30 minutes..."
	./terraform/aws-ecs/scripts/view-cloudwatch-logs.sh --component auth-server --minutes 30

view-logs-follow:
	@echo "📋 Following CloudWatch logs in real-time for all components..."
	./terraform/aws-ecs/scripts/view-cloudwatch-logs.sh --follow

# ========================================
# Unified Container Build System
# ========================================

list-images:
	@./scripts/generate-image-manifest.sh --list

generate-manifest:
	@./scripts/generate-image-manifest.sh

validate-config:
	@python3 -c "import yaml; yaml.safe_load(open('build-config.yaml'))" && echo "Config is valid!"

build:
	@$(if $(IMAGE),IMAGE=$(IMAGE),) ./scripts/build-images.sh build

push:
	@$(if $(IMAGE),IMAGE=$(IMAGE),) ./scripts/build-images.sh push

build-push:
	@$(if $(IMAGE),IMAGE=$(IMAGE),) ./scripts/build-images.sh build-push

# ========================================
# DockerHub Publishing
# ========================================

publish-dockerhub:
	@echo "Publishing all images to DockerHub..."
	./scripts/publish_containers.sh --dockerhub

publish-dockerhub-component:
	@echo "Publishing $(COMPONENT) to DockerHub..."
	./scripts/publish_containers.sh --dockerhub --component $(COMPONENT)

publish-dockerhub-version:
	@echo "Publishing all images to DockerHub with version $(VERSION)..."
	./scripts/publish_containers.sh --dockerhub --version $(VERSION)

publish-dockerhub-no-mirror:
	@echo "Publishing all images to DockerHub (skipping external images)..."
	./scripts/publish_containers.sh --dockerhub --skip-mirror

publish-local:
	@echo "Building all images locally (no push)..."
	./scripts/publish_containers.sh --local

# ========================================
# Local A2A Agent Development
# ========================================

compose-up-agents:
	@echo "Starting A2A agents with docker-compose..."
	cd agents/a2a && docker-compose -f docker-compose.local.yml up -d
	@echo "Agents started:"
	@echo "  Flight Booking Agent: http://localhost:9002/ping"
	@echo "  Travel Assistant Agent: http://localhost:9001/ping"

compose-down-agents:
	@echo "Stopping A2A agents..."
	cd agents/a2a && docker-compose -f docker-compose.local.yml down

compose-logs-agents:
	@echo "Following A2A agent logs..."
	cd agents/a2a && docker-compose -f docker-compose.local.yml logs -f

build-agents:
	@echo "Building A2A agent images locally..."
	@$(MAKE) build IMAGE=flight_booking_agent
	@$(MAKE) build IMAGE=travel_assistant_agent
	@echo "Both agents built successfully"

push-agents:
	@echo "Pushing A2A agent images to ECR..."
	@$(MAKE) push IMAGE=flight_booking_agent
	@$(MAKE) push IMAGE=travel_assistant_agent
	@echo "Both agents pushed to ECR"
