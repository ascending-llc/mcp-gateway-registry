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

```bash
# Microsoft Entra ID Configuration
ENTRA_CLIENT_ID=your-application-client-id
ENTRA_CLIENT_SECRET=your-client-secret-value
ENTRA_TENANT_ID=your-tenant-id-or-common

# Optional: For sovereign clouds
# ENTRA_AUTHORITY=https://login.microsoftonline.us  # US Government
# ENTRA_AUTHORITY=https://login.chinacloudapi.cn    # China
```

**Optional Claim Mapping Environment Variables:**
```bash
# Optional: Custom claim mappings (defaults are shown)
ENTRA_USERNAME_CLAIM=preferred_username
ENTRA_GROUPS_CLAIM=groups
ENTRA_EMAIL_CLAIM=upn # upn or email
ENTRA_NAME_CLAIM=name
```

**Note**: URLs, scopes, and default claim mappings are configured in `auth_server/oauth2_providers.yml`. Environment variables for claim mappings are only needed if you want to override the defaults.

## Step 5: Enable Entra ID Provider

Ensure the Entra ID provider is enabled in the `auth_server/oauth2_providers.yml` configuration:

```yaml
entra_id:
  display_name: "Microsoft Entra ID"
  client_id: "${ENTRA_CLIENT_ID}"
  client_secret: "${ENTRA_CLIENT_SECRET}"
  tenant_id: "${ENTRA_TENANT_ID}"
  auth_url: "https://login.microsoftonline.com/${ENTRA_TENANT_ID}/oauth2/v2.0/authorize"
  token_url: "https://login.microsoftonline.com/${ENTRA_TENANT_ID}/oauth2/v2.0/token"
  user_info_url: "https://graph.microsoft.com/v1.0/me"
  logout_url: "https://login.microsoftonline.com/${ENTRA_TENANT_ID}/oauth2/v2.0/logout"
  scopes: ["openid", "profile", "email", "User.Read"]
  response_type: "code"
  grant_type: "authorization_code"
  username_claim: "preferred_username"
  groups_claim: "groups"
  email_claim: "email"
  name_claim: "name"
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
   - For Azure Government or China clouds, set the appropriate authority URL
   - Ensure app registration is in the correct cloud environment

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
