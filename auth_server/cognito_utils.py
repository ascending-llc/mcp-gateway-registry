"""
Cognito utilities for token generation and AWS Cognito operations.
"""

import logging
import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def generate_token(client_id: str, client_secret: str, user_pool_id: str, region: str, scopes: List[str] = None) -> Dict:
    """
    Generate a token using the client credentials flow
    
    Args:
        client_id: Cognito App Client ID
        client_secret: Cognito App Client Secret
        user_pool_id: Cognito User Pool ID
        region: AWS region
        scopes: List of scopes to request (optional)
        
    Returns:
        Dict containing access token and metadata
    """
    try:
        # Construct the Cognito domain
        user_pool_id_wo_underscore = user_pool_id.replace('_', '')
        cognito_domain = f"https://{user_pool_id_wo_underscore}.auth.{region}.amazoncognito.com"
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret
        }
        
        if scopes:
            data['scope'] = ' '.join(scopes)
        
        token_url = f"{cognito_domain}/oauth2/token"
        
        logger.info(f"Requesting token from {token_url}")
        response = requests.post(token_url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
        
        token_data = response.json()
        logger.info(f"Successfully obtained client credentials token")
        return token_data
        
    except Exception as e:
        logger.error(f"Failed to get client credentials token: {e}")
        raise ValueError(f"Cannot obtain token: {e}")