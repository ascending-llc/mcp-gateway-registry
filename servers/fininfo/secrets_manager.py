"""
Secrets Manager for Financial Info MCP Server

This is a wrapper class to illustrate how you can plugin any secrets manager of choice.
For simplicity, we are reading from a YAML file, but this could be extended to:
- Read from encrypted files that can be decrypted with a secret key
- Connect to AWS Secrets Manager, HashiCorp Vault, Azure Key Vault, etc.
- Use the SECRET_KEY from environment variables for encryption/decryption
- Implement key rotation and caching mechanisms

The current implementation provides a foundation that can be easily extended
for production use cases while maintaining a simple interface.
"""

import os
import yaml
import logging
from typing import Dict, Optional
from pathlib import Path
from cryptography.fernet import Fernet
import base64
import hashlib

logger = logging.getLogger(__name__)


class SecretsManager:
    """
    Generic secrets manager that provides a simple interface for loading and retrieving API keys.
    
    This implementation reads from a YAML file but can be extended to support:
    - Encrypted file storage using the SECRET_KEY from environment
    - External secrets management services (AWS Secrets Manager, Vault, etc.)
    - Database storage with encryption at rest
    - Key rotation and automatic reloading
    """
    
    def __init__(self, secrets_file_path: str = "/app/fininfo/.keys.yml"):
        """
        Initialize the secrets manager.
        
        Args:
            secrets_file_path: Base path to the secrets file (default: /app/fininfo/.keys.yml)
                              Will first try .encrypted version, then fall back to plain text
        """
        self.base_secrets_file_path = Path(secrets_file_path)
        self.secrets: Dict[str, str] = {}
        self.secret_key = os.environ.get("SECRET_KEY")
        
        # Load secrets on initialization
        self.load_secrets()
    
    def _get_encryption_key(self) -> Optional[bytes]:
        """
        Generate a Fernet encryption key from the SECRET_KEY environment variable.
        
        This demonstrates how the existing SECRET_KEY could be used for encryption.
        In production, you might want to use a dedicated encryption key.
        
        Returns:
            bytes: Fernet-compatible encryption key, or None if SECRET_KEY not available
        """
        if not self.secret_key:
            return None
            
        # Create a consistent 32-byte key from the SECRET_KEY
        key_bytes = hashlib.sha256(self.secret_key.encode()).digest()
        return base64.urlsafe_b64encode(key_bytes)
    
    def _decrypt_file_content(self, encrypted_content: bytes) -> str:
        """
        Decrypt file content using the SECRET_KEY.
        
        This is an example of how encrypted secrets could be handled.
        Currently not used but shows the extensibility.
        
        Args:
            encrypted_content: Encrypted file content
            
        Returns:
            str: Decrypted content
            
        Raises:
            ValueError: If decryption fails or SECRET_KEY not available
        """
        encryption_key = self._get_encryption_key()
        if not encryption_key:
            raise ValueError("SECRET_KEY not available for decryption")
            
        fernet = Fernet(encryption_key)
        try:
            decrypted_bytes = fernet.decrypt(encrypted_content)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Failed to decrypt secrets file: {e}")
    
    def load_secrets(self) -> None:
        """
        Load secrets from the configured file with fallback logic.
        
        First tries to load from .encrypted file, then falls back to plain text file.
        
        The file format supports:
        - Simple key-value pairs: client_id: api_key
        - Multiple client IDs with their respective API keys
        
        Example YAML format:
        client1: api_key_1
        client2: api_key_2
        default: fallback_api_key
        
        Fallback logic:
        1. Try base_path + '.encrypted' (encrypted file)
        2. If not found, try base_path (plain text file)
        3. If neither found, create empty secrets dictionary
        """
        # Try encrypted file first
        encrypted_file_path = Path(str(self.base_secrets_file_path) + '.encrypted')
        plain_file_path = self.base_secrets_file_path
        
        secrets_file_path = None
        is_encrypted = False
        
        if encrypted_file_path.exists():
            secrets_file_path = encrypted_file_path
            is_encrypted = True
            logger.info(f"Found encrypted secrets file: {encrypted_file_path}")
        elif plain_file_path.exists():
            secrets_file_path = plain_file_path
            is_encrypted = False
            logger.info(f"Found plain text secrets file: {plain_file_path}")
        else:
            logger.warning(f"No secrets file found. Tried:")
            logger.warning(f"  - Encrypted: {encrypted_file_path}")
            logger.warning(f"  - Plain text: {plain_file_path}")
            logger.info("Creating empty secrets dictionary. Add secrets to enable client-specific API keys.")
            self.secrets = {}
            return
        
        try:
            if is_encrypted:
                logger.info("Loading encrypted secrets file, attempting to decrypt...")
                try:
                    with open(secrets_file_path, 'r') as file:
                        encrypted_content_b64 = file.read().strip()
                    
                    # Decode the base64 content and decrypt
                    import base64
                    encrypted_content = base64.b64decode(encrypted_content_b64)
                    content = self._decrypt_file_content(encrypted_content)
                    logger.info("Successfully decrypted secrets file")
                except Exception as e:
                    logger.error(f"Failed to decrypt secrets file: {e}")
                    raise ValueError(f"Cannot decrypt secrets file: {e}")
            else:
                # Plain text file
                logger.info("Loading plain text secrets file...")
                with open(secrets_file_path, 'r') as file:
                    content = file.read()
            
            self.secrets = yaml.safe_load(content) or {}
                
            logger.info(f"Loaded {len(self.secrets)} client secrets from {secrets_file_path}")
            logger.debug(f"Available client IDs: {list(self.secrets.keys())}")
            
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML secrets file: {e}")
            self.secrets = {}
        except Exception as e:
            logger.error(f"Error loading secrets file: {e}")
            self.secrets = {}
    
    def reload_secrets(self) -> None:
        """
        Reload secrets from the file.
        
        This allows for runtime updates without restarting the server.
        In production, you might want to add file watching or periodic reloading.
        """
        logger.info("Reloading secrets from file...")
        old_count = len(self.secrets)
        self.load_secrets()
        new_count = len(self.secrets)
        
        if new_count != old_count:
            logger.info(f"Secrets reloaded: {old_count} -> {new_count} client configurations")
        else:
            logger.info("Secrets reloaded successfully")
    
    def get_api_key(self, client_id: str) -> Optional[str]:
        """
        Retrieve the API key for a specific client ID.
        
        Args:
            client_id: The client identifier
            
        Returns:
            str: The API key for the client, or None if not found
            
        Note:
            This method could be extended to:
            - Log access attempts for auditing
            - Implement rate limiting per client
            - Cache frequently accessed keys
            - Validate key expiration dates
        """
        if not client_id:
            logger.warning("Empty client_id provided to get_api_key")
            return None
            
        api_key = self.secrets.get(client_id)
        
        if api_key:
            # Redact the API key for security - show only first 4 and last 4 characters
            redacted_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***REDACTED***"
            logger.info(f"API key found for client_id: {client_id} (key: {redacted_key})")
            logger.debug(f"API key length for {client_id}: {len(api_key)} characters")
        else:
            logger.warning(f"No API key found for client_id: {client_id}")
            logger.debug(f"Available client IDs: {list(self.secrets.keys())}")
            
        return api_key
    
    def has_client(self, client_id: str) -> bool:
        """
        Check if a client ID exists in the secrets.
        
        Args:
            client_id: The client identifier
            
        Returns:
            bool: True if client exists, False otherwise
        """
        return client_id in self.secrets
    
    def get_all_client_ids(self) -> list:
        """
        Get a list of all configured client IDs.
        
        Returns:
            list: List of client IDs
            
        Note:
            This method is useful for debugging and administrative purposes.
            In production, you might want to restrict access to this information.
        """
        return list(self.secrets.keys())
    
    def encrypt_secrets_file(self, input_file: str = None, output_file: str = None) -> bool:
        """
        Encrypt a secrets file using the SECRET_KEY.
        
        Args:
            input_file: Path to the plain text secrets file (default: current secrets file)
            output_file: Path to save encrypted file (default: input_file + '.encrypted')
            
        Returns:
            bool: True if encryption successful, False otherwise
            
        Example:
            # Encrypt the current secrets file
            secrets_manager.encrypt_secrets_file()
            
            # Encrypt a specific file
            secrets_manager.encrypt_secrets_file('plain.yml', 'encrypted.yml')
        """
        if not input_file:
            input_file = str(self.base_secrets_file_path)
        
        if not output_file:
            output_file = input_file + '.encrypted'
        
        try:
            encryption_key = self._get_encryption_key()
            if not encryption_key:
                logger.error("Cannot encrypt: SECRET_KEY not available")
                return False
            
            # Read the plain text file
            with open(input_file, 'r') as f:
                plain_content = f.read()
            
            # Encrypt the content
            fernet = Fernet(encryption_key)
            encrypted_data = fernet.encrypt(plain_content.encode('utf-8'))
            
            # Encode to base64 for storage
            import base64
            encoded_data = base64.b64encode(encrypted_data).decode('utf-8')
            
            # Write encrypted file
            with open(output_file, 'w') as f:
                f.write(encoded_data)
            
            logger.info(f"Successfully encrypted {input_file} to {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to encrypt secrets file: {e}")
            return False
    
    def get_stats(self) -> Dict[str, any]:
        """
        Get statistics about the secrets manager.
        
        Returns:
            dict: Statistics including client count, file path, etc.
        """
        encrypted_file_path = Path(str(self.base_secrets_file_path) + '.encrypted')
        plain_file_path = self.base_secrets_file_path
        
        return {
            "base_secrets_file": str(self.base_secrets_file_path),
            "encrypted_file_path": str(encrypted_file_path),
            "plain_file_path": str(plain_file_path),
            "encrypted_file_exists": encrypted_file_path.exists(),
            "plain_file_exists": plain_file_path.exists(),
            "active_file": str(encrypted_file_path) if encrypted_file_path.exists() else str(plain_file_path),
            "using_encrypted": encrypted_file_path.exists(),
            "client_count": len(self.secrets),
            "client_ids": list(self.secrets.keys()),
            "encryption_available": self.secret_key is not None,
            "secret_key_length": len(self.secret_key) if self.secret_key else 0
        }