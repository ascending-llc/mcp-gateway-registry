#!/bin/bash

# AgentCore Live Deployment Script
#
# Deploys A2A agents to AWS using AgentCore CLI with custom Dockerfiles.
# - Builds locally with Docker, pushes to ECR, deploys to AgentCore Runtime
# - Uses container mode with custom Dockerfiles for full control
#
# File Management:
# During deployment, the following files are copied from agents-strands root into each agent directory:
#   - pyproject.toml, uv.lock -> src/<agent>/.tmp/ (for dependency installation in Docker)
#   - .dockerignore -> src/<agent>/ (to optimize Docker build context)
# These files are automatically cleaned up after deployment completes.


set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 AgentCore Live Deployment Script${NC}"
echo "======================================"

# Check if AWS credentials are set
echo -e "\n${BLUE}🔐 Validating AWS credentials...${NC}"

if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo -e "${RED}❌ Error: AWS credentials not found in environment variables${NC}"
    echo "Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
    exit 1
fi

# Validate credentials are not expired by making a simple AWS call
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ Error: AWS credentials are invalid or expired${NC}"
    echo "Please refresh your credentials and try again"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}

echo -e "${GREEN}✅ AWS credentials validated${NC}"
echo -e "   Account: ${ACCOUNT_ID}"
echo -e "   Region: ${REGION}"

# Check if agentcore CLI is installed
echo -e "\n${BLUE}🔍 Checking AgentCore CLI...${NC}"
if ! command -v agentcore &> /dev/null; then
    echo -e "${RED}❌ Error: agentcore CLI not found${NC}"
    echo "Please install it with: pip install bedrock-agentcore-starter-toolkit"
    exit 1
fi
echo -e "${GREEN}✅ AgentCore CLI found${NC}"

# Agent configurations
FLIGHT_AGENT_NAME="flight_booking_agent"
FLIGHT_AGENT_ENTRYPOINT="src/flight-booking-agent/agent.py"

TRAVEL_AGENT_NAME="travel_assistant_agent"
TRAVEL_AGENT_ENTRYPOINT="src/travel-assistant-agent/agent.py"

# Function to configure and deploy an agent
deploy_agent() {
    local agent_name=$1
    local entrypoint=$2
    
    echo -e "\n${BLUE}📦 Deploying ${agent_name}...${NC}"
    echo "   Entrypoint: ${entrypoint}"
    echo "   Protocol: A2A"
    echo "   Deployment: container (custom Dockerfile in agent directory)"
    echo "   Database: /app/data/bookings.db"
    echo "   Build: Local Docker build, then push to ECR"
    
    # Get the entrypoint directory where our Dockerfile lives
    local entrypoint_dir=$(dirname "${entrypoint}")
    
    # Check if agent is already configured
    if agentcore configure list 2>/dev/null | grep -q "${agent_name}"; then
        echo -e "${YELLOW}⚠️  Agent ${agent_name} already configured, will update${NC}"
    else
        echo -e "${BLUE}🔧 Configuring ${agent_name}...${NC}"
        agentcore configure \
            --entrypoint "${entrypoint}" \
            --name "${agent_name}" \
            --region "${REGION}" \
            --protocol A2A \
            --deployment-type container \
            --non-interactive \
            --disable-memory
    fi
    
    # Copy files from agents-strands root into agent directory for Docker build
    # Files copied:
    #   - pyproject.toml, uv.lock -> ${entrypoint_dir}/.tmp/ (for dependency installation)
    #   - .dockerignore -> ${entrypoint_dir}/ (to optimize Docker build context)
    # These files are cleaned up after deployment completes
    echo -e "${BLUE}   Copying dependency files to .tmp directory${NC}"
    mkdir -p "${entrypoint_dir}/.tmp"
    cp pyproject.toml uv.lock "${entrypoint_dir}/.tmp/"
    
    # Copy .dockerignore to agent directory if it doesn't exist
    if [ ! -f "${entrypoint_dir}/.dockerignore" ] && [ -f ".dockerignore" ]; then
        echo -e "${BLUE}   Copying .dockerignore to agent directory${NC}"
        cp .dockerignore "${entrypoint_dir}/.dockerignore"
    fi
    
    # Replace AgentCore's generated Dockerfile with our custom one
    local agentcore_dockerfile=".bedrock_agentcore/${agent_name}/Dockerfile"
    if [ -f "${entrypoint_dir}/Dockerfile" ]; then
        echo -e "${BLUE}   Replacing generated Dockerfile with custom one${NC}"
        cp "${entrypoint_dir}/Dockerfile" "${agentcore_dockerfile}"
    fi
    
    # Launch with local build (builds locally with Docker, then pushes to ECR)
    echo -e "${BLUE}🚀 Launching ${agent_name} (building locally with Docker)...${NC}"
    agentcore launch \
        --agent "${agent_name}" \
        --local-build \
        --auto-update-on-conflict
    
    # Clean up files copied from agents-strands root
    # Removes:
    #   - ${entrypoint_dir}/.tmp/ directory (pyproject.toml, uv.lock)
    #   - ${entrypoint_dir}/.dockerignore (if it matches root .dockerignore)
    echo -e "${BLUE}   Cleaning up temporary files${NC}"
    rm -rf "${entrypoint_dir}/.tmp"
    
    # Remove .dockerignore if we copied it (check if it matches root version)
    if [ -f "${entrypoint_dir}/.dockerignore" ] && [ -f ".dockerignore" ]; then
        if cmp -s "${entrypoint_dir}/.dockerignore" ".dockerignore"; then
            rm "${entrypoint_dir}/.dockerignore"
        fi
    fi
    
    echo -e "${GREEN}✅ ${agent_name} deployed successfully${NC}"
}

# Deploy both agents
echo -e "\n${BLUE}=====================================${NC}"
echo -e "${BLUE}Starting deployment of agents...${NC}"
echo -e "${BLUE}=====================================${NC}"

deploy_agent "${FLIGHT_AGENT_NAME}" "${FLIGHT_AGENT_ENTRYPOINT}"
deploy_agent "${TRAVEL_AGENT_NAME}" "${TRAVEL_AGENT_ENTRYPOINT}"

# Show status of deployed agents
echo -e "\n${BLUE}=====================================${NC}"
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${BLUE}=====================================${NC}"

echo -e "\n${BLUE}📊 Agent Status:${NC}"
echo -e "\n${YELLOW}Flight Booking Agent:${NC}"
agentcore status --agent "${FLIGHT_AGENT_NAME}"

echo -e "\n${YELLOW}Travel Assistant Agent:${NC}"
agentcore status --agent "${TRAVEL_AGENT_NAME}"

echo -e "\n${BLUE}💡 Next Steps:${NC}"
echo "   • Test agents: agentcore invoke '{\"prompt\": \"Hello\"}' --agent <agent-name>"
echo "   • View logs: Check CloudWatch logs (shown in status above)"
echo "   • Update agents: Run this script again to deploy changes"
echo "   • Destroy agents: agentcore destroy --agent <agent-name>"
