import secrets
from typing import Annotated, List, Dict, Any, Optional
import logging
import yaml
from pathlib import Path

from fastapi import Depends, HTTPException, status, Cookie
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from ..core.config import settings

logger = logging.getLogger(__name__)

# Initialize session signer
signer = URLSafeTimedSerializer(settings.secret_key)


def get_current_user(
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> str:
    """
    Get the current authenticated user from session cookie.
    
    Returns:
        str: Username of the authenticated user
        
    Raises:
        HTTPException: If user is not authenticated
    """
    if not session:
        logger.warning("No session cookie provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    try:
        data = signer.loads(session, max_age=settings.session_max_age_seconds)
        username = data.get('username')
        
        if not username:
            logger.warning("No username found in session data")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid session data"
            )
        
        logger.debug(f"Authentication successful for user: {username}")
        return username
        
    except SignatureExpired:
        logger.warning("Session cookie has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired"
        )
    except BadSignature:
        logger.warning("Invalid session cookie signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )


def get_user_session_data(
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> Dict[str, Any]:
    """
    Get the full session data for the authenticated user.
    
    Returns:
        Dict containing username, groups, auth_method, provider, etc.
        
    Raises:
        HTTPException: If user is not authenticated
    """
    if not session:
        logger.warning("No session cookie provided for session data extraction")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    try:
        data = signer.loads(session, max_age=settings.session_max_age_seconds)
        
        if not data.get('username'):
            logger.warning("No username found in session data")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid session data"
            )
        
        # Set defaults for traditional auth users
        if data.get('auth_method') != 'oauth2':
            # Traditional users get admin privileges
            data.setdefault('groups', ['mcp-admin'])
            data.setdefault('scopes', ['mcp-servers-unrestricted/read', 'mcp-servers-unrestricted/execute'])
        
        logger.debug(f"Session data extracted for user: {data.get('username')}")
        return data
        
    except SignatureExpired:
        logger.warning("Session cookie has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired"
        )
    except BadSignature:
        logger.warning("Invalid session cookie signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session"
        )
    except Exception as e:
        logger.error(f"Session data extraction error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )


def load_scopes_config() -> Dict[str, Any]:
    """Load the scopes configuration from auth_server/scopes.yml"""
    try:
        # Look for scopes.yml in auth_server directory
        scopes_file = Path(__file__).parent.parent.parent / "auth_server" / "scopes.yml"
        if not scopes_file.exists():
            logger.warning(f"Scopes config file not found at {scopes_file}")
            return {}
            
        with open(scopes_file, 'r') as f:
            config = yaml.safe_load(f)
            logger.info(f"Loaded scopes configuration with {len(config.get('group_mappings', {}))} group mappings")
            return config
    except Exception as e:
        logger.error(f"Failed to load scopes configuration: {e}")
        return {}


# Global scopes configuration
SCOPES_CONFIG = load_scopes_config()


def map_cognito_groups_to_scopes(groups: List[str]) -> List[str]:
    """
    Map Cognito groups to MCP scopes using the scopes.yml configuration.
    
    Args:
        groups: List of Cognito group names
        
    Returns:
        List of MCP scopes
    """
    scopes = []
    group_mappings = SCOPES_CONFIG.get('group_mappings', {})
    
    for group in groups:
        if group in group_mappings:
            group_scopes = group_mappings[group]
            scopes.extend(group_scopes)
            logger.debug(f"Mapped group '{group}' to scopes: {group_scopes}")
        else:
            logger.debug(f"No scope mapping found for group: {group}")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_scopes = []
    for scope in scopes:
        if scope not in seen:
            seen.add(scope)
            unique_scopes.append(scope)
    
    logger.info(f"Final mapped scopes: {unique_scopes}")
    return unique_scopes


def get_servers_for_scope(scope: str) -> List[str]:
    """
    Get list of server names that a scope provides access to.
    
    Args:
        scope: The scope to check (e.g., 'mcp-servers-restricted/read')
        
    Returns:
        List of server names the scope grants access to
    """
    scope_config = SCOPES_CONFIG.get(scope, [])
    server_names = []
    
    for server_config in scope_config:
        if isinstance(server_config, dict) and 'server' in server_config:
            server_names.append(server_config['server'])
    
    return list(set(server_names))  # Remove duplicates


def get_user_accessible_servers(user_scopes: List[str]) -> List[str]:
    """
    Get list of all servers the user has access to based on their scopes.
    
    Args:
        user_scopes: List of user's scopes
        
    Returns:
        List of server names the user can access
    """
    accessible_servers = set()
    
    logger.info(f"DEBUG: get_user_accessible_servers called with scopes: {user_scopes}")
    logger.info(f"DEBUG: Available scope configs: {list(SCOPES_CONFIG.keys())}")
    
    for scope in user_scopes:
        logger.info(f"DEBUG: Processing scope: {scope}")
        server_names = get_servers_for_scope(scope)
        logger.info(f"DEBUG: Scope {scope} maps to servers: {server_names}")
        accessible_servers.update(server_names)
    
    logger.info(f"DEBUG: Final accessible servers: {list(accessible_servers)}")
    logger.debug(f"User with scopes {user_scopes} has access to servers: {list(accessible_servers)}")
    return list(accessible_servers)


def user_can_modify_servers(user_groups: List[str], user_scopes: List[str]) -> bool:
    """
    Check if user can modify servers (toggle, edit).
    
    Args:
        user_groups: List of user's groups
        user_scopes: List of user's scopes
        
    Returns:
        True if user can modify servers, False otherwise
    """
    # Admin users can always modify
    if 'mcp-admin' in user_groups:
        return True
    
    # Users with unrestricted execute access can modify
    if 'mcp-servers-unrestricted/execute' in user_scopes:
        return True
    
    # mcp-user group cannot modify servers
    if 'mcp-user' in user_groups and 'mcp-admin' not in user_groups:
        return False
    
    # For other cases, check if they have any execute permissions
    execute_scopes = [scope for scope in user_scopes if '/execute' in scope]
    return len(execute_scopes) > 0


def user_can_access_server(server_name: str, user_scopes: List[str]) -> bool:
    """
    Check if user can access a specific server.
    
    Args:
        server_name: Name of the server to check
        user_scopes: List of user's scopes
        
    Returns:
        True if user can access the server, False otherwise
    """
    accessible_servers = get_user_accessible_servers(user_scopes)
    return server_name in accessible_servers


def api_auth(
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> str:
    """
    API authentication dependency that returns the username.
    Used for API endpoints that need authentication.
    """
    return get_current_user(session)


def web_auth(
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> str:
    """
    Web authentication dependency that returns the username.
    Used for web pages that need authentication.
    """
    return get_current_user(session)


def enhanced_auth(
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> Dict[str, Any]:
    """
    Enhanced authentication dependency that returns full user context.
    Returns username, groups, scopes, and permission flags.
    """
    session_data = get_user_session_data(session)
    
    username = session_data['username']
    groups = session_data.get('groups', [])
    auth_method = session_data.get('auth_method', 'traditional')
    
    logger.info(f"Enhanced auth debug for {username}: groups={groups}, auth_method={auth_method}")
    
    # Map groups to scopes for OAuth2 users
    if auth_method == 'oauth2':
        scopes = map_cognito_groups_to_scopes(groups)
        logger.info(f"OAuth2 user {username} with groups {groups} mapped to scopes: {scopes}")
        # If OAuth2 user has no groups, they should get minimal permissions, not admin
        if not groups:
            logger.warning(f"OAuth2 user {username} has no groups! This user may not have proper group assignments in Cognito.")
    else:
        # Traditional users get admin scopes  
        scopes = session_data.get('scopes', ['mcp-servers-unrestricted/read', 'mcp-servers-unrestricted/execute'])
        if not groups:
            groups = ['mcp-admin']
            logger.info(f"Traditional user {username} has no groups, assigning mcp-admin group and unrestricted scopes")
    
    # Get accessible servers
    accessible_servers = get_user_accessible_servers(scopes)
    
    # Check modification permissions
    can_modify = user_can_modify_servers(groups, scopes)
    
    user_context = {
        'username': username,
        'groups': groups,
        'scopes': scopes,
        'auth_method': auth_method,
        'provider': session_data.get('provider', 'local'),
        'accessible_servers': accessible_servers,
        'can_modify_servers': can_modify,
        'is_admin': 'mcp-admin' in groups
    }
    
    logger.debug(f"Enhanced auth context for {username}: {user_context}")
    return user_context


def create_session_cookie(username: str, auth_method: str = "traditional", provider: str = "local") -> str:
    """Create a session cookie for a user."""
    session_data = {
        "username": username,
        "auth_method": auth_method,
        "provider": provider
    }
    return signer.dumps(session_data)


def validate_login_credentials(username: str, password: str) -> bool:
    """Validate traditional login credentials."""
    return username == settings.admin_user and password == settings.admin_password 