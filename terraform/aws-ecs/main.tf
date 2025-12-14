# MCP Gateway Registry - AWS ECS Deployment
# This Terraform configuration deploys the MCP Gateway to AWS ECS Fargate

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# MCP Gateway Module
module "mcp_gateway" {
  source = "./modules/mcp-gateway"

  # Basic configuration
  name = "${var.name}-v2"

  # Network configuration
  vpc_id              = module.vpc.vpc_id
  private_subnet_ids  = module.vpc.private_subnets
  public_subnet_ids   = module.vpc.public_subnets
  ingress_cidr_blocks = var.ingress_cidr_blocks

  # ECS configuration
  ecs_cluster_arn         = module.ecs_cluster.arn
  ecs_cluster_name        = module.ecs_cluster.name
  task_execution_role_arn = module.ecs_cluster.task_exec_iam_role_arn

  # HTTPS configuration
  certificate_arn = aws_acm_certificate.registry.arn
  domain_name     = "registry.${local.root_domain}"

  # Keycloak configuration
  keycloak_domain = local.keycloak_domain

  # Container images
  registry_image_uri               = var.registry_image_uri
  auth_server_image_uri            = var.auth_server_image_uri
  currenttime_image_uri            = var.currenttime_image_uri
  mcpgw_image_uri                  = var.mcpgw_image_uri
  realserverfaketools_image_uri    = var.realserverfaketools_image_uri
  flight_booking_agent_image_uri   = var.flight_booking_agent_image_uri
  travel_assistant_agent_image_uri = var.travel_assistant_agent_image_uri

  # Service replicas
  currenttime_replicas            = var.currenttime_replicas
  mcpgw_replicas                  = var.mcpgw_replicas
  realserverfaketools_replicas    = var.realserverfaketools_replicas
  flight_booking_agent_replicas   = var.flight_booking_agent_replicas
  travel_assistant_agent_replicas = var.travel_assistant_agent_replicas

  # Auto-scaling configuration
  enable_autoscaling        = true
  autoscaling_min_capacity  = 2
  autoscaling_max_capacity  = 4
  autoscaling_target_cpu    = 70
  autoscaling_target_memory = 80

  # Monitoring configuration
  enable_monitoring = var.enable_monitoring
  alarm_email       = var.alarm_email

  # Embeddings configuration
  embeddings_provider         = var.embeddings_provider
  embeddings_model_name       = var.embeddings_model_name
  embeddings_model_dimensions = var.embeddings_model_dimensions
  embeddings_aws_region       = var.embeddings_aws_region
  embeddings_api_key          = var.embeddings_api_key

  # Keycloak admin credentials (for Management API)
  keycloak_admin_password = var.keycloak_admin_password

  # Session cookie security configuration
  session_cookie_secure = var.session_cookie_secure
  session_cookie_domain = var.session_cookie_domain
}
