"""JWT encoding and decoding utilities for MCP Gateway Registry.

Thin wrappers around PyJWT that standardise the HS256 algorithm,
header construction, and decode options used across all services.
"""

import logging
from typing import Any

import jwt

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
_DEFAULT_LEEWAY = 30  # seconds — clock skew tolerance


def encode_jwt(
    payload: dict[str, Any],
    secret_key: str,
    kid: str | None = None,
) -> str:
    """Encode a JWT using HS256.

    PyJWT automatically adds ``typ: JWT`` and ``alg: HS256`` to the header.
    Explicitly passing those fields in headers is therefore redundant; only
    ``kid`` is forwarded when provided.

    Args:
        payload: Claims to encode.
        secret_key: HMAC secret key.
        kid: Key ID added to the JWT header when provided.

    Returns:
        Encoded JWT string.
    """
    headers: dict[str, str] | None = {"kid": kid} if kid is not None else None
    return jwt.encode(payload, secret_key, algorithm=_ALGORITHM, headers=headers)


def decode_jwt(
    token: str,
    secret_key: str,
    issuer: str,
    audience: str | None = None,
    leeway: int = _DEFAULT_LEEWAY,
) -> dict[str, Any]:
    """Decode and verify a JWT.

    Audience is verified when ``audience`` is provided; skipped otherwise.

    Args:
        token: JWT token string.
        secret_key: HMAC secret key.
        issuer: Expected issuer claim.
        audience: Expected audience claim. Pass None to skip aud verification.
        leeway: Clock-skew tolerance in seconds (default: 30).

    Returns:
        Decoded claims dictionary.

    Raises:
        jwt.ExpiredSignatureError: Token has expired.
        jwt.InvalidTokenError: Token is otherwise invalid.
    """
    verify_aud = audience is not None
    options: dict[str, Any] = {
        "verify_exp": True,
        "verify_iat": True,
        "verify_iss": True,
        "verify_aud": verify_aud,
    }
    decode_kwargs: dict[str, Any] = {
        "algorithms": [_ALGORITHM],
        "issuer": issuer,
        "options": options,
        "leeway": leeway,
    }
    if verify_aud:
        decode_kwargs["audience"] = audience

    return jwt.decode(token, secret_key, **decode_kwargs)


def get_token_kid(token: str) -> str | None:
    """Return the ``kid`` from the unverified JWT header.

    Args:
        token: JWT token string.

    Returns:
        The kid value, or None if the header has no kid field.

    Raises:
        jwt.DecodeError: Header cannot be parsed.
    """
    header = jwt.get_unverified_header(token)
    return header.get("kid")


def is_self_signed(token: str, self_signed_kid: str) -> bool:
    """Return True when the token's kid matches self_signed_kid.

    Self-signed tokens use a well-known KID so they can be identified
    without full decoding. Used to skip audience validation per RFC 8707.

    Args:
        token: JWT token string.
        self_signed_kid: Expected KID for self-signed tokens.

    Returns:
        True if the kid matches, False otherwise.

    Raises:
        jwt.DecodeError: Header cannot be parsed.
    """
    return get_token_kid(token) == self_signed_kid
