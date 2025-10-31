# Microsoft Entra ID Implementation

This document provides technical details about the Microsoft Entra ID (Azure AD) authentication provider implementation in the MCP Gateway Registry.

## Overview

The `EntraIDProvider` class implements the `AuthProvider` interface to provide Microsoft Entra ID (Azure AD) authentication capabilities. It supports OAuth2 authorization code flow, JWT token validation, and integration with Microsoft Graph API.

## Architecture

### Class Hierarchy

```
AuthProvider (Abstract Base Class)
└── EntraIDProvider (Concrete Implementation)
```

### Dependencies

- **Python-jose**: For JWT token validation and decoding
- **Requests**: For HTTP API calls to Microsoft endpoints
- **PyJWT**: For JWT header parsing and key handling

## Implementation Details

### Initialization

The `EntraIDProvider` is initialized with the following parameters:

```python
def __init__(
    self,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    authority: Optional[str] = None,
    scopes: Optional[list] = None,
    grant_type: str = "authorization_code",
    username_claim: str = "preferred_username",
    groups_claim: str = "groups",
    email_claim: str = "email",
    name_claim: str = "name"
):
```

**Parameters:**
- `tenant_id`: Azure AD tenant ID (use 'common' for multi-tenant)
- `client_id`: Azure AD application (client) ID
- `client_secret`: Azure AD client secret
- `authority`: Optional custom authority URL (defaults to global Azure AD)
- `scopes`: List of OAuth2 scopes (default: `['openid', 'profile', 'email', 'User.Read']`)
- `grant_type`: OAuth2 grant type (default: `'authorization_code'`)
- `username_claim`: Claim to use for username (default: `'preferred_username'`)
- `groups_claim`: Claim to use for groups (default: `'groups'`)
- `email_claim`: Claim to use for email (default: `'email'`)
- `name_claim`: Claim to use for display name (default: `'name'`)

**Endpoints Configured:**
- `token_url`: `{authority}/oauth2/v2.0/token`
- `auth_url`: `{authority}/oauth2/v2.0/authorize`
- `jwks_url`: `{authority}/discovery/v2.0/keys`
- `logout_url`: `{authority}/oauth2/v2.0/logout`
- `userinfo_url`: `https://graph.microsoft.com/v1.0/me`
- `issuer`: `https://login.microsoftonline.com/{tenant_id}/v2.0`

### Token Validation

The `validate_token` method performs comprehensive JWT validation:

```python
def validate_token(self, token: str, **kwargs: Any) -> Dict[str, Any]:
```

**Validation Steps:**
1. **JWKS Retrieval**: Fetches JSON Web Key Set from Microsoft with 1-hour caching
2. **Key Matching**: Matches token's `kid` header to the appropriate signing key
3. **JWT Decoding**: Validates using RS256 algorithm with multiple audience checks
4. **Claim Extraction**: Extracts user information from token claims

**Supported Audiences:**
- `client_id` (e.g., `12345678-1234-1234-1234-123456789012`)
- `api://{client_id}` (e.g., `api://12345678-1234-1234-1234-123456789012`)

**User Claim Resolution:**
The implementation uses configurable claim mappings for user information extraction:
- **Username**: Configurable via `username_claim` (default: `preferred_username`)
- **Email**: Configurable via `email_claim` (default: `email`)
- **Groups**: Configurable via `groups_claim` (default: `groups`)
- **Name**: Configurable via `name_claim` (default: `name`)

The implementation handles both string and list claims for groups and falls back to 'sub' claim for username if the configured claim is not found.

### JWKS Caching

The implementation includes intelligent JWKS caching:

```python
self._jwks_cache: Optional[Dict[str, Any]] = None
self._jwks_cache_time: float = 0
self._jwks_cache_ttl: int = 3600  # 1 hour
```

**Features:**
- 1-hour TTL for JWKS cache
- Automatic cache refresh on expiration
- Error handling for JWKS retrieval failures

### OAuth2 Flow Implementation

#### Authorization URL Generation

```python
def get_auth_url(self, redirect_uri: str, state: str, scope: Optional[str] = None) -> str:
```

**Default Scopes:** `openid profile email User.Read`
**Response Mode:** `query`

#### Code Exchange

```python
def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
```

**Request Parameters:**
- `grant_type`: `authorization_code`
- `code`: Authorization code
- `redirect_uri`: Must match the authorization request
- `scope`: `openid profile email User.Read`

#### Token Refresh

```python
def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
```

**Request Parameters:**
- `grant_type`: `refresh_token`
- `refresh_token`: The refresh token
- `scope`: `openid profile email User.Read offline_access`

### User Information Retrieval

The implementation integrates with Microsoft Graph API to fetch user profile information:

```python
def get_user_info(self, access_token: str) -> Dict[str, Any]:
```

**Graph API Endpoint:** `https://graph.microsoft.com/v1.0/me`

**Returned Fields:**
- `username`: User Principal Name (UPN)
- `email`: Mail address or UPN
- `name`: Display name
- `given_name`: First name
- `family_name`: Last name
- `id`: Object ID
- `job_title`: Job title
- `office_location`: Office location

### Machine-to-Machine (M2M) Support

#### M2M Token Generation

```python
def get_m2m_token(
    self,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    scope: Optional[str] = None
) -> Dict[str, Any]:
```

**Client Credentials Flow:**
- `grant_type`: `client_credentials`
- Default scope: `https://graph.microsoft.com/.default`
- Supports custom client credentials for service accounts

#### M2M Token Validation

```python
def validate_m2m_token(self, token: str) -> Dict[str, Any]:
```

Uses the same validation logic as user tokens with appropriate audience checks.

### Logout Implementation

```python
def get_logout_url(self, redirect_uri: str) -> str:
```

Generates Microsoft Entra ID logout URL with post-logout redirect.

## Configuration

### Provider Configuration (oauth2_providers.yml)

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

### Environment Variables

```bash
# Required
ENTRA_CLIENT_ID=your-application-client-id
ENTRA_CLIENT_SECRET=your-client-secret-value
ENTRA_TENANT_ID=your-tenant-id-or-common

# Optional - For sovereign clouds
# ENTRA_AUTHORITY=https://login.microsoftonline.us  # US Government
# ENTRA_AUTHORITY=https://login.chinacloudapi.cn    # China

# Optional - Custom claim mappings (defaults are shown)
ENTRA_USERNAME_CLAIM=preferred_username
ENTRA_GROUPS_CLAIM=groups
ENTRA_EMAIL_CLAIM=email
ENTRA_NAME_CLAIM=name
```

## Error Handling

The implementation includes comprehensive error handling:

### Token Validation Errors
- `jwt.ExpiredSignatureError`: Token has expired
- `jwt.InvalidTokenError`: Invalid token structure or signature
- `ValueError`: Missing key ID or no matching key found

### API Call Errors
- `requests.RequestException`: Network or HTTP errors
- Detailed error logging with response bodies for debugging

### JWKS Retrieval Errors
- Fallback handling for JWKS endpoint failures
- Graceful degradation with appropriate error messages

## Logging

The provider uses structured logging with the following patterns:

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
```

**Key Log Events:**
- Token validation successes and failures
- JWKS cache hits and misses
- API call attempts and results
- User authentication events

## Security Features

### Token Security
- **Signature Validation**: Validates token signatures using Microsoft's JWKS
- **Expiration Checking**: Verifies token expiration timestamps
- **Audience Validation**: Checks token audience against client ID
- **Issuer Verification**: Validates token issuer against Microsoft endpoints

### API Security
- **HTTPS Enforcement**: All Microsoft endpoints use HTTPS
- **Client Secret Protection**: Secrets are passed securely in token requests
- **Redirect URI Validation**: Ensures redirect URIs match configured endpoints

### Caching Security
- **JWKS Cache TTL**: 1-hour cache with automatic refresh
- **No Sensitive Data**: Cache only contains public keys

## Performance Considerations

### JWKS Caching
- Reduces API calls to Microsoft endpoints
- 1-hour cache TTL balances performance and security
- Automatic cache refresh prevents stale key usage

### Token Validation
- Efficient key lookup using key ID (kid)
- Supports multiple audience formats for compatibility
- Minimal overhead for token parsing and validation

## Extensibility

### Custom Authority URLs
Support for sovereign clouds:
- Azure US Government: `https://login.microsoftonline.us`
- Azure China: `https://login.chinacloudapi.cn`

### Custom Scopes
Easily extendable to support additional Microsoft Graph permissions:

```yaml
scopes: ["openid", "profile", "email", "User.Read", "Mail.Read", "Calendars.Read"]
```

### Multi-Tenant Support
- Use `tenant_id: "common"` for multi-tenant applications
- Automatic tenant discovery and validation

## Testing

### Unit Testing
The implementation can be tested with:
- Mock JWKS endpoints
- Mock Microsoft Graph API responses
- Test tokens with known signatures

### Integration Testing
- End-to-end OAuth2 flow testing
- Token validation with real Microsoft endpoints
- Error scenario testing

## Usage Examples

### Basic Authentication Flow

```python
from auth_server.providers.entra import EntraIDProvider

# Initialize provider
provider = EntraIDProvider(
    tenant_id="your-tenant-id",
    client_id="your-client-id",
    client_secret="your-client-secret"
)

# Generate authorization URL
auth_url = provider.get_auth_url(
    redirect_uri="https://your-app/callback",
    state="security-token"
)

# Exchange code for token
token_data = provider.exchange_code_for_token(
    code="authorization-code",
    redirect_uri="https://your-app/callback"
)

# Validate token
user_info = provider.validate_token(token_data["access_token"])

# Get user profile
profile = provider.get_user_info(token_data["access_token"])
```

### Machine-to-Machine Authentication

```python
# Get M2M token
m2m_token = provider.get_m2m_token(
    scope="https://graph.microsoft.com/.default"
)

# Validate M2M token
validation_result = provider.validate_m2m_token(m2m_token["access_token"])
```

## Troubleshooting

### Common Issues

1. **Token Validation Failures**
   - Check audience and issuer configuration
   - Verify JWKS endpoint accessibility
   - Ensure token hasn't expired

2. **API Permission Errors**
   - Verify delegated permissions are granted
   - Check admin consent for application permissions
   - Validate scope configuration

3. **Multi-Tenant Issues**
   - Ensure app registration allows multi-tenant access
   - Verify tenant ID is set to "common" for multi-tenant apps

### Debug Mode

Enable debug logging for detailed troubleshooting:

```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

## References

- [Microsoft Identity Platform Documentation](https://docs.microsoft.com/en-us/azure/active-directory/develop/)
- [Microsoft Graph API Reference](https://docs.microsoft.com/en-us/graph/api/overview)
- [OAuth 2.0 Authorization Code Flow](https://oauth.net/2/grant-types/authorization-code/)
