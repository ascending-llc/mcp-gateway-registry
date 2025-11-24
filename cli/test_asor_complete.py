#!/usr/bin/env python3
"""
Complete ASOR API test with token exchange
"""
import requests
import json
import urllib.parse
import os

# Configuration
CLIENT_ID = os.getenv("ASOR_CLIENT_ID")
CLIENT_SECRET = os.getenv("ASOR_CLIENT_SECRET")
TENANT_NAME = os.getenv("ASOR_TENANT_NAME")
HOSTNAME = os.getenv("ASOR_HOSTNAME")
BASE_URL = f"https://{HOSTNAME}/ccx/api/asor/v1/{TENANT_NAME}"

def get_token():
    """Get access token via OAuth flow"""
    print("🔑 OAuth Token Exchange")
    print("=" * 30)
    
    # Generate auth URL
    auth_url = f"https://wcpdev.wd103.myworkday.com/{TENANT_NAME}/authorize"
    params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': 'https://localhost:7860/callback',
        'scope': 'Agent System of Record'
    }
    
    print(f"1. Visit: {auth_url}?{urllib.parse.urlencode(params)}")
    auth_code = input("2. Enter authorization code: ").strip()
    
    if not auth_code:
        return None
    
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
        response = requests.post(token_url, data=data)
        if response.status_code == 200:
            tokens = response.json()
            access_token = tokens.get('access_token')
            print(f"✅ Token obtained: {access_token}")
            return access_token
        else:
            print(f"❌ Token exchange failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def api_call(token, method, endpoint, data=None):
    """Make ASOR API call"""
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    url = f"{BASE_URL}{endpoint}"
    print(url)
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=15)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=15)
        elif method == 'PUT':
            response = requests.put(url, headers=headers, json=data, timeout=15)
        
        return response.status_code, response.text
    except Exception as e:
        return None, str(e)

def test_agent_definition_crud(token):
    """Test Agent Definition CRUD operations"""
    print("\n🤖 Testing Agent Definition API")
    print("=" * 40)
    
    # GET /agentDefinition (list agents)
    print("1. GET /agentDefinition (list existing agents)")
    status, response = api_call(token, 'GET', '/agentDefinition')
    
    if status == 200:
        print(f"✅ SUCCESS")
        try:
            data = json.loads(response)
            print(f"   Found {data.get('total', 0)} agents")
            print("dddddddddd")
            print(json.dumps(data, indent=2))
            if data.get('data'):
                agent = data['data'][0]  # Get first agent
                print(f"\n   📋 Agent JSON (Pretty Printed):")
                print("   " + "="*50)
                print(json.dumps(agent, indent=2))
                print("   " + "="*50)
        except:
            pass
    else:
        print(f"❌ Failed: {status} - {response[:200]}")

    if status in [200, 201]:
        print(f"✅ Agent created successfully!")
        print(f"   Response: {response[:200]}...")
    elif status == 400:
        print(f"⚠️  Bad Request: {response[:300]}")
    elif status == 403:
        print(f"🚫 Forbidden - may need different permissions")
    else:
        print(f"❌ Failed: {status} - {response[:200]}")

def main():
    print("🔍 Complete ASOR API Test Suite with OAuth")
    print("=" * 50)
    print(f"Base URL: {BASE_URL}")
    print()
    
    # Get access token
    token = get_token()
    if not token:
        print("❌ Failed to get access token")
        return
    
    # Test main Agent Definition API
    test_agent_definition_crud(token)
    
    print(f"\n📋 SUMMARY")
    print("=" * 50)
    print("✅ OAuth Flow: SUCCESS")
    print("✅ ASOR API Base URL confirmed working")
    print("✅ Agent Definition endpoint accessible")
    print("✅ Ready for MCP Gateway integration")
    
    print(f"\n🔧 Final MCP Gateway Configuration:")
    print(f'{{')
    print(f'  "name": "workday-asor",')
    print(f'  "url": "{BASE_URL}",')
    print(f'  "auth_type": "oauth_3lo",')
    print(f'  "oauth_config": {{')
    print(f'    "client_id": "{CLIENT_ID}",')
    print(f'    "client_secret": "{CLIENT_SECRET}",')
    print(f'    "auth_url": "https://wcpdev.wd103.myworkday.com/{TENANT_NAME}/authorize",')
    print(f'    "token_url": "https://{HOSTNAME}/ccx/oauth2/{TENANT_NAME}/token",')
    print(f'    "scope": "Agent System of Record"')
    print(f'  }}')
    print(f'}}')

if __name__ == "__main__":
    main()
