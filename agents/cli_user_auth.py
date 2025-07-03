#!/usr/bin/env python3
"""
CLI tool for MCP Gateway user authentication via Cognito OAuth.
Captures session cookie and saves to local file for agent use.

Usage:
    python cli_auth.py [--cookie-file PATH]

Environment variables required:
    COGNITO_DOMAIN: Cognito domain (e.g., 'mcp-gateway' or full URL)
    COGNITO_CLIENT_ID: OAuth client ID
    SECRET_KEY: Must match the registry SECRET_KEY for cookie compatibility
    AWS_REGION: AWS region (optional, defaults to us-east-1)
"""

import os
import sys
import json
import secrets
import hashlib
import base64
import threading
import webbrowser
import argparse
import logging
from pathlib import Path
from urllib.parse import urlencode, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from itsdangerous import URLSafeTimedSerializer
import requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
# Look for .env file in the same directory as this script
script_dir = Path(__file__).parent
env_file = script_dir / '.env.user'
if env_file.exists():
    load_dotenv(env_file, override=True)
    logger.info(f"Loaded environment variables from {env_file}")
else:
    logger.warning(f"No .env file found at {env_file}")

# Configuration from environment
COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID')
COGNITO_DOMAIN = os.environ.get('COGNITO_DOMAIN')
COGNITO_CLIENT_ID = os.environ.get('COGNITO_CLIENT_ID')
COGNITO_CLIENT_SECRET = os.environ.get('COGNITO_CLIENT_SECRET')
SECRET_KEY = os.environ.get('SECRET_KEY')

# Make redirect URI configurable based on environment
REGISTRY_URL = os.environ.get('REGISTRY_URL', 'http://localhost')
USE_DIRECT_CALLBACK = os.environ.get('USE_DIRECT_CALLBACK', 'true').lower() == 'true'

if USE_DIRECT_CALLBACK:
    logger.info("Using direct callback")
    # Direct callback to local server (original behavior)
    COGNITO_REDIRECT_URI = "http://localhost:9090/callback"
    CALLBACK_PORT = 9090
    CALLBACK_PATH = "/callback"
else:
    # Use nginx proxy callback (for Docker environments)
    COGNITO_REDIRECT_URI = f"{REGISTRY_URL}/oauth2/callback/cognito"
    CALLBACK_PORT = 8080  # Different port to avoid conflicts
    CALLBACK_PATH = "/auth_complete"

AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Validate required environment variables
if not all([COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, SECRET_KEY]):
    logger.error("Missing required environment variables")
    logger.error("Required: COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, SECRET_KEY")
    sys.exit(1)

# Construct the Cognito domain
if COGNITO_DOMAIN:
    # Use custom domain if provided
    COGNITO_DOMAIN_URL = f"https://{COGNITO_DOMAIN}.auth.{AWS_REGION}.amazoncognito.com"
else:
    # Otherwise use user pool ID without underscores (standard format)
    user_pool_id_wo_underscore = COGNITO_USER_POOL_ID.replace('_', '')
    COGNITO_DOMAIN_URL = f"https://{user_pool_id_wo_underscore}.auth.{AWS_REGION}.amazoncognito.com"

logger.info(f"Using Cognito domain: {COGNITO_DOMAIN_URL}")
logger.info(f"Redirect URI configured: {COGNITO_REDIRECT_URI if 'COGNITO_REDIRECT_URI' in globals() else 'Not yet configured'}")

# OAuth endpoints
AUTHORIZE_URL = f"{COGNITO_DOMAIN_URL}/oauth2/authorize"
TOKEN_URL = f"{COGNITO_DOMAIN_URL}/oauth2/token"

# Global variables for OAuth flow
auth_result = None
auth_complete = threading.Event()
pkce_verifier = None


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback"""
    
    def log_message(self, format, *args):
        """Override to use logger instead of stderr"""
        logger.debug(f"Callback server: {format}", *args)
    
    def do_GET(self):
        """Handle OAuth callback"""
        global auth_result
        
        if self.path.startswith(CALLBACK_PATH):
            # Parse query parameters
            query_string = self.path.split('?', 1)[1] if '?' in self.path else ''
            params = parse_qs(query_string)
            
            # Check for authorization code
            if 'code' in params:
                auth_code = params['code'][0]
                logger.info("Authorization code received")
                
                # Exchange code for tokens
                token_result = self.exchange_code_for_tokens(auth_code)
                
                if token_result:
                    # Create session cookie
                    cookie_value = self.create_session_cookie(token_result)
                    if cookie_value:
                        auth_result = {
                            'success': True,
                            'cookie': cookie_value,
                            'user_info': token_result
                        }
                        self.send_success_response()
                    else:
                        self.send_error_response("Failed to create session cookie")
                else:
                    self.send_error_response("Failed to exchange authorization code")
            
            elif 'error' in params:
                error = params.get('error', ['Unknown error'])[0]
                error_description = params.get('error_description', [''])[0]
                logger.error(f"OAuth error: {error} - {error_description}")
                self.send_error_response(f"Authentication failed: {error}")
            
            else:
                self.send_error_response("Invalid callback parameters")
            
            # Signal completion
            auth_complete.set()
        else:
            self.send_404()
    
    def exchange_code_for_tokens(self, auth_code):
        """Exchange authorization code for tokens"""
        global pkce_verifier
        
        try:
            # Basic auth with client credentials
            auth_string = f"{COGNITO_CLIENT_ID}:{COGNITO_CLIENT_SECRET}"
            auth_bytes = auth_string.encode('utf-8')
            auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
            
            headers = {
                'Authorization': f'Basic {auth_b64}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            data = {
                'grant_type': 'authorization_code',
                'client_id': COGNITO_CLIENT_ID,
                'code': auth_code,
                'redirect_uri': COGNITO_REDIRECT_URI,
                'code_verifier': pkce_verifier
            }
            
            response = requests.post(TOKEN_URL, headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            logger.info("Successfully exchanged code for tokens")
            
            # Decode ID token to get user info
            id_token = token_data.get('id_token')
            if id_token:
                # Simple JWT decode without verification (Cognito already verified)
                # In production, should verify with Cognito JWKS
                payload = id_token.split('.')[1]
                # Add padding if needed
                payload += '=' * (4 - len(payload) % 4)
                user_info = json.loads(base64.urlsafe_b64decode(payload))
                
                return {
                    'username': user_info.get('cognito:username', user_info.get('email')),
                    'groups': user_info.get('cognito:groups', []),
                    'email': user_info.get('email'),
                    'sub': user_info.get('sub')
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Token exchange failed: {e}")
            return None
    
    def create_session_cookie(self, user_info):
        """Create session cookie matching registry format"""
        try:
            signer = URLSafeTimedSerializer(SECRET_KEY)
            
            # Create session data matching old implementation format
            session_data = {
                'username': user_info['username'],
                'groups': user_info.get('groups', []),
                'provider_type': 'cognito',
                'is_oauth': True,
                'session_id': secrets.token_urlsafe(16),
                'login_time': None  # Will be set by registry if needed
            }
            
            # Serialize the session data
            cookie_value = signer.dumps(session_data)
            logger.info(f"Session cookie created for user: {user_info['username']}")
            
            return cookie_value
            
        except Exception as e:
            logger.error(f"Failed to create session cookie: {e}")
            return None
    
    def send_success_response(self):
        """Send success response to browser"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = """
        <html>
        <head>
            <title>Authentication Successful</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                .success { color: green; }
                .info { margin-top: 20px; padding: 20px; background: #f0f0f0; border-radius: 5px; }
            </style>
        </head>
        <body>
            <h1 class="success">✓ Authentication Successful!</h1>
            <div class="info">
                <p>Your session cookie has been saved.</p>
                <p>You can now close this window and return to the terminal.</p>
            </div>
            <script>setTimeout(() => window.close(), 5000);</script>
        </body>
        </html>
        """
        self.wfile.write(html.encode())
    
    def send_error_response(self, error_message):
        """Send error response to browser"""
        self.send_response(400)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = f"""
        <html>
        <head>
            <title>Authentication Failed</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .error {{ color: red; }}
            </style>
        </head>
        <body>
            <h1 class="error">✗ Authentication Failed</h1>
            <p>{error_message}</p>
            <p>Please close this window and try again.</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode())
    
    def send_404(self):
        """Send 404 response"""
        self.send_response(404)
        self.end_headers()


def generate_pkce_challenge():
    """Generate PKCE code verifier and challenge"""
    # Generate code verifier (43-128 characters)
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    
    # Generate code challenge (SHA256 of verifier)
    challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')
    
    return code_verifier, code_challenge


def start_callback_server():
    """Start the OAuth callback server"""
    server = HTTPServer(('localhost', CALLBACK_PORT), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    logger.info(f"Callback server started on http://localhost:{CALLBACK_PORT}")
    return server


def save_cookie_to_file(cookie_value, file_path):
    """Save cookie to file with secure permissions"""
    try:
        # Expand user path and create directory if needed
        cookie_path = Path(file_path).expanduser()
        cookie_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        
        # Write cookie to file
        cookie_path.write_text(cookie_value)
        
        # Set secure permissions (owner read/write only)
        cookie_path.chmod(0o600)
        
        logger.info(f"Session cookie saved to: {cookie_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save cookie: {e}")
        return False


def main():
    """Main authentication flow"""
    global pkce_verifier
    
    parser = argparse.ArgumentParser(description='MCP Gateway CLI Authentication')
    parser.add_argument(
        '--cookie-file',
        default='~/.mcp/session_cookie',
        help='Path to save session cookie (default: ~/.mcp/session_cookie)'
    )
    parser.add_argument(
        '--use-proxy',
        action='store_true',
        help='Use nginx proxy callback instead of direct callback (for Docker environments)'
    )
    parser.add_argument(
        '--registry-url',
        default='http://localhost',
        help='Registry URL for proxy-based auth (default: http://localhost)'
    )
    args = parser.parse_args()
    
    # Override environment variables with CLI arguments
    if args.use_proxy:
        global USE_DIRECT_CALLBACK, COGNITO_REDIRECT_URI, CALLBACK_PORT, CALLBACK_PATH, REGISTRY_URL
        USE_DIRECT_CALLBACK = False
        REGISTRY_URL = args.registry_url
        COGNITO_REDIRECT_URI = f"{REGISTRY_URL}/oauth2/callback/cognito"
        CALLBACK_PORT = 8081
        CALLBACK_PATH = "/auth_complete"
    
    try:
        # Generate PKCE challenge
        pkce_verifier, pkce_challenge = generate_pkce_challenge()
        
        # Start callback server
        server = start_callback_server()
        
        # Build authorization URL
        auth_params = {
            'response_type': 'code',
            'client_id': COGNITO_CLIENT_ID,
            'redirect_uri': COGNITO_REDIRECT_URI,
            'scope': 'openid email profile',
            'code_challenge': pkce_challenge,
            'code_challenge_method': 'S256'
        }
        auth_url = f"{AUTHORIZE_URL}?{urlencode(auth_params)}"
        
        # Open browser for authentication
        logger.info("Opening browser for Cognito login...")
        print("\n" + "="*50)
        print("Opening your browser for authentication...")
        print("Please complete the login process.")
        print(f"Redirect URI: {COGNITO_REDIRECT_URI}")
        print(f"Callback server: http://localhost:{CALLBACK_PORT}")
        print("="*50 + "\n")
        
        logger.info(f"Authorization URL: {auth_url}")
        webbrowser.open(auth_url)
        
        # Wait for callback
        logger.info("Waiting for authentication callback...")
        auth_complete.wait(timeout=300)  # 5 minute timeout
        
        # Shutdown callback server
        server.shutdown()
        
        # Check results
        if auth_result and auth_result.get('success'):
            cookie_value = auth_result['cookie']
            
            if save_cookie_to_file(cookie_value, args.cookie_file):
                print("\n" + "="*50)
                print("✓ Authentication successful!")
                print(f"✓ Session cookie saved to: {Path(args.cookie_file).expanduser()}")
                print("\nYou can now use this cookie with agents:")
                print(f"  python agents/agent.py --use-session-cookie")
                print("="*50 + "\n")
                return 0
            else:
                print("\n✗ Failed to save session cookie")
                return 1
        else:
            print("\n✗ Authentication failed")
            return 1
            
    except KeyboardInterrupt:
        print("\n\nAuthentication cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\n✗ Error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())