# Installation Guide

Complete installation instructions for the MCP Gateway & Registry on various platforms.

## Prerequisites

- **Node.js 16+**: Required for building the React frontend
- **Docker & Docker Compose**: Container runtime and orchestration
- **Amazon Cognito**: Identity provider for authentication (see [Cognito Setup Guide](cognito.md))
- **SSL Certificate**: Optional for HTTPS deployment in production

## Quick Start (5 Minutes)

```bash
# 1. Clone and setup
git clone https://github.com/agentic-community/mcp-gateway-registry.git
cd mcp-gateway-registry

# 2. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 3. Generate authentication credentials
./credentials-provider/generate_creds.sh

# 4. Install prerequisites
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt-get update && sudo apt-get install -y docker.io docker-compose

# 5. Deploy
./build_and_run.sh

# 6. Access registry
open http://localhost:7860
```

## Installation on Amazon EC2

### System Requirements

**Minimum (Development)**:
- EC2 Instance: `t3.large` (2 vCPU, 8GB RAM)
- Storage: 20GB SSD
- Network: Ports 80, 443, 7860, 8080 accessible

**Recommended (Production)**:
- EC2 Instance: `t3.2xlarge` (8 vCPU, 32GB RAM)  
- Storage: 50GB+ SSD
- Network: Multi-AZ with load balancer

### Detailed Setup Steps

1. **Create Local Directories**
   ```bash
   sudo mkdir -p /opt/mcp-gateway/{servers,auth_server,secrets}
   sudo cp -r registry/servers /opt/mcp-gateway/
   sudo cp auth_server/scopes.yml /opt/mcp-gateway/auth_server/
   sudo mkdir /var/log/mcp-gateway
   ```

2. **Configure Environment Variables**
   ```bash
   cp .env.example .env
   nano .env  # Configure required values
   ```

   **Required Configuration:**
   - `ADMIN_PASSWORD`: Secure admin password
   - `COGNITO_USER_POOL_ID`: AWS Cognito User Pool ID
   - `COGNITO_CLIENT_ID`: Cognito App Client ID
   - `COGNITO_CLIENT_SECRET`: Cognito App Client Secret
   - `AWS_REGION`: AWS region for Cognito

3. **Generate Authentication Credentials**
   ```bash
   # Configure OAuth credentials
   cp credentials-provider/oauth/.env.example credentials-provider/oauth/.env
   nano credentials-provider/oauth/.env
   
   # Generate tokens and client configurations
   ./credentials-provider/generate_creds.sh
   ```

4. **Install Dependencies**
   ```bash
   # Install uv (Python package manager)
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source $HOME/.local/bin/env
   uv venv --python 3.12 && source .venv/bin/activate
   
   # Install Docker
   sudo apt-get update
   sudo apt-get install --reinstall docker.io -y
   sudo apt-get install -y docker-compose
   sudo usermod -a -G docker $USER
   newgrp docker
   ```

5. **Deploy Services**
   ```bash
   ./build_and_run.sh
   ```

### HTTPS Configuration

For production deployments with SSL:

1. **Prepare SSL Certificates**
   ```bash
   sudo mkdir -p /home/ubuntu/ssl_data/{certs,private}
   # Copy certificate files:
   # - fullchain.pem → /home/ubuntu/ssl_data/certs/
   # - privkey.pem → /home/ubuntu/ssl_data/private/
   ```

2. **Configure Security Group**
   - Enable TCP port 443 for HTTPS access
   - Restrict access to authorized IP ranges

3. **Deploy with HTTPS**
   ```bash
   ./build_and_run.sh  # Automatically detects SSL certificates
   ```

## Installation on Amazon EKS

For production Kubernetes deployments, see the [EKS deployment guide](https://github.com/aws-samples/amazon-eks-machine-learning-with-terraform-and-kubeflow/tree/master/examples/agentic/mcp-gateway-microservices).

### Architecture Overview

```mermaid
graph TB
    subgraph "EKS Cluster"
        subgraph "Ingress"
            ALB[Application Load Balancer]
            IC[Ingress Controller]
        end
        
        subgraph "Application Pods"
            RP[Registry Pod]
            AS[Auth Server Pod]
            NG[Nginx Pod]
        end
        
        subgraph "MCP Servers"
            MS1[MCP Server 1]
            MS2[MCP Server 2]
            MSN[MCP Server N]
        end
    end
    
    subgraph "AWS Services"
        COG[Amazon Cognito]
        CW[CloudWatch]
        ECR[Amazon ECR]
    end
    
    ALB --> IC
    IC --> RP
    IC --> AS
    IC --> NG
    NG --> MS1
    NG --> MS2
    NG --> MSN
    AS --> COG
    RP --> CW
```

### Key Benefits of EKS Deployment

- **High Availability**: Multi-AZ pod distribution
- **Auto Scaling**: Horizontal pod autoscaling based on metrics
- **Service Mesh**: Istio integration for advanced traffic management
- **Observability**: Native integration with CloudWatch and Prometheus
- **Security**: Pod security policies and network policies

## Post-Installation

### Verify Installation

1. **Check Service Status**
   ```bash
   docker-compose ps
   docker-compose logs -f
   ```

2. **Test Web Interface**
   - Navigate to `http://localhost:7860`
   - Login with admin credentials
   - Verify MCP server health status

3. **Test Authentication**
   ```bash
   cd tests
   ./mcp_cmds.sh ping
   ```

### Configure AI Coding Assistants

1. **Generate Client Configurations**
   ```bash
   ./credentials-provider/generate_creds.sh
   ls .oauth-tokens/  # View generated configurations
   ```

2. **Setup VS Code**
   ```bash
   cp .oauth-tokens/vscode-mcp.json ~/.vscode/settings.json
   ```

3. **Setup Roo Code**
   ```bash
   cp .oauth-tokens/mcp.json ~/.vscode/mcp-settings.json
   ```

For detailed AI assistant setup, see [AI Coding Assistants Setup Guide](ai-coding-assistants-setup.md).

## Troubleshooting

### Common Issues

**Services won't start:**
```bash
# Check Docker daemon
sudo systemctl status docker

# Check environment variables
cat .env | grep -v SECRET

# View detailed logs
docker-compose logs --tail=50
```

**Authentication failures:**
```bash
# Verify Cognito configuration
aws cognito-idp describe-user-pool --user-pool-id YOUR_POOL_ID

# Test credential generation
cd credentials-provider && ./generate_creds.sh --verbose
```

**Network connectivity issues:**
```bash
# Check port availability
sudo netstat -tlnp | grep -E ':(80|443|7860|8080)'

# Test internal services
curl -v http://localhost:7860/health
```

For more troubleshooting help, see [Troubleshooting Guide](troubleshooting.md).

## Next Steps

- [Authentication Setup](auth.md) - Configure identity providers
- [AI Assistant Integration](ai-coding-assistants-setup.md) - Setup development tools
- [Production Deployment](production-deployment.md) - High availability configuration
- [API Reference](registry_api.md) - Programmatic management