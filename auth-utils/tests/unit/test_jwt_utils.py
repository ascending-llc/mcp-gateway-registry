"""Unit tests for auth_utils.jwt_utils module."""

import time
from typing import Any

import jwt
import pytest

from auth_utils.jwt_utils import (
    build_jwt_payload,
    decode_jwt,
    encode_jwt,
    get_token_kid,
)

_SECRET = "test-secret-key"
_ISSUER = "test-issuer"
_AUDIENCE = "test-audience"
_KID = "self-signed-v1"


def _make_payload(
    offset_seconds: int = 3600,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a minimal valid payload expiring ``offset_seconds`` from now."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": "user-1",
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + offset_seconds,
    }
    if extra:
        payload.update(extra)
    return payload


class TestEncodeJwt:
    """Tests for encode_jwt."""

    def test_produces_decodable_token(self):
        """encode_jwt output can be decoded by decode_jwt with matching params."""
        token = encode_jwt(_make_payload(), _SECRET, kid=_KID)
        claims = decode_jwt(token, _SECRET, issuer=_ISSUER, audience=_AUDIENCE)
        assert claims["sub"] == "user-1"

    def test_kid_is_set_in_header(self):
        """When kid is provided it appears in the JWT header."""
        token = encode_jwt(_make_payload(), _SECRET, kid=_KID)
        header = jwt.get_unverified_header(token)
        assert header["kid"] == _KID

    def test_no_kid_omits_kid_from_header(self):
        """When kid is None the header contains no kid field."""
        token = encode_jwt(_make_payload(), _SECRET)
        header = jwt.get_unverified_header(token)
        assert "kid" not in header

    def test_algorithm_is_hs256(self):
        """The encoded token always uses HS256."""
        token = encode_jwt(_make_payload(), _SECRET, kid=_KID)
        header = jwt.get_unverified_header(token)
        assert header["alg"] == "HS256"

    def test_explicit_kid_typ_alg_produce_same_token(self):
        """encode_jwt(kid=k) produces the same token as jwt.encode with explicit typ/alg headers."""
        payload = _make_payload()
        via_wrapper = encode_jwt(payload, _SECRET, kid=_KID)
        via_direct = jwt.encode(
            payload,
            _SECRET,
            algorithm="HS256",
            headers={"kid": _KID, "typ": "JWT", "alg": "HS256"},
        )
        assert via_wrapper == via_direct


class TestDecodeJwt:
    """Tests for decode_jwt."""

    def test_returns_claims_for_valid_token(self):
        """Decoding a valid token returns the expected claims."""
        token = encode_jwt(_make_payload(), _SECRET, kid=_KID)
        claims = decode_jwt(token, _SECRET, issuer=_ISSUER, audience=_AUDIENCE)
        assert claims["iss"] == _ISSUER

    def test_audience_none_skips_aud_verification(self):
        """audience=None decodes tokens without an aud claim."""
        payload = {
            "sub": "svc-1",
            "iss": _ISSUER,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }
        token = encode_jwt(payload, _SECRET)
        # Must not raise even though aud is absent in token
        claims = decode_jwt(token, _SECRET, issuer=_ISSUER)
        assert claims["sub"] == "svc-1"

    def test_wrong_audience_raises(self):
        """Providing a mismatched audience raises InvalidAudienceError."""
        token = encode_jwt(_make_payload(), _SECRET, kid=_KID)
        with pytest.raises(jwt.InvalidAudienceError):
            decode_jwt(token, _SECRET, issuer=_ISSUER, audience="wrong-audience")

    def test_expired_token_raises(self):
        """An expired token raises ExpiredSignatureError."""
        expired_payload = _make_payload(offset_seconds=-3600)
        token = encode_jwt(expired_payload, _SECRET)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_jwt(token, _SECRET, issuer=_ISSUER, leeway=0)

    def test_leeway_allows_slightly_expired_token(self):
        """A token expired 10s ago passes when leeway=30."""
        expired_payload = _make_payload(offset_seconds=-10)
        token = encode_jwt(expired_payload, _SECRET)
        # leeway=30 should tolerate 10 s of expiry
        claims = decode_jwt(token, _SECRET, issuer=_ISSUER, leeway=30)
        assert claims["sub"] == "user-1"

    def test_leeway_zero_rejects_slightly_expired_token(self):
        """A token expired 10s ago fails when leeway=0."""
        expired_payload = _make_payload(offset_seconds=-10)
        token = encode_jwt(expired_payload, _SECRET)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_jwt(token, _SECRET, issuer=_ISSUER, leeway=0)

    def test_bad_signature_raises(self):
        """A token signed with the wrong key raises InvalidSignatureError."""
        token = encode_jwt(_make_payload(), _SECRET, kid=_KID)
        with pytest.raises(jwt.InvalidSignatureError):
            decode_jwt(token, "wrong-secret", issuer=_ISSUER, audience=_AUDIENCE)

    def test_wrong_issuer_raises(self):
        """A token with a mismatched issuer raises InvalidIssuerError."""
        token = encode_jwt(_make_payload(), _SECRET, kid=_KID)
        with pytest.raises(jwt.InvalidIssuerError):
            decode_jwt(token, _SECRET, issuer="wrong-issuer", audience=_AUDIENCE)


class TestGetTokenKid:
    """Tests for get_token_kid."""

    def test_returns_kid_from_header(self):
        """Returns the kid value when present in the JWT header."""
        token = encode_jwt(_make_payload(), _SECRET, kid=_KID)
        assert get_token_kid(token) == _KID

    def test_returns_none_when_kid_absent(self):
        """Returns None when the token has no kid in the header."""
        token = encode_jwt(_make_payload(), _SECRET)
        assert get_token_kid(token) is None

    def test_raises_on_malformed_token(self):
        """Raises DecodeError for a string that is not a valid JWT."""
        with pytest.raises(jwt.DecodeError):
            get_token_kid("not.a.jwt")


class TestBuildJwtPayload:
    """Tests for build_jwt_payload."""

    def test_includes_standard_claims(self):
        """Payload includes sub, iss, aud, iat, exp claims."""
        payload = build_jwt_payload(
            subject="user@example.com",
            issuer=_ISSUER,
            audience=_AUDIENCE,
            expires_in_seconds=3600,
        )
        assert payload["sub"] == "user@example.com"
        assert payload["iss"] == _ISSUER
        assert payload["aud"] == _AUDIENCE
        assert "iat" in payload
        assert "exp" in payload

    def test_expiration_calculated_correctly(self):
        """exp is iat + expires_in_seconds."""
        payload = build_jwt_payload(
            subject="user",
            issuer=_ISSUER,
            audience=_AUDIENCE,
            expires_in_seconds=7200,
        )
        assert payload["exp"] == payload["iat"] + 7200

    def test_custom_iat_used_when_provided(self):
        """When iat is provided, it overrides auto-generated timestamp."""
        custom_iat = 1234567890
        payload = build_jwt_payload(
            subject="user",
            issuer=_ISSUER,
            audience=_AUDIENCE,
            expires_in_seconds=3600,
            iat=custom_iat,
        )
        assert payload["iat"] == custom_iat
        assert payload["exp"] == custom_iat + 3600

    def test_token_type_included_when_provided(self):
        """token_type is added to payload when specified."""
        payload = build_jwt_payload(
            subject="user",
            issuer=_ISSUER,
            audience=_AUDIENCE,
            expires_in_seconds=3600,
            token_type="access_token",
        )
        assert payload["token_type"] == "access_token"

    def test_token_type_omitted_when_none(self):
        """token_type is not in payload when None."""
        payload = build_jwt_payload(
            subject="user",
            issuer=_ISSUER,
            audience=_AUDIENCE,
            expires_in_seconds=3600,
            token_type=None,
        )
        assert "token_type" not in payload

    def test_extra_claims_merged_into_payload(self):
        """extra_claims dict is merged into the payload."""
        payload = build_jwt_payload(
            subject="user",
            issuer=_ISSUER,
            audience=_AUDIENCE,
            expires_in_seconds=3600,
            extra_claims={"groups": ["admin"], "scope": "read write", "custom_field": 123},
        )
        assert payload["groups"] == ["admin"]
        assert payload["scope"] == "read write"
        assert payload["custom_field"] == 123

    def test_extra_claims_can_override_standard_claims(self):
        """extra_claims can override standard claims if needed."""
        payload = build_jwt_payload(
            subject="user",
            issuer=_ISSUER,
            audience=_AUDIENCE,
            expires_in_seconds=3600,
            extra_claims={"sub": "overridden-user", "custom": "value"},
        )
        # extra_claims overwrites standard claims
        assert payload["sub"] == "overridden-user"
        assert payload["custom"] == "value"

    def test_empty_extra_claims_dict_works(self):
        """Passing empty dict for extra_claims doesn't break anything."""
        payload = build_jwt_payload(
            subject="user",
            issuer=_ISSUER,
            audience=_AUDIENCE,
            expires_in_seconds=3600,
            extra_claims={},
        )
        # Should only have standard claims
        assert "sub" in payload
        assert "iss" in payload
        assert len([k for k in payload if k not in ["sub", "iss", "aud", "iat", "exp"]]) == 0

    def test_payload_compatible_with_encode_jwt(self):
        """Payload from build_jwt_payload can be encoded and decoded."""
        payload = build_jwt_payload(
            subject="testuser",
            issuer=_ISSUER,
            audience=_AUDIENCE,
            expires_in_seconds=3600,
            token_type="access_token",
            extra_claims={"groups": ["admin"]},
        )
        token = encode_jwt(payload, _SECRET, kid=_KID)
        decoded = decode_jwt(token, _SECRET, issuer=_ISSUER, audience=_AUDIENCE)
        assert decoded["sub"] == "testuser"
        assert decoded["token_type"] == "access_token"
        assert decoded["groups"] == ["admin"]
