# MCP Gateway Registry Helm Charts

This directory contains Helm charts for deploying the MCP Gateway Registry stack on Kubernetes.

## Prerequisites

### EKS Cluster Setup

For deploying on Amazon EKS, we recommend using the [AWS AI/ML on Amazon EKS](https://github.com/awslabs/ai-on-eks) blueprints to provision a production-ready EKS cluster with GPU support, autoscaling, and AI/ML optimizations.

**Quick Start with AI on EKS:**

```bash
# Clone the AI on EKS repository
git clone https://github.com/awslabs/ai-on-eks.git
cd ai-on-eks

# Until https://github.com/awslabs/ai-on-eks/pull/232 is merged, the custom stack can be used

cd infra/custom
./install.sh
```

Once your EKS cluster is provisioned, return to this directory to deploy the MCP Gateway Registry using the Helm charts.

### Required Components

- Kubernetes cluster (EKS, GKE, AKS, or self-managed)
- `helm` CLI installed (v3.0+)
- `kubectl` configured to access your cluster
- Ingress controller (ALB, NGINX, or Traefik)
- DNS configuration for your domain
- SSL/TLS certificates (optional but recommended)

## Charts Overview

### Individual Charts

- **auth-server**: Authentication service for the MCP Gateway
- **registry**: MCP server registry service
- **keycloak-configure**: Job to configure Keycloak realms and clients

### Stack Chart

- **mcp-gateway-registry-stack**: Complete stack deployment including Keycloak, auth-server, registry, and configuration

## Improved Values Structure

The values files have been standardized with the following structure:

### Global Configuration

```yaml
global:
  image:
    repository: mcpgateway/service-name
    tag: v1.0.7
    pullPolicy: IfNotPresent
```

### Application Configuration

```yaml
app:
  name: service-name
  replicas: 1
  externalUrl: http://localhost:8080
  secretKey: your-secret-key
```

### Service Configuration

```yaml
service:
  type: ClusterIP
  port: 8080
  annotations: { }
```

### Resources

```yaml
resources:
  requests:
    cpu: 1
    memory: 1Gi
  limits:
    cpu: 2
    memory: 2Gi
```

### Ingress

```yaml
ingress:
  enabled: false
  className: alb
  hostname: ""
  annotations: { }
  tls: false
```

## Key Improvements

1. **Consistent Structure**: All charts now follow the same values organization
2. **Standardized Naming**: Unified naming conventions across all charts
3. **Reduced Duplication**: Eliminated redundant resource definitions
4. **Better Defaults**: Sensible default values for development and production
5. **Clean Templates**: Updated all templates to use the new values structure
6. **Clear Documentation**: Inline comments explaining configuration options

## Usage

### Deploy Individual Services

```bash
helm install auth-server ./charts/auth-server
helm install registry ./charts/registry
```

### Deploy Complete Stack

```bash
# Option 1: Update values.yaml file directly
# Edit charts/mcp-gateway-registry-stack/values.yaml and change global.domain

# Option 2: Override via command line
helm install mcp-stack ./charts/mcp-gateway-registry-stack \
  --set global.domain=yourdomain.com \
  --set global.secretKey=your-production-secret
```

## Configuration Notes

- **Domain**: The stack chart uses the domain from `global.domain` and applies it to all subcharts
- **Secret Keys**: Change default secret keys in production - they should match across all services
- **Resources**: Adjust CPU/memory based on your requirements
- **Ingress**: Configure ingress settings for your environment

### Domain Configuration

The stack chart uses `global.domain` to automatically configure all subdomains:

- `keycloak.{domain}` - Keycloak authentication server
- `auth-server.{domain}` - MCP Gateway auth server
- `mcpregistry.{domain}` - MCP server registry

**How it works:**

1. Set `global.domain` in the stack values file
2. All subchart templates reference `{{ .Values.global.domain }}` to build URLs and hostnames
3. Change the domain once and all services update automatically

**To change the domain:**

```bash
# Edit the values file
vim charts/mcp-gateway-registry-stack/values.yaml
# Change: global.domain: "your-new-domain.com"

# Or override via command line
helm upgrade mcp-stack ./charts/mcp-gateway-registry-stack \
  --set global.domain=your-new-domain.com
```

Make sure your DNS is configured to point these subdomains to your Kubernetes ingress.

## Deployment Options: Kubernetes vs AWS ECS

This project supports two deployment methods:

### 1. Kubernetes Deployment (This Directory)

Deploy the MCP Gateway Registry on any Kubernetes cluster using Helm charts. Ideal for:
- Multi-cloud deployments (AWS EKS, Google GKE, Azure AKS)
- On-premises Kubernetes clusters
- Organizations with existing Kubernetes infrastructure
- Scenarios requiring portability and vendor neutrality

**Location:** `/charts` directory (this location)

**Tools:** Helm charts, Kubernetes manifests

### 2. AWS ECS Deployment (Terraform)

Deploy the MCP Gateway Registry on AWS ECS using Terraform for infrastructure-as-code. Ideal for:
- AWS-native deployments with full AWS integration
- Organizations using AWS Fargate for serverless containers
- Teams preferring Terraform for infrastructure management
- Deployments requiring tight AWS service integration (ALB, ECR, EFS, Secrets Manager)

**Location:** `/terraform/aws-ecs` directory

**Tools:** Terraform modules, AWS ECS task definitions, AWS Fargate

### Choosing Between Kubernetes and ECS

| Feature | Kubernetes (Helm) | AWS ECS (Terraform) |
|---------|------------------|---------------------|
| **Portability** | High - works on any K8s cluster | AWS-specific |
| **Multi-cloud** | Yes | No (AWS only) |
| **Complexity** | Moderate - requires K8s knowledge | Lower - managed by AWS |
| **Customization** | High - full K8s ecosystem | Moderate - AWS services |
| **Auto-scaling** | K8s HPA, Cluster Autoscaler | ECS Service Auto Scaling |
| **Cost** | Depends on cluster costs | Pay-per-task (Fargate) |
| **Tools** | kubectl, helm | AWS CLI, terraform |

**Note:** The Helm charts and Terraform configurations are separate deployment methods. Choose the one that best fits your infrastructure and team expertise.