#!/usr/bin/env python3
"""
Generate Microsoft Entra ID (Azure AD) tokens for testing and development.

This script supports multiple authentication flows:
1. Client Credentials Flow (for M2M/service accounts)
2. Authorization Code Flow (requires browser interaction)

Usage:
    # Client credentials flow (M2M)
    python generate_tokens.py --tenant-id <tenant_id> --client-id <client_id> \
                              --client-secret <secret> --flow client_credentials
    
    # Save tokens to file
    python generate_tokens.py --tenant-id <tenant_id> --client-id <client_id> \
                              --output tokens.json

Environment Variables:
    ENTRA_TENANT_ID: Azure AD tenant ID
    ENTRA_CLIENT_ID: Application (client) ID
    ENTRA_CLIENT_SECRET: Client secret (for client credentials flow)
"""

import argparse
import json
import os
import sys
import time
import requests
from typing import Dict, Any, Optional


class EntraTokenGenerator:
    """Generate tokens from Microsoft Entra ID."""

    def __init__(
            self,
            tenant_id: str,
            client_id: str,
            client_secret: Optional[str] = None,
            authority: Optional[str] = None
    ):
        """Initialize token generator.
        
        Args:
            tenant_id: Azure AD tenant ID
            client_id: Application (client) ID
            client_secret: Client secret (required for client credentials flow)
            authority: Custom authority URL (defaults to global Azure AD)
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret

        self.authority = authority or f"https://login.microsoftonline.com/{tenant_id}"
        self.token_url = f"{self.authority}/oauth2/v2.0/token"
        self.device_code_url = f"{self.authority}/oauth2/v2.0/devicecode"
        self.auth_url = f"{self.authority}/oauth2/v2.0/authorize"

    def get_device_code_token(
            self,
            scope: str = "openid profile email User.Read offline_access"
    ) -> Dict[str, Any]:
        """Get tokens using device code flow (interactive).
        
        This is the recommended flow for CLI tools and testing.
        User will need to visit a URL and enter a code.
        
        Args:
            scope: OAuth2 scopes to request
            
        Returns:
            Dictionary containing access_token, refresh_token, etc.
        """
        print("Starting device code flow...")

        # Request device code
        data = {
            'client_id': self.client_id,
            'scope': scope
        }

        response = requests.post(self.device_code_url, data=data)
        response.raise_for_status()
        device_code_data = response.json()

        # Display instructions to user
        print("\n" + "=" * 70)
        print("DEVICE CODE AUTHENTICATION")
        print("=" * 70)
        print(f"\n1. Visit: {device_code_data['verification_uri']}")
        print(f"2. Enter code: {device_code_data['user_code']}")
        print(f"\nWaiting for authentication (expires in {device_code_data['expires_in']} seconds)...")
        print("=" * 70 + "\n")

        # Poll for token
        device_code = device_code_data['device_code']
        interval = device_code_data.get('interval', 5)
        expires_in = device_code_data['expires_in']
        start_time = time.time()

        while True:
            if time.time() - start_time > expires_in:
                raise TimeoutError("Device code expired before user completed authentication")

            time.sleep(interval)

            token_data = {
                'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
                'device_code': device_code,
                'client_id': self.client_id
            }

            # Add client_secret if available (required for confidential clients)
            if self.client_secret:
                token_data['client_secret'] = self.client_secret

            response = requests.post(self.token_url, data=token_data)
            result = response.json()

            if response.status_code == 200:
                print("✓ Authentication successful!")
                return result

            error = result.get('error')
            if error == 'authorization_pending':
                print(".", end="", flush=True)
                continue
            elif error == 'slow_down':
                interval += 5
                continue
            elif error in ['authorization_declined', 'bad_verification_code', 'expired_token']:
                raise ValueError(f"Authentication failed: {error}")
            else:
                raise ValueError(f"Unexpected error: {error} - {result.get('error_description')}")

    def get_client_credentials_token(
            self,
            scope: str = "https://graph.microsoft.com/.default"
    ) -> Dict[str, Any]:
        """Get token using client credentials flow (M2M).
        
        This flow is for service-to-service authentication.
        Requires client_secret to be set.
        
        Args:
            scope: OAuth2 scope (use .default for all configured permissions)
            
        Returns:
            Dictionary containing access_token
        """
        if not self.client_secret:
            raise ValueError("Client secret is required for client credentials flow")

        print("Requesting token using client credentials flow...")

        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': scope
        }

        response = requests.post(self.token_url, data=data)
        response.raise_for_status()

        token_data = response.json()
        print("✓ Token generated successfully!")

        return token_data

    def refresh_token(
            self,
            refresh_token: str,
            scope: str = "openid profile email User.Read offline_access"
    ) -> Dict[str, Any]:
        """Refresh an access token.
        
        Args:
            refresh_token: The refresh token
            scope: OAuth2 scopes to request
            
        Returns:
            Dictionary containing new access_token and refresh_token
        """
        print("Refreshing access token...")

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.client_id,
            'scope': scope
        }

        if self.client_secret:
            data['client_secret'] = self.client_secret

        response = requests.post(self.token_url, data=data)
        response.raise_for_status()

        token_data = response.json()
        print("✓ Token refreshed successfully!")

        return token_data

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode JWT token (without validation) to inspect claims.
        
        Args:
            token: JWT token string
            
        Returns:
            Dictionary containing token claims
        """
        import base64

        # Split token into parts
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT token format")

        # Decode payload (add padding if needed)
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding

        decoded_bytes = base64.urlsafe_b64decode(payload)
        return json.loads(decoded_bytes)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate Microsoft Entra ID tokens',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--tenant-id',
        default=os.environ.get('ENTRA_TENANT_ID'),
        help='Azure AD tenant ID (or env: ENTRA_TENANT_ID)'
    )

    parser.add_argument(
        '--client-id',
        default=os.environ.get('ENTRA_CLIENT_ID'),
        help='Application (client) ID (or env: ENTRA_CLIENT_ID)'
    )

    parser.add_argument(
        '--client-secret',
        default=os.environ.get('ENTRA_CLIENT_SECRET'),
        help='Client secret (or env: ENTRA_CLIENT_SECRET)'
    )

    parser.add_argument(
        '--flow',
        choices=['device_code', 'client_credentials', 'refresh'],
        default='device_code',
        help='Authentication flow to use (default: device_code)'
    )

    parser.add_argument(
        '--scope',
        help='OAuth2 scopes (space-separated)'
    )

    parser.add_argument(
        '--refresh-token',
        help='Refresh token (for refresh flow)'
    )

    parser.add_argument(
        '--output',
        help='Output file path to save tokens (default: print to stdout)'
    )

    parser.add_argument(
        '--decode',
        action='store_true',
        help='Decode and display token claims'
    )

    parser.add_argument(
        '--authority',
        help='Custom authority URL (for sovereign clouds)'
    )

    args = parser.parse_args()

    # Validate required arguments
    if not args.tenant_id:
        parser.error("--tenant-id is required (or set ENTRA_TENANT_ID)")

    if not args.client_id:
        parser.error("--client-id is required (or set ENTRA_CLIENT_ID)")

    # Create token generator
    generator = EntraTokenGenerator(
        tenant_id=args.tenant_id,
        client_id=args.client_id,
        client_secret=args.client_secret,
        authority=args.authority
    )

    # Generate tokens based on flow
    token_data = None
    try:
        if args.flow == 'device_code':
            scope = args.scope or "openid profile email User.Read offline_access"
            token_data = generator.get_device_code_token(scope=scope)

        elif args.flow == 'client_credentials':
            scope = args.scope or "https://graph.microsoft.com/.default"
            token_data = generator.get_client_credentials_token(scope=scope)

        elif args.flow == 'refresh':
            if not args.refresh_token:
                parser.error("--refresh-token is required for refresh flow")
            scope = args.scope or "openid profile email User.Read offline_access"
            token_data = generator.refresh_token(
                refresh_token=args.refresh_token,
                scope=scope
            )

        # Add metadata
        token_data['generated_at'] = time.time()
        token_data['expires_at'] = time.time() + token_data.get('expires_in', 3600)

        # Decode token if requested
        if args.decode and 'access_token' in token_data:
            print("\n" + "=" * 70)
            print("TOKEN CLAIMS")
            print("=" * 70)
            claims = generator.decode_token(token_data['access_token'])
            print(json.dumps(claims, indent=2))
            print("=" * 70 + "\n")

        # Output tokens
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(token_data, f, indent=2)
            print(f"\n✓ Tokens saved to: {args.output}")
        else:
            print("\n" + "=" * 70)
            print("TOKENS")
            print("=" * 70)
            print(json.dumps(token_data, indent=2))
            print("=" * 70)

        # Display useful information
        print("\nToken Information:")
        print(f"  Token Type: {token_data.get('token_type', 'Bearer')}")
        print(f"  Expires In: {token_data.get('expires_in', 'N/A')} seconds")
        if 'scope' in token_data:
            print(f"  Scopes: {token_data['scope']}")

        return 0

    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
