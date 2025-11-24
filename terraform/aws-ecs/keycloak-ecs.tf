#
# Keycloak ECS Service
#

locals {
  keycloak_container_env = [
    {
      name  = "AWS_REGION"
      value = var.aws_region
    },
    {
      name  = "KC_PROXY"
      value = "edge"
    },
    {
      name  = "KC_PROXY_ADDRESS_FORWARDING"
      value = "true"
    },
    {
      name  = "KC_HOSTNAME"
      value = local.keycloak_domain
    },
    {
      name  = "KC_HOSTNAME_STRICT"
      value = "false"
    },
    {
      name  = "KC_HOSTNAME_STRICT_HTTPS"
      value = "false"
    },
    {
      name  = "KC_HEALTH_ENABLED"
      value = "true"
    },
    {
      name  = "KC_METRICS_ENABLED"
      value = "true"
    },
    {
      name  = "KEYCLOAK_LOGLEVEL"
      value = var.keycloak_log_level
    }
  ]

  keycloak_container_secrets = [
    {
      name      = "KEYCLOAK_ADMIN"
      valueFrom = aws_ssm_parameter.keycloak_admin.arn
    },
    {
      name      = "KEYCLOAK_ADMIN_PASSWORD"
      valueFrom = aws_ssm_parameter.keycloak_admin_password.arn
    },
    {
      name      = "KC_DB_URL"
      valueFrom = aws_ssm_parameter.keycloak_database_url.arn
    },
    {
      name      = "KC_DB_USERNAME"
      valueFrom = aws_ssm_parameter.keycloak_database_username.arn
    },
    {
      name      = "KC_DB_PASSWORD"
      valueFrom = aws_ssm_parameter.keycloak_database_password.arn
    }
  ]
}

# ECS Cluster for Keycloak
resource "aws_ecs_cluster" "keycloak" {
  name = "keycloak"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
}

resource "aws_ecs_cluster_capacity_providers" "keycloak" {
  cluster_name       = aws_ecs_cluster.keycloak.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "keycloak" {
  name              = "/ecs/keycloak"
  retention_in_days = 7

  tags = local.common_tags
}

# ECS Task Execution Role
resource "aws_iam_role" "keycloak_task_exec_role" {
  name = "keycloak-task-exec-role-${var.aws_region}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# Attach default ECS task execution policy
resource "aws_iam_role_policy_attachment" "keycloak_task_exec_role_policy" {
  role       = aws_iam_role.keycloak_task_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Policy to read from SSM Parameter Store
resource "aws_iam_role_policy" "keycloak_task_exec_ssm_policy" {
  name = "keycloak-task-exec-ssm-policy"
  role = aws_iam_role.keycloak_task_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        Resource = [
          aws_ssm_parameter.keycloak_admin.arn,
          aws_ssm_parameter.keycloak_admin_password.arn,
          aws_ssm_parameter.keycloak_database_url.arn,
          aws_ssm_parameter.keycloak_database_username.arn,
          aws_ssm_parameter.keycloak_database_password.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = "*"
      }
    ]
  })
}

# Policy to write logs to CloudWatch
resource "aws_iam_role_policy" "keycloak_task_exec_logs_policy" {
  name = "keycloak-task-exec-logs-policy"
  role = aws_iam_role.keycloak_task_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.keycloak.arn}:*"
      }
    ]
  })
}

# ECS Task Role
resource "aws_iam_role" "keycloak_task_role" {
  name = "keycloak-task-role-${var.aws_region}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# Policy for SSM Session Manager
resource "aws_iam_role_policy" "keycloak_task_ssm_policy" {
  name = "keycloak-task-ssm-policy"
  role = aws_iam_role.keycloak_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
        ]
        Resource = "*"
      }
    ]
  })
}

# ECS Task Definition
resource "aws_ecs_task_definition" "keycloak" {
  family                   = "keycloak"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.keycloak_task_exec_role.arn
  task_role_arn            = aws_iam_role.keycloak_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "keycloak"
      image     = "${aws_ecr_repository.keycloak.repository_url}:latest"
      essential = true

      portMappings = [
        {
          name          = "keycloak"
          containerPort = 8080
          hostPort      = 8080
          protocol      = "tcp"
        },
        {
          name          = "keycloak-management"
          containerPort = 9000
          hostPort      = 9000
          protocol      = "tcp"
        }
      ]

      environment = local.keycloak_container_env

      secrets = local.keycloak_container_secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.keycloak.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      readonlyRootFilesystem = false

      healthCheck = {
        command     = ["CMD-SHELL", "exit 0"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = local.common_tags
}

# ECS Service
resource "aws_ecs_service" "keycloak" {
  name            = "keycloak"
  cluster         = aws_ecs_cluster.keycloak.id
  task_definition = aws_ecs_task_definition.keycloak.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.keycloak_ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.keycloak.arn
    container_name   = "keycloak"
    container_port   = 8080
  }

  depends_on = [
    aws_lb_listener.keycloak_https,
    aws_iam_role_policy.keycloak_task_exec_ssm_policy,
    aws_iam_role_policy.keycloak_task_exec_logs_policy
  ]

  tags = local.common_tags
}

# Auto Scaling Target
resource "aws_appautoscaling_target" "keycloak" {
  max_capacity       = 4
  min_capacity       = 1
  resource_id        = "service/${aws_ecs_cluster.keycloak.name}/${aws_ecs_service.keycloak.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  tags = local.common_tags
}

# Auto Scaling Policy - CPU
resource "aws_appautoscaling_policy" "keycloak_cpu" {
  name               = "keycloak-cpu-autoscaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.keycloak.resource_id
  scalable_dimension = aws_appautoscaling_target.keycloak.scalable_dimension
  service_namespace  = aws_appautoscaling_target.keycloak.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}

# Auto Scaling Policy - Memory
resource "aws_appautoscaling_policy" "keycloak_memory" {
  name               = "keycloak-memory-autoscaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.keycloak.resource_id
  scalable_dimension = aws_appautoscaling_target.keycloak.scalable_dimension
  service_namespace  = aws_appautoscaling_target.keycloak.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value = 80.0
  }
}

# SSM Parameters for Keycloak Credentials
resource "aws_ssm_parameter" "keycloak_admin" {
  name  = "/keycloak/admin"
  type  = "SecureString"
  value = var.keycloak_admin
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "keycloak_admin_password" {
  name  = "/keycloak/admin_password"
  type  = "SecureString"
  value = var.keycloak_admin_password
  tags  = local.common_tags
}
