import secrets
from typing import Annotated, List, Dict, Any, Optional
import logging
import yaml
from pathlib import Path

from fastapi import Depends, HTTPException, status, Cookie, Header, Request
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
            data.setdefault('groups', ['mcp-registry-admin'])
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
        # Check for SCOPES_CONFIG_PATH environment variable first
        import os
        scopes_path = os.getenv("SCOPES_CONFIG_PATH")

        # Print to stderr for immediate visibility before logging is configured
        print(f"[SCOPES_INIT] SCOPES_CONFIG_PATH env var: {scopes_path}", flush=True)

        # Fall back to default location if env var not set
        if not scopes_path:
            scopes_file = Path(__file__).parent.parent.parent / "auth_server" / "scopes.yml"
        else:
            scopes_file = Path(scopes_path)

        # If file doesn't exist, try the EFS mounted location (auth_config subdirectory)
        if not scopes_file.exists():
            alt_scopes_file = Path(__file__).parent.parent.parent / "auth_server" / "auth_config" / "scopes.yml"
            if alt_scopes_file.exists():
                scopes_file = alt_scopes_file
                print(f"[SCOPES_INIT] File not found at primary location, using EFS mount location: {scopes_file}", flush=True)

        print(f"[SCOPES_INIT] Looking for scopes config at: {scopes_file}", flush=True)
        print(f"[SCOPES_INIT] Scopes file exists: {scopes_file.exists()}", flush=True)

        if not scopes_file.exists():
            print(f"[SCOPES_INIT] ERROR: Scopes config file not found at {scopes_file}", flush=True)
            auth_server_dir = scopes_file.parent
            print(f"[SCOPES_INIT] Auth server directory exists: {auth_server_dir.exists()}", flush=True)
            if auth_server_dir.exists():
                print(f"[SCOPES_INIT] Auth server directory contents: {list(auth_server_dir.iterdir())}", flush=True)
            logger.warning(f"Scopes config file not found at {scopes_file}")
            return {}

        with open(scopes_file, 'r') as f:
            config = yaml.safe_load(f)
            logger.info(f"Loaded scopes configuration with {len(config.get('group_mappings', {}))} group mappings")
            return config
    except Exception as e:
        logger.error(f"Failed to load scopes configuration: {e}", exc_info=True)
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


def get_ui_permissions_for_user(user_scopes: List[str]) -> Dict[str, List[str]]:
    """
    Get UI permissions for a user based on their scopes.

    Args:
        user_scopes: List of user's scopes (includes UI scope names like 'mcp-registry-admin')

    Returns:
        Dict mapping UI actions to lists of services they can perform the action on
        Example: {'list_service': ['mcpgw', 'auth_server'], 'toggle_service': ['mcpgw']}
    """
    ui_permissions = {}
    ui_scopes = SCOPES_CONFIG.get('UI-Scopes', {})

    for scope in user_scopes:
        if scope in ui_scopes:
            scope_config = ui_scopes[scope]
            logger.debug(f"Processing UI scope '{scope}' with config: {scope_config}")

            # Process each permission in the scope
            for permission, services in scope_config.items():
                if permission not in ui_permissions:
                    ui_permissions[permission] = set()

                # Handle "all" case
                if services == ['all'] or (isinstance(services, list) and 'all' in services):
                    ui_permissions[permission].add('all')
                    logger.debug(f"UI permission '{permission}' granted for all services")
                else:
                    # Add specific services
                    if isinstance(services, list):
                        ui_permissions[permission].update(services)
                        logger.debug(f"UI permission '{permission}' granted for services: {services}")

    # Convert sets back to lists
    result = {k: list(v) for k, v in ui_permissions.items()}
    logger.info(f"Final UI permissions for user: {result}")
    return result


def user_has_ui_permission_for_service(permission: str, service_name: str, user_ui_permissions: Dict[str, List[str]]) -> bool:
    """
    Check if user has a specific UI permission for a specific service.
    
    Args:
        permission: The UI permission to check (e.g., 'list_service', 'toggle_service')
        service_name: The service name to check permission for
        user_ui_permissions: User's UI permissions dict from get_ui_permissions_for_user()
        
    Returns:
        True if user has the permission for the service, False otherwise
    """
    if permission not in user_ui_permissions:
        return False
    
    allowed_services = user_ui_permissions[permission]
    
    # Check if user has permission for all services or the specific service
    has_permission = 'all' in allowed_services or service_name in allowed_services
    
    logger.debug(f"Permission check: {permission} for {service_name} = {has_permission} (allowed: {allowed_services})")
    return has_permission


def get_accessible_services_for_user(user_ui_permissions: Dict[str, List[str]]) -> List[str]:
    """
    Get list of services the user can see based on their list_service permission.

    Args:
        user_ui_permissions: User's UI permissions dict from get_ui_permissions_for_user()

    Returns:
        List of service names the user can see, or ['all'] if they can see all services
    """
    list_permissions = user_ui_permissions.get('list_service', [])

    if 'all' in list_permissions:
        return ['all']

    return list_permissions


def get_accessible_agents_for_user(user_ui_permissions: Dict[str, List[str]]) -> List[str]:
    """
    Get list of agents the user can see based on their list_agents permission.

    Args:
        user_ui_permissions: User's UI permissions dict from get_ui_permissions_for_user()

    Returns:
        List of agent paths the user can see, or ['all'] if they can see all agents
    """
    list_permissions = user_ui_permissions.get('list_agents', [])

    if 'all' in list_permissions:
        return ['all']

    return list_permissions


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


def user_has_wildcard_access(user_scopes: List[str]) -> bool:
    """
    Check if user has wildcard access to all servers via their scopes.

    A user has wildcard access if any of their scopes includes server: '*'.
    This is determined dynamically from the scopes configuration, not hardcoded group names.

    Args:
        user_scopes: List of user's scopes

    Returns:
        True if user has wildcard access to all servers, False otherwise
    """
    for scope in user_scopes:
        servers = get_servers_for_scope(scope)
        if '*' in servers:
            logger.debug(f"User scope '{scope}' grants wildcard access to all servers")
            return True

    return False


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
    if 'mcp-registry-admin' in user_groups:
        return True
    
    # Users with unrestricted execute access can modify
    if 'mcp-servers-unrestricted/execute' in user_scopes:
        return True
    
    # mcp-registry-user group cannot modify servers
    if 'mcp-registry-user' in user_groups and 'mcp-registry-admin' not in user_groups:
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
        # Traditional users dynamically map to admin
        if not groups:
            groups = ['mcp-registry-admin']
        # Map traditional admin groups to scopes dynamically
        scopes = map_cognito_groups_to_scopes(groups)
        if not scopes:
            # Fallback for traditional users if no mapping exists
            scopes = ['mcp-registry-admin', 'mcp-servers-unrestricted/read', 'mcp-servers-unrestricted/execute']
        logger.info(f"Traditional user {username} with groups {groups} mapped to scopes: {scopes}")
    
    # Get UI permissions
    ui_permissions = get_ui_permissions_for_user(scopes)

    # Get accessible servers (from server scopes)
    accessible_servers = get_user_accessible_servers(scopes)

    # Get accessible services (from UI permissions)
    accessible_services = get_accessible_services_for_user(ui_permissions)

    # Get accessible agents (from UI permissions)
    accessible_agents = get_accessible_agents_for_user(ui_permissions)

    # Check modification permissions
    can_modify = user_can_modify_servers(groups, scopes)

    user_context = {
        'username': username,
        'groups': groups,
        'scopes': scopes,
        'auth_method': auth_method,
        'provider': session_data.get('provider', 'local'),
        'accessible_servers': accessible_servers,
        'accessible_services': accessible_services,
        'accessible_agents': accessible_agents,
        'ui_permissions': ui_permissions,
        'can_modify_servers': can_modify,
        'is_admin': user_has_wildcard_access(scopes)
    }

    logger.debug(f"Enhanced auth context for {username}: {user_context}")
    return user_context


def nginx_proxied_auth(
    request: Request,
    session: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
    x_user: Annotated[str | None, Header(alias="X-User")] = None,
    x_username: Annotated[str | None, Header(alias="X-Username")] = None,
    x_scopes: Annotated[str | None, Header(alias="X-Scopes")] = None,
    x_auth_method: Annotated[str | None, Header(alias="X-Auth-Method")] = None,
) -> Dict[str, Any]:
    """
    Authentication dependency that works with both nginx-proxied requests and direct requests.

    For nginx-proxied requests: Reads user context from headers set by nginx after auth validation
    For direct requests: Falls back to session cookie authentication

    This allows Anthropic Registry API endpoints to work both when accessed through nginx (with JWT tokens)
    and when accessed directly (with session cookies).

    Returns:
        Dict containing username, groups, scopes, and permission flags
    """
    # CRITICAL DIAGNOSTIC: Log ALL incoming headers and auth parameters
    logger.debug(f"[NGINX_AUTH_DEBUG] Request path: {request.url.path}")
    logger.debug(f"[NGINX_AUTH_DEBUG] Request method: {request.method}")
    logger.debug(f"[NGINX_AUTH_DEBUG] X-User header: '{x_user}' (type: {type(x_user).__name__})")
    logger.debug(f"[NGINX_AUTH_DEBUG] X-Username header: '{x_username}' (type: {type(x_username).__name__})")
    logger.debug(f"[NGINX_AUTH_DEBUG] X-Scopes header: '{x_scopes}' (type: {type(x_scopes).__name__})")
    logger.debug(f"[NGINX_AUTH_DEBUG] X-Auth-Method header: '{x_auth_method}' (type: {type(x_auth_method).__name__})")
    logger.debug(f"[NGINX_AUTH_DEBUG] Session cookie present: {session is not None}")
    logger.debug(f"[NGINX_AUTH_DEBUG] Authorization header: {request.headers.get('authorization', 'NOT PRESENT')[:50] if request.headers.get('authorization') else 'NOT PRESENT'}")

    # Log ALL headers for complete diagnostic
    all_headers = dict(request.headers)
    logger.debug(f"[NGINX_AUTH_DEBUG] ALL REQUEST HEADERS: {all_headers}")

    # First, try to get user context from nginx headers (JWT Bearer token flow)
    if x_user or x_username:
        username = x_username or x_user

        # Parse scopes from space-separated header
        scopes = x_scopes.split() if x_scopes else []

        # Map scopes to get groups based on auth method
        groups = []
        if x_auth_method in ['keycloak', 'entra', 'cognito']:
            # User authenticated via OAuth2 JWT (Keycloak, Entra ID, or Cognito)
            # Scopes already contain mapped permissions
            # Check if user has admin scopes
            if 'mcp-servers-unrestricted/read' in scopes and 'mcp-servers-unrestricted/execute' in scopes:
                groups = ['mcp-registry-admin']
            else:
                groups = ['mcp-registry-user']

        logger.info(f"nginx-proxied auth for user: {username}, method: {x_auth_method}, scopes: {scopes}")

        # Get accessible servers based on scopes
        accessible_servers = get_user_accessible_servers(scopes)

        # Get UI permissions
        ui_permissions = get_ui_permissions_for_user(scopes)

        # Get accessible services
        accessible_services = get_accessible_services_for_user(ui_permissions)

        # Get accessible agents
        accessible_agents = get_accessible_agents_for_user(ui_permissions)

        # Check modification permissions
        can_modify = user_can_modify_servers(groups, scopes)

        user_context = {
            'username': username,
            'groups': groups,
            'scopes': scopes,
            'auth_method': x_auth_method or 'keycloak',
            'provider': x_auth_method or 'keycloak',  # Use actual auth method as provider
            'accessible_servers': accessible_servers,
            'accessible_services': accessible_services,
            'accessible_agents': accessible_agents,
            'ui_permissions': ui_permissions,
            'can_modify_servers': can_modify,
            'is_admin': user_has_wildcard_access(scopes)
        }

        logger.debug(f"nginx-proxied auth context for {username}: {user_context}")
        return user_context

    # Fallback to session cookie authentication
    logger.debug("No nginx auth headers found, falling back to session cookie auth")
    return enhanced_auth(session)


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


def ui_permission_required(permission: str, service_name: str = None):
    """
    Decorator to require a specific UI permission for a route.
    
    Args:
        permission: The UI permission required (e.g., 'register_service')
        service_name: Optional service name to check permission for. If None, checks if user has permission for any service.
    
    Returns:
        Dependency function that checks the permission
    """
    def check_permission(user_context: Dict[str, Any] = Depends(enhanced_auth)) -> Dict[str, Any]:
        ui_permissions = user_context.get('ui_permissions', {})
        
        if service_name:
            # Check permission for specific service
            if not user_has_ui_permission_for_service(permission, service_name, ui_permissions):
                logger.warning(f"User {user_context.get('username')} lacks UI permission '{permission}' for service '{service_name}'")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required: {permission} for {service_name}"
                )
        else:
            # Check if user has permission for any service
            if permission not in ui_permissions or not ui_permissions[permission]:
                logger.warning(f"User {user_context.get('username')} lacks UI permission: {permission}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required: {permission}"
                )
        
        return user_context
    
    return check_permission 