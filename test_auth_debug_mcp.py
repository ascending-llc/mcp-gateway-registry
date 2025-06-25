#!/usr/bin/env python3
"""
Debug script to test authentication and cookie handling in the MCP Gateway Registry
"""

import requests
import json
from requests.cookies import RequestsCookieJar

def test_auth_flow():
    """Test the complete authentication flow"""
    base_url = "http://localhost:80"  # Docker environment
    
    print("🧪 Testing MCP Gateway Registry Authentication Flow")
    print("=" * 60)
    
    # Test 1: Health check
    print("\n1️⃣ Testing health endpoint...")
    try:
        response = requests.get(f"{base_url}/health")
        print(f"   ✅ Health check: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        return
    
    # Test 2: Check current auth status
    print("\n2️⃣ Testing auth status (should be unauthorized)...")
    try:
        response = requests.get(f"{base_url}/api/auth/me")
        print(f"   ❌ Unexpected auth success: {response.status_code}")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print(f"   ✅ Correctly unauthorized: {e.response.status_code}")
        else:
            print(f"   ❓ Unexpected status: {e.response.status_code}")
    except Exception as e:
        print(f"   ❌ Auth check failed: {e}")
    
    # Test 3: Login
    print("\n3️⃣ Testing login...")
    try:
        session = requests.Session()
        login_data = {
            'username': 'admin', 
            'password': 'password'  # Default from docker-compose
        }
        response = session.post(f"{base_url}/api/auth/login", data=login_data)
        print(f"   Login response: {response.status_code}")
        print(f"   Cookies: {dict(session.cookies)}")
        
        if response.status_code == 200:
            print("   ✅ Login successful")
            
            # Test 4: Check auth status after login
            print("\n4️⃣ Testing auth status after login...")
            auth_response = session.get(f"{base_url}/api/auth/me")
            if auth_response.status_code == 200:
                user_data = auth_response.json()
                print(f"   ✅ Auth successful: {user_data}")
            else:
                print(f"   ❌ Auth failed after login: {auth_response.status_code}")
        else:
            response_text = response.text
            print(f"   ❌ Login failed: {response_text}")
            return
            
    except Exception as e:
        print(f"   ❌ Login test failed: {e}")
        return
    
    # Test 5: Test WebSocket health endpoint (HTTP version)
    print("\n5️⃣ Testing WebSocket health endpoint (HTTP)...")
    try:
        ws_response = session.get(f"{base_url}/api/health/ws/health_status")
        if ws_response.status_code == 200:
            print(f"   ✅ WebSocket health endpoint accessible: {len(ws_response.json())} services")
        else:
            print(f"   ❌ WebSocket health endpoint failed: {ws_response.status_code}")
    except Exception as e:
        print(f"   ❌ WebSocket health test failed: {e}")
    
    print("\n" + "=" * 60)
    print("🎯 Test completed! Check the results above.")
    print("💡 If login works but WebSocket fails, the issue is with WebSocket cookie handling.")

if __name__ == "__main__":
    test_auth_flow() 