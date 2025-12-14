# IAM resources for MCP Gateway Registry ECS services

# IAM policy for ECS tasks to access Secrets Manager
resource "aws_iam_policy" "ecs_secrets_access" {
  name_prefix = "${local.name_prefix}-ecs-secrets-"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.secret_key.arn,
          aws_secretsmanager_secret.admin_password.arn,
          aws_secretsmanager_secret.keycloak_client_secret.arn,
          aws_secretsmanager_secret.keycloak_m2m_client_secret.arn,
          aws_secretsmanager_secret.embeddings_api_key.arn,
          aws_secretsmanager_secret.keycloak_admin_password.arn
        ]
      }
    ]
  })

  tags = local.common_tags
}

# IAM policy for ECS Exec - task execution role
resource "aws_iam_policy" "ecs_exec_task_execution" {
  name_prefix = "${local.name_prefix}-ecs-exec-task-exec-"

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
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })

  tags = local.common_tags
}

# IAM policy for ECS Exec - task role
resource "aws_iam_policy" "ecs_exec_task" {
  name_prefix = "${local.name_prefix}-ecs-exec-task-"

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

  tags = local.common_tags
}