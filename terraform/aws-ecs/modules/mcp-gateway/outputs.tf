# MCP Gateway Registry Module Outputs





# Main ALB outputs
output "alb_dns_name" {
  description = "DNS name of the MCP Gateway Registry ALB"
  value       = module.alb.dns_name
  sensitive   = false
}

output "alb_zone_id" {
  description = "Zone ID of the MCP Gateway Registry ALB"
  value       = module.alb.zone_id
  sensitive   = false
}

output "alb_arn" {
  description = "ARN of the MCP Gateway Registry ALB"
  value       = module.alb.arn
  sensitive   = false
}

output "alb_security_group_id" {
  description = "ID of the ALB security group"
  value       = module.alb.security_group_id
  sensitive   = false
}





# Service URLs
output "service_urls" {
  description = "URLs for MCP Gateway Registry services"
  value = {
    registry = var.domain_name != "" ? "https://${var.domain_name}" : "http://${module.alb.dns_name}"
    auth     = var.domain_name != "" ? "https://${var.domain_name}" : "http://${module.alb.dns_name}"
    gradio   = var.domain_name != "" ? "https://${var.domain_name}" : "http://${module.alb.dns_name}"
  }
  sensitive = false
}

# EFS outputs
output "efs_id" {
  description = "MCP Gateway Registry EFS file system ID"
  value       = module.efs.id
  sensitive   = false
}

output "efs_arn" {
  description = "MCP Gateway Registry EFS file system ARN"
  value       = module.efs.arn
  sensitive   = false
}

output "efs_access_points" {
  description = "EFS access point IDs"
  value = {
    servers     = module.efs.access_points["servers"].id
    models      = module.efs.access_points["models"].id
    logs        = module.efs.access_points["logs"].id
    auth_config = module.efs.access_points["auth_config"].id
  }
  sensitive = false
}

# Service Discovery outputs
output "service_discovery_namespace_id" {
  description = "MCP Gateway Registry service discovery namespace ID"
  value       = aws_service_discovery_private_dns_namespace.mcp.id
  sensitive   = false
}

output "service_discovery_namespace_arn" {
  description = "MCP Gateway Registry service discovery namespace ARN"
  value       = aws_service_discovery_private_dns_namespace.mcp.arn
  sensitive   = false
}

# Secrets Manager outputs
output "secret_arns" {
  description = "ARNs of MCP Gateway Registry secrets"
  value = {
    secret_key     = aws_secretsmanager_secret.secret_key.arn
    admin_password = aws_secretsmanager_secret.admin_password.arn
  }
  sensitive = false
}

# ECS Service outputs
output "ecs_service_arns" {
  description = "ARNs of the ECS services"
  value = {
    auth     = module.ecs_service_auth.id
    registry = module.ecs_service_registry.id
  }
  sensitive = false
}

output "ecs_service_names" {
  description = "Names of the ECS services"
  value = {
    auth     = module.ecs_service_auth.name
    registry = module.ecs_service_registry.name
  }
  sensitive = false
}

# Security Group outputs
output "ecs_security_group_ids" {
  description = "Security group IDs for ECS services"
  value = {
    auth     = module.ecs_service_auth.security_group_id
    registry = module.ecs_service_registry.security_group_id
  }
  sensitive = false
}

# Admin credentials output (for initial setup)
output "admin_credentials" {
  description = "Admin credentials for initial MCP Gateway Registry setup"
  value = {
    username = "admin"
    # Note: Password is stored in AWS Secrets Manager
    password_secret_arn = aws_secretsmanager_secret.admin_password.arn
  }
  sensitive = false
}


# Monitoring outputs
output "monitoring_enabled" {
  description = "Whether monitoring is enabled"
  value       = var.enable_monitoring
}

output "sns_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarms"
  value       = var.enable_monitoring && var.alarm_email != "" ? module.sns_alarms.topic_arn : null
}

output "autoscaling_enabled" {
  description = "Whether auto-scaling is enabled"
  value       = var.enable_autoscaling
}

output "https_enabled" {
  description = "Whether HTTPS is enabled"
  value       = var.certificate_arn != ""
}