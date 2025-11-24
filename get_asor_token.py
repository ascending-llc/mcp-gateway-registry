#!/usr/bin/env python3
"""
Helper script to get ASOR access token for federation.

This script performs the 3-legged OAuth flow to get an access token
that can be used for ASOR federation in the MCP Gateway.
"""
import requests
import urllib.parse
import os

# Configuration from environment or defaults
CLIENT_ID = os.getenv("ASOR_CLIENT_ID")
CLIENT_SECRET = os.getenv("ASOR_CLIENT_SECRET")
TENANT_NAME = os.getenv("ASOR_TENANT_NAME")
HOSTNAME = os.getenv("ASOR_HOSTNAME")

def get_asor_token():
    """Get ASOR access token via 3-legged OAuth flow"""
    print("🔑 ASOR Token Generator for MCP Gateway Federation")
    print("=" * 60)
    print(f"Tenant: {TENANT_NAME}")
    print(f"Hostname: {HOSTNAME}")
    print()
    
    # Generate auth URL
    auth_url = f"https://wcpdev.wd103.myworkday.com/{TENANT_NAME}/authorize"
    params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': 'https://localhost:7860/callback',
        'scope': 'Agent System of Record'
    }
    
    print("Step 1: Get Authorization Code")
    print("-" * 30)
    print(f"Visit this URL in your browser:")
    print(f"{auth_url}?{urllib.parse.urlencode(params)}")
    print()
    
    auth_code = input("Enter the authorization code from the callback URL: ").strip()
    
    if not auth_code:
        print("❌ No authorization code provided")
        return None
    
    print("\nStep 2: Exchange Code for Token")
    print("-" * 30)
    
    # Exchange code for token
    token_url = f"https://{HOSTNAME}/ccx/oauth2/{TENANT_NAME}/token"
    data = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code,
        'redirect_uri': 'https://localhost:7860/callback'
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=15)
        if response.status_code == 200:
            tokens = response.json()
            access_token = tokens.get('access_token')
            expires_in = tokens.get('expires_in', 'unknown')
            
            print(f"✅ Successfully obtained access token!")
            print(f"   Token: {access_token}")
            print(f"   Expires in: {expires_in} seconds")
            print()
            
            print("Step 3: Configure MCP Gateway")
            print("-" * 30)
            print("Add this to your .env file:")
            print(f"ASOR_ACCESS_TOKEN={access_token}")
            print()
            print("Then restart the MCP Gateway with:")
            print("./build_and_run.sh --prebuilt")
            print()
            
            return access_token
        else:
            print(f"❌ Token exchange failed: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error during token exchange: {e}")
        return None

if __name__ == "__main__":
    get_asor_token()
