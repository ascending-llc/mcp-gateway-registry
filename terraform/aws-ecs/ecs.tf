data "aws_region" "current" {}
data "aws_partition" "current" {}

# ECS Cluster using terraform-aws-modules/ecs/aws//modules/cluster
module "ecs_cluster" {
  source  = "terraform-aws-modules/ecs/aws//modules/cluster"
  version = "~> 6.0"

  name = "${var.name}-ecs-cluster"

  configuration = {
    execute_command_configuration = {
      logging = "OVERRIDE"
      log_configuration = {
        cloud_watch_log_group_name = "/aws/ecs/${var.name}"
      }
    }
  }

  # Enable containerInsights
  setting = [
    {
      name  = "containerInsights"
      value = "enabled"
    }
  ]

  # Cluster capacity providers - Fargate only
  default_capacity_provider_strategy = {
    FARGATE = {
      weight = 50
      base   = 1
    }
  }

  # Create task execution role
  create_task_exec_iam_role = true
  task_exec_iam_role_name   = "${var.name}-task-execution"

  # Additional policies for task execution role
  task_exec_iam_role_policies = {
    AmazonECSTaskExecutionRolePolicy = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
  }

  tags = {
    Name = "${var.name} ECS Cluster"
  }
}