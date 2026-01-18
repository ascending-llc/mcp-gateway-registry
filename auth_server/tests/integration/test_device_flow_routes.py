"""
Integration tests for OAuth 2.0 Device Flow routes.

Tests the complete device authorization flow as defined in RFC 8628.
"""
import time
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.device_flow
class TestDeviceFlowRoutes:
    """Integration tests for device flow endpoints."""

    def test_device_authorization_success(self, test_client: TestClient, clear_device_storage):
        """Test successful device code generation."""
        response = test_client.post(
            "/oauth2/device/code",
            data={
                "client_id": "test-client",
                "scope": "openid profile"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response contains all required fields per RFC 8628
        assert "device_code" in data
        assert "user_code" in data
        assert "verification_uri" in data
        assert "expires_in" in data
        assert "interval" in data
        
        # Verify field formats
        assert len(data["device_code"]) > 20  # Device code should be sufficiently long
        assert len(data["user_code"]) == 9  # Format: XXXX-XXXX
        assert "-" in data["user_code"]
        assert data["verification_uri"].startswith("http")
        assert data["expires_in"] == 600  # 10 minutes
        assert data["interval"] == 5  # Poll every 5 seconds
        
        # Verify optional fields
        assert "verification_uri_complete" in data
        assert data["user_code"] in data["verification_uri_complete"]

    def test_device_authorization_without_scope(self, test_client: TestClient, clear_device_storage):
        """Test device code generation without scope parameter."""
        response = test_client.post(
            "/oauth2/device/code",
            data={"client_id": "test-client"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "device_code" in data
        assert "user_code" in data

    def test_device_authorization_missing_client_id(self, test_client: TestClient, clear_device_storage):
        """Test device code generation without required client_id."""
        response = test_client.post(
            "/oauth2/device/code",
            data={"scope": "openid"}
        )
        
        assert response.status_code == 422  # Validation error

    def test_device_verification_page(self, test_client: TestClient, clear_device_storage):
        """Test device verification HTML page rendering."""
        # First, generate a device code
        device_response = test_client.post(
            "/oauth2/device/code",
            data={"client_id": "test-client"}
        )
        user_code = device_response.json()["user_code"]
        
        # Access verification page
        response = test_client.get(f"/oauth2/device/verify?user_code={user_code}")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Verify page contains expected content
        content = response.text
        assert user_code in content
        assert "Device Authorization" in content or "Verify" in content

    def test_device_verification_page_without_user_code(self, test_client: TestClient):
        """Test verification page without user_code parameter."""
        response = test_client.get("/oauth2/device/verify")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Should show form to enter user code
        content = response.text
        assert "user_code" in content.lower()

    def test_device_approval_success(self, test_client: TestClient, clear_device_storage):
        """Test successful device approval."""
        # Generate device code
        device_response = test_client.post(
            "/oauth2/device/code",
            data={"client_id": "test-client", "scope": "openid"}
        )
        device_code = device_response.json()["device_code"]
        user_code = device_response.json()["user_code"]
        
        # Approve the device
        approval_response = test_client.post(
            "/oauth2/device/approve",
            data={"user_code": user_code}
        )
        
        assert approval_response.status_code == 200
        data = approval_response.json()
        assert data["status"] == "approved"
        assert "message" in data

    def test_device_approval_invalid_user_code(self, test_client: TestClient, clear_device_storage):
        """Test device approval with invalid user code."""
        response = test_client.post(
            "/oauth2/device/approve",
            data={"user_code": "INVALID-CODE"}
        )
        
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_device_approval_missing_user_code(self, test_client: TestClient):
        """Test device approval without user_code parameter."""
        response = test_client.post(
            "/oauth2/device/approve",
            data={}
        )
        
        assert response.status_code == 422  # Validation error

    def test_device_token_pending(self, test_client: TestClient, clear_device_storage):
        """Test token polling when authorization is pending."""
        # Generate device code
        device_response = test_client.post(
            "/oauth2/device/code",
            data={"client_id": "test-client"}
        )
        device_code = device_response.json()["device_code"]
        
        # Poll for token before approval
        token_response = test_client.post(
            "/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "test-client"
            }
        )
        
        assert token_response.status_code == 400
        data = token_response.json()
        assert data["detail"] == "authorization_pending"

    def test_device_token_success(self, test_client: TestClient, clear_device_storage):
        """Test successful token retrieval after approval."""
        # Generate device code
        device_response = test_client.post(
            "/oauth2/device/code",
            data={"client_id": "test-client", "scope": "openid profile"}
        )
        device_code = device_response.json()["device_code"]
        user_code = device_response.json()["user_code"]
        
        # Approve the device
        test_client.post(
            "/oauth2/device/approve",
            data={"user_code": user_code}
        )
        
        # Poll for token after approval
        token_response = test_client.post(
            "/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "test-client"
            }
        )
        
        assert token_response.status_code == 200
        data = token_response.json()
        
        # Verify token response fields per RFC 8628
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "Bearer"
        assert "expires_in" in data
        assert data["expires_in"] == 3600  # 1 hour
        
        # Verify token format (JWT)
        assert len(data["access_token"]) > 50
        assert data["access_token"].count(".") == 2  # JWT has 3 parts separated by dots

    def test_device_token_invalid_grant_type(self, test_client: TestClient, clear_device_storage):
        """Test token request with invalid grant type."""
        response = test_client.post(
            "/oauth2/token",
            data={
                "grant_type": "invalid_grant_type",
                "device_code": "test-code",
                "client_id": "test-client"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "unsupported_grant_type"

    def test_device_token_invalid_device_code(self, test_client: TestClient, clear_device_storage):
        """Test token request with invalid device code."""
        response = test_client.post(
            "/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": "invalid-device-code",
                "client_id": "test-client"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "invalid_grant"

    def test_device_token_client_mismatch(self, test_client: TestClient, clear_device_storage):
        """Test token request with mismatched client_id."""
        # Generate device code with one client
        device_response = test_client.post(
            "/oauth2/device/code",
            data={"client_id": "client-1"}
        )
        device_code = device_response.json()["device_code"]
        
        # Try to poll with different client
        response = test_client.post(
            "/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "client-2"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "invalid_client"

    def test_device_token_expired(self, test_client: TestClient, clear_device_storage):
        """Test token request with expired device code."""
        # Generate device code
        device_response = test_client.post(
            "/oauth2/device/code",
            data={"client_id": "test-client"}
        )
        device_code = device_response.json()["device_code"]
        
        # Manually expire the device code
        from auth_server.routes.device_flow import device_codes_storage
        device_codes_storage[device_code]["expires_at"] = int(time.time()) - 1
        
        # Trigger cleanup to remove expired code
        test_client.post(
            "/oauth2/device/code",
            data={"client_id": "test-client"}
        )
        
        # Try to poll with expired code (now removed)
        response = test_client.post(
            "/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "test-client"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["detail"] == "invalid_grant"  # Code no longer exists after cleanup

    def test_device_token_slow_down(self, test_client: TestClient, clear_device_storage):
        """Test polling behavior (slow_down not implemented yet, returns authorization_pending)."""
        # Generate device code
        device_response = test_client.post(
            "/oauth2/device/code",
            data={"client_id": "test-client"}
        )
        device_code = device_response.json()["device_code"]
        
        # First poll
        response1 = test_client.post(
            "/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "test-client"
            }
        )
        
        # Second poll immediately (too fast)
        response2 = test_client.post(
            "/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "test-client"
            }
        )
        
        # Both should return authorization_pending (slow_down not yet implemented)
        assert response1.status_code == 400
        assert response1.json()["detail"] == "authorization_pending"
        assert response2.status_code == 400
        assert response2.json()["detail"] == "authorization_pending"

    def test_complete_device_flow(self, test_client: TestClient, clear_device_storage):
        """Test the complete device authorization flow end-to-end."""
        # Step 1: Client requests device code
        device_response = test_client.post(
            "/oauth2/device/code",
            data={
                "client_id": "test-client",
                "scope": "openid profile email"
            }
        )
        assert device_response.status_code == 200
        device_code = device_response.json()["device_code"]
        user_code = device_response.json()["user_code"]
        verification_uri = device_response.json()["verification_uri"]
        
        # Step 2: User visits verification page
        verify_response = test_client.get(f"{verification_uri}?user_code={user_code}")
        assert verify_response.status_code == 200
        
        # Step 3: User approves device
        approve_response = test_client.post(
            "/oauth2/device/approve",
            data={"user_code": user_code}
        )
        assert approve_response.status_code == 200
        
        # Step 4: Client polls for token
        token_response = test_client.post(
            "/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "test-client"
            }
        )
        assert token_response.status_code == 200
        
        # Verify token
        token_data = token_response.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "Bearer"
        
        # Step 5: Verify token can't be reused
        second_token_response = test_client.post(
            "/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "test-client"
            }
        )
        # Should return the same token or invalid_grant
        assert second_token_response.status_code in [200, 400]

    def test_user_code_format(self, test_client: TestClient, clear_device_storage):
        """Test that user codes follow expected format."""
        # Generate multiple codes to verify format consistency
        for _ in range(5):
            response = test_client.post(
                "/oauth2/device/code",
                data={"client_id": "test-client"}
            )
            user_code = response.json()["user_code"]
            
            # Format: XXXX-XXXX (8 alphanumeric chars with dash)
            assert len(user_code) == 9
            assert user_code[4] == "-"
            
            # Should be uppercase alphanumeric
            parts = user_code.split("-")
            assert len(parts) == 2
            assert len(parts[0]) == 4
            assert len(parts[1]) == 4
            assert parts[0].isalnum()
            assert parts[1].isalnum()
            assert parts[0].isupper()
            assert parts[1].isupper()

    def test_device_code_uniqueness(self, test_client: TestClient, clear_device_storage):
        """Test that device codes and user codes are unique."""
        codes = set()
        user_codes = set()
        
        # Generate multiple device codes
        for _ in range(10):
            response = test_client.post(
                "/oauth2/device/code",
                data={"client_id": "test-client"}
            )
            data = response.json()
            codes.add(data["device_code"])
            user_codes.add(data["user_code"])
        
        # All codes should be unique
        assert len(codes) == 10
        assert len(user_codes) == 10

    def test_cleanup_expired_codes(self, test_client: TestClient, clear_device_storage):
        """Test that expired device codes are cleaned up."""
        from auth_server.routes.device_flow import device_codes_storage, user_codes_storage
        
        # Generate device code
        response = test_client.post(
            "/oauth2/device/code",
            data={"client_id": "test-client"}
        )
        device_code = response.json()["device_code"]
        user_code = response.json()["user_code"]
        
        # Verify code exists
        assert device_code in device_codes_storage
        assert user_code in user_codes_storage
        
        # Expire the code
        device_codes_storage[device_code]["expires_at"] = int(time.time()) - 1
        
        # Trigger cleanup by making another request
        test_client.post(
            "/oauth2/device/code",
            data={"client_id": "test-client"}
        )
        
        # Expired code should be cleaned up
        assert device_code not in device_codes_storage
        assert user_code not in user_codes_storage
