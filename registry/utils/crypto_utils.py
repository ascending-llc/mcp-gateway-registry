"""
Cryptographic utilities for encrypting/decrypting sensitive data.

This module provides AES-CBC encryption compatible with the TypeScript
encryption implementation used elsewhere in the system.

TypeScript equivalent:
- Algorithm: AES-CBC
- Key derivation: CREDS_KEY from hex string
- IV: Random 16 bytes per encryption
- Format: hex(iv):hex(ciphertext)
"""

import os
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from registry.utils.log import logger

# Algorithm constants
ALGORITHM = "AES-CBC"
IV_LENGTH = 16  # 128 bits

# Get encryption key from environment
_ENCRYPTION_KEY: bytes | None = None


def _get_encryption_key() -> bytes:
    """
    Get the encryption key from environment variable.

    Returns:
        bytes: encryption key from CREDS_KEY (hex decoded)

    Raises:
        ValueError: If CREDS_KEY is not set or invalid
    """
    global _ENCRYPTION_KEY

    if _ENCRYPTION_KEY is None:
        creds_key = os.environ.get("CREDS_KEY")
        if not creds_key:
            raise ValueError("CREDS_KEY environment variable must be set for encryption/decryption")

        # Decode from hex (matching TypeScript: Buffer.from(process.env.CREDS_KEY, 'hex'))
        try:
            key_bytes = bytes.fromhex(creds_key)
        except ValueError as e:
            raise ValueError(f"CREDS_KEY must be a valid hex string: {e}")

        _ENCRYPTION_KEY = key_bytes

    return _ENCRYPTION_KEY


def generate_service_jwt(
    user_id: str, username: str | None = None, scopes: list[str] | None = None
) -> str:
    """
    Generate internal service JWT for MCP server authentication.
    Used to authenticate registry -> MCP server requests with user context.

    Args:
        user_id: User ID to include in JWT
        username: Optional username/email
        scopes: Optional list of scopes

    Returns:
        JWT token string (without Bearer prefix)
    """
    from registry.core.config import settings

    now = datetime.now(UTC)

    # Build JWT payload with user context
    payload = {
        "user_id": user_id,
        "sub": username or user_id,
        "iss": settings.JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=5),  # Short-lived for service-to-service
        "jti": f"registry-{now.timestamp()}",
        "client_id": settings.registry_app_name,
        "token_type": "service",
    }

    # Add optional fields
    if scopes:
        payload["scopes"] = scopes

    # Sign with registry secret
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")

    return token


def encrypt_value(plaintext: str) -> str:
    """
    Encrypts a value using AES-CBC with a random IV.

    This implementation is compatible with the TypeScript encryptV2 function:
    - Uses AES-CBC encryption (matching Web Crypto API)
    - Generates a random 16-byte IV for each encryption
    - Returns format: hex(iv):hex(ciphertext)
    - NO padding (Web Crypto API handles this automatically)

    Args:
        plaintext: The plaintext string to encrypt

    Returns:
        str: Encrypted string in format "iv_hex:ciphertext_hex"

    Raises:
        ValueError: If CREDS_KEY is not configured
        Exception: If encryption fails
    """
    if not plaintext:
        return plaintext

    try:
        # Get encryption key
        key = _get_encryption_key()

        # Generate random IV
        gen_iv = os.urandom(IV_LENGTH)

        # Encode plaintext
        plaintext_bytes = plaintext.encode("utf-8")

        # Pad to 16-byte boundary (AES block size)
        block_size = 16
        padding_length = block_size - (len(plaintext_bytes) % block_size)
        padded_data = plaintext_bytes + bytes([padding_length] * padding_length)

        # Create cipher
        cipher = Cipher(algorithms.AES(key), modes.CBC(gen_iv), backend=default_backend())
        encryptor = cipher.encryptor()

        # Encrypt
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        # Return as hex(iv):hex(ciphertext)
        return gen_iv.hex() + ":" + ciphertext.hex()

    except Exception as e:
        logger.error(f"Encryption failed: {e}", exc_info=True)
        raise Exception(f"Failed to encrypt value: {e}")


def decrypt_value(encrypted_value: str) -> str:
    """
    Decrypts an encrypted value using AES-CBC.

    This implementation is compatible with the TypeScript decryptV2 function:
    - Expects format: hex(iv):hex(ciphertext)
    - Uses AES-CBC decryption (matching Web Crypto API)
    - Returns original plaintext

    If the value doesn't contain a colon separator, it's assumed to be
    already decrypted and returned as-is (for backward compatibility).

    Args:
        encrypted_value: The encrypted string in format "iv_hex:ciphertext_hex"

    Returns:
        str: Decrypted plaintext string

    Raises:
        ValueError: If CREDS_KEY is not configured or format is invalid
        Exception: If decryption fails
    """
    if not encrypted_value:
        return encrypted_value

    # Check if value is encrypted (contains colon separator)
    parts = encrypted_value.split(":")
    if len(parts) == 1:
        # Not encrypted, return as-is (matching TS: if (parts.length === 1) return parts[0])
        return parts[0]

    try:
        # Get encryption key
        key = _get_encryption_key()

        # Split IV and ciphertext (matching TS logic)
        gen_iv = bytes.fromhex(parts[0])
        encrypted = ":".join(parts[1:])

        # Convert ciphertext from hex
        ciphertext = bytes.fromhex(encrypted)

        # Validate IV length
        if len(gen_iv) != IV_LENGTH:
            raise ValueError(f"Invalid IV length: expected {IV_LENGTH}, got {len(gen_iv)}")

        # Create cipher
        cipher = Cipher(algorithms.AES(key), modes.CBC(gen_iv), backend=default_backend())
        decryptor = cipher.decryptor()

        # Decrypt
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        # Remove padding (standard PKCS#7 unpadding)
        padding_length = padded_plaintext[-1]
        plaintext_bytes = padded_plaintext[:-padding_length]

        # Convert to string
        return plaintext_bytes.decode("utf-8")

    except Exception as e:
        logger.error(f"Decryption failed: {e}", exc_info=True)
        raise Exception(f"Failed to decrypt value: {e}")


def encrypt_auth_fields(config: dict) -> dict:
    """
    Encrypt sensitive authentication fields in server config.

    Handles two authentication patterns:
    1. authentication.client_secret (when type=oauth)
    2. apiKey.key

    Args:
        config: Server configuration dictionary

    Returns:
        dict: Config with encrypted sensitive fields

    Note:
        If CREDS_KEY is not set, values will be stored as plaintext.
        A warning will be logged in this case.
    """
    if not config:
        return config

    config = config.copy()

    # Check if CREDS_KEY is available
    if not os.environ.get("CREDS_KEY"):
        logger.warning(
            "CREDS_KEY environment variable is not set. "
            "Sensitive authentication fields will be stored as PLAINTEXT. "
            "Set CREDS_KEY to enable encryption of credentials."
        )
        return config

    try:
        # Handle authentication field
        if "authentication" in config and isinstance(config["authentication"], dict):
            auth = config["authentication"].copy()
            auth_type = auth.get("type", "").lower()

            if auth_type == "oauth" and "client_secret" in auth:
                # Encrypt OAuth client_secret
                client_secret = auth["client_secret"]
                if client_secret and ":" not in str(client_secret):
                    # Only encrypt if not already encrypted
                    try:
                        auth["client_secret"] = encrypt_value(str(client_secret))
                        config["authentication"] = auth
                        logger.debug("Encrypted authentication.client_secret")
                    except Exception as encrypt_error:
                        logger.error(f"Failed to encrypt client_secret: {encrypt_error}")
                        # Keep plaintext value

        # Handle apiKey field
        if "apiKey" in config and isinstance(config["apiKey"], dict):
            api_key = config["apiKey"].copy()

            if "key" in api_key:
                key_value = api_key["key"]
                if key_value and ":" not in str(key_value):
                    # Only encrypt if not already encrypted
                    try:
                        api_key["key"] = encrypt_value(str(key_value))
                        config["apiKey"] = api_key
                        logger.debug("Encrypted apiKey.key")
                    except Exception as encrypt_error:
                        logger.error(f"Failed to encrypt apiKey.key: {encrypt_error}")
                        # Keep plaintext value

    except Exception as e:
        logger.error(f"Failed to encrypt auth fields: {e}", exc_info=True)
        # Return original config if encryption fails
        return config

    return config


def decrypt_auth_fields(config: dict) -> dict:
    """
    Decrypt sensitive authentication fields in server config.

    Handles two authentication patterns:
    1. authentication.client_secret (when type=oauth)
    2. apiKey.key

    Args:
        config: Server configuration dictionary with encrypted fields

    Returns:
        dict: Config with decrypted sensitive fields

    Note:
        If CREDS_KEY is not set, encrypted values will be returned as-is (still encrypted).
        This prevents the API from crashing when CREDS_KEY is not configured.
    """
    if not config:
        return config

    config = config.copy()

    # Check if CREDS_KEY is available
    if not os.environ.get("CREDS_KEY"):
        logger.warning(
            "CREDS_KEY environment variable is not set. "
            "Encrypted authentication fields will be returned as-is (still encrypted). "
            "Set CREDS_KEY to decrypt sensitive credentials."
        )
        return config

    try:
        # Handle authentication field
        if "authentication" in config and isinstance(config["authentication"], dict):
            auth = config["authentication"].copy()
            auth_type = auth.get("type", "").lower()

            if auth_type == "oauth" and "client_secret" in auth:
                # Decrypt OAuth client_secret
                client_secret = auth["client_secret"]
                if client_secret:
                    try:
                        auth["client_secret"] = decrypt_value(str(client_secret))
                        config["authentication"] = auth
                        logger.debug("Decrypted authentication.client_secret")
                    except Exception as decrypt_error:
                        logger.warning(f"Failed to decrypt client_secret: {decrypt_error}")
                        # Keep encrypted value

        # Handle apiKey field
        if "apiKey" in config and isinstance(config["apiKey"], dict):
            api_key = config["apiKey"].copy()

            if "key" in api_key:
                key_value = api_key["key"]
                if key_value:
                    try:
                        api_key["key"] = decrypt_value(str(key_value))
                        config["apiKey"] = api_key
                        logger.debug("Decrypted apiKey.key")
                    except Exception as decrypt_error:
                        logger.warning(f"Failed to decrypt apiKey.key: {decrypt_error}")
                        # Keep encrypted value

    except Exception as e:
        logger.error(f"Failed to decrypt auth fields: {e}", exc_info=True)
        # Return original config if decryption fails
        return config

    return config
