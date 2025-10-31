"""Factory for creating authentication provider instances."""

import logging
import os
import yaml
from pathlib import Path
from string import Template
from typing import Optional, Dict, Any

from .base import AuthProvider
from .cognito import CognitoProvider
from .keycloak import KeycloakProvider
from .entra import EntraIDProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


def _load_oauth2_config() -> Dict[str, Any]:
    """Load OAuth2 providers configuration from oauth2_providers.yml.
    
    Returns:
        Dict containing OAuth2 providers configuration
    """
    try:
        oauth2_file = Path(__file__).parent.parent / "oauth2_providers.yml"
        with open(oauth2_file, 'r') as f:
            config = yaml.safe_load(f)
        # Substitute environment variables in configuration
        processed_config = _substitute_env_vars(config)
        logger.debug("Successfully loaded OAuth2 configuration")
        return processed_config
    except Exception as e:
        logger.error(f"Failed to load OAuth2 configuration: {e}")
        return {"providers": {}, "session": {}, "registry": {}}


def _substitute_env_vars(config: Any) -> Any:
    """Recursively substitute environment variables in configuration.
    
    Args:
        config: Configuration value (dict, list, or str)
        
    Returns:
        Configuration with environment variables substituted
    """
    if isinstance(config, dict):
        return {k: _substitute_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [_substitute_env_vars(item) for item in config]
    elif isinstance(config, str) and "${" in config:
        try:
            template = Template(config)
            return template.substitute(os.environ)
        except KeyError as e:
            logger.warning(f"Environment variable not found for template {config}: {e}")
            return config
    else:
        return config


def get_auth_provider(
    provider_type: Optional[str] = None
) -> AuthProvider:
    """Factory function to get the appropriate auth provider.
    
    Args:
        provider_type: Type of provider to create ('cognito', 'keycloak', or 'entra_id').
                      If None, uses AUTH_PROVIDER environment variable.
                      
    Returns:
        AuthProvider instance configured for the specified provider
        
    Raises:
        ValueError: If provider type is unknown or required config is missing
    """
    provider_type = provider_type or os.environ.get('AUTH_PROVIDER', 'cognito')
    
    logger.info(f"Creating authentication provider: {provider_type}")
    
    if provider_type == 'keycloak':
        return _create_keycloak_provider()
    elif provider_type == 'cognito':
        return _create_cognito_provider()
    elif provider_type == 'entra_id':
        return _create_entra_id_provider()
    else:
        raise ValueError(f"Unknown auth provider: {provider_type}")


def _create_keycloak_provider() -> KeycloakProvider:
    """Create and configure Keycloak provider."""
    # Required configuration
    keycloak_url = os.environ.get('KEYCLOAK_URL')
    keycloak_external_url = os.environ.get('KEYCLOAK_EXTERNAL_URL', keycloak_url)
    realm = os.environ.get('KEYCLOAK_REALM', 'mcp-gateway')
    client_id = os.environ.get('KEYCLOAK_CLIENT_ID')
    client_secret = os.environ.get('KEYCLOAK_CLIENT_SECRET')

    # Optional M2M configuration
    m2m_client_id = os.environ.get('KEYCLOAK_M2M_CLIENT_ID')
    m2m_client_secret = os.environ.get('KEYCLOAK_M2M_CLIENT_SECRET')

    # Validate required configuration
    missing_vars = []
    if not keycloak_url:
        missing_vars.append('KEYCLOAK_URL')
    if not client_id:
        missing_vars.append('KEYCLOAK_CLIENT_ID')
    if not client_secret:
        missing_vars.append('KEYCLOAK_CLIENT_SECRET')

    if missing_vars:
        raise ValueError(
            f"Missing required Keycloak configuration: {', '.join(missing_vars)}. "
            "Please set these environment variables."
        )

    logger.info(f"Initializing Keycloak provider for realm '{realm}' at {keycloak_url} (external: {keycloak_external_url})")

    return KeycloakProvider(
        keycloak_url=keycloak_url,
        keycloak_external_url=keycloak_external_url,
        realm=realm,
        client_id=client_id,
        client_secret=client_secret,
        m2m_client_id=m2m_client_id,
        m2m_client_secret=m2m_client_secret
    )


def _create_cognito_provider() -> CognitoProvider:
    """Create and configure Cognito provider."""
    # Required configuration
    user_pool_id = os.environ.get('COGNITO_USER_POOL_ID')
    client_id = os.environ.get('COGNITO_CLIENT_ID')
    client_secret = os.environ.get('COGNITO_CLIENT_SECRET')
    region = os.environ.get('AWS_REGION', 'us-east-1')
    
    # Optional configuration
    domain = os.environ.get('COGNITO_DOMAIN')
    
    # Validate required configuration
    missing_vars = []
    if not user_pool_id:
        missing_vars.append('COGNITO_USER_POOL_ID')
    if not client_id:
        missing_vars.append('COGNITO_CLIENT_ID')
    if not client_secret:
        missing_vars.append('COGNITO_CLIENT_SECRET')
    
    if missing_vars:
        raise ValueError(
            f"Missing required Cognito configuration: {', '.join(missing_vars)}. "
            "Please set these environment variables."
        )
    
    logger.info(f"Initializing Cognito provider for user pool '{user_pool_id}' in region '{region}'")
    
    return CognitoProvider(
        user_pool_id=user_pool_id,
        client_id=client_id,
        client_secret=client_secret,
        region=region,
        domain=domain
    )


def _create_entra_id_provider() -> EntraIDProvider:
    """Create and configure Microsoft Entra ID provider."""
    # Load OAuth2 configuration
    oauth2_config = _load_oauth2_config()
    entra_config = oauth2_config.get('providers', {}).get('entra_id', {})
    
    # Required configuration from environment variables
    tenant_id = os.environ.get('ENTRA_TENANT_ID')
    client_id = os.environ.get('ENTRA_CLIENT_ID')
    client_secret = os.environ.get('ENTRA_CLIENT_SECRET')
    
    # Optional configuration
    authority = os.environ.get('ENTRA_AUTHORITY')
    
    # OAuth2 configuration from oauth2_providers.yml with fallbacks
    scopes = entra_config.get('scopes')
    grant_type = entra_config.get('grant_type')
    
    # Optional claim mappings from oauth2_providers.yml
    username_claim = entra_config.get('username_claim')
    groups_claim = entra_config.get('groups_claim')
    email_claim = entra_config.get('email_claim')
    name_claim = entra_config.get('name_claim')
    
    # Validate required configuration
    missing_vars = []
    if not tenant_id:
        missing_vars.append('ENTRA_TENANT_ID')
    if not client_id:
        missing_vars.append('ENTRA_CLIENT_ID')
    if not client_secret:
        missing_vars.append('ENTRA_CLIENT_SECRET')
    
    if missing_vars:
        raise ValueError(
            f"Missing required Entra ID configuration: {', '.join(missing_vars)}. "
            "Please set these environment variables."
        )
    
    logger.info(f"Initializing Entra ID provider for tenant '{tenant_id}' with scopes={scopes}, grant_type={grant_type}")
    
    return EntraIDProvider(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        authority=authority,
        scopes=scopes,
        grant_type=grant_type,
        username_claim=username_claim,
        groups_claim=groups_claim,
        email_claim=email_claim,
        name_claim=name_claim
    )


def _get_provider_health_info() -> dict:
    """Get health information for the current provider."""
    try:
        provider = get_auth_provider()
        if hasattr(provider, 'get_provider_info'):
            return provider.get_provider_info()
        else:
            return {
                'provider_type': os.environ.get('AUTH_PROVIDER', 'cognito'),
                'status': 'unknown'
            }
    except Exception as e:
        logger.error(f"Failed to get provider health info: {e}")
        return {
            'provider_type': os.environ.get('AUTH_PROVIDER', 'cognito'),
            'status': 'error',
            'error': str(e)
        }