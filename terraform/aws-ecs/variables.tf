variable "name" {
  description = "Name of the deployment"
  type        = string
  default     = "mcp-gateway"
}

variable "aws_region" {
  description = "AWS region for deployment. Can be set via TF_VAR_aws_region environment variable or terraform.tfvars"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "ingress_cidr_blocks" {
  description = "List of CIDR blocks allowed to access the ALB (main ALB + auth server + registry)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
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

#
# Keycloak Configuration Variables
#

variable "use_regional_domains" {
  description = "Use region-based domains (e.g., kc.us-west-2.mycorp.click). If false, uses keycloak_domain and root_domain directly"
  type        = bool
  default     = true
}

variable "base_domain" {
  description = "Base domain for regional domains (e.g., mycorp.click). Used when use_regional_domains is true"
  type        = string
  default     = "mycorp.click"
}

variable "keycloak_domain" {
  description = "Full domain for Keycloak (e.g., kc.example.com). Used when use_regional_domains is false"
  type        = string
  default     = ""
}

variable "root_domain" {
  description = "Root domain with Route53 hosted zone. Used when use_regional_domains is false"
  type        = string
  default     = ""
}

variable "keycloak_admin" {
  description = "Keycloak admin username"
  type        = string
  sensitive   = true
  default     = "admin"
}

variable "keycloak_admin_password" {
  description = "Keycloak admin password"
  type        = string
  sensitive   = true
}

variable "keycloak_database_username" {
  description = "Keycloak database username"
  type        = string
  sensitive   = true
  default     = "keycloak"
}

variable "keycloak_database_password" {
  description = "Keycloak database password"
  type        = string
  sensitive   = true
}

variable "keycloak_database_min_acu" {
  description = "Minimum Aurora Capacity Units"
  type        = number
  default     = 0.5
}

variable "keycloak_database_max_acu" {
  description = "Maximum Aurora Capacity Units"
  type        = number
  default     = 2
}

variable "keycloak_log_level" {
  description = "Keycloak log level"
  type        = string
  default     = "INFO"
}

#
# MCP Gateway Services - Container Images
#

variable "registry_image_uri" {
  description = "Container image URI for registry service"
  type        = string
  default     = ""
}

variable "auth_server_image_uri" {
  description = "Container image URI for auth server service"
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

#
# MCP Gateway Services - Replica Counts
#

variable "currenttime_replicas" {
  description = "Number of replicas for CurrentTime MCP server"
  type        = number
  default     = 1
}

variable "mcpgw_replicas" {
  description = "Number of replicas for MCPGW MCP server"
  type        = number
  default     = 1
}

variable "realserverfaketools_replicas" {
  description = "Number of replicas for RealServerFakeTools MCP server"
  type        = number
  default     = 1
}

variable "flight_booking_agent_replicas" {
  description = "Number of replicas for Flight Booking A2A agent"
  type        = number
  default     = 1
}

variable "travel_assistant_agent_replicas" {
  description = "Number of replicas for Travel Assistant A2A agent"
  type        = number
  default     = 1
}

