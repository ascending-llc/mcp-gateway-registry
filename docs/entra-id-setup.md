# Microsoft Entra ID Setup Guide

This guide provides step-by-step instructions for setting up Microsoft Entra ID (formerly Azure Active Directory) authentication for the MCP Gateway Registry.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Azure Portal Configuration](#azure-portal-configuration)
3. [Environment Configuration](#environment-configuration)
4. [Group Configuration](#group-configuration)
5. [Testing the Setup](#testing-the-setup)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before you begin, ensure you have:

- Access to an Azure account with permissions to create App Registrations
- Azure Active Directory (Entra ID) tenant
- Admin rights to configure App Registrations and assign users to groups
- The MCP Gateway Registry codebase

---

## Azure Portal Configuration

### Step 1: Create an App Registration

1. Navigate to the [Azure Portal](https://portal.azure.com)
2. Go to **Azure Active Directory** → **App registrations**
3. Click **New registration**
4. Configure the app registration:
   - **Name**: `mcp-gateway-web` (or your preferred name)
   - **Supported account types**: Select the appropriate option:
     - **Single tenant** (recommended): Only users in your organization
     - **Multi-tenant**: Users from any Azure AD tenant
   - **Redirect URI**:
     - Platform: **Web**
     - URI: `http://localhost/auth/callback` (for local development)
     - For production, use: `https://your-domain.com/auth/callback`
5. Click **Register**

### Step 2: Note Your Application IDs

After creating the app registration, note the following values (you'll need them later):

1. From the app registration **Overview** page:
   - **Application (client) ID**: This is your `ENTRA_CLIENT_ID`
   - **Directory (tenant) ID**: This is your `ENTRA_TENANT_ID`

### Step 3: Create a Client Secret

1. In your app registration, click **Certificates & secrets** in the left menu
2. Click **New client secret**
3. Configure the secret:
   - **Description**: `mcp-gateway-auth` (or your preferred description)
   - **Expires**: Choose an appropriate expiration period (recommended: 24 months)
4. Click **Add**
5. **IMPORTANT**: Copy the **Value** immediately (not the Secret ID)
   - This is your `ENTRA_CLIENT_SECRET`
   - You cannot retrieve this value later - if you lose it, you'll need to create a new secret

### Step 4: Configure Redirect URIs

1. In your app registration, click **Authentication** in the left menu
2. Under **Platform configurations** → **Web**, add redirect URIs:
   - For local development: `http://localhost/auth/callback`
   - For production: `https://your-domain.com/auth/callback`
3. Under **Implicit grant and hybrid flows**, ensure nothing is checked (not needed for authorization code flow)
4. Click **Save**

### Step 5: Add API Permissions

To get user email and group information, you need to configure API permissions:

1. Click **API permissions** in the left menu
2. Click **Add a permission**
3. Select **Microsoft Graph**
4. Select **Delegated permissions**
5. Search for and add the following permissions:
   - `User.Read` (should already be present)
   - `email` - Read user's email address
   - `profile` - Read user's basic profile
   - `GroupMember.Read.All` - Read groups user belongs to
6. Click **Add permissions**
7. **CRITICAL**: Click **Grant admin consent for [Your Tenant]**
   - This step is required for the permissions to work
   - You need admin privileges to grant consent

### Step 6: Configure Optional Claims

To include email, username, and groups in the ID token:

1. Click **Token configuration** in the left menu
2. Click **Add optional claim**
3. Select **ID** token type
4. Add these claims:
   - `email` - User's email address
   - `preferred_username` - User's UPN (User Principal Name)
   - `groups` - Security group Object IDs
5. Click **Add**
6. When prompted "Turn on the Microsoft Graph email, profile permission", click **Add**

### Step 7: Configure Group Claims

1. Still in **Token configuration**
2. Click **Add groups claim**
3. Select **Security groups**
4. Under "Customize token properties by type":
   - **ID**: Check "Group ID"
   - **Access**: Check "Group ID"
5. Click **Add**

### Step 8: Create Security Groups

Create Azure AD security groups for authorization:

1. Go to **Azure Active Directory** → **Groups**
2. Click **New group**
3. Create an admin group:
   - **Group type**: Security
   - **Group name**: `Mcp-test-admin` (or your preferred name)
   - **Group description**: MCP Gateway administrators
   - **Membership type**: Assigned
4. Click **Create**
5. Repeat for a users group:
   - **Group name**: `mcp-test-users` (or your preferred name)
   - **Group description**: MCP Gateway users

### Step 9: Note Group Object IDs

For each group you created:

1. Click on the group name
2. From the **Overview** page, copy the **Object Id**
3. Note these IDs - you'll need them for `scopes.yml` configuration

### Step 10: Add Users to Groups

1. For each group, click on the group name
2. Click **Members** in the left menu
3. Click **Add members**
4. Search for and select users
5. Click **Select**

### Step 11: Configure App for API Access (Optional)

If you plan to use machine-to-machine (M2M) authentication:

1. Click **Expose an API** in the left menu
2. Click **Add** next to "Application ID URI"
3. Accept the default (`api://{client-id}`) or customize it
4. Click **Save**
5. Click **Add a scope**
6. Configure the scope:
   - **Scope name**: `.default`
   - **Who can consent**: Admins only
   - **Admin consent display name**: Access MCP Gateway
   - **Admin consent description**: Allow the application to access MCP Gateway
   - **State**: Enabled
7. Click **Add scope**

---

## Environment Configuration

### Step 1: Update .env File

1. Copy `.env.example` to `.env` if you haven't already:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file and configure Entra ID settings:

```bash
# =============================================================================
# AUTHENTICATION PROVIDER CONFIGURATION
# =============================================================================
# Choose authentication provider: 'cognito', 'keycloak', or 'entra'
AUTH_PROVIDER=entra

# =============================================================================
# MICROSOFT ENTRA ID CONFIGURATION
# =============================================================================

# Azure AD Tenant ID (from Azure Portal → App registration → Overview)
ENTRA_TENANT_ID=12345678-1234-1234-1234-123456789012

# Entra ID Application (client) ID (from Azure Portal → App registration → Overview)
ENTRA_CLIENT_ID=87654321-4321-4321-4321-210987654321

# Entra ID Client Secret (from Azure Portal → App registration → Certificates & secrets)
ENTRA_CLIENT_SECRET=your-secret-value-here

# Enable Entra ID in OAuth2 providers
ENTRA_ENABLED=true

# Azure AD Group Object IDs (from Azure Portal → Groups → Overview)
ENTRA_GROUP_ADMIN_ID=16c7e67e-e8ae-498c-ba2e-0593c0159e43
ENTRA_GROUP_USERS_ID=62c07ac1-03d0-4924-90c7-a0255f23bd1d
```

3. Update other required settings:

```bash
# =============================================================================
# REGISTRY CONFIGURATION
# =============================================================================
# For local development
REGISTRY_URL=http://localhost

# For production with custom domain
# REGISTRY_URL=https://mcpgateway.mycorp.com

# =============================================================================
# AUTH SERVER CONFIGURATION
# =============================================================================
# For local development
AUTH_SERVER_EXTERNAL_URL=http://localhost

# For production with custom domain
# AUTH_SERVER_EXTERNAL_URL=https://mcpgateway.mycorp.com

# =============================================================================
# APPLICATION SECURITY
# =============================================================================
# CRITICAL: CHANGE THIS SECRET KEY IMMEDIATELY!
SECRET_KEY=your-super-secure-random-64-character-string-here
```

---

## Group Configuration

### Configure scopes.yml

The `auth_server/scopes.yml` file maps Azure AD groups to MCP Gateway scopes and permissions.

1. Open `auth_server/scopes.yml`

2. Update the Entra ID group mappings section with your group Object IDs:

```yaml
group_mappings:
  # Entra ID group mappings (by Azure AD Group Object IDs)
  # Admin group
  "object_id":
  - mcp-registry-admin
  - registry-admins

```

3. Replace the group Object IDs with your actual group IDs from Azure Portal

### Understanding Scope Mappings

- **mcp-registry-admin**: Full administrative access to the registry
  - Can list, register, modify, and toggle services
  - Has unrestricted read and execute access to MCP servers

- **mcp-registry-user**: Limited user access
  - Can list and view specific services
  - Has restricted read access to MCP servers

- **mcp-registry-developer**: Development access
  - Can list, register, and health check services
  - Has restricted read and execute access

- **mcp-registry-operator**: Operations access
  - Can list, health check, and toggle services
  - Has restricted read and execute access

---

## Testing the Setup

### Step 1: Start the Services

1. Build and start the Docker containers:
   ```bash
   docker-compose up -d --build
   ```

2. Check that services are running:
   ```bash
   docker-compose ps
   ```

### Step 2: Test User Authentication

1. Open your browser and navigate to:
   ```
   http://localhost
   ```

2. You should see the MCP Gateway Registry login page

3. Click the **Sign in with Microsoft Entra ID** button

4. You will be redirected to Microsoft's login page

5. Sign in with a user account that belongs to one of your configured groups

6. After successful authentication, you should be redirected back to the registry

### Step 3: Verify User Information

1. Check the auth server logs to verify user information is being received:
   ```bash
   docker-compose logs auth-server | grep "Raw user info"
   ```

2. You should see output similar to:
   ```
   Raw user info from entra: {
     'sub': 'abc123...',
     'email': 'user@yourdomain.onmicrosoft.com',
     'preferred_username': 'user@yourdomain.onmicrosoft.com',
     'groups': ['16c7e67e-...', '62c07ac1-...'],
     'name': 'First Last'
   }
   ```

3. Verify the mapped scopes:
   ```bash
   docker-compose logs auth-server | grep "Mapped user info"
   ```

4. You should see:
   ```
   Mapped user info: {
     'username': 'user@yourdomain.onmicrosoft.com',
     'email': 'user@yourdomain.onmicrosoft.com',
     'name': 'First Last',
     'groups': ['mcp-registry-admin', 'mcp-servers-unrestricted/read', ...]
   }
   ```

### Step 4: Test Authorization

1. Log in with an admin user (member of the admin group)

2. Verify you can access admin functions:
   - Register new services
   - Modify service configurations
   - Toggle services on/off

3. Log in with a regular user (member of the users group)

4. Verify restricted access:
   - Can view services
   - Cannot register or modify services

### Step 5: Test Machine-to-Machine (M2M) Authentication

If you configured API access for M2M authentication:

1. Create a service principal for your AI agent:
   ```bash
   # This is done in Azure Portal → App registrations
   # Create a new app registration for the AI agent
   ```

2. Test M2M token generation:
   ```bash
   curl -X POST "https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "grant_type=client_credentials" \
     -d "client_id={agent-client-id}" \
     -d "client_secret={agent-client-secret}" \
     -d "scope=api://{mcp-gateway-client-id}/.default"
   ```

3. Use the access token to call MCP Gateway APIs

---

## Troubleshooting

### Issue: Missing email and groups claims

**Symptoms:**
```
Raw user info from entra: {'sub': '...', 'name': 'User Name', 'family_name': '...', 'given_name': '...'}
Mapped user info: {'username': None, 'email': None, 'groups': []}
```

**Solution:**
1. Verify you completed [Step 5: Add API Permissions](#step-5-add-api-permissions)
2. Ensure you clicked **Grant admin consent**
3. Complete [Step 6: Configure Optional Claims](#step-6-configure-optional-claims)
4. Complete [Step 7: Configure Group Claims](#step-7-configure-group-claims)
5. Wait 5-10 minutes for Azure AD to propagate changes
6. Clear browser cookies and try logging in again

### Issue: Token validation fails with "Invalid issuer"

**Symptoms:**
```
Token validation failed: Invalid issuer: https://sts.windows.net/{tenant}/
```

**Solution:**
The Entra ID provider supports both v1.0 and v2.0 token formats. This error should not occur with the current implementation. If you see this:

1. Check that `ENTRA_TENANT_ID` in `.env` matches your actual tenant ID
2. Verify the token is being issued by Microsoft Entra ID
3. Check auth server logs for more details

### Issue: User cannot access any resources

**Symptoms:**
User can log in but sees "Access Denied" or "Insufficient Permissions"

**Solution:**
1. Verify the user is added to at least one security group in Azure AD
2. Check that group Object IDs in `scopes.yml` match the groups in Azure Portal
3. Verify the group mappings include the necessary scopes
4. Check auth server logs to see what groups are being received:
   ```bash
   docker-compose logs auth-server | grep "groups"
   ```

### Issue: Redirect URI mismatch error

**Symptoms:**
```
AADSTS50011: The redirect URI 'http://localhost/auth/callback' does not match the redirect URIs configured for the application
```

**Solution:**
1. Go to Azure Portal → App registrations → Your app → Authentication
2. Verify the redirect URI exactly matches what's in the error message
3. Add any missing redirect URIs
4. Ensure `AUTH_SERVER_EXTERNAL_URL` in `.env` matches the base URL

### Issue: "Groups overage" claim

**Symptoms:**
Groups claim contains `_claim_names` and `_claim_sources` instead of group IDs

**Solution:**
This occurs when a user is a member of more than 200 groups. You need to:

1. Modify the auth provider to fetch groups via Microsoft Graph API
2. See the alternative implementation in `docs/ENTRA-ID-APP-CONFIGURATION.md` Step 5

### Issue: Client secret expired

**Symptoms:**
```
AADSTS7000215: Invalid client secret provided
```

**Solution:**
1. Go to Azure Portal → App registrations → Your app → Certificates & secrets
2. Create a new client secret
3. Update `ENTRA_CLIENT_SECRET` in `.env`
4. Restart the services:
   ```bash
   docker-compose restart auth-server
   ```

### Issue: Cannot grant admin consent

**Symptoms:**
You don't see the "Grant admin consent" button or get an error when clicking it

**Solution:**
1. You need Global Administrator, Application Administrator, or Cloud Application Administrator role
2. Contact your Azure AD administrator to grant the permissions
3. Alternatively, users can consent individually (not recommended for production)

---

## Additional Resources

- [Microsoft Entra ID Documentation](https://learn.microsoft.com/en-us/entra/)
- [OAuth 2.0 Authorization Code Flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Optional Claims Configuration](https://learn.microsoft.com/en-us/entra/identity-platform/optional-claims)
- [Configure Group Claims](https://learn.microsoft.com/en-us/entra/identity-platform/optional-claims#configure-groups-optional-claims)
- [Microsoft Graph Permissions Reference](https://learn.microsoft.com/en-us/graph/permissions-reference)

---

## Production Deployment

### Update Redirect URIs

For production, update redirect URIs:
```
https://your-domain.com/oauth2/callback/entra
```

### Environment Variables

Update production `.env`:
```bash
ENTRA_REDIRECT_URI=https://your-domain.com/oauth2/callback/entra
AUTH_SERVER_EXTERNAL_URL=https://your-domain.com:8888
```

### SSL/TLS Configuration

Ensure your production deployment uses HTTPS for all OAuth flows.

---

## Advanced Configuration

### Custom Claims

To add custom claims to tokens:
1. Go to **Token configuration**
2. Click **Add optional claim**
3. Select token type and claims
4. Configure claim conditions

### Group Filtering

To limit which groups are included in tokens:
1. Go to **Token configuration** 
2. Click **Add groups claim**
3. Configure **Groups assigned to the application**

### Enterprise Applications

For advanced management:
1. Go to **Enterprise applications**
2. Find your app registration
3. Configure:
   - User assignment required
   - Visibility settings
   - Provisioning (if needed)

---

## Adding New Users

### Option 1: Add User to Existing Group (Recommended)

**In Azure Portal:**
1. Go to **Microsoft Entra ID** → **Groups**
2. Click on **MCP Registry Admins** (or appropriate group)
3. Click **Members** → **Add members**
4. Search and select the new user
5. Click **Select**

**Access will be immediate** - user can login and see servers/agents.

### Option 2: Create New Group for User

**If you need different permissions:**

1. **Create new group in Azure:**
   - **Group name**: `MCP Registry LOB3 Users`
   - **Members**: Add the new user

2. **Get the group Object ID** from the group overview page

3. **Add to scopes.yml:**
```yaml
group_mappings:
  # Add new group mapping
  "new-group-object-id-here":
  - registry-users-lob1  # or whatever permission level needed
```

4. **Restart auth server:**
```bash
cp auth_server/scopes.yml ~/mcp-gateway/auth_server/scopes.yml
docker-compose restart auth-server
```

---

## API Reference

### Token Endpoint
```
POST https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/token
```

### Authorization Endpoint
```
GET https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/authorize
```

### User Info Endpoint
```
GET https://graph.microsoft.com/v1.0/me
```

---

## Security Best Practices

1. **Client Secret Management**
   - Store client secrets securely (use Azure Key Vault in production)
   - Rotate secrets regularly (set expiration and create new secrets)
   - Never commit secrets to version control

2. **Token Configuration**
   - Keep token expiration times reasonable (default: 1 hour for access tokens)
   - Use refresh tokens for long-running sessions
   - Implement proper token revocation

3. **Group Management**
   - Use security groups (not distribution lists or Microsoft 365 groups)
   - Apply principle of least privilege
   - Regularly audit group memberships

4. **HTTPS in Production**
   - Always use HTTPS in production environments
   - Configure proper SSL/TLS certificates
   - Update redirect URIs to use HTTPS

5. **Monitoring and Logging**
   - Enable Azure AD audit logs
   - Monitor sign-in logs for suspicious activity
   - Set up alerts for authentication failures

6. **Multi-Factor Authentication**
   - Enable MFA for all users (configured in Azure AD)
   - Use conditional access policies
   - Enforce MFA for admin accounts

---

## Next Steps

After completing the setup:

1. **Configure Additional Services**: Add more MCP servers to the registry
2. **Set Up Custom Domain**: Configure HTTPS and custom domain names
3. **Configure M2M Authentication**: Set up service principals for AI agents
4. **Implement Monitoring**: Set up observability and alerting
5. **Production Deployment**: Deploy to your production environment

For more information, see:
- [Complete Setup Guide](./complete-setup-guide.md)
- [Observability Documentation](./OBSERVABILITY.md)
- [FAQ](./FAQ.md)
