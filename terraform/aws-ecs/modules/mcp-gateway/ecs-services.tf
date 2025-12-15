# ECS Services for MCP Gateway Registry

# ECS Service: Auth Server
module "ecs_service_auth" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "~> 6.0"

  name                     = "${local.name_prefix}-auth"
  cluster_arn              = var.ecs_cluster_arn
  cpu                      = tonumber(var.cpu)
  memory                   = tonumber(var.memory)
  desired_count            = var.enable_autoscaling ? var.autoscaling_min_capacity : var.auth_replicas
  enable_autoscaling       = var.enable_autoscaling
  autoscaling_min_capacity = var.autoscaling_min_capacity
  autoscaling_max_capacity = var.autoscaling_max_capacity
  autoscaling_policies = var.enable_autoscaling ? {
    cpu = {
      policy_type = "TargetTrackingScaling"
      target_tracking_scaling_policy_configuration = {
        predefined_metric_specification = {
          predefined_metric_type = "ECSServiceAverageCPUUtilization"
        }
        target_value = var.autoscaling_target_cpu
      }
    }
    memory = {
      policy_type = "TargetTrackingScaling"
      target_tracking_scaling_policy_configuration = {
        predefined_metric_specification = {
          predefined_metric_type = "ECSServiceAverageMemoryUtilization"
        }
        target_value = var.autoscaling_target_memory
      }
    }
  } : {}

  enable_execute_command = true

  requires_compatibilities = ["FARGATE", "EC2"]
  capacity_provider_strategy = {
    FARGATE = {
      capacity_provider = "FARGATE"
      weight            = 100
      base              = 1
    }
  }

  # Task roles
  create_task_exec_iam_role = true
  task_exec_iam_role_policies = {
    SecretsManagerAccess = aws_iam_policy.ecs_secrets_access.arn
    EcsExecTaskExecution = aws_iam_policy.ecs_exec_task_execution.arn
  }
  create_tasks_iam_role = true
  tasks_iam_role_policies = {
    SecretsManagerAccess = aws_iam_policy.ecs_secrets_access.arn
    EcsExecTask          = aws_iam_policy.ecs_exec_task.arn
  }

  # Enable Service Connect
  service_connect_configuration = {
    namespace = aws_service_discovery_private_dns_namespace.mcp.arn
    service = [{
      client_alias = {
        port     = 8888
        dns_name = "auth-server"
      }
      port_name      = "auth-server"
      discovery_name = "auth-server"
    }]
  }

  # Container definitions
  container_definitions = {
    auth-server = {
      cpu                    = tonumber(var.cpu)
      memory                 = tonumber(var.memory)
      essential              = true
      image                  = var.auth_server_image_uri
      readonlyRootFilesystem = false

      portMappings = [
        {
          name          = "auth-server"
          containerPort = 8888
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "REGISTRY_URL"
          value = "https://${var.domain_name}"
        },
        {
          name  = "AUTH_SERVER_URL"
          value = "http://auth-server:8888"
        },
        {
          name  = "AUTH_SERVER_EXTERNAL_URL"
          value = "https://${var.domain_name}"
        },
        {
          name  = "AWS_REGION"
          value = data.aws_region.current.id
        },
        {
          name  = "AUTH_PROVIDER"
          value = var.keycloak_domain != "" ? "keycloak" : "default"
        },
        {
          name  = "KEYCLOAK_URL"
          value = var.keycloak_domain != "" ? "https://${var.keycloak_domain}" : ""
        },
        {
          name  = "KEYCLOAK_EXTERNAL_URL"
          value = var.keycloak_domain != "" ? "https://${var.keycloak_domain}" : ""
        },
        {
          name  = "KEYCLOAK_REALM"
          value = "mcp-gateway"
        },
        {
          name  = "KEYCLOAK_CLIENT_ID"
          value = "mcp-gateway-web"
        },
        {
          name  = "SCOPES_CONFIG_PATH"
          value = "/efs/auth_config/auth_config/scopes.yml"
        },
        {
          name  = "SESSION_COOKIE_SECURE"
          value = tostring(var.session_cookie_secure)
        },
        {
          name  = "SESSION_COOKIE_DOMAIN"
          value = var.session_cookie_domain
        }
      ]

      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = aws_secretsmanager_secret.secret_key.arn
        },
        {
          name      = "KEYCLOAK_CLIENT_SECRET"
          valueFrom = "${aws_secretsmanager_secret.keycloak_client_secret.arn}:client_secret::"
        }
      ]

      mountPoints = [
        {
          sourceVolume  = "mcp-logs"
          containerPath = "/app/logs"
          readOnly      = false
        },
        {
          sourceVolume  = "auth-config"
          containerPath = "/efs/auth_config"
          readOnly      = false
        }
      ]

      enable_cloudwatch_logging              = true
      cloudwatch_log_group_name              = "/ecs/${local.name_prefix}-auth-server"
      cloudwatch_log_group_retention_in_days = 30

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8888/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  }

  volume = {
    mcp-logs = {
      efs_volume_configuration = {
        file_system_id     = module.efs.id
        access_point_id    = module.efs.access_points["logs"].id
        transit_encryption = "ENABLED"
      }
    }
    auth-config = {
      efs_volume_configuration = {
        file_system_id     = module.efs.id
        access_point_id    = module.efs.access_points["auth_config"].id
        transit_encryption = "ENABLED"
      }
    }
  }

  load_balancer = {
    service = {
      target_group_arn = module.alb.target_groups["auth"].arn
      container_name   = "auth-server"
      container_port   = 8888
    }
  }

  subnet_ids = var.private_subnet_ids
  security_group_ingress_rules = {
    alb_8888 = {
      description                  = "Auth server port from ALB"
      from_port                    = 8888
      to_port                      = 8888
      ip_protocol                  = "tcp"
      referenced_security_group_id = module.alb.security_group_id
    }
  }
  security_group_egress_rules = {
    all = {
      ip_protocol = "-1"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  tags = local.common_tags
}

# ECS Service: Registry (Main service with nginx, SSL, FAISS, models)
module "ecs_service_registry" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "~> 6.0"

  name                     = "${local.name_prefix}-registry"
  cluster_arn              = var.ecs_cluster_arn
  cpu                      = tonumber(var.cpu)
  memory                   = tonumber(var.memory)
  desired_count            = var.enable_autoscaling ? var.autoscaling_min_capacity : var.registry_replicas
  enable_autoscaling       = var.enable_autoscaling
  autoscaling_min_capacity = var.autoscaling_min_capacity
  autoscaling_max_capacity = var.autoscaling_max_capacity
  autoscaling_policies = var.enable_autoscaling ? {
    cpu = {
      policy_type = "TargetTrackingScaling"
      target_tracking_scaling_policy_configuration = {
        predefined_metric_specification = {
          predefined_metric_type = "ECSServiceAverageCPUUtilization"
        }
        target_value = var.autoscaling_target_cpu
      }
    }
    memory = {
      policy_type = "TargetTrackingScaling"
      target_tracking_scaling_policy_configuration = {
        predefined_metric_specification = {
          predefined_metric_type = "ECSServiceAverageMemoryUtilization"
        }
        target_value = var.autoscaling_target_memory
      }
    }
  } : {}

  enable_execute_command = true

  requires_compatibilities = ["FARGATE", "EC2"]
  capacity_provider_strategy = {
    FARGATE = {
      capacity_provider = "FARGATE"
      weight            = 100
      base              = 1
    }
  }

  # Task roles
  create_task_exec_iam_role = true
  task_exec_iam_role_policies = {
    SecretsManagerAccess = aws_iam_policy.ecs_secrets_access.arn
    EcsExecTaskExecution = aws_iam_policy.ecs_exec_task_execution.arn
  }
  create_tasks_iam_role = true
  tasks_iam_role_policies = {
    SecretsManagerAccess = aws_iam_policy.ecs_secrets_access.arn
    EcsExecTask          = aws_iam_policy.ecs_exec_task.arn
  }

  # Enable Service Connect
  service_connect_configuration = {
    namespace = aws_service_discovery_private_dns_namespace.mcp.arn
    service = [{
      client_alias = {
        port     = 7860
        dns_name = "registry"
      }
      port_name      = "registry"
      discovery_name = "registry"
    }]
  }

  # Container definitions
  container_definitions = {
    registry = {
      cpu                    = tonumber(var.cpu)
      memory                 = tonumber(var.memory)
      essential              = true
      image                  = var.registry_image_uri
      readonlyRootFilesystem = false

      portMappings = [
        {
          name          = "http"
          containerPort = 80
          protocol      = "tcp"
        },
        {
          name          = "https"
          containerPort = 443
          protocol      = "tcp"
        },
        {
          name          = "registry"
          containerPort = 7860
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "GATEWAY_ADDITIONAL_SERVER_NAMES"
          value = var.domain_name != "" ? var.domain_name : ""
        },
        {
          name  = "EC2_PUBLIC_DNS"
          value = var.domain_name != "" ? var.domain_name : module.alb.dns_name
        },
        {
          name  = "AUTH_SERVER_URL"
          value = "http://auth-server:8888"
        },
        {
          name  = "AUTH_SERVER_EXTERNAL_URL"
          value = var.domain_name != "" ? "https://${var.domain_name}" : "http://${module.alb.dns_name}"
        },
        {
          name  = "KEYCLOAK_URL"
          value = var.keycloak_domain != "" ? "https://${var.keycloak_domain}" : ""
        },
        {
          name  = "KEYCLOAK_ENABLED"
          value = var.keycloak_domain != "" ? "true" : "false"
        },
        {
          name  = "KEYCLOAK_REALM"
          value = "mcp-gateway"
        },
        {
          name  = "KEYCLOAK_CLIENT_ID"
          value = "mcp-gateway-web"
        },
        {
          name  = "AUTH_PROVIDER"
          value = var.keycloak_domain != "" ? "keycloak" : "default"
        },
        {
          name  = "AWS_REGION"
          value = data.aws_region.current.id
        },
        {
          name  = "SCOPES_CONFIG_PATH"
          value = "/app/auth_server/scopes.yml"
        },
        {
          name  = "EMBEDDINGS_PROVIDER"
          value = var.embeddings_provider
        },
        {
          name  = "EMBEDDINGS_MODEL_NAME"
          value = var.embeddings_model_name
        },
        {
          name  = "EMBEDDINGS_MODEL_DIMENSIONS"
          value = tostring(var.embeddings_model_dimensions)
        },
        {
          name  = "EMBEDDINGS_AWS_REGION"
          value = var.embeddings_aws_region
        },
        {
          name  = "SESSION_COOKIE_SECURE"
          value = tostring(var.session_cookie_secure)
        },
        {
          name  = "SESSION_COOKIE_DOMAIN"
          value = var.session_cookie_domain
        },
        {
          name  = "SECURITY_SCAN_ENABLED"
          value = tostring(var.security_scan_enabled)
        },
        {
          name  = "SECURITY_SCAN_ON_REGISTRATION"
          value = tostring(var.security_scan_on_registration)
        },
        {
          name  = "SECURITY_BLOCK_UNSAFE_SERVERS"
          value = tostring(var.security_block_unsafe_servers)
        },
        {
          name  = "SECURITY_ANALYZERS"
          value = var.security_analyzers
        },
        {
          name  = "SECURITY_SCAN_TIMEOUT"
          value = tostring(var.security_scan_timeout)
        },
        {
          name  = "SECURITY_ADD_PENDING_TAG"
          value = tostring(var.security_add_pending_tag)
        },
        {
          name  = "KEYCLOAK_ADMIN"
          value = "admin"
        }
      ]

      secrets = [
        {
          name      = "SECRET_KEY"
          valueFrom = aws_secretsmanager_secret.secret_key.arn
        },
        {
          name      = "ADMIN_PASSWORD"
          valueFrom = aws_secretsmanager_secret.admin_password.arn
        },
        {
          name      = "KEYCLOAK_CLIENT_SECRET"
          valueFrom = "${aws_secretsmanager_secret.keycloak_client_secret.arn}:client_secret::"
        },
        {
          name      = "KEYCLOAK_M2M_CLIENT_SECRET"
          valueFrom = "${aws_secretsmanager_secret.keycloak_m2m_client_secret.arn}:client_secret::"
        },
        {
          name      = "KEYCLOAK_ADMIN_PASSWORD"
          valueFrom = aws_secretsmanager_secret.keycloak_admin_password.arn
        },
        {
          name      = "EMBEDDINGS_API_KEY"
          valueFrom = aws_secretsmanager_secret.embeddings_api_key.arn
        }
      ]

      mountPoints = [
        {
          sourceVolume  = "mcp-servers"
          containerPath = "/app/registry/servers"
          readOnly      = false
        },
        {
          sourceVolume  = "mcp-agents"
          containerPath = "/app/registry/agents"
          readOnly      = false
        },
        {
          sourceVolume  = "mcp-models"
          containerPath = "/app/registry/models"
          readOnly      = false
        },
        {
          sourceVolume  = "mcp-logs"
          containerPath = "/app/logs"
          readOnly      = false
        },
        {
          sourceVolume  = "auth-config"
          containerPath = "/app/auth_server"
          readOnly      = false
        }
      ]

      enable_cloudwatch_logging              = true
      cloudwatch_log_group_name              = "/ecs/${local.name_prefix}-registry"
      cloudwatch_log_group_retention_in_days = 30

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:7860/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  }

  volume = {
    mcp-servers = {
      efs_volume_configuration = {
        file_system_id     = module.efs.id
        access_point_id    = module.efs.access_points["servers"].id
        transit_encryption = "ENABLED"
      }
    }
    mcp-agents = {
      efs_volume_configuration = {
        file_system_id     = module.efs.id
        access_point_id    = module.efs.access_points["agents"].id
        transit_encryption = "ENABLED"
      }
    }
    mcp-models = {
      efs_volume_configuration = {
        file_system_id     = module.efs.id
        access_point_id    = module.efs.access_points["models"].id
        transit_encryption = "ENABLED"
      }
    }
    mcp-logs = {
      efs_volume_configuration = {
        file_system_id     = module.efs.id
        access_point_id    = module.efs.access_points["logs"].id
        transit_encryption = "ENABLED"
      }
    }
    auth-config = {
      efs_volume_configuration = {
        file_system_id     = module.efs.id
        access_point_id    = module.efs.access_points["auth_config"].id
        transit_encryption = "ENABLED"
      }
    }
  }

  load_balancer = {
    http = {
      target_group_arn = module.alb.target_groups["registry"].arn
      container_name   = "registry"
      container_port   = 80
    }
    gradio = {
      target_group_arn = module.alb.target_groups["gradio"].arn
      container_name   = "registry"
      container_port   = 7860
    }
  }

  subnet_ids = var.private_subnet_ids
  security_group_ingress_rules = {
    alb_80 = {
      description                  = "HTTP port"
      from_port                    = 80
      to_port                      = 80
      ip_protocol                  = "tcp"
      referenced_security_group_id = module.alb.security_group_id
    }
    alb_443 = {
      description                  = "HTTPS port"
      from_port                    = 443
      to_port                      = 443
      ip_protocol                  = "tcp"
      referenced_security_group_id = module.alb.security_group_id
    }
    alb_7860 = {
      description                  = "Gradio port"
      from_port                    = 7860
      to_port                      = 7860
      ip_protocol                  = "tcp"
      referenced_security_group_id = module.alb.security_group_id
    }
  }
  security_group_egress_rules = {
    all = {
      ip_protocol = "-1"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  tags = local.common_tags

  depends_on = [module.ecs_service_auth]
}


# Allow registry to communicate with auth server on port 8888
resource "aws_vpc_security_group_ingress_rule" "registry_to_auth" {
  security_group_id            = module.ecs_service_auth.security_group_id
  referenced_security_group_id = module.ecs_service_registry.security_group_id
  from_port                    = 8888
  to_port                      = 8888
  ip_protocol                  = "tcp"
  description                  = "Allow registry to access auth server"

  tags = local.common_tags
}


# ECS Service: CurrentTime MCP Server
module "ecs_service_currenttime" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "~> 6.0"

  name                     = "${local.name_prefix}-currenttime"
  cluster_arn              = var.ecs_cluster_arn
  cpu                      = "512"
  memory                   = "1024"
  desired_count            = var.enable_autoscaling ? var.autoscaling_min_capacity : var.currenttime_replicas
  enable_autoscaling       = var.enable_autoscaling
  autoscaling_min_capacity = var.autoscaling_min_capacity
  autoscaling_max_capacity = var.autoscaling_max_capacity
  autoscaling_policies = var.enable_autoscaling ? {
    cpu = {
      policy_type = "TargetTrackingScaling"
      target_tracking_scaling_policy_configuration = {
        predefined_metric_specification = {
          predefined_metric_type = "ECSServiceAverageCPUUtilization"
        }
        target_value = var.autoscaling_target_cpu
      }
    }
  } : {}

  enable_execute_command = true

  requires_compatibilities = ["FARGATE", "EC2"]
  capacity_provider_strategy = {
    FARGATE = {
      capacity_provider = "FARGATE"
      weight            = 100
      base              = 1
    }
  }

  create_task_exec_iam_role = true
  task_exec_iam_role_policies = {
    EcsExecTaskExecution = aws_iam_policy.ecs_exec_task_execution.arn
  }
  create_tasks_iam_role = true
  tasks_iam_role_policies = {
    EcsExecTask = aws_iam_policy.ecs_exec_task.arn
  }

  service_connect_configuration = {
    namespace = aws_service_discovery_private_dns_namespace.mcp.arn
    service = [{
      client_alias = {
        port     = 8000
        dns_name = "currenttime-server"
      }
      port_name      = "currenttime"
      discovery_name = "currenttime-server"
    }]
  }

  container_definitions = {
    currenttime-server = {
      cpu                    = 512
      memory                 = 1024
      essential              = true
      image                  = var.currenttime_image_uri
      readonlyRootFilesystem = false

      portMappings = [
        {
          name          = "currenttime"
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "PORT"
          value = "8000"
        },
        {
          name  = "MCP_TRANSPORT"
          value = "streamable-http"
        }
      ]

      enable_cloudwatch_logging              = true
      cloudwatch_log_group_name              = "/ecs/${local.name_prefix}-currenttime"
      cloudwatch_log_group_retention_in_days = 30

      healthCheck = {
        command     = ["CMD-SHELL", "nc -z localhost 8000 || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    }
  }

  subnet_ids = var.private_subnet_ids
  security_group_ingress_rules = {
    service_connect = {
      description                  = "Service Connect from registry"
      from_port                    = 8000
      to_port                      = 8000
      ip_protocol                  = "tcp"
      referenced_security_group_id = module.ecs_service_registry.security_group_id
    }
  }
  security_group_egress_rules = {
    all = {
      ip_protocol = "-1"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  tags = local.common_tags

  depends_on = [module.ecs_service_registry]
}


# ECS Service: MCPGW MCP Server
module "ecs_service_mcpgw" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "~> 6.0"

  name                     = "${local.name_prefix}-mcpgw"
  cluster_arn              = var.ecs_cluster_arn
  cpu                      = "512"
  memory                   = "1024"
  desired_count            = var.enable_autoscaling ? var.autoscaling_min_capacity : var.mcpgw_replicas
  enable_autoscaling       = var.enable_autoscaling
  autoscaling_min_capacity = var.autoscaling_min_capacity
  autoscaling_max_capacity = var.autoscaling_max_capacity
  autoscaling_policies = var.enable_autoscaling ? {
    cpu = {
      policy_type = "TargetTrackingScaling"
      target_tracking_scaling_policy_configuration = {
        predefined_metric_specification = {
          predefined_metric_type = "ECSServiceAverageCPUUtilization"
        }
        target_value = var.autoscaling_target_cpu
      }
    }
  } : {}

  enable_execute_command = true

  requires_compatibilities = ["FARGATE", "EC2"]
  capacity_provider_strategy = {
    FARGATE = {
      capacity_provider = "FARGATE"
      weight            = 100
      base              = 1
    }
  }

  create_task_exec_iam_role = true
  task_exec_iam_role_policies = {
    SecretsManagerAccess = aws_iam_policy.ecs_secrets_access.arn
    EcsExecTaskExecution = aws_iam_policy.ecs_exec_task_execution.arn
  }
  create_tasks_iam_role = true
  tasks_iam_role_policies = {
    SecretsManagerAccess = aws_iam_policy.ecs_secrets_access.arn
    EcsExecTask          = aws_iam_policy.ecs_exec_task.arn
  }

  service_connect_configuration = {
    namespace = aws_service_discovery_private_dns_namespace.mcp.arn
    service = [{
      client_alias = {
        port     = 8003
        dns_name = "mcpgw-server"
      }
      port_name      = "mcpgw"
      discovery_name = "mcpgw-server"
    }]
  }

  container_definitions = {
    mcpgw-server = {
      cpu                    = 512
      memory                 = 1024
      essential              = true
      image                  = var.mcpgw_image_uri
      readonlyRootFilesystem = false

      portMappings = [
        {
          name          = "mcpgw"
          containerPort = 8003
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "PORT"
          value = "8003"
        },
        {
          name  = "REGISTRY_BASE_URL"
          value = "http://registry:7860"
        },
        {
          name  = "REGISTRY_USERNAME"
          value = "admin"
        }
      ]

      secrets = [
        {
          name      = "REGISTRY_PASSWORD"
          valueFrom = aws_secretsmanager_secret.admin_password.arn
        }
      ]

      mountPoints = [
        {
          sourceVolume  = "mcpgw-data"
          containerPath = "/app/data"
          readOnly      = false
        }
      ]

      enable_cloudwatch_logging              = true
      cloudwatch_log_group_name              = "/ecs/${local.name_prefix}-mcpgw"
      cloudwatch_log_group_retention_in_days = 30

      healthCheck = {
        command     = ["CMD-SHELL", "nc -z localhost 8003 || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    }
  }

  volume = {
    mcpgw-data = {
      efs_volume_configuration = {
        file_system_id     = module.efs.id
        access_point_id    = module.efs.access_points["mcpgw_data"].id
        transit_encryption = "ENABLED"
      }
    }
  }

  subnet_ids = var.private_subnet_ids
  security_group_ingress_rules = {
    service_connect = {
      description                  = "Service Connect from registry"
      from_port                    = 8003
      to_port                      = 8003
      ip_protocol                  = "tcp"
      referenced_security_group_id = module.ecs_service_registry.security_group_id
    }
  }
  security_group_egress_rules = {
    all = {
      ip_protocol = "-1"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  tags = local.common_tags

  depends_on = [module.ecs_service_registry]
}


# ECS Service: RealServerFakeTools MCP Server
module "ecs_service_realserverfaketools" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "~> 6.0"

  name                     = "${local.name_prefix}-realserverfaketools"
  cluster_arn              = var.ecs_cluster_arn
  cpu                      = "512"
  memory                   = "1024"
  desired_count            = var.enable_autoscaling ? var.autoscaling_min_capacity : var.realserverfaketools_replicas
  enable_autoscaling       = var.enable_autoscaling
  autoscaling_min_capacity = var.autoscaling_min_capacity
  autoscaling_max_capacity = var.autoscaling_max_capacity
  autoscaling_policies = var.enable_autoscaling ? {
    cpu = {
      policy_type = "TargetTrackingScaling"
      target_tracking_scaling_policy_configuration = {
        predefined_metric_specification = {
          predefined_metric_type = "ECSServiceAverageCPUUtilization"
        }
        target_value = var.autoscaling_target_cpu
      }
    }
  } : {}

  enable_execute_command = true

  requires_compatibilities = ["FARGATE", "EC2"]
  capacity_provider_strategy = {
    FARGATE = {
      capacity_provider = "FARGATE"
      weight            = 100
      base              = 1
    }
  }

  create_task_exec_iam_role = true
  task_exec_iam_role_policies = {
    EcsExecTaskExecution = aws_iam_policy.ecs_exec_task_execution.arn
  }
  create_tasks_iam_role = true
  tasks_iam_role_policies = {
    EcsExecTask = aws_iam_policy.ecs_exec_task.arn
  }

  service_connect_configuration = {
    namespace = aws_service_discovery_private_dns_namespace.mcp.arn
    service = [{
      client_alias = {
        port     = 8002
        dns_name = "realserverfaketools-server"
      }
      port_name      = "realserverfaketools"
      discovery_name = "realserverfaketools-server"
    }]
  }

  container_definitions = {
    realserverfaketools-server = {
      cpu                    = 512
      memory                 = 1024
      essential              = true
      image                  = var.realserverfaketools_image_uri
      readonlyRootFilesystem = false

      portMappings = [
        {
          name          = "realserverfaketools"
          containerPort = 8002
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "PORT"
          value = "8002"
        },
        {
          name  = "MCP_TRANSPORT"
          value = "streamable-http"
        }
      ]

      enable_cloudwatch_logging              = true
      cloudwatch_log_group_name              = "/ecs/${local.name_prefix}-realserverfaketools"
      cloudwatch_log_group_retention_in_days = 30

      healthCheck = {
        command     = ["CMD-SHELL", "nc -z localhost 8002 || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    }
  }

  subnet_ids = var.private_subnet_ids
  security_group_ingress_rules = {
    service_connect = {
      description                  = "Service Connect from registry"
      from_port                    = 8002
      to_port                      = 8002
      ip_protocol                  = "tcp"
      referenced_security_group_id = module.ecs_service_registry.security_group_id
    }
  }
  security_group_egress_rules = {
    all = {
      ip_protocol = "-1"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  tags = local.common_tags

  depends_on = [module.ecs_service_registry]
}


# ECS Service: Flight Booking A2A Agent
module "ecs_service_flight_booking_agent" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "~> 6.0"

  name                     = "${local.name_prefix}-flight-booking-agent"
  cluster_arn              = var.ecs_cluster_arn
  cpu                      = "512"
  memory                   = "1024"
  desired_count            = var.enable_autoscaling ? var.autoscaling_min_capacity : var.flight_booking_agent_replicas
  enable_autoscaling       = var.enable_autoscaling
  autoscaling_min_capacity = var.autoscaling_min_capacity
  autoscaling_max_capacity = var.autoscaling_max_capacity
  autoscaling_policies = var.enable_autoscaling ? {
    cpu = {
      policy_type = "TargetTrackingScaling"
      target_tracking_scaling_policy_configuration = {
        predefined_metric_specification = {
          predefined_metric_type = "ECSServiceAverageCPUUtilization"
        }
        target_value = var.autoscaling_target_cpu
      }
    }
  } : {}

  enable_execute_command = true

  requires_compatibilities = ["FARGATE", "EC2"]
  capacity_provider_strategy = {
    FARGATE = {
      capacity_provider = "FARGATE"
      weight            = 100
      base              = 1
    }
  }

  create_task_exec_iam_role = true
  task_exec_iam_role_policies = {
    EcsExecTaskExecution = aws_iam_policy.ecs_exec_task_execution.arn
  }
  create_tasks_iam_role = true
  tasks_iam_role_policies = {
    EcsExecTask = aws_iam_policy.ecs_exec_task.arn
  }

  service_connect_configuration = {
    namespace = aws_service_discovery_private_dns_namespace.mcp.arn
    service = [{
      client_alias = {
        port     = 9000
        dns_name = "flight-booking-agent"
      }
      port_name      = "flight-booking"
      discovery_name = "flight-booking-agent"
    }]
  }

  container_definitions = {
    flight-booking-agent = {
      cpu                    = 512
      memory                 = 1024
      essential              = true
      image                  = var.flight_booking_agent_image_uri
      readonlyRootFilesystem = false

      portMappings = [
        {
          name          = "flight-booking"
          containerPort = 9000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "AWS_REGION"
          value = data.aws_region.current.id
        },
        {
          name  = "AWS_DEFAULT_REGION"
          value = data.aws_region.current.id
        }
      ]

      enable_cloudwatch_logging              = true
      cloudwatch_log_group_name              = "/ecs/${local.name_prefix}-flight-booking-agent"
      cloudwatch_log_group_retention_in_days = 30

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:9000/ping || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  }

  subnet_ids = var.private_subnet_ids
  security_group_ingress_rules = {
    service_connect = {
      description = "Service Connect - A2A protocol"
      from_port   = 9000
      to_port     = 9000
      ip_protocol = "tcp"
      cidr_ipv4   = data.aws_vpc.vpc.cidr_block
    }
  }
  security_group_egress_rules = {
    all = {
      ip_protocol = "-1"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  tags = local.common_tags

  depends_on = [module.ecs_service_registry]
}


# ECS Service: Travel Assistant A2A Agent
module "ecs_service_travel_assistant_agent" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "~> 6.0"

  name                     = "${local.name_prefix}-travel-assistant-agent"
  cluster_arn              = var.ecs_cluster_arn
  cpu                      = "512"
  memory                   = "1024"
  desired_count            = var.enable_autoscaling ? var.autoscaling_min_capacity : var.travel_assistant_agent_replicas
  enable_autoscaling       = var.enable_autoscaling
  autoscaling_min_capacity = var.autoscaling_min_capacity
  autoscaling_max_capacity = var.autoscaling_max_capacity
  autoscaling_policies = var.enable_autoscaling ? {
    cpu = {
      policy_type = "TargetTrackingScaling"
      target_tracking_scaling_policy_configuration = {
        predefined_metric_specification = {
          predefined_metric_type = "ECSServiceAverageCPUUtilization"
        }
        target_value = var.autoscaling_target_cpu
      }
    }
  } : {}

  enable_execute_command = true

  requires_compatibilities = ["FARGATE", "EC2"]
  capacity_provider_strategy = {
    FARGATE = {
      capacity_provider = "FARGATE"
      weight            = 100
      base              = 1
    }
  }

  create_task_exec_iam_role = true
  task_exec_iam_role_policies = {
    EcsExecTaskExecution = aws_iam_policy.ecs_exec_task_execution.arn
  }
  create_tasks_iam_role = true
  tasks_iam_role_policies = {
    EcsExecTask = aws_iam_policy.ecs_exec_task.arn
  }

  service_connect_configuration = {
    namespace = aws_service_discovery_private_dns_namespace.mcp.arn
    service = [{
      client_alias = {
        port     = 9000
        dns_name = "travel-assistant-agent"
      }
      port_name      = "travel-assistant"
      discovery_name = "travel-assistant-agent"
    }]
  }

  container_definitions = {
    travel-assistant-agent = {
      cpu                    = 512
      memory                 = 1024
      essential              = true
      image                  = var.travel_assistant_agent_image_uri
      readonlyRootFilesystem = false

      portMappings = [
        {
          name          = "travel-assistant"
          containerPort = 9000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "AWS_REGION"
          value = data.aws_region.current.id
        },
        {
          name  = "AWS_DEFAULT_REGION"
          value = data.aws_region.current.id
        }
      ]

      enable_cloudwatch_logging              = true
      cloudwatch_log_group_name              = "/ecs/${local.name_prefix}-travel-assistant-agent"
      cloudwatch_log_group_retention_in_days = 30

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:9000/ping || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  }

  subnet_ids = var.private_subnet_ids
  security_group_ingress_rules = {
    service_connect = {
      description = "Service Connect - A2A protocol"
      from_port   = 9000
      to_port     = 9000
      ip_protocol = "tcp"
      cidr_ipv4   = data.aws_vpc.vpc.cidr_block
    }
  }
  security_group_egress_rules = {
    all = {
      ip_protocol = "-1"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  tags = local.common_tags

  depends_on = [module.ecs_service_registry]
}
