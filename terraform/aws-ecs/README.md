# MCP Gateway Registry - AWS ECS Infrastructure

Production-grade infrastructure for the MCP Gateway Registry using AWS ECS Fargate, Aurora Serverless, and Keycloak authentication.

[![Infrastructure](https://img.shields.io/badge/infrastructure-terraform-purple)](https://www.terraform.io/)
[![AWS ECS](https://img.shields.io/badge/compute-ECS%20Fargate-orange)](https://aws.amazon.com/ecs/)
[![Database](https://img.shields.io/badge/database-Aurora%20Serverless%20v2-blue)](https://aws.amazon.com/rds/aurora/)

## Table of Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Post-Deployment](#post-deployment)
- [Operations and Maintenance](#operations-and-maintenance)
- [Troubleshooting](#troubleshooting)
- [Cost Optimization](#cost-optimization)
- [Security](#security-considerations)

## Architecture

![Architecture Diagram](img/architecture-ecs.png)

### Network Architecture

The infrastructure is deployed within a dedicated VPC spanning two availability zones for high availability. User traffic enters through Route 53 DNS resolution, directing requests to either the Main ALB (for Registry and Auth Server) or the Keycloak ALB (for identity management). AWS Certificate Manager provisions and manages SSL/TLS certificates for secure HTTPS communication.

### Application Load Balancers

**Main ALB (Internet-Facing)**
- Deployed in public subnets across both availability zones
- Routes traffic to Registry and Auth Server tasks
- SSL termination with ACM certificates
- Health checks to ensure task availability
- Target groups with dynamic port mapping

**Keycloak ALB (Private Subnets)***
- Internal load balancer for Keycloak services
- Isolated from direct internet access
- Dedicated SSL certificate for Keycloak domain
- Health check endpoint monitoring

*Currently deployed in public subnets for initial setup and management. Will be updated soon to use internal ALB with a bastion host in the VPC for secure Keycloak admin console access from within the VPC for management purposes.

### ECS Cluster and Services

The infrastructure runs on an ECS cluster with Fargate launch type, eliminating server management. Three primary service types run as containerized tasks:

**Registry Tasks** provide the core MCP server registry and discovery service. An auto-scaling group manages task count based on CPU and memory utilization, with tasks deployed across both availability zones for high availability. The registry retrieves secrets from AWS Secrets Manager for secure credential management, writes logs to CloudWatch Logs for centralized monitoring, and stores server metadata in Amazon EFS for persistent, shared access.

**Auth Server Tasks** handle OAuth2/OIDC authentication and authorization for the entire platform. These tasks manage user sessions and token validation, integrate with Keycloak for identity federation, and auto-scale based on demand. User data and session information is stored in Aurora PostgreSQL Serverless for reliable, scalable persistence.

**Keycloak Tasks** serve as the identity and access management layer, providing user authentication, single sign-on (SSO), and an admin console for user management. Keycloak connects to Aurora PostgreSQL for data persistence and stores configuration files in Amazon EFS for shared access across multiple task instances.

### Data Layer

**Amazon Aurora PostgreSQL Serverless v2** provides a fully managed, auto-scaling database with capacity ranging from 0.5 to 2 ACUs based on workload demands. The database stores user credentials, session data, and application state with automatic backups and point-in-time recovery capabilities. Deployed in a multi-AZ configuration for high availability, Aurora uses RDS Proxy for efficient connection pooling and management across ECS tasks.

**Amazon EFS (Elastic File System)** serves as shared persistent storage accessible from all ECS tasks across availability zones. EFS stores Keycloak configuration files, server metadata, and registry information that needs to be shared between multiple container instances. The file system automatically scales capacity and throughput based on storage requirements while maintaining high availability across multiple availability zones.

### Observability

**CloudWatch Logs** provides centralized logging for all ECS tasks with separate log groups created for each service to organize and isolate log streams. Log retention policies automatically expire old logs after a configurable period, and the logs integrate with CloudWatch Alarms to trigger alerts based on specific patterns or error rates found in the log data.

**CloudWatch Alarms** continuously monitor key infrastructure and application metrics including CPU and memory utilization across all ECS tasks, database connection counts and pool exhaustion, and HTTP error rates from the load balancers. When alarm thresholds are breached, notifications are sent through Amazon SNS to configured endpoints such as email, SMS, or other automated incident response systems.

**AWS Secrets Manager** provides secure storage and lifecycle management for sensitive credentials including Keycloak admin passwords, database connection strings, and API keys. ECS tasks retrieve these secrets at runtime as environment variables, eliminating the need to hardcode credentials in container images or configuration files. Secrets Manager supports automatic rotation of credentials on a scheduled basis to enhance security posture.

---

## Quick Start

**Total Time:** ~60-90 minutes for first deployment

> **IMPORTANT:** We recommend running this deployment from an EC2 instance with an IAM instance profile attached (preferably with `AdministratorAccess` policy). This eliminates credential management complexity and ensures all AWS CLI commands work seamlessly. For more restrictive IAM permissions, see [IAM Permissions](#iam-permissions).
>
> While these instructions should work on macOS or other development environments, you will need to have AWS credentials configured via `aws configure` or an AWS profile.

### Step 1: Prerequisites

#### Step 1.1: Domain Configuration

You need a domain with a Route53 hosted zone for SSL certificates and DNS routing. The domain can be registered with **any registrar** (GoDaddy, Namecheap, Google Domains, Cloudflare, etc.) - you just need to create a hosted zone in Route53 and point your domain's nameservers to Route53.

**Option A: Domain registered with Route53**

If you register your domain directly through Route53, a hosted zone is created automatically.

```bash
# Go to Route53 console > Registered domains > Register domain
# The hosted zone will be created automatically
```

**Option B: Domain registered with another provider (GoDaddy, Namecheap, Cloudflare, etc.)**

If your domain is registered elsewhere, create a hosted zone in Route53 and update your registrar's nameservers:

```bash
# 1. Create hosted zone in Route53
aws route53 create-hosted-zone \
  --name your.domain \
  --caller-reference $(date +%s)

# 2. Get the nameservers assigned by Route53
aws route53 list-hosted-zones --query 'HostedZones[?Name==`your.domain.`]'

# The output will show the hosted zone ID. Get the nameservers:
aws route53 get-hosted-zone --id <HOSTED_ZONE_ID> --query 'DelegationSet.NameServers'

# Example output:
# [
#     "ns-1234.awsdns-12.org",
#     "ns-567.awsdns-34.com",
#     "ns-890.awsdns-56.co.uk",
#     "ns-123.awsdns-78.net"
# ]

# 3. Update nameservers at your domain registrar:
#    - GoDaddy: My Products > DNS > Nameservers > Change > Enter my own nameservers
#    - Namecheap: Domain List > Manage > Nameservers > Custom DNS
#    - Cloudflare: DNS > Records > (remove from Cloudflare, use external nameservers)
#    - Google Domains: DNS > Custom name servers
#
#    Enter all 4 Route53 nameservers from step 2

# 4. Wait for DNS propagation (can take up to 48 hours, usually 15-30 minutes)
dig NS your.domain
```

When `use_regional_domains = true` (default), subdomains are automatically created based on region:
- Keycloak: `kc.{region}.{base_domain}` (e.g., `kc.us-east-1.your.domain`)
- Registry: `registry.{region}.{base_domain}` (e.g., `registry.us-east-1.your.domain`)

#### Step 1.2: Install Prerequisites

| Tool | Minimum Version | Installation |
|------|----------------|--------------|
| Terraform | >= 1.5.0 | [terraform.io/downloads](https://www.terraform.io/downloads) |
| AWS CLI | >= 2.0 | [docs.aws.amazon.com/cli](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| Docker | >= 20.10 | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| Docker Buildx | Latest | See below |
| Session Manager Plugin | Latest | See below |
| uv | Latest | [astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) |
| Python | >= 3.12 | Via uv or [python.org](https://www.python.org/downloads/) |

**Install Docker Buildx (Ubuntu/Debian):**

```bash
sudo apt-get update && sudo apt-get install -y docker-buildx-plugin
docker buildx version
```

**Install AWS Session Manager Plugin (Ubuntu/Debian):**

```bash
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" -o "/tmp/session-manager-plugin.deb"
sudo dpkg -i /tmp/session-manager-plugin.deb
session-manager-plugin --version
```

**Install uv (Python Package Manager):**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv --version
```

**Install Terraform (Ubuntu/Debian):**

```bash
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform
terraform version
```

**Setup Python environment:**

```bash
cd mcp-gateway-registry
uv sync
source .venv/bin/activate
aws --version
```

**Configure AWS CLI:**

```bash
aws configure
# AWS Access Key ID: YOUR_ACCESS_KEY
# AWS Secret Access Key: YOUR_SECRET_KEY
# Default region: us-east-1
# Default output format: json

# Verify credentials
aws sts get-caller-identity
```

### Step 2: Build and Push Container Images (~30 min)

```bash
# Set your target AWS region
export AWS_REGION=us-east-1

# cd to the directory where you cloned this repo

# Build and push all images
make build-push
```

### Step 3: Configure terraform.tfvars

```bash
cd terraform/aws-ecs
cp terraform.tfvars.example terraform.tfvars
```

**Edit the following mandatory parameters in `terraform.tfvars`:**

| Parameter | Description |
|-----------|-------------|
| `aws_region` | AWS region (must match where you pushed ECR images) |
| `base_domain` | Your Route53 domain (e.g., `YOUR.DOMAIN`) |
| `ingress_cidr_blocks` | IP addresses allowed to access the ALB |
| `keycloak_admin_password` | Keycloak admin password (min 12 chars) |
| `keycloak_database_password` | Database password (min 12 chars) |
| 7 ECR image URIs | Container image URIs with your account ID and region |

**Helper commands to get your configuration values:**

These commands have been tested on EC2 Ubuntu. If you are on a different development environment, you may need to edit the file manually if these commands don't work for you.

```bash
# Get your public IP address
curl -s ifconfig.me

# Get your AWS account ID
aws sts get-caller-identity --query Account --output text

# Get your AWS region
echo $AWS_REGION
```

**Auto-configure ECR image URIs with sed:**

```bash
# Set your values
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Update all 7 ECR image URIs in terraform.tfvars
sed -i "s/YOUR_ACCOUNT_ID/${AWS_ACCOUNT_ID}/g" terraform.tfvars
sed -i "s/YOUR_AWS_REGION/${AWS_REGION}/g" terraform.tfvars
```

**Configure ingress_cidr_blocks:**

```bash
# Get your IP address
MY_IP=$(curl -s ifconfig.me)
echo "Your IP: ${MY_IP}/32"
```

If you are running this from an EC2 instance, you may also want to run `curl -s ifconfig.me` on your laptop so you can access the registry from both the EC2 instance and your laptop.

**Warning:** Setting `ingress_cidr_blocks` to `["0.0.0.0/0"]` opens access to anyone on the internet. While authentication (username/password) is still required, this is not recommended for production environments.

**Example minimal terraform.tfvars:**

```hcl
# AWS Region (must match where you pushed ECR images)
aws_region = "us-east-1"

# Your Route53 domain
base_domain = "YOUR.DOMAIN"

# IP addresses allowed to access the ALB
ingress_cidr_blocks = [
  "203.0.113.10/32",   # Your EC2 instance IP
  "198.51.100.25/32",  # Your laptop IP
]

# Keycloak credentials (CHANGE THESE)
keycloak_admin_password    = "YourSecurePassword123!"
keycloak_database_password = "YourDBPassword456!"

# ECR image URIs (after running sed commands above)
registry_image_uri               = "123456789012.dkr.ecr.us-east-1.amazonaws.com/mcp-gateway-registry:latest"
auth_server_image_uri            = "123456789012.dkr.ecr.us-east-1.amazonaws.com/mcp-gateway-auth-server:latest"
currenttime_image_uri            = "123456789012.dkr.ecr.us-east-1.amazonaws.com/mcp-gateway-currenttime:latest"
mcpgw_image_uri                  = "123456789012.dkr.ecr.us-east-1.amazonaws.com/mcp-gateway-mcpgw:latest"
realserverfaketools_image_uri    = "123456789012.dkr.ecr.us-east-1.amazonaws.com/mcp-gateway-realserverfaketools:latest"
flight_booking_agent_image_uri   = "123456789012.dkr.ecr.us-east-1.amazonaws.com/mcp-gateway-flight-booking-agent:latest"
travel_assistant_agent_image_uri = "123456789012.dkr.ecr.us-east-1.amazonaws.com/mcp-gateway-travel-assistant-agent:latest"
```

### Step 4: Deploy Infrastructure (~20 min)

**First-time deployments require a two-stage process due to SSL certificate dependencies.**

```bash
# Initialize Terraform
terraform init -upgrade

# Stage 1: Create SSL certificates first
terraform apply \
  -target=aws_acm_certificate.keycloak \
  -target=aws_acm_certificate.registry \
  -target=aws_acm_certificate_validation.keycloak \
  -target=aws_acm_certificate_validation.registry

# Stage 2: Deploy all remaining infrastructure
terraform apply
```

### Step 5: Post-Deployment Setup

See [Post-Deployment](#post-deployment) section for:
- Initializing Keycloak
- Running scopes initialization
- Restarting ECS tasks
- Accessing the Web UI

---

## Important Notes

- **Cost Warning:** This infrastructure incurs AWS charges (~$110-250/month). See [Cost Optimization](#cost-optimization) for details.
- **Deployment Time:** First deployment takes 15-20 minutes (RDS provisioning is the slowest part).
- **Region Considerations:** All resources (ECR images, infrastructure) must be in the same AWS region.
- **State Management:** Terraform state is stored locally by default. For production, use S3 backend (see [Security](#security-considerations)).

## Post-Deployment

Critical steps to complete **after** `terraform apply` finishes successfully.

### Step 1: Automated Post-Deployment Setup (Recommended)

The automated setup script handles all post-deployment tasks in sequence:

```bash
cd terraform/aws-ecs

# Set required environment variables
export AWS_REGION=us-east-1
export INITIAL_ADMIN_PASSWORD="YourSecureRealmAdminPassword"  # Password for 'admin' user in mcp-gateway realm

# Run the automated post-deployment setup
./scripts/post-deployment-setup.sh
```

**What the script does:**
1. Saves terraform outputs to JSON file
2. Validates all required resources were created
3. Waits for DNS propagation (up to 10 minutes)
4. Verifies ECS services are running and healthy
5. Initializes Keycloak (realm, clients, users, groups, scopes)
6. Initializes MCP scopes on EFS
7. Restarts registry and auth services to pick up new configuration
8. Verifies all endpoints are responding

**Expected output:**
```
==========================================
MCP Gateway Post-Deployment Setup
==========================================

Step 1: Saving Terraform Outputs
[SUCCESS] Terraform outputs saved

Step 2: Validating Terraform Outputs
[SUCCESS] Found: vpc_id = vpc-xxx
[SUCCESS] Found: ecs_cluster_name = mcp-gateway-ecs-cluster
[SUCCESS] Found: keycloak_url = https://kc.us-east-1.YOUR.DOMAIN
...

Step 3: Waiting for DNS Propagation
[SUCCESS] DNS resolved: kc.us-east-1.YOUR.DOMAIN
[SUCCESS] DNS resolved: registry.us-east-1.YOUR.DOMAIN

Step 4: Verifying ECS Services
[SUCCESS] mcp-gateway-v2-registry: 2/2 running
[SUCCESS] mcp-gateway-v2-auth: 2/2 running
[SUCCESS] keycloak-service: 2/2 running

Step 5: Initializing Keycloak
[SUCCESS] Keycloak initialized successfully!

Step 6: Initializing MCP Scopes on EFS
[SUCCESS] MCP scopes initialized on EFS!

Step 7: Restarting Registry and Auth Services
[SUCCESS] All services restarted successfully!

Step 8: Verifying Application Endpoints
[SUCCESS] Registry Health: HTTP 200
[SUCCESS] Keycloak Admin: HTTP 200

==========================================
Post-Deployment Setup Summary
==========================================
Total Steps: 8
Passed:      8
Failed:      0
Skipped:     0

Post-deployment setup completed successfully!
```

### Step 2: Access Web UI and Register Example Servers/Agents

First, extract URLs from your terraform outputs:

```bash
# Load URLs from terraform outputs
OUTPUTS_FILE="scripts/terraform-outputs.json"
if [[ ! -f "$OUTPUTS_FILE" ]]; then
    echo "Run ./scripts/save-terraform-outputs.sh first"
    exit 1
fi

# Extract URLs
REGISTRY_URL=$(jq -r '.registry_url.value' "$OUTPUTS_FILE")
KEYCLOAK_URL=$(jq -r '.keycloak_url.value' "$OUTPUTS_FILE")
KEYCLOAK_ADMIN_URL=$(jq -r '.keycloak_admin_console.value' "$OUTPUTS_FILE")

echo "Registry URL: $REGISTRY_URL"
echo "Keycloak URL: $KEYCLOAK_URL"
echo "Keycloak Admin Console: $KEYCLOAK_ADMIN_URL"
```

**Open the Registry UI in your browser:**

```bash
# Open using the extracted URL
open "$REGISTRY_URL"
```

You should see the login page. Login with the admin credentials for the **mcp-gateway** realm:
- **Username**: `admin`
- **Password**: The password you set via `INITIAL_ADMIN_PASSWORD` environment variable when running init-keycloak.sh

**Important Password Distinction**:
- **Realm Admin Password** (`INITIAL_ADMIN_PASSWORD`): Used to log into the MCP Gateway Registry
- **Keycloak Master Admin Password** (`keycloak_admin_password` from terraform.tfvars): Used to access the Keycloak admin console

![MCP Gateway Registry First Login](img/MCP-Gateway-Registry-first-login.png)

After successful login, you'll see the empty Registry dashboard showing 0 servers and 0 agents.

**Access Keycloak Admin Console:**

```bash
# Open Keycloak admin console
open "$KEYCLOAK_ADMIN_URL"
```

**Register Example MCP Servers:**

Now let's register some example MCP servers using the CLI tool:

```bash
cd ../../mcp-gateway-registry

# Load URLs from terraform outputs (both REGISTRY_URL and KEYCLOAK_URL are required)
OUTPUTS_FILE="terraform/aws-ecs/scripts/terraform-outputs.json"
export REGISTRY_URL=$(jq -r '.registry_url.value' "$OUTPUTS_FILE")
export KEYCLOAK_URL=$(jq -r '.keycloak_url.value' "$OUTPUTS_FILE")

echo "Registry URL: $REGISTRY_URL"
echo "Keycloak URL: $KEYCLOAK_URL"

# Register Cloudflare Docs server
uv run python api/registry_management.py register \
  --config cli/examples/cloudflare-docs-server-config.json

# Register Context7 server
uv run python api/registry_management.py register \
  --config cli/examples/context7-server-config.json

# Register MCPGW server (registry management tools)
uv run python api/registry_management.py register \
  --config cli/examples/mcpgw.json

# Register CurrentTime server
uv run python api/registry_management.py register \
  --config cli/examples/currenttime.json
```

**Register Example A2A Agents:**

```bash
# Register Flight Booking Agent
uv run python api/registry_management.py agent-register \
  --config cli/examples/flight_booking_agent_card.json

# Register Travel Assistant Agent
uv run python api/registry_management.py agent-register \
  --config cli/examples/travel_assistant_agent_card.json
```

**Verify Registration:**

Refresh the browser and you should now see:
- 4 MCP servers (Cloudflare Docs, Context7, MCPGW, CurrentTime)
- 2 A2A agents (Flight Booking Agent, Travel Assistant Agent)

You can also verify via CLI:

```bash
# List all registered servers
uv run python api/registry_management.py list

# List all registered agents
uv run python api/registry_management.py agent-list
```

### Step 3: Review Logs (Verify No Errors)

```bash
cd terraform/aws-ecs

# Check for errors across all services (last 10 minutes)
./scripts/view-cloudwatch-logs.sh --minutes 10 --filter "ERROR|FATAL|Exception"

# If errors found, view full context for specific service
./scripts/view-cloudwatch-logs.sh --component registry --minutes 30
./scripts/view-cloudwatch-logs.sh --component keycloak --minutes 30
./scripts/view-cloudwatch-logs.sh --component auth-server --minutes 30

# Common startup errors to ignore:
# - "Waiting for database..." (normal during RDS startup)
# - "Connection refused" in first 2-3 minutes (normal)
# - "Health check failed" during task startup (normal)

# Real errors to investigate:
# - "Authentication failed"
# - "Database connection pool exhausted"
# - "Out of memory"
# - "Permission denied"
```

### Step 4: Test Complete Workflow

**Deployment Complete!** Your MCP Gateway Registry is now fully operational with example servers and agents registered.

You can now:
- Browse servers and agents in the Web UI
- Use the "Get JWT Token" button in the UI to generate M2M tokens for API access
- Test MCP server connections through the gateway
- Explore semantic search for servers and agents
- Manage server/agent permissions and groups via Keycloak

For advanced usage, see the [Operations and Maintenance](#operations-and-maintenance) section below.

## Operations and Maintenance

See [OPERATIONS.md](OPERATIONS.md) for detailed operations and maintenance documentation, including:
- Accessing ECS tasks via SSH
- Viewing CloudWatch logs
- Container build and deployment
- Updating running services
- Rolling back deployments

## Troubleshooting

### Common Issues

#### DNS Not Resolving
```bash
# Check Route53 hosted zone
aws route53 list-hosted-zones --query "HostedZones[?Name=='YOUR.DOMAIN.']"

# Check DNS records
aws route53 list-resource-record-sets \
  --hosted-zone-id ZONE_ID \
  --query "ResourceRecordSets[?Type=='CNAME']"

# Wait 5-10 minutes for propagation
# Test with different DNS servers
dig @8.8.8.8 kc.us-east-1.YOUR.DOMAIN
dig @1.1.1.1 registry.us-east-1.YOUR.DOMAIN
```

#### ECS Tasks Not Starting
```bash
# Check service events
aws ecs describe-services \
  --cluster mcp-gateway-ecs-cluster \
  --services mcp-gateway-v2-registry \
  --region $AWS_REGION \
  --query 'services[0].events[:10]' \
  --output table

# Check task stopped reason
aws ecs describe-tasks \
  --cluster mcp-gateway-ecs-cluster \
  --tasks TASK_ARN \
  --region $AWS_REGION \
  --query 'tasks[0].{StoppedReason:stoppedReason,Containers:containers[*].{Name:name,Reason:reason}}'

# Common causes:
# - ECR image pull failure (wrong region or permissions)
# - Resource limits (insufficient CPU/memory)
# - Invalid environment variables
# - Secrets Manager access denied
```

#### SSL Certificate Validation Pending
```bash
# Check certificate status
aws acm list-certificates --region $AWS_REGION

# Get certificate details
aws acm describe-certificate \
  --certificate-arn CERT_ARN \
  --region $AWS_REGION

# DNS validation may take 5-30 minutes
# Ensure Route53 hosted zone is correct
# Check CNAME validation records exist
```

#### Database Connection Failures
```bash
# Check RDS cluster status
aws rds describe-db-clusters \
  --db-cluster-identifier mcp-gateway-keycloak-cluster \
  --region $AWS_REGION \
  --query 'DBClusters[0].{Status:Status,Endpoint:Endpoint}'

# Check security group rules
aws ec2 describe-security-groups \
  --group-ids sg-xxx \
  --region $AWS_REGION

# Verify database credentials in Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id /mcp-gateway/keycloak/db-password \
  --region $AWS_REGION
```

### Getting Help

Check logs first:
```bash
./scripts/view-cloudwatch-logs.sh --filter "ERROR|FATAL|Exception"
```

Review Terraform state:
```bash
terraform show
terraform state list
terraform state show aws_ecs_service.registry
```

## Cost Optimization

### Estimated Monthly Costs (us-east-1)

| Resource | Configuration | Estimated Cost |
|----------|--------------|----------------|
| RDS Aurora Serverless v2 | 0.5-2 ACU, PostgreSQL | $40-100/month |
| ECS Fargate Tasks | 3 services, 0.25 vCPU, 0.5GB each | $20-50/month |
| Application Load Balancers | 2 ALBs | $32-50/month |
| EFS | 5GB storage | $1.50/month |
| CloudWatch Logs | 10GB/month | $5/month |
| Data Transfer | 100GB/month | $9/month |
| **Total** | | **~$110-250/month** |

### Cost Reduction Strategies

**1. Use Aurora Serverless v2 auto-pause**
```hcl
keycloak_database_min_acu = 0.5  # Scale down to minimum
keycloak_database_max_acu = 1.0  # Lower max capacity
```

**2. Reduce ECS task count for non-prod**
```hcl
registry_replicas = 1    # Down from 2
auth_server_replicas = 1 # Down from 2
```

**3. Use internal ALB for Keycloak in production**
```hcl
keycloak_alb_scheme = "internal"
```

**4. Enable CloudWatch log retention**
```hcl
# Already configured - logs expire after 7 days
```

**5. Use Fargate Spot for non-critical workloads**
```hcl
capacity_provider_strategy = {
  base = 1  # Keep 1 on-demand
  weight = 1  # Use Spot for additional tasks
}
```

## Security Considerations

### Network Security
- All traffic encrypted with TLS (ACM certificates)
- Security groups restrict access to approved CIDR blocks only
- Keycloak ALB can be internal-only for production
- NAT Gateway for outbound internet access from private subnets

### Secrets Management
- All credentials stored in AWS Secrets Manager
- Automatic rotation supported (configure separately)
- ECS tasks retrieve secrets at runtime
- Never log or expose credentials

### IAM Permissions

For running Terraform and the deployment scripts, your IAM user or role needs the following permissions:

```json
{
    "Sid": "MCPGatewayDeployment",
    "Effect": "Allow",
    "Action": [
        "secretsmanager:*",
        "bedrock-agentcore:*",
        "iam:PassRole",
        "ec2:*",
        "ecs:*",
        "rds:*",
        "elasticloadbalancing:*",
        "route53:*",
        "acm:*",
        "iam:*",
        "logs:*",
        "elasticfilesystem:*",
        "ecr:*",
        "application-autoscaling:*",
        "cloudwatch:*",
        "sns:*",
        "ssm:*",
        "kms:*",
        "servicediscovery:*"
    ],
    "Resource": "*"
}
```

**Note:** For production, consider restricting these permissions to specific resource ARNs.

**ECS Task Role Security:**
- ECS task roles follow principle of least privilege
- Separate execution role for pulling images and secrets
- Task role for application-specific AWS API access
- Regular audit of IAM policies recommended

### Database Security
- RDS in private subnets only
- Encryption at rest enabled
- Encryption in transit (SSL)
- Automated backups enabled
- Security group limits access to ECS tasks only

### Best Practices
```bash
# Rotate Keycloak admin password
./scripts/rotate-keycloak-web-client-secret.sh

# Enable MFA for AWS console access
aws iam enable-mfa-device --user-name admin

# Use IAM roles for ECS tasks (already configured)
# Avoid hardcoding credentials in environment variables

# Regularly update container images
make build-push
aws ecs update-service --cluster mcp-gateway-ecs-cluster --service mcp-gateway-v2-registry --force-new-deployment --region us-east-1

# Enable AWS CloudTrail for audit logs
# Enable AWS Config for compliance monitoring
# Use AWS Security Hub for security posture management
```

## Backup and Disaster Recovery

### RDS Automated Backups
```bash
# Backups enabled by default (7 day retention)
# Point-in-time recovery available

# Create manual snapshot
aws rds create-db-cluster-snapshot \
  --db-cluster-identifier mcp-gateway-keycloak-cluster \
  --db-cluster-snapshot-identifier manual-backup-$(date +%Y%m%d) \
  --region $AWS_REGION

# List snapshots
aws rds describe-db-cluster-snapshots \
  --db-cluster-identifier mcp-gateway-keycloak-cluster \
  --region $AWS_REGION

# Restore from snapshot (requires terraform changes)
```

### EFS Backup
```bash
# EFS backup to AWS Backup (configure in AWS Backup console)
# Or use EFS-to-EFS replication for cross-region DR
```

### Terraform State Backup
```bash
# Local state - backup manually
cp terraform.tfstate terraform.tfstate.backup

# S3 backend (recommended for production)
terraform {
  backend "s3" {
    bucket         = "your-terraform-state-bucket"
    key            = "mcp-gateway/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-lock-table"
  }
}
```

## Additional Resources

- [ECS Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/)
- [Aurora Serverless v2 Documentation](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html)
- [Application Load Balancer Guide](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/)
- [Keycloak Documentation](https://www.keycloak.org/documentation)
- [Session Manager Plugin Installation](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)

## Quick Reference

### Common Commands Cheat Sheet

```bash
# ============================================================================
# DEPLOYMENT
# ============================================================================
# Initial deployment
export AWS_REGION=us-east-1
make build-push                    # Build and push all images (~30 min)
terraform init && terraform apply  # Deploy infrastructure (~20 min)
./scripts/init-keycloak.sh         # Initialize Keycloak

# ============================================================================
# UPDATES
# ============================================================================
# Update specific service
make build-push IMAGE=registry
aws ecs update-service --cluster mcp-gateway-ecs-cluster --service mcp-gateway-v2-registry --force-new-deployment --region us-east-1

# ============================================================================
# MONITORING
# ============================================================================
# View logs
./scripts/view-cloudwatch-logs.sh --component registry --follow
./scripts/view-cloudwatch-logs.sh --filter "ERROR"

# Check service status
aws ecs describe-services --cluster mcp-gateway-ecs-cluster --services mcp-gateway-v2-registry --region us-east-1 --query 'services[0].{Running:runningCount,Desired:desiredCount}' --output table

# ============================================================================
# DEBUGGING
# ============================================================================
# SSH into running task
./scripts/ecs-ssh.sh registry

# Check DNS
dig +short registry.us-east-1.YOUR.DOMAIN

# Test endpoints
curl https://registry.us-east-1.YOUR.DOMAIN/health
curl https://kc.us-east-1.YOUR.DOMAIN/health

# ============================================================================
# CLEANUP
# ============================================================================
# See "Destroying Resources" section below for detailed instructions
./scripts/pre-destroy-cleanup.sh  # Run first to clean up blocking resources
terraform destroy                  # Then destroy infrastructure
```

## Destroying Resources

Before running `terraform destroy`, you must run the pre-destroy cleanup script to remove resources that may block deletion:

```bash
cd terraform/aws-ecs

# Step 1: Run pre-destroy cleanup
./scripts/pre-destroy-cleanup.sh

# Step 2: Destroy infrastructure
terraform destroy
```

### Why Pre-Destroy Cleanup is Required

Terraform destroy may fail due to:
- **ECS Services**: Services must be scaled to 0 and deleted before clusters can be removed
- **Service Discovery Namespaces**: Must delete services within namespaces before deleting namespaces
- **ECS Cluster Capacity Providers**: Clusters with active capacity providers cannot be deleted
- **Secrets Manager Secrets**: Deleted secrets are scheduled for deletion (7-30 days) and block recreation with the same name

**Note:** ECR repositories are intentionally NOT deleted by the pre-destroy cleanup script. Container images are preserved to avoid expensive rebuilds when redeploying. See the "ECR Repository Cleanup (Optional)" section below for manual deletion commands.

### Manual Cleanup Commands

If `terraform destroy` fails, you may need to run these commands manually:

```bash
export AWS_REGION=us-east-1

# ============================================================================
# ECS Services Cleanup
# ============================================================================
# Scale down and delete ECS services
aws ecs update-service --cluster mcp-gateway-ecs-cluster --service mcp-gateway-v2-registry --desired-count 0 --region $AWS_REGION
aws ecs delete-service --cluster mcp-gateway-ecs-cluster --service mcp-gateway-v2-registry --force --region $AWS_REGION

aws ecs update-service --cluster mcp-gateway-ecs-cluster --service mcp-gateway-v2-auth --desired-count 0 --region $AWS_REGION
aws ecs delete-service --cluster mcp-gateway-ecs-cluster --service mcp-gateway-v2-auth --force --region $AWS_REGION

aws ecs update-service --cluster keycloak --service keycloak --desired-count 0 --region $AWS_REGION
aws ecs delete-service --cluster keycloak --service keycloak --force --region $AWS_REGION

# Wait for tasks to stop (check with)
aws ecs list-tasks --cluster mcp-gateway-ecs-cluster --region $AWS_REGION
aws ecs list-tasks --cluster keycloak --region $AWS_REGION

# ============================================================================
# Service Discovery Cleanup
# ============================================================================
# List namespaces
aws servicediscovery list-namespaces --region $AWS_REGION

# Delete services in namespace first
aws servicediscovery list-services --filters Name=NAMESPACE_ID,Values=ns-xxxxx --region $AWS_REGION
aws servicediscovery delete-service --id srv-xxxxx --region $AWS_REGION

# Then delete namespace
aws servicediscovery delete-namespace --id ns-xxxxx --region $AWS_REGION

# ============================================================================
# Secrets Manager Cleanup
# ============================================================================
# Force delete secrets that are scheduled for deletion (required before recreating)
aws secretsmanager delete-secret --secret-id "keycloak/database" --force-delete-without-recovery --region $AWS_REGION
aws secretsmanager delete-secret --secret-id "mcp-gateway-keycloak-client-secret" --force-delete-without-recovery --region $AWS_REGION
aws secretsmanager delete-secret --secret-id "mcp-gateway-keycloak-m2m-client-secret" --force-delete-without-recovery --region $AWS_REGION

# ============================================================================
# Targeted Terraform Destroy
# ============================================================================
# If full destroy fails, try targeted destroy of remaining resources
terraform state list  # List remaining resources

terraform destroy \
  -target=module.mcp_gateway.aws_service_discovery_private_dns_namespace.mcp \
  -target=module.ecs_cluster.aws_ecs_cluster.this[0] \
  -target=module.vpc.aws_vpc.this[0]
```

### ECR Repository Cleanup (Optional)

ECR repositories are intentionally NOT deleted by the pre-destroy cleanup script to preserve container images and avoid expensive rebuilds when redeploying. If you want to completely remove all resources including ECR repositories, run these commands manually:

```bash
export AWS_REGION=us-east-1

# Delete all ECR repositories (WARNING: This deletes all container images!)
aws ecr delete-repository --repository-name keycloak --force --region $AWS_REGION
aws ecr delete-repository --repository-name mcp-gateway-registry --force --region $AWS_REGION
aws ecr delete-repository --repository-name mcp-gateway-auth-server --force --region $AWS_REGION
aws ecr delete-repository --repository-name mcp-gateway-currenttime --force --region $AWS_REGION
aws ecr delete-repository --repository-name mcp-gateway-mcpgw --force --region $AWS_REGION
aws ecr delete-repository --repository-name mcp-gateway-realserverfaketools --force --region $AWS_REGION
aws ecr delete-repository --repository-name mcp-gateway-flight-booking-agent --force --region $AWS_REGION
aws ecr delete-repository --repository-name mcp-gateway-travel-assistant-agent --force --region $AWS_REGION
```

### File Structure Reference

```
terraform/aws-ecs/
├── README.md                          # This file
├── main.tf                            # Main infrastructure definition
├── variables.tf                       # Variable definitions with defaults
├── locals.tf                          # Computed local values (domain logic)
├── terraform.tfvars                   # Your configuration (NOT in git)
├── terraform.tfvars.example           # Template for terraform.tfvars
├── outputs.tf                         # Terraform output definitions
├── keycloak-*.tf                      # Keycloak-specific resources
├── registry-*.tf                      # Registry-specific resources
├── auth-*.tf                          # Auth server resources
├── network.tf                         # VPC, subnets, security groups
├── database.tf                        # RDS Aurora configuration
├── efs.tf                             # Elastic File System
├── img/
│   └── architecture-ecs.png           # Architecture diagram
└── scripts/
    ├── init-keycloak.sh               # Initialize Keycloak (run after terraform apply)
    ├── ecs-ssh.sh                     # SSH into ECS tasks
    ├── view-cloudwatch-logs.sh        # View/follow CloudWatch logs
    ├── user_mgmt.sh                   # Keycloak user management
    ├── service_mgmt.sh                # Service management utilities
    ├── rotate-keycloak-web-client-secret.sh  # Rotate OAuth2 secrets
    ├── save-terraform-outputs.sh      # Export terraform outputs as JSON
    └── pre-destroy-cleanup.sh         # Run before terraform destroy
```

### Environment Variables Reference

| Variable | Purpose | Example |
|----------|---------|---------|
| `AWS_REGION` | Target AWS region | `us-east-1` |
| `AWS_PROFILE` | AWS CLI profile | `mcp-gateway` |
| `TF_VAR_aws_region` | Override terraform region | `us-west-2` |
| `KEYCLOAK_ADMIN_URL` | Keycloak URL for scripts | `https://kc.us-east-1.YOUR.DOMAIN` |
| `KEYCLOAK_ADMIN_PASSWORD` | Keycloak admin password | From terraform.tfvars |

### Service Port Mapping

| Service | Internal Port | ALB Port | Health Check |
|---------|--------------|----------|--------------|
| Registry | 7860 | 443 (HTTPS) | `/health` |
| Auth Server | 8888 | 443 (HTTPS) | `/auth/health` |
| Keycloak | 8080 | 443 (HTTPS) | `/health` |

### Resource Naming Conventions

| Resource Type | Naming Pattern | Example |
|--------------|----------------|---------|
| ECS Cluster | `mcp-gateway-ecs-cluster` | - |
| ECS Service | `mcp-gateway-v2-{service}` | `mcp-gateway-v2-registry` |
| ECR Repository | `mcp-gateway-{image}` | `mcp-gateway-registry` |
| RDS Cluster | `mcp-gateway-keycloak-cluster` | - |
| ALB | `mcp-gateway-{type}-alb` | `mcp-gateway-alb` |
| Log Group | `/aws/ecs/mcp-gateway-{service}` | `/aws/ecs/mcp-gateway-registry` |

## Support

For issues or questions:

1. **Check Logs First:**
   ```bash
   ./scripts/view-cloudwatch-logs.sh --filter "ERROR"
   ```

2. **Verify Service Status:**
   ```bash
   aws ecs describe-services --cluster mcp-gateway-ecs-cluster --services mcp-gateway-v2-registry --region us-east-1
   ```

3. **Test DNS Resolution:**
   ```bash
   dig kc.us-east-1.YOUR.DOMAIN
   dig registry.us-east-1.YOUR.DOMAIN
   ```

4. **Review Common Issues:**
   - See [Troubleshooting](#troubleshooting) section above
   - Check [AWS ECS Troubleshooting Guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/troubleshooting.html)

5. **Community Support:**
   - [GitHub Issues](https://github.com/agentic-community/mcp-gateway-registry/issues)
