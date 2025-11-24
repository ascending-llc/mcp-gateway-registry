# Root Module Outputs

# VPC Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "vpc_cidr" {
  description = "VPC CIDR block"
  value       = module.vpc.vpc_cidr_block
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnets
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnets
}

# ECS Cluster Outputs
output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.ecs_cluster.name
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = module.ecs_cluster.arn
}

# MCP Gateway Outputs
output "mcp_gateway_url" {
  description = "MCP Gateway main URL"
  value       = module.mcp_gateway.service_urls.registry
}

output "mcp_gateway_auth_url" {
  description = "MCP Gateway auth server URL"
  value       = module.mcp_gateway.service_urls.auth
}


output "mcp_gateway_alb_dns" {
  description = "MCP Gateway ALB DNS name"
  value       = module.mcp_gateway.alb_dns_name
}

output "mcp_gateway_https_enabled" {
  description = "Whether HTTPS is enabled for MCP Gateway"
  value       = module.mcp_gateway.https_enabled
}

output "mcp_gateway_autoscaling_enabled" {
  description = "Whether auto-scaling is enabled for MCP Gateway"
  value       = module.mcp_gateway.autoscaling_enabled
}

output "mcp_gateway_monitoring_enabled" {
  description = "Whether monitoring is enabled for MCP Gateway"
  value       = module.mcp_gateway.monitoring_enabled
}

# EFS Outputs
output "mcp_gateway_efs_id" {
  description = "MCP Gateway EFS file system ID"
  value       = module.mcp_gateway.efs_id
}

output "mcp_gateway_efs_arn" {
  description = "MCP Gateway EFS file system ARN"
  value       = module.mcp_gateway.efs_arn
}

output "mcp_gateway_efs_access_points" {
  description = "MCP Gateway EFS access point IDs"
  value       = module.mcp_gateway.efs_access_points
}

# Monitoring Outputs
output "monitoring_sns_topic" {
  description = "SNS topic ARN for CloudWatch alarms"
  value       = var.enable_monitoring ? module.mcp_gateway.sns_topic_arn : null
}

# Summary Output
output "deployment_summary" {
  description = "Summary of deployed components"
  value = {
    mcp_gateway_deployed = true
    https_enabled        = aws_acm_certificate.registry.arn != ""
    monitoring_enabled   = var.enable_monitoring
    multi_az_nat         = true
    autoscaling_enabled  = true
  }
}

#
# Keycloak Outputs
#

output "keycloak_url" {
  description = "Keycloak URL"
  value       = "https://${local.keycloak_domain}"
}

output "keycloak_admin_console" {
  description = "Keycloak admin console URL"
  value       = "https://${local.keycloak_domain}/admin"
}

output "keycloak_alb_dns" {
  description = "Keycloak ALB DNS name"
  value       = aws_lb.keycloak.dns_name
}

output "keycloak_ecr_repository" {
  description = "Keycloak ECR repository URL"
  value       = aws_ecr_repository.keycloak.repository_url
}

#
# Registry DNS and Certificate Outputs
#

output "registry_url" {
  description = "Registry URL with custom domain"
  value       = "https://registry.${local.root_domain}"
}

output "registry_certificate_arn" {
  description = "ACM certificate ARN for registry subdomain"
  value       = aws_acm_certificate.registry.arn
}

output "registry_dns_record" {
  description = "Registry DNS A record details"
  value = {
    name    = aws_route53_record.registry.name
    type    = aws_route53_record.registry.type
    zone_id = aws_route53_record.registry.zone_id
  }
}
