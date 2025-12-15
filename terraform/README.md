# MCP Gateway Registry Terraform Configurations

This directory contains Terraform infrastructure-as-code for deploying the MCP Gateway Registry on AWS.

## Available Deployments

### AWS ECS (Available)

Deploy the MCP Gateway Registry on AWS ECS using Fargate for serverless container orchestration.

**Location:** [`aws-ecs/`](aws-ecs/)

**Features:**
- Serverless containers with AWS Fargate
- Application Load Balancer (ALB) for traffic routing
- Amazon EFS for persistent storage
- AWS Secrets Manager for credential management
- Amazon ECR for container images
- CloudWatch for logging and monitoring
- Auto-scaling ECS services
- VPC with public/private subnets
- NAT Gateway for outbound connectivity

**Quick Start:**
```bash
cd terraform/aws-ecs
terraform init
terraform plan
terraform apply
```

See [`aws-ecs/README.md`](aws-ecs/README.md) for detailed instructions.

### AWS EKS (Recommended: Use ai-on-eks)

For Kubernetes deployments on Amazon EKS, we recommend using the Helm charts with an EKS cluster provisioned via [AWS AI/ML on Amazon EKS](https://github.com/awslabs/ai-on-eks).

**Why not Terraform for EKS here?**

The [awslabs/ai-on-eks](https://github.com/awslabs/ai-on-eks) project provides production-ready, battle-tested Terraform blueprints specifically designed for AI/ML workloads on EKS. Rather than duplicate this excellent work, we recommend:

1. **Provision EKS cluster** using ai-on-eks blueprints:
   ```bash
   git clone https://github.com/awslabs/ai-on-eks.git
# Until https://github.com/awslabs/ai-on-eks/pull/232 is merged, the custom stack can be used

cd ai-on-eks/infra/custom
./install.sh
   ```

2. **Deploy MCP Gateway Registry** using Helm charts:
   ```bash
   cd /path/to/mcp-gateway-registry/charts/mcp-gateway-registry-stack
   helm dependency build && helm dependency update
   helm install mcp-gateway-registry . -n mcp-gateway --create-namespace --set global.domain "YOUR DOMAIN" --set global.secretKey "CHANGEME"
   ```

This approach provides:
- GPU support for AI/ML workloads
- Karpenter for efficient auto-scaling
- EKS-optimized AMIs
- Security best practices
- Observability with Prometheus/Grafana
- ArgoCD for GitOps workflows
- Proven blueprints maintained by AWS Labs

**Reference:**
- ai-on-eks Repository: https://github.com/awslabs/ai-on-eks
- ai-on-eks Blueprints: https://github.com/awslabs/ai-on-eks/tree/main/blueprints
- MCP Gateway Helm Charts: [`/charts`](../charts/)

## Deployment Comparison

| Feature | AWS ECS (Terraform) | AWS EKS (ai-on-eks + Helm) |
|---------|---------------------|---------------------------|
| **Container Orchestration** | AWS Fargate | Kubernetes (EKS) |
| **Provisioning Tool** | Terraform (this repo) | Terraform (ai-on-eks) |
| **Application Deployment** | Terraform | Helm charts (this repo) |
| **Infrastructure Complexity** | Lower | Higher |
| **Kubernetes Knowledge** | Not required | Required |
| **Multi-cloud Portability** | No | Yes |
| **GPU Support** | Limited | Excellent (via ai-on-eks) |
| **Auto-scaling** | ECS Service Scaling | Karpenter + HPA |
| **Cost Model** | Pay-per-task | Cluster + pods |
| **Best For** | AWS-native, simpler deployments | Advanced K8s users, multi-cloud |

## Choosing Your Deployment Method

### Use AWS ECS (Terraform) if:
- You want the simplest AWS-native deployment
- Your team is familiar with AWS services but not Kubernetes
- You prefer managed infrastructure with less operational overhead
- You don't need Kubernetes-specific features
- You're already using ECS in your organization

### Use AWS EKS (ai-on-eks + Helm) if:
- You need Kubernetes for portability or multi-cloud strategy
- Your team has Kubernetes expertise
- You require GPU support for AI/ML workloads
- You want to leverage the broader Kubernetes ecosystem
- You need advanced scaling with Karpenter
- You're already using Kubernetes in your organization

## Directory Structure

```
terraform/
├── README.md                 # This file
└── aws-ecs/                  # ECS deployment with Terraform
    ├── README.md             # ECS-specific documentation
    ├── main.tf               # Main ECS configuration
    ├── modules/              # ECS Terraform modules
    └── terraform.tfvars.example
```

For Kubernetes deployments, see the [`/charts`](../charts/) directory.

## Additional Resources

- AWS ECS Documentation: https://docs.aws.amazon.com/ecs/
- AWS EKS Documentation: https://docs.aws.amazon.com/eks/
- AI on EKS: https://github.com/awslabs/ai-on-eks
- Terraform Registry: https://registry.terraform.io/
- Helm Documentation: https://helm.sh/docs/
