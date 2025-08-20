# AgentCore Gateway Access Token Utility

A standalone utility for generating OAuth2 access tokens for existing Amazon Bedrock AgentCore Gateways.

## Overview

This utility extracts the essential token generation functionality from the main SRE Agent gateway scripts, allowing you to easily generate access tokens for existing gateways without needing the full gateway creation infrastructure.

## Features

- Generate OAuth2 access tokens for existing AgentCore Gateways
- Support for Amazon Cognito and Auth0 OAuth providers
- Flexible configuration via YAML files and environment variables
- Minimal dependencies for easy deployment
- Command-line interface with comprehensive options

## Prerequisites

- Python 3.11+
- AWS credentials configured (if using Cognito)
- Access to the OAuth provider (Cognito User Pool or Auth0)
- Client ID and Client Secret for your OAuth application

## Installation

1. Copy the `agentcore` folder to your desired location
2. Install dependencies:
   ```bash
   cd agentcore
   uv install
   # or with pip:
   pip install -r requirements.txt
   ```

## Configuration

### Option 1: Configuration File

Create or edit `config.yaml`:

```yaml
# Gateway Configuration (optional, for reference)
gateway_arn: "arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/your-gateway-id"

# Cognito Configuration
user_pool_id: "us-west-2_abcdef123"
client_id: "your_cognito_client_id"

# OAuth Configuration (alternative to Cognito)
# oauth_domain: "https://your-domain.auth0.com"
# oauth_client_id: "your_oauth_client_id"
# oauth_audience: "MCPGateway"
```

### Option 2: Environment Variables

Create a `.env` file:

```env
# For Cognito
COGNITO_DOMAIN=https://cognito-idp.us-west-2.amazonaws.com/us-west-2_abcdef123
COGNITO_CLIENT_ID=your_cognito_client_id
COGNITO_CLIENT_SECRET=your_cognito_client_secret

# For Auth0 or other OAuth providers
# OAUTH_DOMAIN=https://your-domain.auth0.com
# OAUTH_CLIENT_ID=your_oauth_client_id
# OAUTH_CLIENT_SECRET=your_oauth_client_secret
```

## Usage

### Basic Usage

Generate a token using configuration file and environment variables:

```bash
python generate_access_token.py
```

### Advanced Usage

```bash
# Specify gateway ARN for reference
python generate_access_token.py --gateway-arn arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/my-gateway

# Use custom config file
python generate_access_token.py --config-file my-config.yaml

# Save token to custom file
python generate_access_token.py --output-file my-token.txt

# Use custom audience for Auth0
python generate_access_token.py --audience "https://api.mycompany.com"

# Enable debug logging
python generate_access_token.py --debug
```

### Using as a Module

```python
from generate_access_token import generate_access_token

# Generate token programmatically
generate_access_token(
    gateway_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/my-gateway",
    output_file="my_token.txt"
)
```

## Configuration Priority

The utility uses the following priority order for configuration:

1. Environment variables (highest priority)
2. Configuration file values
3. Command-line arguments
4. Default values (lowest priority)

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `COGNITO_DOMAIN` | Full Cognito domain URL | Yes* |
| `COGNITO_CLIENT_ID` | Cognito App Client ID | Yes |
| `COGNITO_CLIENT_SECRET` | Cognito App Client Secret | Yes |
| `OAUTH_DOMAIN` | OAuth provider domain (Auth0, etc.) | Yes* |
| `OAUTH_CLIENT_ID` | OAuth client ID | Yes* |
| `OAUTH_CLIENT_SECRET` | OAuth client secret | Yes* |

*Either Cognito or OAuth variables are required, not both.

## Output

The utility generates:
- `.access_token` file containing the access token (default)
- Console output with token expiration information
- Logs showing the generation process

## Example Output

```
2024-07-31 10:30:15,p12345,{generate_access_token.py:89},INFO,Loaded configuration from config.yaml
2024-07-31 10:30:15,p12345,{generate_access_token.py:156},INFO,Generating OAuth2 access token...
2024-07-31 10:30:16,p12345,{generate_access_token.py:76},INFO,Successfully obtained Cognito access token
2024-07-31 10:30:16,p12345,{generate_access_token.py:98},INFO,Access token saved to .access_token
2024-07-31 10:30:16,p12345,{generate_access_token.py:100},INFO,Token expires in 3600 seconds
2024-07-31 10:30:16,p12345,{generate_access_token.py:178},INFO,Token generation completed successfully! Token saved to .access_token
```

## Troubleshooting

### Common Issues

1. **Missing environment variables**
   ```
   ERROR: Missing required parameters: COGNITO_CLIENT_SECRET
   ```
   Solution: Ensure all required environment variables are set in your `.env` file.

2. **Invalid User Pool ID**
   ```
   ERROR: Invalid User Pool ID format: invalid_pool_id
   ```
   Solution: Ensure the User Pool ID follows the format `region_poolId` (e.g., `us-west-2_abcdef123`).

3. **Authentication failed**
   ```
   ERROR: Error getting token: 401 Client Error: Unauthorized
   ```
   Solution: Verify your client ID and client secret are correct and that the client has the necessary permissions.

### Debug Mode

Enable debug logging to see detailed information:

```bash
python generate_access_token.py --debug
```

## Dependencies

Minimal dependencies for easy deployment:
- `requests` - HTTP client for OAuth requests
- `python-dotenv` - Environment variable loading
- `pyyaml` - YAML configuration file parsing

## Security Notes

- Never commit `.env` files or access tokens to version control
- Access tokens are temporary and should be regenerated as needed
- Store client secrets securely using environment variables or secret management systems
- The generated access token file (`.access_token`) should be protected with appropriate file permissions

## Integration with AgentCore

Once you have generated an access token, you can use it with AgentCore Gateway APIs:

```bash
# Use the generated token in API requests
TOKEN=$(cat .access_token)
curl -H "Authorization: Bearer $TOKEN" https://your-gateway-url/api/endpoint
```

## Support

For issues related to:
- Gateway creation: See the main SRE Agent documentation
- OAuth configuration: Consult your OAuth provider documentation
- This utility: Check the troubleshooting section above