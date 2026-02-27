"""JWT encoding and decoding utilities for MCP Gateway Registry.

Thin wrappers around PyJWT that standardise the HS256 algorithm,
header construction, and decode options used across all services.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import jwt

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
_DEFAULT_LEEWAY = 30  # seconds — clock skew tolerance


def build_jwt_payload(
    subject: str,
    issuer: str,
    audience: str,
    expires_in_seconds: int,
    token_type: str | None = None,
    iat: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standardized JWT payload with common claims.

    Constructs a JWT payload dict with standard claims (sub, iss, aud, iat, exp)
    and optional extra claims. Centralizes JWT claim structure across services.

    Args:
        subject: Subject claim (typically username or user ID).
        issuer: Issuer claim (typically service name).
        audience: Audience claim (typically target service).
        expires_in_seconds: Token expiration time from now in seconds.
        token_type: Optional token type (e.g., "access_token", "refresh_token").
        iat: Optional issued-at timestamp. If None, uses current UTC time.
        extra_claims: Optional dict of additional claims to include.

    Returns:
        JWT payload dictionary with standard and extra claims.

    """
    now = iat if iat is not None else int(datetime.now(UTC).timestamp())
    exp = now + expires_in_seconds

    payload: dict[str, Any] = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": exp,
    }

    if token_type is not None:
        payload["token_type"] = token_type

    if extra_claims:
        payload.update(extra_claims)

    return payload


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
