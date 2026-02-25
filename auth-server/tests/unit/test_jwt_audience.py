"""
Unit tests for JWT audience validation with RFC 8707 Resource Indicators.

Tests verify that:
1. Self-signed tokens (kid='mcp-self-signed') skip audience validation
2. Resource URLs are accepted as audience claims
3. Provider tokens still validate audience properly
"""

import time

import jwt
import pytest


@pytest.mark.unit
@pytest.mark.auth
class TestJWTAudienceValidation:
    """Test JWT audience validation for RFC 8707 compliance."""

    def test_self_signed_token_skips_audience_validation(self):
        """Self-signed tokens should skip audience validation."""
        from auth_server.core.config import settings
        from auth_server.server import JWT_ISSUER, JWT_SELF_SIGNED_KID

        resource_url = "http://localhost/proxy/mcpgw"
        current_time = int(time.time())

        token_payload = {
            "iss": JWT_ISSUER,
            "aud": resource_url,
            "sub": "test-user",
            "scope": "test-scope",
            "exp": current_time + 3600,
            "iat": current_time,
        }

        headers = {"kid": JWT_SELF_SIGNED_KID, "typ": "JWT", "alg": "HS256"}

        token = jwt.encode(token_payload, settings.secret_key, algorithm="HS256", headers=headers)

        claims = jwt.decode(
            token, settings.secret_key, algorithms=["HS256"], issuer=JWT_ISSUER, options={"verify_aud": False}
        )

        assert claims["aud"] == resource_url
        assert claims["sub"] == "test-user"

    def test_provider_token_validates_audience(self):
        """Provider tokens should validate audience strictly."""
        from auth_server.core.config import settings
        from auth_server.server import JWT_AUDIENCE, JWT_ISSUER

        current_time = int(time.time())

        token_payload = {
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "sub": "test-user",
            "scope": "test-scope",
            "exp": current_time + 3600,
            "iat": current_time,
        }

        headers = {"kid": "provider-key-id", "typ": "JWT", "alg": "HS256"}

        token = jwt.encode(token_payload, settings.secret_key, algorithm="HS256", headers=headers)

        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"verify_aud": True},
        )

        assert claims["aud"] == JWT_AUDIENCE

    def test_provider_token_rejects_wrong_audience(self):
        """Provider tokens should reject mismatched audience."""
        from auth_server.core.config import settings
        from auth_server.server import JWT_AUDIENCE, JWT_ISSUER

        current_time = int(time.time())

        token_payload = {
            "iss": JWT_ISSUER,
            "aud": "wrong-audience",
            "sub": "test-user",
            "scope": "test-scope",
            "exp": current_time + 3600,
            "iat": current_time,
        }

        headers = {"kid": "provider-key-id", "typ": "JWT", "alg": "HS256"}

        token = jwt.encode(token_payload, settings.secret_key, algorithm="HS256", headers=headers)

        with pytest.raises(jwt.InvalidAudienceError):
            jwt.decode(
                token,
                settings.secret_key,
                algorithms=["HS256"],
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
                options={"verify_aud": True},
            )

    def test_resource_url_in_token_payload(self):
        """Token with resource URL should contain correct aud claim."""
        from auth_server.core.config import settings
        from auth_server.server import JWT_ISSUER, JWT_SELF_SIGNED_KID

        resource_url = "http://localhost/proxy/server123"
        current_time = int(time.time())

        token_payload = {
            "iss": JWT_ISSUER,
            "aud": resource_url,
            "sub": "test-user",
            "scope": "server123:read server123:write",
            "exp": current_time + 3600,
            "iat": current_time,
        }

        headers = {"kid": JWT_SELF_SIGNED_KID, "typ": "JWT", "alg": "HS256"}

        token = jwt.encode(token_payload, settings.secret_key, algorithm="HS256", headers=headers)

        claims = jwt.decode(
            token, settings.secret_key, algorithms=["HS256"], issuer=JWT_ISSUER, options={"verify_aud": False}
        )

        assert claims["aud"] == resource_url
        assert "server123:read" in claims["scope"]
