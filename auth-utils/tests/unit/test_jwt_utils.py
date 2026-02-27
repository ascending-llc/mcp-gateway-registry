"""Unit tests for auth_utils.jwt_utils module."""

import time
from typing import Any

import jwt
import pytest

from auth_utils.jwt_utils import (
    decode_jwt,
    encode_jwt,
    get_token_kid,
    is_self_signed,
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

    def test_pyjwt_adds_typ_automatically(self):
        """PyJWT sets typ=JWT even when not specified in headers arg."""
        token = encode_jwt(_make_payload(), _SECRET, kid=_KID)
        header = jwt.get_unverified_header(token)
        assert header["typ"] == "JWT"

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
        """A token expired 10 s ago passes when leeway=30."""
        expired_payload = _make_payload(offset_seconds=-10)
        token = encode_jwt(expired_payload, _SECRET)
        # leeway=30 should tolerate 10 s of expiry
        claims = decode_jwt(token, _SECRET, issuer=_ISSUER, leeway=30)
        assert claims["sub"] == "user-1"

    def test_leeway_zero_rejects_slightly_expired_token(self):
        """A token expired 10 s ago fails when leeway=0."""
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


class TestIsSelfSigned:
    """Tests for is_self_signed."""

    def test_returns_true_when_kid_matches(self):
        """Returns True when the token's kid equals self_signed_kid."""
        token = encode_jwt(_make_payload(), _SECRET, kid=_KID)
        assert is_self_signed(token, _KID) is True

    def test_returns_false_when_kid_differs(self):
        """Returns False when the token's kid does not match self_signed_kid."""
        token = encode_jwt(_make_payload(), _SECRET, kid="other-kid")
        assert is_self_signed(token, _KID) is False

    def test_returns_false_when_kid_absent(self):
        """Returns False when the token has no kid header."""
        token = encode_jwt(_make_payload(), _SECRET)
        assert is_self_signed(token, _KID) is False
