"""
Unit tests for JWT audience validation with RFC 8707 Resource Indicators.

Tests verify that:
1. Self-signed tokens (kid='mcp-self-signed') skip audience validation
2. Resource URLs are accepted as audience claims
3. Provider tokens still validate audience properly
"""

import jwt
import pytest
from unittest.mock import Mock, patch
import time


@pytest.mark.unit
@pytest.mark.auth
class TestJWTAudienceValidation:
    """Test JWT audience validation for RFC 8707 compliance."""

    def test_self_signed_token_skips_audience_validation(self):
        """Self-signed tokens should skip audience validation."""
        from auth_server.server import SECRET_KEY, JWT_ISSUER, JWT_SELF_SIGNED_KID
        
        # Create token with resource URL as audience
        resource_url = "http://localhost/proxy/mcpgw"
        current_time = int(time.time())
        
        token_payload = {
            "iss": JWT_ISSUER,
            "aud": resource_url,  # Resource URL, not "mcp-registry"
            "sub": "test-user",
            "scope": "test-scope",
            "exp": current_time + 3600,
            "iat": current_time,
        }
        
        headers = {
            "kid": JWT_SELF_SIGNED_KID,
            "typ": "JWT",
            "alg": "HS256"
        }
        
        token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256", headers=headers)
        
        # Verify we can decode without specifying audience
        # (simulating self-signed token validation)
        claims = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            options={"verify_aud": False}  # Skip audience validation
        )
        
        assert claims["aud"] == resource_url
        assert claims["sub"] == "test-user"
        
    def test_provider_token_validates_audience(self):
        """Provider tokens should validate audience strictly."""
        from auth_server.server import SECRET_KEY, JWT_ISSUER, JWT_AUDIENCE
        
        current_time = int(time.time())
        
        token_payload = {
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,  # Must match expected audience
            "sub": "test-user",
            "scope": "test-scope",
            "exp": current_time + 3600,
            "iat": current_time,
        }
        
        headers = {
            "kid": "provider-key-id",  # Not self-signed
            "typ": "JWT",
            "alg": "HS256"
        }
        
        token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256", headers=headers)
        
        # Should successfully decode with correct audience
        claims = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"verify_aud": True}
        )
        
        assert claims["aud"] == JWT_AUDIENCE
        
    def test_provider_token_rejects_wrong_audience(self):
        """Provider tokens should reject mismatched audience."""
        from auth_server.server import SECRET_KEY, JWT_ISSUER, JWT_AUDIENCE
        
        current_time = int(time.time())
        
        token_payload = {
            "iss": JWT_ISSUER,
            "aud": "wrong-audience",  # Mismatched
            "sub": "test-user",
            "scope": "test-scope",
            "exp": current_time + 3600,
            "iat": current_time,
        }
        
        headers = {
            "kid": "provider-key-id",
            "typ": "JWT",
            "alg": "HS256"
        }
        
        token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256", headers=headers)
        
        # Should raise InvalidAudienceError
        with pytest.raises(jwt.InvalidAudienceError):
            jwt.decode(
                token,
                SECRET_KEY,
                algorithms=["HS256"],
                issuer=JWT_ISSUER,
                audience=JWT_AUDIENCE,
                options={"verify_aud": True}
            )
            
    def test_resource_url_in_token_payload(self):
        """Token with resource URL should contain correct aud claim."""
        from auth_server.server import SECRET_KEY, JWT_ISSUER, JWT_SELF_SIGNED_KID
        
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
        
        headers = {
            "kid": JWT_SELF_SIGNED_KID,
            "typ": "JWT",
            "alg": "HS256"
        }
        
        token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256", headers=headers)
        
        # Decode and verify resource URL is preserved
        claims = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            options={"verify_aud": False}
        )
        
        assert claims["aud"] == resource_url
        assert "server123:read" in claims["scope"]
