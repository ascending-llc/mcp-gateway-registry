import logging
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from auth_utils.models import UserContextDict
from auth_utils.scopes import load_scopes_config

from ..core.config import settings

logger = logging.getLogger(__name__)

# Initialize session signer
signer = URLSafeTimedSerializer(settings.secret_key)

# Global scopes configuration
SCOPES_CONFIG = load_scopes_config()


def get_current_user_by_mid(request: Request) -> UserContextDict:
    """
    Get current authenticated user from request state.

    Args:
        request: FastAPI request object

    Returns:
        User context dictionary with all authentication details

    Raises:
        HTTPException: If user is not authenticated
    """
    if not hasattr(request.state, "user") or not request.state.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Is not authenticated")
    return request.state.user


# Use this type to annotate a parameter of a path operation function or its dependency function so that
# FastAPI extracts the `user` attribute (typed as UserContextDict) of the current request and pass it to the parameter.
# Since it's Python 3.12, we use the new type statement instead of typing.TypeAlias
type CurrentUser = Annotated[UserContextDict, Depends(get_current_user_by_mid)]


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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    try:
        data = signer.loads(session, max_age=settings.session_max_age_seconds)
        username = data.get("username")

        if not username:
            logger.warning("No username found in session data")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session data")

        logger.debug(f"Authentication successful for user: {username}")
        return username

    except SignatureExpired:
        logger.warning("Session cookie has expired")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has expired")
    except BadSignature:
        logger.warning("Invalid session cookie signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed")


def get_ui_permissions_for_user(user_scopes: list[str]) -> dict[str, list[str]]:
    """
    Get UI permissions for a user based on their scopes.

    Args:
        user_scopes: List of user's scopes (includes UI scope names like 'mcp-registry-admin')

    Returns:
        Dict mapping UI actions to lists of services they can perform the action on
        Example: {'list_service': ['mcpgw', 'auth_server'], 'toggle_service': ['mcpgw']}
    """
    ui_permissions = {}
    ui_scopes = SCOPES_CONFIG.get("UI-Scopes", {})

    for scope in user_scopes:
        if scope in ui_scopes:
            scope_config = ui_scopes[scope]
            logger.debug(f"Processing UI scope '{scope}' with config: {scope_config}")

            # Process each permission in the scope
            for permission, services in scope_config.items():
                if permission not in ui_permissions:
                    ui_permissions[permission] = set()

                # Handle "all" case
                if services == ["all"] or (isinstance(services, list) and "all" in services):
                    ui_permissions[permission].add("all")
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


def user_has_ui_permission_for_service(
    permission: str, service_name: str, user_ui_permissions: dict[str, list[str]]
) -> bool:
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
    has_permission = "all" in allowed_services or service_name in allowed_services

    logger.debug(f"Permission check: {permission} for {service_name} = {has_permission} (allowed: {allowed_services})")
    return has_permission


def get_accessible_services_for_user(user_ui_permissions: dict[str, list[str]]) -> list[str]:
    """
    Get list of services the user can see based on their list_service permission.

    Args:
        user_ui_permissions: User's UI permissions dict from get_ui_permissions_for_user()

    Returns:
        List of service names the user can see, or ['all'] if they can see all services
    """
    list_permissions = user_ui_permissions.get("list_service", [])

    if "all" in list_permissions:
        return ["all"]

    return list_permissions


def get_accessible_agents_for_user(user_ui_permissions: dict[str, list[str]]) -> list[str]:
    """
    Get list of agents the user can see based on their list_agents permission.

    Args:
        user_ui_permissions: User's UI permissions dict from get_ui_permissions_for_user()

    Returns:
        List of agent paths the user can see, or ['all'] if they can see all agents
    """
    list_permissions = user_ui_permissions.get("list_agents", [])

    if "all" in list_permissions:
        return ["all"]

    return list_permissions


def get_servers_for_scope(scope: str) -> list[str]:
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
        if isinstance(server_config, dict) and "server" in server_config:
            server_names.append(server_config["server"])

    return list(set(server_names))  # Remove duplicates


def user_has_wildcard_access(user_scopes: list[str]) -> bool:
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
        if "*" in servers:
            logger.debug(f"User scope '{scope}' grants wildcard access to all servers")
            return True

    return False


def get_user_accessible_servers(user_scopes: list[str]) -> list[str]:
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


def user_can_modify_servers(user_groups: list[str], user_scopes: list[str]) -> bool:
    """
    Check if user can modify servers (toggle, edit).

    Args:
        user_groups: List of user's groups
        user_scopes: List of user's scopes

    Returns:
        True if user can modify servers, False otherwise
    """
    # Admin users can always modify
    if "mcp-registry-admin" in user_groups:
        return True

    # Users with unrestricted execute access can modify
    if "mcp-servers-unrestricted/execute" in user_scopes:
        return True

    # mcp-registry-user group cannot modify servers
    if "mcp-registry-user" in user_groups and "mcp-registry-admin" not in user_groups:
        return False

    # For other cases, check if they have any execute permissions
    execute_scopes = [scope for scope in user_scopes if "/execute" in scope]
    return len(execute_scopes) > 0


def user_can_access_server(server_name: str, user_scopes: list[str]) -> bool:
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


def create_session_cookie(
    username: str, auth_method: str = "traditional", provider: str = "local", groups: list[str] = None
) -> str:
    """
    Create a session cookie for a user.

    Security Note: For traditional auth, this function grants admin privileges.
    Only call this function AFTER validating credentials with validate_login_credentials().

    Args:
        username: The authenticated username
        auth_method: Authentication method ('traditional' or 'oauth2')
        provider: Authentication provider
        groups: User groups (for OAuth2). If None and auth_method is 'traditional',
                defaults to admin group.

    Returns:
        Signed session cookie string

    Raises:
        ValueError: If attempting to create traditional session for non-admin user
    """
    # For traditional auth users, validate and default to admin group
    if groups is None and auth_method == "traditional":
        # Security check: Traditional auth only supports the configured admin user
        if username != settings.admin_user:
            logger.error(f"Security violation: Attempted to create traditional session for non-admin user: {username}")
            raise ValueError("Traditional authentication only supports the configured admin user")
        groups = ["mcp-registry-admin"]

    session_data = {"username": username, "auth_method": auth_method, "provider": provider, "groups": groups or []}

    # For traditional (local) auth users, include groups and scopes in the session cookie
    # This ensures the auth server can validate access without needing to query external systems
    # Use registry-admins group which has wildcard access to all servers and agents
    if auth_method == "traditional":
        session_data["groups"] = ["registry-admins"]
        session_data["scopes"] = ["registry-admins"]

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

    def check_permission(user_context: CurrentUser) -> UserContextDict:
        ui_permissions = user_context.get("ui_permissions", {})

        if service_name:
            # Check permission for specific service
            if not user_has_ui_permission_for_service(permission, service_name, ui_permissions):
                logger.warning(
                    f"User {user_context.get('username')} lacks UI permission '{permission}' for service '{service_name}'"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required: {permission} for {service_name}",
                )
        else:
            # Check if user has permission for any service
            if permission not in ui_permissions or not ui_permissions[permission]:
                logger.warning(f"User {user_context.get('username')} lacks UI permission: {permission}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail=f"Insufficient permissions. Required: {permission}"
                )

        return user_context

    return check_permission
