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


# Keycloak admin password secret (for Management API operations)
resource "aws_secretsmanager_secret" "keycloak_admin_password" {
  name_prefix = "${local.name_prefix}-keycloak-admin-password-"
  description = "Keycloak admin password for Management API user/group operations"
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "keycloak_admin_password" {
  secret_id     = aws_secretsmanager_secret.keycloak_admin_password.id
  secret_string = var.keycloak_admin_password
}


# Embeddings API key secret (optional - only needed for LiteLLM provider)
resource "aws_secretsmanager_secret" "embeddings_api_key" {
  name_prefix = "${local.name_prefix}-embeddings-api-key-"
  description = "API key for embeddings provider (OpenAI, Anthropic, etc.)"
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "embeddings_api_key" {
  secret_id     = aws_secretsmanager_secret.embeddings_api_key.id
  secret_string = var.embeddings_api_key != "" ? var.embeddings_api_key : "not-configured"

  lifecycle {
    ignore_changes = [secret_string]
  }
}