# Configuration Reference

This document provides a comprehensive reference for all configuration files in the MCP Gateway Registry project. Each configuration file serves a specific purpose in the authentication and operation of the system.

## Configuration Files Overview

| File | Purpose | Type | Location | Example File | User Modification |
|------|---------|------|----------|--------------|-------------------|
| [`.env`](#main-environment-configuration) | Main project environment variables | Environment | Project root | `.env.example` | **Yes** - Required |
| [`.env` (OAuth)](#oauth-environment-configuration) | OAuth provider credentials | Environment | `credentials-provider/oauth/` | `.env.example` | **Yes** - Required |
| [`.env` (AgentCore)](#agentcore-environment-configuration) | AgentCore authentication config | Environment | `credentials-provider/agentcore-auth/` | `.env.example` | **Optional** - Only if using AgentCore |
| [`config.yaml` (AgentCore)](#agentcore-yaml-configuration) | AgentCore gateway settings | YAML | `credentials-provider/agentcore-auth/` | `config.yaml.example` | **Optional** - Only if using AgentCore |
| [`oauth2_providers.yml`](#oauth2-providers-configuration) | OAuth2 provider definitions | YAML | `auth_server/` | - | **No** - Pre-configured |
| [`scopes.yml`](#scopes-configuration) | Fine-grained access control scopes | YAML | `auth_server/` | - | **Rarely** - Only for custom permissions |
| [`oauth_providers.yaml`](#oauth-providers-mapping) | Provider-specific OAuth configurations | YAML | `credentials-provider/oauth/` | - | **No** - Pre-configured |
| [`docker-compose.yml`](#docker-compose-configuration) | Container orchestration | YAML | Project root | - | **Rarely** - Only for custom deployments |

---

## Main Environment Configuration

**File:** `.env` (Project root)
**Purpose:** Core project settings, registry URLs, and primary authentication credentials.

### Required Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `REGISTRY_URL` | Public URL of the MCP Gateway Registry | `https://mcpgateway.ddns.net` | ✅ |
| `ADMIN_USER` | Registry admin username | `admin` | ✅ |
| `ADMIN_PASSWORD` | Registry admin password | `your-secure-password` | ✅ |
| `AWS_REGION` | AWS region for Cognito services | `us-east-1` | ✅ |
| `COGNITO_USER_POOL_ID` | AWS Cognito User Pool ID | `us-east-1_vm1115QSU` | ✅ |
| `COGNITO_CLIENT_ID` | AWS Cognito App Client ID | `3aju04s66t...` | ✅ |
| `COGNITO_CLIENT_SECRET` | AWS Cognito App Client Secret | `85ps32t55df39hm61k966fqjurj...` | ✅ |

### Optional Variables

| Variable | Description | Example | Default |
|----------|-------------|---------|---------|
| `AUTH_SERVER_URL` | Internal auth server URL | `http://auth-server:8888` | - |
| `AUTH_SERVER_EXTERNAL_URL` | External auth server URL | `https://mcpgateway.ddns.net` | - |
| `SECRET_KEY` | Application secret key | Auto-generated if not provided | Auto-generated |
| `ATLASSIAN_AUTH_TOKEN` | Atlassian OAuth token | Auto-populated from credentials | - |
| `SRE_GATEWAY_AUTH_TOKEN` | SRE Gateway auth token | Auto-populated from credentials | - |

---

## OAuth Environment Configuration

**File:** `credentials-provider/oauth/.env`
**Purpose:** OAuth provider credentials for ingress and egress authentication flows.

### Ingress Authentication (Required)

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `INGRESS_OAUTH_USER_POOL_ID` | Cognito User Pool for ingress auth | `us-east-1_vm1115QSU` | ✅ |
| `INGRESS_OAUTH_CLIENT_ID` | Cognito client ID for ingress | `5v2rav1v93...` | ✅ |
| `INGRESS_OAUTH_CLIENT_SECRET` | Cognito client secret for ingress | `1i888fnolv6k5sa1b8s5k839pdm...` | ✅ |

### Egress Authentication (Optional)

Support for multiple OAuth provider configurations using numbered suffixes (`_1`, `_2`, `_3`, etc.):

| Variable Pattern | Description | Example | Required |
|------------------|-------------|---------|----------|
| `EGRESS_OAUTH_CLIENT_ID_N` | OAuth client ID for provider N | `cNYWTFwyZB...` | For each provider |
| `EGRESS_OAUTH_CLIENT_SECRET_N` | OAuth client secret for provider N | `ATOAubT-N-lAzpT05RDFq9dxcVr...` | For each provider |
| `EGRESS_OAUTH_REDIRECT_URI_N` | OAuth redirect URI for provider N | `http://localhost:8080/callback` | For each provider |
| `EGRESS_OAUTH_SCOPE_N` | OAuth scopes for provider N | Uses provider defaults if not set | Optional |
| `EGRESS_PROVIDER_NAME_N` | Provider name (atlassian, google, etc.) | `atlassian` | For each provider |
| `EGRESS_MCP_SERVER_NAME_N` | MCP server name for provider N | `atlassian` | For each provider |

### Supported Providers

- **Atlassian**: Confluence, Jira integration
- **Google**: Gmail, Drive, Calendar services  
- **GitHub**: Repository and issue management
- **Microsoft**: Office 365, Teams integration
- **Bedrock AgentCore**: AWS AgentCore services

---

## AgentCore Environment Configuration

**File:** `credentials-provider/agentcore-auth/.env`
**Purpose:** Amazon Bedrock AgentCore authentication configuration.

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `COGNITO_DOMAIN` | AgentCore Cognito domain URL | `https://test-genesis.auth.us-west-2.amazoncognito.com` | ✅ |
| `COGNITO_CLIENT_ID` | AgentCore Cognito client ID | `2aushg8dlg6r4hbb7g3huka1j8` | ✅ |
| `COGNITO_CLIENT_SECRET` | AgentCore Cognito client secret | `1jd8cnm2npnq6fv397v67s6bm5...` | ✅ |

---

## AgentCore YAML Configuration

**File:** `credentials-provider/agentcore-auth/config.yaml`
**Purpose:** AgentCore gateway settings and Cognito configuration.

| Field | Description | Example | Required |
|-------|-------------|---------|----------|
| `gateway_arn` | Amazon Bedrock AgentCore Gateway ARN | `arn:aws:bedrock-agentcore:us-east-1:015469603702:gateway/sre-gateway-i7ge1zayhw` | ✅ |
| `server_name` | MCP server name for AgentCore | `sre-gateway` | ✅ |
| `user_pool_id` | Cognito User Pool ID | `us-west-2_moykgwumT` | ✅ |
| `client_id` | Cognito client ID | `2aushg8dlg6r4hbb7g3huka1j8` | ✅ |

---

## OAuth2 Providers Configuration

**File:** `auth_server/oauth2_providers.yml`
**Purpose:** OAuth2 provider definitions for web-based authentication flows.

### Provider Configuration Fields

| Field | Description | Required | Example |
|-------|-------------|----------|---------|
| `display_name` | Human-readable provider name | ✅ | `"AWS Cognito"` |
| `client_id` | OAuth client ID (can use env vars) | ✅ | `"${COGNITO_CLIENT_ID}"` |
| `client_secret` | OAuth client secret (can use env vars) | ✅ | `"${COGNITO_CLIENT_SECRET}"` |
| `auth_url` | Authorization endpoint URL | ✅ | `"https://domain.auth.region.amazoncognito.com/oauth2/authorize"` |
| `token_url` | Token endpoint URL | ✅ | `"https://domain.auth.region.amazoncognito.com/oauth2/token"` |
| `user_info_url` | User info endpoint URL | ✅ | `"https://domain.auth.region.amazoncognito.com/oauth2/userInfo"` |
| `logout_url` | Logout endpoint URL | ✅ | `"https://domain.auth.region.amazoncognito.com/logout"` |
| `scopes` | OAuth scopes array | ✅ | `["openid", "email", "profile"]` |
| `response_type` | OAuth response type | ✅ | `"code"` |
| `grant_type` | OAuth grant type | ✅ | `"authorization_code"` |
| `username_claim` | JWT claim for username | ✅ | `"email"` |
| `groups_claim` | JWT claim for groups | ❌ | `"cognito:groups"` |
| `email_claim` | JWT claim for email | ✅ | `"email"` |
| `name_claim` | JWT claim for name | ✅ | `"name"` |
| `enabled` | Whether provider is enabled | ✅ | `true` |

### Supported Providers

- **AWS Cognito**: Primary authentication provider
- **GitHub**: Repository and development services
- **Google**: Google Workspace and consumer services

---

## Scopes Configuration

**File:** `auth_server/scopes.yml`
**Purpose:** Fine-grained access control (FGAC) scope definitions.

### Scope Categories

- **MCP Servers**: Individual server access (`mcp-servers-{name}/read`, `mcp-servers-{name}/execute`)
- **Unrestricted**: Global access (`mcp-servers-unrestricted/read`, `mcp-servers-unrestricted/execute`)
- **Admin**: Administrative functions (`admin/registry`, `admin/users`)

---

## OAuth Providers Mapping

**File:** `credentials-provider/oauth/oauth_providers.yaml`
**Purpose:** Provider-specific OAuth endpoint configurations and metadata.

### Provider Fields

| Field | Description | Example |
|-------|-------------|---------|
| `auth_url` | OAuth authorization URL | `https://api.atlassian.com/ex/oauth/authorize` |
| `token_url` | OAuth token exchange URL | `https://api.atlassian.com/ex/oauth/token` |
| `scopes` | Default OAuth scopes | `["read:confluence-content.all", "write:confluence-content"]` |
| `client_credentials_supported` | Whether provider supports client credentials flow | `false` |

---

## Docker Compose Configuration

**File:** `docker-compose.yml`
**Purpose:** Container orchestration for development and deployment.

### Services

- **registry**: Main MCP Gateway Registry service
- **auth-server**: OAuth2 authentication server
- **frontend**: Web interface (React application)

### Key Configuration

- Environment variable injection from `.env` files
- Port mappings for local development
- Volume mounts for persistent data
- Health checks and restart policies

---

## Configuration Security

### Best Practices

1. **Never commit real credentials** to version control
2. **Use environment variables** for sensitive data
3. **Rotate credentials regularly** especially for production
4. **Limit scope permissions** to minimum required access
5. **Monitor credential usage** through logging and audit trails

### File Permissions

- `.env` files should have `600` permissions (readable only by owner)
- Configuration directories should have `700` permissions
- Generated token files are automatically secured with `600` permissions

---

## Troubleshooting

### Common Issues

1. **Missing environment variables**: Check that all required variables are set in the appropriate `.env` files
2. **Invalid credentials**: Verify OAuth client IDs and secrets with providers
3. **Network connectivity**: Ensure firewall rules allow OAuth callback URLs
4. **Token expiration**: Use the credential refresh scripts to update expired tokens
5. **Scope mismatches**: Verify requested OAuth scopes match provider configurations

### Validation Commands

```bash
# Validate OAuth configuration
cd credentials-provider
./generate_creds.sh --verbose

# Test MCP gateway connectivity
cd tests
./mcp_cmds.sh ping

# Check configuration files
python -c "import yaml; yaml.safe_load(open('file.yml'))"  # YAML validation
```

### Log Files

- **OAuth flows**: `.oauth-tokens/` directory contains generated tokens and logs
- **Registry operations**: Check `registry.log` for service-level issues
- **Authentication**: Check `auth.log` for OAuth and FGAC issues