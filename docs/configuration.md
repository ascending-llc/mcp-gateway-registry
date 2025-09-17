# Configuration Reference

This document provides a comprehensive reference for all configuration files in the MCP Gateway Registry project. Each configuration file serves a specific purpose in the authentication and operation of the system.

## Configuration Files Overview

| File | Purpose | Type | Location | Example File | User Modification |
|------|---------|------|----------|--------------|-------------------|
| [`.env`](#main-environment-configuration) | Main project environment variables | Environment | Project root | `.env.example` | **Yes** - Required |
| [`.env` (OAuth)](#oauth-environment-configuration) | OAuth provider credentials | Environment | `credentials-provider/oauth/` | `.env.example` | **Yes** - Required |
| [`.env` (AgentCore)](#agentcore-environment-configuration) | AgentCore authentication config | Environment | `credentials-provider/agentcore-auth/` | `.env.example` | **Optional** - Only if using AgentCore |
| [`oauth2_providers.yml`](#oauth2-providers-configuration) | OAuth2 provider definitions | YAML | `auth_server/` | - | **No** - Pre-configured |
| [`scopes.yml`](#scopes-configuration) | Fine-grained access control scopes | YAML | `auth_server/` | - | **Rarely** - Only for custom permissions |
| [`oauth_providers.yaml`](#oauth-providers-mapping) | Provider-specific OAuth configurations | YAML | `credentials-provider/oauth/` | - | **No** - Pre-configured |
| [`docker-compose.yml`](#docker-compose-configuration) | Container orchestration | YAML | Project root | - | **Rarely** - Only for custom deployments |

---

## Main Environment Configuration

**File:** `.env` (Project root)
**Purpose:** Core project settings, registry URLs, and primary authentication credentials.

### Authentication Provider Selection

The MCP Gateway Registry supports multiple authentication providers. Choose one by setting the `AUTH_PROVIDER` environment variable:

- **`keycloak`**: Enterprise-grade open-source identity and access management with individual agent audit trails
- **`cognito`**: Amazon managed authentication service

Based on your selection, configure the corresponding provider-specific variables below.

### Core Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `REGISTRY_URL` | Public URL of the MCP Gateway Registry | `https://mcpgateway.ddns.net` | ✅ |
| `ADMIN_USER` | Registry admin username | `admin` | ✅ |
| `ADMIN_PASSWORD` | Registry admin password | `your-secure-password` | ✅ |
| `AUTH_PROVIDER` | Authentication provider (`cognito` or `keycloak`) | `keycloak` | ✅ |
| `AWS_REGION` | AWS region for services | `us-east-1` | ✅ |

### Keycloak Configuration (if AUTH_PROVIDER=keycloak)

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `KEYCLOAK_URL` | Keycloak server URL (internal/Docker network) | `http://keycloak:8080` | ✅ |
| `KEYCLOAK_EXTERNAL_URL` | Keycloak server URL (external/browser access) | `https://mcpgateway.ddns.net` (production)<br/>`http://localhost:8080` (local development) | ✅ |
| `KEYCLOAK_ADMIN_URL` | Keycloak admin URL (for setup scripts) | `http://localhost:8080` | ✅ |
| `KEYCLOAK_REALM` | Keycloak realm name | `mcp-gateway` | ✅ |
| `KEYCLOAK_ADMIN` | Keycloak admin username | `admin` | ✅ |
| `KEYCLOAK_ADMIN_PASSWORD` | Keycloak admin password | `SecureKeycloakAdmin123!` | ✅ |
| `KEYCLOAK_DB_PASSWORD` | Keycloak database password | `SecureKeycloakDB123!` | ✅ |
| `KEYCLOAK_CLIENT_ID` | Keycloak web client ID (see note below) | `mcp-gateway-web` | ✅ |
| `KEYCLOAK_CLIENT_SECRET` | Keycloak web client secret (auto-generated) | `0tiBtgQFcaBiwHXIxDws...` | ✅ |
| `KEYCLOAK_M2M_CLIENT_ID` | Keycloak M2M client ID (see note below) | `mcp-gateway-m2m` | ✅ |
| `KEYCLOAK_M2M_CLIENT_SECRET` | Keycloak M2M client secret (auto-generated) | `ZJqbsamnQs79hbUbkJLB...` | ✅ |
| `KEYCLOAK_ENABLED` | Enable Keycloak in OAuth2 providers | `true` | ✅ |
| `INITIAL_ADMIN_PASSWORD` | Initial admin user password | `changeme` | For setup |
| `INITIAL_USER_PASSWORD` | Initial test user password | `testpass` | For setup |

**Note: Getting Keycloak Client IDs and Secrets**

The client IDs and secrets are automatically generated when you run the Keycloak initialization script:

```bash
cd keycloak/setup
./init-keycloak.sh
```

The script will:
1. Create the clients with the IDs you specify (`mcp-gateway-web` and `mcp-gateway-m2m`)
2. Generate secure random secrets for each client
3. Display the generated secrets at the end of the script output
4. Save them to a file for your reference

**To retrieve existing client secrets from a running Keycloak instance:**

```bash
# Method 1: Use the helper script (Recommended)
cd keycloak/setup
export KEYCLOAK_ADMIN_PASSWORD="your-admin-password"
./get-all-client-credentials.sh
# This will display the secrets and save them to .oauth-tokens/keycloak-client-secrets.txt

# Method 2: Using Keycloak Admin Console (Web UI)
# 1. Navigate to https://your-keycloak-url/admin
# 2. Login with admin credentials
# 3. Select your realm (mcp-gateway)
# 4. Go to Clients → Select your client
# 5. Go to Credentials tab
# 6. Copy the Secret value

# Method 3: Check the original initialization output
# The init-keycloak.sh script saves secrets to keycloak-client-secrets.txt
cat keycloak/setup/keycloak-client-secrets.txt
```

### Amazon Cognito Configuration (if AUTH_PROVIDER=cognito)

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `COGNITO_USER_POOL_ID` | Amazon Cognito User Pool ID | `us-east-1_vm1115QSU` | ✅ |
| `COGNITO_CLIENT_ID` | Amazon Cognito App Client ID | `3aju04s66t...` | ✅ |
| `COGNITO_CLIENT_SECRET` | Amazon Cognito App Client Secret | `85ps32t55df39hm61k966fqjurj...` | ✅ |
| `COGNITO_DOMAIN` | Cognito domain (optional) | `auto` | Optional |

### Optional Variables

| Variable | Description | Example | Default |
|----------|-------------|---------|---------|
| `AUTH_SERVER_URL` | Internal auth server URL | `http://auth-server:8888` | - |
| `AUTH_SERVER_EXTERNAL_URL` | External auth server URL | `https://mcpgateway.ddns.net` | - |
| `SECRET_KEY` | Application secret key | Auto-generated if not provided | Auto-generated |
| `ATLASSIAN_AUTH_TOKEN` | Atlassian OAuth token | Auto-populated from credentials | - |
| `SRE_GATEWAY_AUTH_TOKEN` | SRE Gateway auth token | Auto-populated from credentials | - |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude models | `sk-ant-api03-...` | For AI functionality |

---

## Keycloak Setup and Configuration

When using Keycloak as your authentication provider, the system provides comprehensive setup scripts and configuration options:

### Initial Setup

Run the Keycloak initialization script to set up the realm, clients, and groups:

```bash
cd keycloak/setup
./init-keycloak.sh
```

This script will:
1. Create the `mcp-gateway` realm
2. Set up web and M2M clients with proper configurations
3. Create necessary groups (`mcp-servers-unrestricted`, `mcp-servers-restricted`)
4. Configure group mappers for JWT token claims
5. Create initial admin and test users

### Service Account Management

For individual AI agent audit trails, create service accounts:

```bash
# Create individual agent service account
./setup-agent-service-account.sh --agent-id sre-agent --group mcp-servers-unrestricted

# Create shared M2M service account
./setup-m2m-service-account.sh
```

### Token Generation

Generate tokens for Keycloak authentication:

```bash
# Generate M2M token for ingress
uv run python credentials-provider/token_refresher.py

# Generate agent-specific token
uv run python credentials-provider/token_refresher.py --agent-id sre-agent
```

For detailed Keycloak integration documentation, see [Keycloak Integration Guide](keycloak-integration.md).

---

## OAuth Environment Configuration

**File:** `credentials-provider/oauth/.env`
**Purpose:** OAuth provider credentials for ingress and egress authentication flows.

### Ingress Authentication

#### For Keycloak (if AUTH_PROVIDER=keycloak)

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `KEYCLOAK_URL` | Keycloak server URL | `https://mcpgateway.ddns.net` | ✅ |
| `KEYCLOAK_REALM` | Keycloak realm | `mcp-gateway` | ✅ |
| `KEYCLOAK_M2M_CLIENT_ID` | M2M client ID | `mcp-gateway-m2m` | ✅ |
| `KEYCLOAK_M2M_CLIENT_SECRET` | M2M client secret | `ZJqbsamnQs79hbUbkJLB...` | ✅ |

#### For Cognito (if AUTH_PROVIDER=cognito)

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
**Purpose:** Amazon Bedrock AgentCore authentication configuration with support for multiple gateways.

### Shared Configuration

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `COGNITO_DOMAIN` | AgentCore Cognito domain URL | `https://your-cognito-domain.auth.region.amazoncognito.com` | ✅ |
| `COGNITO_USER_POOL_ID` | Cognito User Pool ID | `region_your_pool_id` | ✅ |

### Gateway-Specific Configurations

Support for multiple gateways using numbered suffixes (`_1`, `_2`, `_3`, etc., up to `_100`). Each configuration set requires all four parameters:

| Variable Pattern | Description | Example | Required |
|------------------|-------------|---------|----------|
| `AGENTCORE_CLIENT_ID_N` | AgentCore Cognito client ID for gateway N | `your_client_id_here` | ✅ |
| `AGENTCORE_CLIENT_SECRET_N` | AgentCore Cognito client secret for gateway N | `your_client_secret_here` | ✅ |
| `AGENTCORE_GATEWAY_ARN_N` | Amazon Bedrock AgentCore Gateway ARN for gateway N | `arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/my-gateway-1` | ✅ |
| `AGENTCORE_SERVER_NAME_N` | MCP server name for AgentCore gateway N | `my-gateway-1` | ✅ |

**Example Configuration:**
```bash
# Configuration Set 1
AGENTCORE_CLIENT_ID_1=your_client_id_here
AGENTCORE_CLIENT_SECRET_1=your_client_secret_here
AGENTCORE_GATEWAY_ARN_1=arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/my-gateway-1
AGENTCORE_SERVER_NAME_1=my-gateway-1

# Configuration Set 2
AGENTCORE_CLIENT_ID_2=your_client_id_here
AGENTCORE_CLIENT_SECRET_2=your_client_secret_here
AGENTCORE_GATEWAY_ARN_2=arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/my-gateway-2
AGENTCORE_SERVER_NAME_2=my-gateway-2
```

---

## OAuth2 Providers Configuration

**File:** `auth_server/oauth2_providers.yml`
**Purpose:** OAuth2 provider definitions for web-based authentication flows.

### Keycloak Provider Configuration

When using Keycloak as the authentication provider, the following configuration is used:

| Field | Description | Required | Example |
|-------|-------------|----------|---------|
| `display_name` | Human-readable name | ✅ | `"Keycloak"` |
| `client_id` | OAuth client ID | ✅ | `"${KEYCLOAK_CLIENT_ID}"` |
| `client_secret` | OAuth client secret | ✅ | `"${KEYCLOAK_CLIENT_SECRET}"` |
| `auth_url` | Authorization endpoint | ✅ | `"${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/auth"` |
| `token_url` | Token endpoint | ✅ | `"${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token"` |
| `user_info_url` | User info endpoint | ✅ | `"${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/userinfo"` |
| `logout_url` | Logout endpoint | ✅ | `"${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/logout"` |
| `scopes` | OAuth scopes | ✅ | `["openid", "email", "profile"]` |
| `groups_claim` | JWT claim for groups | ✅ | `"groups"` |
| `enabled` | Provider enabled | ✅ | `true` |

### General Provider Configuration Fields

| Field | Description | Required | Example |
|-------|-------------|----------|---------|
| `display_name` | Human-readable provider name | ✅ | `"Amazon Cognito"` |
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

- **Keycloak**: Enterprise-grade open-source identity and access management
- **Amazon Cognito**: Amazon managed authentication service
- **GitHub**: Repository and development services (planned)
- **Google**: Google Workspace and consumer services (planned)

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