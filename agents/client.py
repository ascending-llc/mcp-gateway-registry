"""
Client for the Auth Server REST API.

This script demonstrates connecting to the Auth Server with Cognito authentication.

Configuration can be provided via command line arguments or environment variables.
Command line arguments take precedence over environment variables.

Environment Variables:
- AUTH_SERVER_URL: URL of the Auth server
- COGNITO_CLIENT_ID: Cognito App Client ID
- COGNITO_CLIENT_SECRET: Cognito App Client Secret
- COGNITO_USER_POOL_ID: Cognito User Pool ID
- AWS_REGION: AWS region for Cognito

Usage:
    python client.py --generate-token --scopes "read write"

Example with command line arguments:
    python client.py --server-url http://localhost:8888 \
        --client-id [CLIENT_ID] --client-secret [CLIENT_SECRET] \
        --user-pool-id [USER_POOL_ID] --region us-east-1 \
        --generate-token --scopes "read write"

Example with environment variables (create a .env file):
    AUTH_SERVER_URL=http://localhost:8888
    COGNITO_CLIENT_ID=your_client_id
    COGNITO_CLIENT_SECRET=your_client_secret
    COGNITO_USER_POOL_ID=your_user_pool_id
    AWS_REGION=us-east-1
    
    python client.py --generate-token --scopes "read write"
"""

import os
import argparse
import logging
import requests
from typing import Dict, List, Optional
from cognito_utils import generate_token

# Import dotenv for loading environment variables
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    print("Warning: python-dotenv not installed. Environment file loading disabled.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s|p%(process)d|%(pathname)s:%(lineno)d|%(levelname)s|%(message)s'
)

# Create a custom formatter that extracts folder and filename
class CustomFormatter(logging.Formatter):
    def format(self, record):
        # Get the full path and extract just the folder and filename
        pathname = record.pathname
        parts = pathname.split('/')
        if len(parts) >= 2:
            folder_and_file = '/'.join(parts[-2:])  # Get last two parts (folder/file)
        else:
            folder_and_file = parts[-1]  # Just filename if no folder
        
        # Replace the pathname with our custom format
        record.pathname = folder_and_file
        return super().format(record)

# Get the root logger and set our custom formatter
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    handler.setFormatter(CustomFormatter('%(asctime)s|p%(process)d|%(pathname)s:%(lineno)d|%(levelname)s|%(message)s'))

logger = logging.getLogger(__name__)

def load_env_config() -> Dict[str, Optional[str]]:
    """
    Load configuration from .env file if available.
    
    Returns:
        Dict[str, Optional[str]]: Dictionary containing environment variables
    """
    env_config = {
        'client_id': None,
        'client_secret': None,
        'region': None,
        'user_pool_id': None,
        'server_url': None
    }
    
    if DOTENV_AVAILABLE:
        # Try to load from .env file in the current directory
        env_file = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(env_file):
            load_dotenv(env_file)
            logger.info(f"Loading environment variables from {env_file}")
        else:
            # Try to load from .env file in the parent directory
            env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
            if os.path.exists(env_file):
                load_dotenv(env_file)
                logger.info(f"Loading environment variables from {env_file}")
            else:
                # Try to load from current working directory
                load_dotenv()
                logger.info("Loading environment variables from current directory")
        
        # Get values from environment
        env_config['client_id'] = os.getenv('COGNITO_CLIENT_ID')
        env_config['client_secret'] = os.getenv('COGNITO_CLIENT_SECRET')
        env_config['region'] = os.getenv('AWS_REGION')
        env_config['user_pool_id'] = os.getenv('COGNITO_USER_POOL_ID')
        env_config['server_url'] = os.getenv('AUTH_SERVER_URL')
    
    return env_config

def parse_arguments():
    """
    Parse command line arguments for the Auth Server REST Client.
    Command line arguments take precedence over environment variables.
    
    Returns:
        argparse.Namespace: The parsed command line arguments
    """
    # Load environment configuration first
    env_config = load_env_config()
    
    parser = argparse.ArgumentParser(description="Auth Server REST Client")
    
    parser.add_argument(
        "--server-url",
        type=str,
        default=env_config['server_url'] or "http://localhost:8888",
        help="URL of the Auth server (can be set via AUTH_SERVER_URL env var, default: http://localhost:8888)",
    )
    
    parser.add_argument(
        "--client-id",
        type=str,
        default=env_config['client_id'],
        help="Cognito App Client ID (can be set via COGNITO_CLIENT_ID env var)",
    )
    
    parser.add_argument(
        "--client-secret",
        type=str,
        default=env_config['client_secret'],
        help="Cognito App Client Secret (can be set via COGNITO_CLIENT_SECRET env var, required for token generation)",
    )
    
    parser.add_argument(
        "--user-pool-id",
        type=str,
        default=env_config['user_pool_id'],
        help="Cognito User Pool ID (can be set via COGNITO_USER_POOL_ID env var)",
    )
    
    parser.add_argument(
        "--region",
        type=str,
        default=env_config['region'] or "us-east-1",
        help="AWS Region (can be set via AWS_REGION env var, default: us-east-1)",
    )
    
    parser.add_argument(
        "--token",
        type=str,
        help="Provide a token directly",
    )
    
    parser.add_argument(
        "--generate-token",
        action="store_true",
        help="Generate a valid token using client credentials flow",
    )
    
    parser.add_argument(
        "--scopes",
        type=str,
        help="Space-separated list of scopes for token generation (e.g., 'read write')",
    )
    
    args = parser.parse_args()
    
    # Validate that required Cognito parameters are available (either from command line or environment)
    missing_params = []
    if not args.client_id:
        missing_params.append('--client-id (or COGNITO_CLIENT_ID env var)')
    if not args.client_secret:
        missing_params.append('--client-secret (or COGNITO_CLIENT_SECRET env var)')
    if not args.user_pool_id:
        missing_params.append('--user-pool-id (or COGNITO_USER_POOL_ID env var)')
    if not args.region:
        missing_params.append('--region (or AWS_REGION env var)')
    
    if missing_params:
        parser.error(f"Missing required parameters: {', '.join(missing_params)}")
    
    return args

def main():
    """Main function to demonstrate client usage."""
    args = parse_arguments()
    
    # Example: Check server health
    try:
        health_response = requests.get(f"{args.server_url}/health")
        health_response.raise_for_status()
        logger.info(f"Server health: {health_response.json()}")
    except Exception as e:
        logger.error(f"Error checking server health: {e}")
        return
    
    # Determine which token to use
    access_token = None
    
    # Option 1: Generate a token if requested
    if args.generate_token:
        if not args.client_secret:
            logger.error("Client secret is required for token generation")
            return
            
        try:
            scopes = args.scopes.split() if args.scopes else None
            token_response = generate_token(
                client_id=args.client_id,
                client_secret=args.client_secret,
                user_pool_id=args.user_pool_id,
                region=args.region,
                scopes=scopes
            )
            access_token = token_response['access_token']
            logger.info(f"Generated token: {access_token[:20]}...")
            
            # Print token details
            logger.info(f"Token type: {token_response.get('token_type', 'N/A')}")
            logger.info(f"Expires in: {token_response.get('expires_in', 'N/A')} seconds")
            if 'scope' in token_response:
                logger.info(f"Scopes: {token_response['scope']}")
                
        except Exception as e:
            logger.error(f"Failed to generate token: {e}")
            return
    
    # Option 2: Use provided token
    elif args.token:
        access_token = args.token
        logger.info(f"Using provided token: {access_token[:20]}...")
    
    # No token available
    else:
        logger.error("No token available. Use --generate-token or --token to provide a token.")
        return
    
    # Include the new required headers
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Client-Id": args.client_id,
        "X-User-Pool-Id": args.user_pool_id,
        "X-Region": args.region
    }
    
    logger.info("Sending validation request with headers:")
    logger.info(f"  Authorization: Bearer {access_token[:10]}...")
    logger.info(f"  X-Client-Id: {args.client_id}")
    logger.info(f"  X-User-Pool-Id: {args.user_pool_id}")
    logger.info(f"  X-Region: {args.region}")
    
    try:
        # Call the validate endpoint
        validate_response = requests.post(f"{args.server_url}/validate", headers=headers)
        validate_response.raise_for_status()
        result = validate_response.json()
        
        # Print the result
        logger.info("Token validation result:")
        logger.info(f"Valid: {result['valid']}")
        logger.info(f"Scopes: {', '.join(result['scopes'])}")
        logger.info(f"Method: {result.get('method', 'N/A')}")
        logger.info(f"Client ID: {result.get('client_id', 'N/A')}")
        if result.get('error'):
            logger.info(f"Error: {result['error']}")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            logger.error(f"Authentication error: {e.response.json().get('detail', 'Unknown error')}")
        else:
            logger.error(f"HTTP error: {e}")
    except Exception as e:
        logger.error(f"Error validating token: {e}")
    
    # Example: Get auth configuration
    try:
        config_response = requests.get(f"{args.server_url}/config")
        config_response.raise_for_status()
        auth_config = config_response.json()
        
        logger.info("Server auth configuration:")
        for key, value in auth_config.items():
            logger.info(f"{key}: {value}")
        
        logger.info("\nClient configuration:")
        logger.info(f"Client ID: {args.client_id}")
        logger.info(f"User Pool ID: {args.user_pool_id}")
        logger.info(f"Region: {args.region}")
    except Exception as e:
        logger.error(f"Error accessing auth configuration: {e}")

if __name__ == "__main__":
    main()