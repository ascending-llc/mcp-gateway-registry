#!/usr/bin/env python3
"""
MCP Gateway CLI Authentication Tool

This tool provides GitHub device flow authentication for CLI usage.
It creates a session cookie that can be used with the MCP Gateway registry.
"""

import os
import sys
import logging
import argparse
import requests
import time
import json
from pathlib import Path
from itsdangerous import URLSafeTimedSerializer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Required environment variables
SECRET_KEY = os.environ.get('SECRET_KEY')
GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID')
GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET')

def validate_environment():
    """Validate that required environment variables are set"""
    missing_vars = []
    
    if not SECRET_KEY:
        missing_vars.append('SECRET_KEY')
    if not GITHUB_CLIENT_ID:
        missing_vars.append('GITHUB_CLIENT_ID')
    if not GITHUB_CLIENT_SECRET:
        missing_vars.append('GITHUB_CLIENT_SECRET')
    
    if missing_vars:
        logger.error("Missing required environment variables:")
        logger.error(f"Required: {', '.join(missing_vars)}")
        sys.exit(1)

def start_github_device_flow() -> dict:
    """Start GitHub device flow and return device info"""
    try:
        response = requests.post(
            'https://github.com/login/device/code',
            data={
                'client_id': GITHUB_CLIENT_ID,
                'scope': 'read:user user:email'
            },
            headers={
                'Accept': 'application/json'
            }
        )
        response.raise_for_status()
        
        return response.json()
    
    except Exception as e:
        logger.error(f"Failed to start device flow: {e}")
        raise

def poll_github_device_token(device_code: str, interval: int = 5) -> dict:
    """Poll for GitHub device token"""
    while True:
        try:
            response = requests.post(
                'https://github.com/login/oauth/access_token',
                data={
                    'client_id': GITHUB_CLIENT_ID,
                    'device_code': device_code,
                    'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
                },
                headers={
                    'Accept': 'application/json'
                }
            )
            response.raise_for_status()
            result = response.json()
            
            if 'access_token' in result:
                return result
            elif result.get('error') == 'authorization_pending':
                logger.debug("Authorization pending, continuing to poll...")
                time.sleep(interval)
                continue
            elif result.get('error') == 'slow_down':
                logger.debug("Rate limited, slowing down polling...")
                interval += 5
                time.sleep(interval)
                continue
            elif result.get('error') == 'expired_token':
                raise ValueError("Device code expired")
            elif result.get('error') == 'access_denied':
                raise ValueError("User denied authorization")
            else:
                raise ValueError(f"Unknown error: {result.get('error', 'Unknown')}")
                
        except Exception as e:
            logger.error(f"Error polling for token: {e}")
            raise

def get_github_user_info(access_token: str) -> dict:
    """Get GitHub user information using access token"""
    try:
        response = requests.get(
            'https://api.github.com/user',
            headers={
                'Authorization': f'token {access_token}',
                'Accept': 'application/json'
            }
        )
        response.raise_for_status()
        
        return response.json()
    
    except Exception as e:
        logger.error(f"Failed to get user info: {e}")
        raise

def create_session_cookie(user_info: dict) -> str:
    """Create a session cookie from user info"""
    try:
        session_data = {
            "username": user_info.get('login'),
            "email": user_info.get('email'),
            "name": user_info.get('name'),
            "groups": [],
            "provider": "github",
            "auth_method": "device_flow"
        }
        
        signer = URLSafeTimedSerializer(SECRET_KEY)
        return signer.dumps(session_data)
        
    except Exception as e:
        logger.error(f"Failed to create session cookie: {e}")
        raise

def save_cookie_to_file(cookie: str, cookie_file: str):
    """Save session cookie to file"""
    try:
        cookie_path = Path(cookie_file).expanduser()
        cookie_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(cookie_path, 'w') as f:
            f.write(cookie)
        
        logger.info(f"Session cookie saved to: {cookie_path}")
        
    except Exception as e:
        logger.error(f"Failed to save cookie to file: {e}")
        raise

def main():
    """Main authentication flow"""
    parser = argparse.ArgumentParser(description='MCP Gateway CLI Authentication - GitHub Device Flow')
    parser.add_argument(
        '--cookie-file',
        default='~/.mcp/session_cookie',
        help='Path to save session cookie (default: ~/.mcp/session_cookie)'
    )
    args = parser.parse_args()
    
    # Validate environment
    validate_environment()
    
    try:
        logger.info("Starting GitHub device flow authentication...")
        
        # Step 1: Start device flow
        device_info = start_github_device_flow()
        device_code = device_info['device_code']
        user_code = device_info['user_code']
        verification_uri = device_info['verification_uri']
        interval = device_info.get('interval', 5)
        
        # Step 2: Display instructions to user
        print("\n" + "="*60)
        print("GITHUB DEVICE FLOW AUTHENTICATION")
        print("="*60)
        print(f"1. Go to: {verification_uri}")
        print(f"2. Enter code: {user_code}")
        print("3. Complete the authorization in your browser")
        print("="*60)
        print("\nWaiting for authorization...")
        
        # Step 3: Poll for token
        token_data = poll_github_device_token(device_code, interval)
        access_token = token_data['access_token']
        
        # Step 4: Get user info
        user_info = get_github_user_info(access_token)
        logger.info(f"Successfully authenticated as: {user_info.get('login')}")
        
        # Step 5: Create session cookie
        session_cookie = create_session_cookie(user_info)
        
        # Step 6: Save cookie to file
        save_cookie_to_file(session_cookie, args.cookie_file)
        
        print("\n" + "="*60)
        print("✅ AUTHENTICATION SUCCESSFUL!")
        print(f"User: {user_info.get('login')} ({user_info.get('name', 'No name')})")
        print(f"Email: {user_info.get('email', 'No email')}")
        print(f"Cookie saved to: {Path(args.cookie_file).expanduser()}")
        print("="*60)
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Authentication cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())