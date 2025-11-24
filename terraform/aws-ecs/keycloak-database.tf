#
# Keycloak Aurora MySQL Database (Serverless v2)
#

# RDS Proxy for connection pooling
resource "aws_db_proxy" "keycloak" {
  name          = "keycloak-proxy"
  engine_family = "MYSQL"

  auth {
    auth_scheme = "SECRETS"
    secret_arn  = aws_secretsmanager_secret.keycloak_db_secret.arn
  }

  role_arn               = aws_iam_role.rds_proxy_role.arn
  vpc_subnet_ids         = module.vpc.private_subnets
  vpc_security_group_ids = [aws_security_group.keycloak_db.id]

  require_tls = false

  tags = local.common_tags

  depends_on = [
    aws_secretsmanager_secret_version.keycloak_db_secret
  ]
}

# RDS Proxy Target
resource "aws_db_proxy_target" "keycloak" {
  db_proxy_name         = aws_db_proxy.keycloak.name
  target_group_name     = "default"
  db_cluster_identifier = aws_rds_cluster.keycloak.cluster_identifier

  depends_on = [
    aws_rds_cluster_instance.keycloak
  ]
}

# Aurora MySQL Serverless v2 Cluster
resource "aws_rds_cluster" "keycloak" {
  cluster_identifier = "keycloak"
  engine             = "aurora-mysql"
  engine_version     = "8.0.mysql_aurora.3.08.2"
  database_name      = "keycloak"
  master_username    = var.keycloak_database_username
  master_password    = var.keycloak_database_password

  db_subnet_group_name            = aws_db_subnet_group.keycloak.name
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.keycloak.name
  vpc_security_group_ids          = [aws_security_group.keycloak_db.id]

  # Backup and maintenance
  backup_retention_period      = 7
  preferred_backup_window      = "02:00-04:00"
  preferred_maintenance_window = "sun:04:00-sun:05:00"
  copy_tags_to_snapshot        = true

  # Encryption
  storage_encrypted = true
  kms_key_id        = aws_kms_key.rds.arn

  # Deletion protection
  deletion_protection = false
  skip_final_snapshot = true

  # Serverless v2 scaling
  serverlessv2_scaling_configuration {
    max_capacity = var.keycloak_database_max_acu
    min_capacity = var.keycloak_database_min_acu
  }

  tags = local.common_tags
}

# Aurora Cluster Instance (Serverless v2)
resource "aws_rds_cluster_instance" "keycloak" {
  cluster_identifier = aws_rds_cluster.keycloak.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.keycloak.engine
  engine_version     = aws_rds_cluster.keycloak.engine_version

  performance_insights_enabled = false

  tags = local.common_tags
}

# DB Subnet Group
resource "aws_db_subnet_group" "keycloak" {
  name       = "keycloak-subnet-group"
  subnet_ids = module.vpc.private_subnets

  tags = merge(
    local.common_tags,
    {
      Name = "keycloak-subnet-group"
    }
  )
}

# RDS Cluster Parameter Group
resource "aws_rds_cluster_parameter_group" "keycloak" {
  family      = "aurora-mysql8.0"
  name        = "keycloak-params"
  description = "Keycloak Aurora MySQL parameter group"

  parameter {
    name  = "character_set_server"
    value = "utf8mb4"
  }

  parameter {
    name  = "collation_server"
    value = "utf8mb4_unicode_ci"
  }

  tags = local.common_tags
}

# KMS Key for RDS Encryption
resource "aws_kms_key" "rds" {
  description             = "KMS key for RDS encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = local.common_tags
}

resource "aws_kms_alias" "rds" {
  name          = "alias/keycloak-rds"
  target_key_id = aws_kms_key.rds.key_id
}

# IAM Role for RDS Proxy
resource "aws_iam_role" "rds_proxy_role" {
  name = "keycloak-rds-proxy-role-${var.aws_region}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "rds.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# IAM Policy for RDS Proxy
resource "aws_iam_role_policy" "rds_proxy_policy" {
  name = "keycloak-rds-proxy-policy"
  role = aws_iam_role.rds_proxy_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.keycloak_db_secret.arn
      }
    ]
  })
}

# Secrets Manager Secret for Database Credentials
resource "aws_secretsmanager_secret" "keycloak_db_secret" {
  name                    = "keycloak/database"
  description             = "Keycloak database credentials"
  recovery_window_in_days = 7

  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "keycloak_db_secret" {
  secret_id = aws_secretsmanager_secret.keycloak_db_secret.id
  secret_string = jsonencode({
    username = var.keycloak_database_username
    password = var.keycloak_database_password
  })
}

# SSM Parameters for Database Connection
resource "aws_ssm_parameter" "keycloak_database_url" {
  name  = "/keycloak/database/url"
  type  = "SecureString"
  value = "jdbc:mysql://${aws_rds_cluster.keycloak.endpoint}:3306/keycloak"
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "keycloak_database_username" {
  name  = "/keycloak/database/username"
  type  = "SecureString"
  value = var.keycloak_database_username
  tags  = local.common_tags
}

resource "aws_ssm_parameter" "keycloak_database_password" {
  name  = "/keycloak/database/password"
  type  = "SecureString"
  value = var.keycloak_database_password
  tags  = local.common_tags
}
