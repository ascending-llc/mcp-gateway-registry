# Financial Info MCP Server - Secrets Manager

This document describes the local secrets manager implementation for the Financial Info MCP Server.

## Overview

The secrets manager allows different clients to use their own Polygon API keys by including an `x-client-id` header in their HTTP requests. This enables:

- Multi-tenant API key management
- Client-specific rate limiting and billing
- Secure key storage and rotation
- Fallback mechanisms for backward compatibility

## Setup

### 1. Docker Configuration

The `docker-compose.yml` has been updated to map the secrets file:

```yaml
volumes:
  - /opt/mcp-gateway/secrets/.keys.yml:/app/fininfo/.keys.yml
```

### 2. Create Secrets File

Create the secrets file on your host system:

```bash
sudo mkdir -p /opt/mcp-gateway/secrets
sudo touch /opt/mcp-gateway/secrets/.keys.yml
sudo chmod 600 /opt/mcp-gateway/secrets/.keys.yml
```

### 3. Configure Client API Keys

Edit the secrets file with your client configurations:

```yaml
# Default fallback key
default: your_default_polygon_api_key

# Client-specific keys
client_demo: demo_polygon_api_key
client_prod: production_polygon_api_key
client_test: test_polygon_api_key
```

## Usage

### Client Requests

Clients should include the `x-client-id` header in their HTTP requests:

```bash
curl -X POST "http://localhost:8001/sse" \
  -H "Content-Type: application/json" \
  -H "x-client-id: client_demo" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "get_stock_aggregates",
      "arguments": {
        "stock_ticker": "AAPL",
        "multiplier": 1,
        "timespan": "day",
        "from_date": "2023-01-01",
        "to_date": "2023-01-31"
      }
    }
  }'
```

### Fallback Behavior

If no `x-client-id` header is provided or the client ID is not found:

1. Uses the `POLYGON_API_KEY` environment variable (backward compatibility)
2. Falls back to the `default` key from the secrets file
3. Throws an error if no API key is available

## Security Features

### Current Implementation

- YAML file-based storage with secure file permissions
- Client ID validation and logging
- API key masking in logs
- Graceful fallback mechanisms

### Future Enhancements

The secrets manager is designed to be extensible:

```python
# Encryption support using SECRET_KEY
def _decrypt_file_content(self, encrypted_content: bytes) -> str:
    encryption_key = self._get_encryption_key()
    fernet = Fernet(encryption_key)
    return fernet.decrypt(encrypted_content).decode('utf-8')

# External secrets manager integration
def _fetch_from_vault(self, client_id: str) -> str:
    # Connect to HashiCorp Vault, AWS Secrets Manager, etc.
    pass
```

## API Key Management

### Reloading Secrets

The secrets manager supports runtime reloading:

```python
# Programmatically reload secrets
secrets_manager.reload_secrets()
```

### Monitoring

The server logs all API key access attempts with redacted keys for security:

```
INFO: 🔑 Client ID found in header: client_demo
INFO: API key found for client_id: client_demo (key: oN7d...EKTp)
INFO: ✅ Using client-specific API key for client: client_demo
```

API keys are automatically redacted in logs showing only the first 4 and last 4 characters.

## File Encryption (Supported)

The secrets manager now supports encrypted secrets files using the existing `SECRET_KEY`.

### Encrypting a Secrets File

Use the built-in encryption method:

```python
# Encrypt the current secrets file
success = secrets_manager.encrypt_secrets_file()

# Encrypt a specific file
success = secrets_manager.encrypt_secrets_file('plain.yml', 'encrypted.yml')
```

Or manually encrypt using the SECRET_KEY:

```python
from cryptography.fernet import Fernet
import base64
import hashlib

# Generate encryption key from SECRET_KEY
secret_key = os.environ.get("SECRET_KEY")
key_bytes = hashlib.sha256(secret_key.encode()).digest()
encryption_key = base64.urlsafe_b64encode(key_bytes)

# Encrypt secrets file
fernet = Fernet(encryption_key)
with open('.keys.yml', 'r') as f:
    plain_content = f.read()

encrypted_data = fernet.encrypt(plain_content.encode('utf-8'))
encoded_data = base64.b64encode(encrypted_data).decode('utf-8')

with open('.keys.yml.encrypted', 'w') as f:
    f.write(encoded_data)
```

### Using Encrypted Files

The secrets manager automatically detects and decrypts encrypted files:

1. **Filename-based Detection**: Files ending with `.encrypted` are recognized as encrypted
2. **Transparent Decryption**: Encrypted files are automatically decrypted using the SECRET_KEY
3. **Error Handling**: Clear error messages if decryption fails

```
INFO: Encrypted secrets file detected (filename ends with .encrypted), attempting to decrypt...
INFO: Successfully decrypted secrets file
```

Example usage:
- Plain text: `.keys.yml` → loaded directly
- Encrypted: `.keys.yml.encrypted` → automatically decrypted

### Encryption Format

Encrypted files are stored as base64-encoded Fernet tokens:
- **Detection**: Files with `.encrypted` extension are treated as encrypted
- **Encoding**: Base64 encoded for text file storage
- **Key Derivation**: SHA256 hash of SECRET_KEY for consistent key generation
- **Content**: Fernet-encrypted YAML data encoded as base64 text

### Encryption Utility Script

A utility script [`encrypt_secrets.py`](servers/fininfo/encrypt_secrets.py:1-78) is provided for easy encryption/decryption:

```bash
# Encrypt the default secrets file
python encrypt_secrets.py

# Encrypt a specific file
python encrypt_secrets.py plain.yml encrypted.yml

# Test decryption of an encrypted file
python encrypt_secrets.py --test encrypted.yml

# Decrypt an encrypted file back to plain text
python encrypt_secrets.py --decrypt encrypted.yml decrypted.yml
```

The script requires the `SECRET_KEY` environment variable to be set.

## Troubleshooting

### Common Issues

1. **File not found**: Ensure the secrets file exists at the mapped path
2. **Permission denied**: Check file permissions (should be 600)
3. **YAML parsing error**: Validate YAML syntax
4. **No API key found**: Check client ID spelling and file contents

### Debug Logging

Enable debug logging to see detailed information:

```python
logging.basicConfig(level=logging.DEBUG)
```

### Health Check

Check secrets manager status:

```python
stats = secrets_manager.get_stats()
print(f"Loaded {stats['client_count']} clients")
print(f"File exists: {stats['file_exists']}")
```

## Production Considerations

1. **Backup**: Regularly backup the secrets file
2. **Rotation**: Implement API key rotation procedures
3. **Monitoring**: Monitor API usage per client
4. **Encryption**: Consider encrypting the secrets file
5. **Access Control**: Restrict file system access
6. **Auditing**: Log all key access attempts

## Integration Examples

### AWS Secrets Manager

```python
import boto3

class AWSSecretsManager(SecretsManager):
    def __init__(self):
        self.client = boto3.client('secretsmanager')
    
    def get_api_key(self, client_id: str) -> str:
        response = self.client.get_secret_value(
            SecretId=f'fininfo/clients/{client_id}/api-key'
        )
        return response['SecretString']
```

### HashiCorp Vault

```python
import hvac

class VaultSecretsManager(SecretsManager):
    def __init__(self):
        self.client = hvac.Client(url='https://vault.example.com')
    
    def get_api_key(self, client_id: str) -> str:
        response = self.client.secrets.kv.v2.read_secret_version(
            path=f'fininfo/clients/{client_id}'
        )
        return response['data']['data']['api_key']