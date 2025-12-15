# MCP Gateway Registry Module Variables

# Required Variables - Shared Resources
variable "name" {
  description = "Name prefix for MCP Gateway Registry resources"
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC where resources will be created"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for ECS services"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for ALB"
  type        = list(string)
}

variable "ecs_cluster_arn" {
  description = "ARN of the existing ECS cluster"
  type        = string
}

variable "ecs_cluster_name" {
  description = "Name of the existing ECS cluster"
  type        = string
}

variable "task_execution_role_arn" {
  description = "ARN of the task execution IAM role (DEPRECATED: Module now creates its own task execution roles)"
  type        = string
  default     = ""
}

# Container Image URIs (pre-built images from Docker Hub)
variable "registry_image_uri" {
  description = "Container image URI for registry service (defaults to pre-built image from mcpgateway Docker Hub)"
  type        = string
  default     = "mcpgateway/registry:latest"
}

variable "auth_server_image_uri" {
  description = "Container image URI for auth server service (defaults to pre-built image from mcpgateway Docker Hub)"
  type        = string
  default     = "mcpgateway/auth-server:latest"
}

variable "currenttime_image_uri" {
  description = "Container image URI for currenttime MCP server"
  type        = string
  default     = ""
}

variable "mcpgw_image_uri" {
  description = "Container image URI for mcpgw MCP server"
  type        = string
  default     = ""
}

variable "realserverfaketools_image_uri" {
  description = "Container image URI for realserverfaketools MCP server"
  type        = string
  default     = ""
}

variable "flight_booking_agent_image_uri" {
  description = "Container image URI for flight booking A2A agent"
  type        = string
  default     = ""
}

variable "travel_assistant_agent_image_uri" {
  description = "Container image URI for travel assistant A2A agent"
  type        = string
  default     = ""
}

variable "dockerhub_org" {
  description = "Docker Hub organization for pre-built images"
  type        = string
  default     = "mcpgateway"
}


# Resource Configuration
variable "cpu" {
  description = "CPU allocation for MCP Gateway Registry containers (in vCPU units: 256, 512, 1024, 2048, 4096)"
  type        = string
  default     = "1024"
  validation {
    condition     = contains(["256", "512", "1024", "2048", "4096"], var.cpu)
    error_message = "CPU must be one of: 256, 512, 1024, 2048, 4096"
  }
}

variable "memory" {
  description = "Memory allocation for MCP Gateway Registry containers (in MB, must be compatible with CPU)"
  type        = string
  default     = "2048"
}

variable "registry_replicas" {
  description = "Number of replicas for MCP Gateway Registry main service"
  type        = number
  default     = 1
  validation {
    condition     = var.registry_replicas > 0
    error_message = "Registry replicas must be greater than 0."
  }
}

variable "auth_replicas" {
  description = "Number of replicas for MCP Gateway Auth service"
  type        = number
  default     = 1
  validation {
    condition     = var.auth_replicas > 0
    error_message = "Auth replicas must be greater than 0."
  }
}

variable "currenttime_replicas" {
  description = "Number of replicas for CurrentTime MCP server"
  type        = number
  default     = 1
  validation {
    condition     = var.currenttime_replicas > 0
    error_message = "CurrentTime replicas must be greater than 0."
  }
}

variable "mcpgw_replicas" {
  description = "Number of replicas for MCPGW MCP server"
  type        = number
  default     = 1
  validation {
    condition     = var.mcpgw_replicas > 0
    error_message = "MCPGW replicas must be greater than 0."
  }
}

variable "realserverfaketools_replicas" {
  description = "Number of replicas for RealServerFakeTools MCP server"
  type        = number
  default     = 1
  validation {
    condition     = var.realserverfaketools_replicas > 0
    error_message = "RealServerFakeTools replicas must be greater than 0."
  }
}

variable "flight_booking_agent_replicas" {
  description = "Number of replicas for Flight Booking A2A agent"
  type        = number
  default     = 1
  validation {
    condition     = var.flight_booking_agent_replicas > 0
    error_message = "Flight Booking agent replicas must be greater than 0."
  }
}

variable "travel_assistant_agent_replicas" {
  description = "Number of replicas for Travel Assistant A2A agent"
  type        = number
  default     = 1
  validation {
    condition     = var.travel_assistant_agent_replicas > 0
    error_message = "Travel Assistant agent replicas must be greater than 0."
  }
}

# ALB Configuration
variable "alb_scheme" {
  description = "Scheme for the ALB (internal or internet-facing)"
  type        = string
  default     = "internet-facing"
  validation {
    condition     = contains(["internal", "internet-facing"], var.alb_scheme)
    error_message = "ALB scheme must be either 'internal' or 'internet-facing'."
  }
}

variable "ingress_cidr_blocks" {
  description = "List of CIDR blocks allowed to access the ALB (main ALB + auth server + registry)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "certificate_arn" {
  description = "ARN of ACM certificate for HTTPS (optional)"
  type        = string
  default     = ""
}

variable "keycloak_domain" {
  description = "Domain name for Keycloak (e.g., kc.mycorp.click)"
  type        = string
  default     = ""
}

variable "enable_autoscaling" {
  description = "Whether to enable auto-scaling for ECS services"
  type        = bool
  default     = true
}

variable "autoscaling_min_capacity" {
  description = "Minimum number of tasks for auto-scaling"
  type        = number
  default     = 2
}

variable "autoscaling_max_capacity" {
  description = "Maximum number of tasks for auto-scaling"
  type        = number
  default     = 4
}

variable "autoscaling_target_cpu" {
  description = "Target CPU utilization percentage for auto-scaling"
  type        = number
  default     = 70
}

variable "autoscaling_target_memory" {
  description = "Target memory utilization percentage for auto-scaling"
  type        = number
  default     = 80
}

variable "enable_monitoring" {
  description = "Whether to enable CloudWatch monitoring and alarms"
  type        = bool
  default     = true
}

variable "alarm_email" {
  description = "Email address for CloudWatch alarm notifications"
  type        = string
  default     = ""
}

# EFS Configuration
# Note: 'bursting' mode is recommended for most workloads and is FREE.
# It provides up to 100 MiB/s burst throughput, which is sufficient for registry operations.
# 'provisioned' mode costs $6/MiB/s-month and should only be used for proven high-throughput needs.
variable "efs_throughput_mode" {
  description = "Throughput mode for EFS (bursting or provisioned)"
  type        = string
  default     = "bursting"
  validation {
    condition     = contains(["bursting", "provisioned"], var.efs_throughput_mode)
    error_message = "EFS throughput mode must be either 'bursting' or 'provisioned'."
  }
}

variable "efs_provisioned_throughput" {
  description = "Provisioned throughput in MiB/s for EFS (only used if throughput_mode is provisioned)"
  type        = number
  default     = 100
}

variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}


# Domain Configuration (Optional)
variable "domain_name" {
  description = "Domain name for the MCP Gateway Registry (optional)"
  type        = string
  default     = ""
}

variable "create_route53_record" {
  description = "Whether to create Route53 DNS record for the domain"
  type        = bool
  default     = false
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID (required if create_route53_record is true)"
  type        = string
  default     = ""
}


# Embeddings Configuration
variable "embeddings_provider" {
  description = "Embeddings provider: 'sentence-transformers' for local models or 'litellm' for API-based models"
  type        = string
  default     = "sentence-transformers"
  validation {
    condition     = contains(["sentence-transformers", "litellm"], var.embeddings_provider)
    error_message = "Embeddings provider must be either 'sentence-transformers' or 'litellm'."
  }
}

variable "embeddings_model_name" {
  description = "Name of the embeddings model to use (e.g., 'all-MiniLM-L6-v2' for sentence-transformers, 'openai/text-embedding-ada-002' for litellm)"
  type        = string
  default     = "all-MiniLM-L6-v2"
}

variable "embeddings_model_dimensions" {
  description = "Dimension of the embeddings model (e.g., 384 for MiniLM, 1536 for OpenAI/Titan)"
  type        = number
  default     = 384
  validation {
    condition     = var.embeddings_model_dimensions > 0
    error_message = "Embeddings model dimensions must be greater than 0."
  }
}

variable "embeddings_aws_region" {
  description = "AWS region for Bedrock embeddings (only used when embeddings_provider is 'litellm' with Bedrock)"
  type        = string
  default     = "us-east-1"
}

variable "embeddings_api_key" {
  description = "API key for embeddings provider (OpenAI, Anthropic, etc.). Only used when embeddings_provider is 'litellm'. Leave empty for Bedrock (uses IAM)."
  type        = string
  default     = ""
  sensitive   = true
}


# Keycloak Admin Credentials (for Management API)
variable "keycloak_admin_password" {
  description = "Keycloak admin password for Management API user/group operations"
  type        = string
  sensitive   = true
}

# =============================================================================
# SESSION COOKIE SECURITY CONFIGURATION
# =============================================================================

variable "session_cookie_secure" {
  description = "Enable secure flag on session cookies (HTTPS-only transmission). Set to true in production with HTTPS."
  type        = bool
  default     = true
}

variable "session_cookie_domain" {
  description = "Domain for session cookies (e.g., '.example.com' for cross-subdomain sharing). Leave empty for single-domain deployments (cookie scoped to exact host only)."
  type        = string
  default     = ""
}

# Security Scanning Configuration
variable "security_scan_enabled" {
  description = "Enable/disable security scanning for MCP servers during registration"
  type        = bool
  default     = true
}

variable "security_scan_on_registration" {
  description = "Automatically scan servers when they are registered"
  type        = bool
  default     = true
}

variable "security_block_unsafe_servers" {
  description = "Block (disable) servers that fail security scans"
  type        = bool
  default     = true
}

variable "security_analyzers" {
  description = "Comma-separated list of analyzers to use for security scanning (available: yara, llm, api)"
  type        = string
  default     = "yara"
}

variable "security_scan_timeout" {
  description = "Security scan timeout in seconds"
  type        = number
  default     = 60
}

variable "security_add_pending_tag" {
  description = "Add 'security-pending' tag to servers that fail security scan"
  type        = bool
  default     = true
}
