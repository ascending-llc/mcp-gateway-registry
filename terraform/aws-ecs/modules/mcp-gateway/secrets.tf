# Secrets Manager resources for MCP Gateway Registry

# Random passwords for application secrets

resource "random_password" "secret_key" {
  length  = 64
  special = true
}

resource "random_password" "admin_password" {
  length      = 32
  special     = true
  min_lower   = 1
  min_upper   = 1
  min_numeric = 1
  min_special = 1
}

# Core application secrets

resource "aws_secretsmanager_secret" "secret_key" {
  name_prefix = "${local.name_prefix}-secret-key-"
  description = "Secret key for MCP Gateway Registry"
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "secret_key" {
  secret_id     = aws_secretsmanager_secret.secret_key.id
  secret_string = random_password.secret_key.result
}

resource "aws_secretsmanager_secret" "admin_password" {
  name_prefix = "${local.name_prefix}-admin-password-"
  description = "Admin password for MCP Gateway Registry"
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "admin_password" {
  secret_id     = aws_secretsmanager_secret.admin_password.id
  secret_string = random_password.admin_password.result
}

# Keycloak client secrets (created with placeholder, updated by init-keycloak.sh)
resource "aws_secretsmanager_secret" "keycloak_client_secret" {
  name        = "mcp-gateway-keycloak-client-secret"
  description = "Keycloak web client secret (updated by init-keycloak.sh after deployment)"
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "keycloak_client_secret" {
  secret_id = aws_secretsmanager_secret.keycloak_client_secret.id
  secret_string = jsonencode({
    client_secret = "placeholder-will-be-updated-by-init-script"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

resource "aws_secretsmanager_secret" "keycloak_m2m_client_secret" {
  name        = "mcp-gateway-keycloak-m2m-client-secret"
  description = "Keycloak M2M client secret (updated by init-keycloak.sh after deployment)"
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "keycloak_m2m_client_secret" {
  secret_id = aws_secretsmanager_secret.keycloak_m2m_client_secret.id
  secret_string = jsonencode({
    client_secret = "placeholder-will-be-updated-by-init-script"
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}