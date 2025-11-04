# Microsoft Entra ID (Azure AD) Setup Guide

This guide provides step-by-step instructions for setting up Microsoft Entra ID (formerly Azure AD) as an authentication provider in the MCP Gateway Registry.

## Prerequisites

- An Azure subscription with Entra ID (Azure AD) tenant
- Access to the Azure Portal with administrative privileges
- MCP Gateway Registry deployed and accessible

## Step 1: Create App Registration in Azure Portal

1. **Navigate to Azure Portal**
   - Go to [Azure Portal](https://portal.azure.com)
   - Navigate to **Azure Active Directory** > **App registrations**

2. **Create New Registration**
   - Click **New registration**
   - **Name**: `MCP Gateway Registry` (or your preferred name)
   - **Supported account types**: 
     - For single tenant: *Accounts in this organizational directory only*
     - For multi-tenant: *Accounts in any organizational directory*
   - **Redirect URI**: 
     - Type: **Web**
     - URI: `https://your-registry-domain/auth/callback`
     - Replace `your-registry-domain` with your actual registry URL

3. **Register the Application**
   - Click **Register**
   - Note down the **Application (client) ID** and **Directory (tenant) ID**

## Step 2: Configure Authentication

1. **Configure Platform Settings**
   - In your app registration, go to **Authentication**
   - Under **Platform configurations**, ensure your redirect URI is listed
   - **Implicit grant**: Enable **ID tokens** (recommended)

2. **Configure API Permissions**
   - Go to **API permissions**
   - Click **Add a permission** > **Microsoft Graph** > **Delegated permissions**
   - Add the following permissions:
     - `email` - Read user email address
     - `openid` - Sign users in
     - `profile` - Read user profile
     - `User.Read` - Read user's full profile
   - Click **Add permissions**
   - **Grant admin consent** for the permissions

## Step 3: Create Client Secret

1. **Generate New Secret**
   - In your app registration, go to **Certificates & secrets**
   - Click **New client secret**
   - **Description**: `MCP Gateway Registry Secret`
   - **Expires**: Choose appropriate expiration (recommended: 12-24 months)
   - Click **Add**

2. **Copy the Secret Value**
   - **Important**: Copy the secret value immediately - it won't be shown again
   - Store this securely

## Step 4: Environment Configuration

Add the following environment variables to your MCP Gateway Registry deployment:

### Required Variables

```bash
# Microsoft Entra ID Configuration
ENTRA_CLIENT_ID=your-application-client-id
ENTRA_CLIENT_SECRET=your-client-secret-value
ENTRA_TENANT_ID=your-tenant-id-or-common
```

### Optional Configuration Variables

```bash
# Token Configuration
# Determines which token to use for extracting user information
# - 'id': Extract user info from ID token (default, recommended)
# - 'access': Extract user info from access token
# If token extraction fails, the system will automatically fallback to Graph API
ENTRA_TOKEN_KIND=id

# Microsoft Graph API Configuration
# For sovereign clouds or custom Graph API endpoints
# Default: https://graph.microsoft.com
ENTRA_GRAPH_URL=https://graph.microsoft.com

# M2M (Machine-to-Machine) Scope Configuration
# Default scope for client credentials flow
# Default: https://graph.microsoft.com/.default
ENTRA_M2M_SCOPE=https://graph.microsoft.com/.default

# Custom Claim Mappings (defaults are shown)
ENTRA_USERNAME_CLAIM=preferred_username
ENTRA_GROUPS_CLAIM=groups
ENTRA_EMAIL_CLAIM=email
ENTRA_NAME_CLAIM=name
```

### Sovereign Cloud Configuration

For non-global Azure clouds, update **both** `ENTRA_TENANT_ID` and `ENTRA_GRAPH_URL`:

```bash
# US Government Cloud
ENTRA_TENANT_ID=your-tenant-id
ENTRA_GRAPH_URL=https://graph.microsoft.us

# China Cloud (operated by 21Vianet)
ENTRA_TENANT_ID=your-tenant-id
ENTRA_GRAPH_URL=https://microsoftgraph.chinacloudapi.cn

# Germany Cloud
ENTRA_TENANT_ID=your-tenant-id
ENTRA_GRAPH_URL=https://graph.microsoft.de
```

**Note**: URLs, scopes, and default claim mappings are configured in `auth_server/oauth2_providers.yml`. Environment variables for claim mappings are only needed if you want to override the defaults.

## Step 5: Enable Entra ID Provider

Ensure the Entra ID provider is enabled in the `auth_server/oauth2_providers.yml` configuration:

```yaml
entra_id:
  display_name: "Microsoft Entra ID"
  client_id: "${ENTRA_CLIENT_ID}"
  client_secret: "${ENTRA_CLIENT_SECRET}"
  # Tenant ID can be specific tenant or 'common' for multi-tenant
  tenant_id: "${ENTRA_TENANT_ID}"
  auth_url: "https://login.microsoftonline.com/${ENTRA_TENANT_ID}/oauth2/v2.0/authorize"
  token_url: "https://login.microsoftonline.com/${ENTRA_TENANT_ID}/oauth2/v2.0/token"
  jwks_url: "https://login.microsoftonline.com/${ENTRA_TENANT_ID}/discovery/v2.0/keys"
  user_info_url: "https://graph.microsoft.com/v1.0/me"
  logout_url: "https://login.microsoftonline.com/${ENTRA_TENANT_ID}/oauth2/v2.0/logout"
  scopes: ["openid", "profile", "email", "User.Read"]
  response_type: "code"
  grant_type: "authorization_code"
  # Entra ID specific claim mapping
  username_claim: "${ENTRA_USERNAME_CLAIM}"
  groups_claim: "${ENTRA_GROUPS_CLAIM}"
  email_claim: "${ENTRA_EMAIL_CLAIM}"
  name_claim: "${ENTRA_NAME_CLAIM}"
  # Microsoft Graph API base URL (for sovereign clouds)
  graph_url: "${ENTRA_GRAPH_URL:-https://graph.microsoft.com}"
  # M2M (Machine-to-Machine) default scope
  m2m_scope: "${ENTRA_M2M_SCOPE:-https://graph.microsoft.com/.default}"
  enabled: true
```

## Step 6: Test the Setup

1. **Restart Services**
   - Restart the authentication server and registry services

2. **Test Authentication Flow**
   - Navigate to your registry login page
   - Select "Microsoft Entra ID" as the authentication method
   - Complete the Microsoft login process
   - Verify successful authentication and user information retrieval

## Step 7: Optional Configurations

### Multi-Tenant Setup
For multi-tenant applications, set `ENTRA_TENANT_ID=common` and ensure the app registration is configured for multi-tenant access.

```bash
# Support any Microsoft organizational account
ENTRA_TENANT_ID=common

# Support only organizational accounts (exclude personal accounts)
ENTRA_TENANT_ID=organizations

# Support only personal Microsoft accounts
ENTRA_TENANT_ID=consumers
```

### Machine-to-Machine (M2M) Authentication
For service accounts and automated processes:

1. **Configure App Permissions**
   - In your app registration, go to **API permissions**
   - Add **Application permissions** (not delegated) as needed
   - Grant admin consent

2. **Use Client Credentials Flow**
   - The implementation supports M2M token generation using client credentials
   - See implementation documentation for usage details

### Custom Scopes
Modify the `scopes` configuration in `oauth2_providers.yml` to include additional Microsoft Graph permissions as needed.

## Troubleshooting

### Common Issues

1. **Invalid Redirect URI**
   - Ensure the redirect URI in Azure matches exactly with your registry callback URL
   - Check for trailing slashes and protocol (http vs https)

2. **Insufficient Permissions**
   - Verify all required API permissions are granted with admin consent
   - Check that the user has appropriate permissions in Entra ID

3. **Token Validation Failures**
   - Verify client ID, tenant ID, and client secret are correct
   - Check token audience and issuer configuration

4. **Sovereign Cloud Issues**
   - For Azure Government or China clouds, set the appropriate `ENTRA_GRAPH_URL`
   - Ensure app registration is in the correct cloud environment
   - Verify OAuth endpoints match your cloud environment

5. **Token Kind Configuration**
   - If using `ENTRA_TOKEN_KIND=id` but ID token is not available, system will fallback to access token
   - If using `ENTRA_TOKEN_KIND=access`, ensure access token contains user claims
   - Check logs to see which token extraction method was used

### Logs and Debugging

Enable debug logging to troubleshoot authentication issues:

```bash
# Set log level to DEBUG in your environment
AUTH_LOG_LEVEL=DEBUG
```

Check authentication server logs for detailed error messages and token validation information.

## Security Considerations

- **Client Secrets**: Rotate client secrets regularly and store them securely
- **Token Validation**: The implementation validates token signatures, expiration, and audience
- **JWKS Caching**: JWKS are cached for 1 hour to reduce API calls while maintaining security
- **Multi-tenancy**: Use tenant-specific configurations when needed for enhanced security

## Next Steps

After successful setup, refer to the [Implementation Documentation](./entra-id-implementation.md) for technical details and advanced configuration options.
