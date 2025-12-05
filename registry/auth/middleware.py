from fastapi import Request
from fastapi.responses import JSONResponse
from itsdangerous import SignatureExpired, BadSignature
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, Dict, Any
import logging

from registry.auth.dependencies import (map_cognito_groups_to_scopes, signer, get_ui_permissions_for_user,
                               get_user_accessible_servers, get_accessible_services_for_user,
                               get_accessible_agents_for_user, user_can_modify_servers,
                               user_has_wildcard_access)
from registry.core.config import settings

logger = logging.getLogger(__name__)


class UnifiedAuthMiddleware(BaseHTTPMiddleware):
    """
        A unified authentication middleware that encapsulates the functionality of `enhanced_auth` and `nginx_proxied_auth`.

        It automatically attempts all authentication methods and stores the results in `request.state`.
    """

    def __init__(self, app, public_paths: Optional[list] = None):
        super().__init__(app)
        self.public_paths = public_paths or [
            "/", "/health", "/docs", "/openapi.json",
            "/static",
            "/api/auth/login",
            "/logout",
            "/auth",
            "/callback",
        ]
        self.internal_paths = [
            "/internal/register",
            "/internal/remove",
            "/internal/toggle",
            "/internal/healthcheck",
            "/internal/add-to-groups",
            "/internal/remove-from-groups",
            "/internal/list",
            "/internal/create-group",
            "/internal/delete-group",
            "/internal/list-groups",
        ]

    async def dispatch(self, request: Request, call_next):
        if self._is_public_path(request.url.path):
            return await call_next(request)
        try:
            user_context = await self._authenticate(request)
            request.state.user = user_context
            request.state.is_authenticated = True
            request.state.auth_source = user_context.get('auth_source', 'unknown')
            return await call_next(request)
        except AuthenticationError as e:
            logger.warning(f"Auth failed for {request.url.path}: {e}")
            return JSONResponse(status_code=401, content={"detail": str(e)})
        except Exception as e:
            logger.error(f"Auth error for {request.url.path}: {e}")
            return JSONResponse(status_code=500, content={"detail": "Authentication error"})

    def _is_public_path(self, path: str) -> bool:
        """检查路径是否为公开路径"""
        all_paths = self.public_paths + self.internal_paths
        for public_path in all_paths:
            if public_path == "/" and path == "/":
                return True
            elif public_path != "/" and (path == public_path or path.startswith(public_path + "/")):
                return True
        return False

    async def _authenticate(self, request: Request) -> Dict[str, Any]:
        """
        Unified authentication logic: Implementing the logic of the original nginx_proxied_auth
            1. Prioritize nginx headers (JWT)
            2. As a fallback, try session cookies (enhanced_auth logic)
        """
        # 1. Try nginx headers authentication (the first part of nginx_proxied_auth).
        user_context = self._try_nginx_headers_auth(request)
        if user_context:
            user_context['auth_source'] = 'nginx_headers'
            logger.info(f"nginx headers auth success: {user_context['username']}")
            return user_context

        # 2. Attempt session cookie authentication (enhanced_auth logic)
        user_context = self._try_session_auth(request)
        if user_context:
            user_context['auth_source'] = 'session_cookie'
            logger.info(f"session auth success: {user_context['username']}")
            return user_context

        raise AuthenticationError("No valid authentication found")

    def _try_nginx_headers_auth(self, request: Request) -> Optional[Dict[str, Any]]:
        """nginx 代理认证 (原 nginx_proxied_auth 逻辑)"""
        try:
            x_user = request.headers.get("X-User")
            x_username = request.headers.get("X-Username")
            x_scopes = request.headers.get("X-Scopes")
            x_auth_method = request.headers.get("X-Auth-Method")

            if not (x_user or x_username):
                return None

            username = x_username or x_user
            scopes = x_scopes.split() if x_scopes else []

            groups = []
            if x_auth_method in ['keycloak', 'entra', 'cognito']:
                if ('mcp-servers-unrestricted/read' in scopes and
                        'mcp-servers-unrestricted/execute' in scopes):
                    groups = ['mcp-registry-admin']
                else:
                    groups = ['mcp-registry-user']

            logger.info(f"nginx-proxied auth for user: {username}, method: {x_auth_method}, scopes: {scopes}")

            return self._build_user_context(
                username=username,
                groups=groups,
                scopes=scopes,
                auth_method=x_auth_method or 'keycloak',
                provider=x_auth_method or 'keycloak'
            )

        except Exception as e:
            logger.debug(f"nginx headers auth failed: {e}")
            return None

    def _try_session_auth(self, request: Request) -> Optional[Dict[str, Any]]:
        """session 认证 (原 enhanced_auth 逻辑)"""
        try:
            session_cookie = request.cookies.get(settings.session_cookie_name)
            if not session_cookie:
                return None
            session_data = self._parse_session_data(session_cookie)
            if not session_data:
                return None

            username = session_data['username']
            groups = session_data.get('groups', [])
            auth_method = session_data.get('auth_method', 'traditional')

            logger.info(f"Enhanced auth debug for {username}: groups={groups}, auth_method={auth_method}")

            # 按照 enhanced_auth 的逻辑处理权限
            if auth_method == 'oauth2':
                scopes = map_cognito_groups_to_scopes(groups)
                logger.info(f"OAuth2 user {username} with groups {groups} mapped to scopes: {scopes}")
                if not groups:
                    logger.warning(f"OAuth2 user {username} has no groups!")
            else:
                # 传统用户动态映射到 admin
                if not groups:
                    groups = ['mcp-registry-admin']
                scopes = map_cognito_groups_to_scopes(groups)
                if not scopes:
                    scopes = ['mcp-registry-admin', 'mcp-servers-unrestricted/read', 'mcp-servers-unrestricted/execute']
                logger.info(f"Traditional user {username} with groups {groups} mapped to scopes: {scopes}")

            return self._build_user_context(
                username=username,
                groups=groups,
                scopes=scopes,
                auth_method=auth_method,
                provider=session_data.get('provider', 'local')
            )

        except Exception as e:
            logger.debug(f"session auth failed: {e}")
            return None

    def _parse_session_data(self, session_cookie: str) -> Optional[Dict[str, Any]]:
        try:
            data = signer.loads(session_cookie, max_age=settings.session_max_age_seconds)
            if not data.get('username'):
                return None
            # Sets the default value for traditionally authenticated users (from the original get_user_session_data).
            if data.get('auth_method') != 'oauth2':
                data.setdefault('groups', ['mcp-registry-admin'])
                data.setdefault('scopes', ['mcp-servers-unrestricted/read',
                                           'mcp-servers-unrestricted/execute'])
            return data

        except (SignatureExpired, BadSignature, Exception):
            return None

    def _build_user_context(self, username: str, groups: list, scopes: list,
                            auth_method: str, provider: str) -> Dict[str, Any]:
        """
            Construct the complete user context (from the original enhanced_auth logic).
        """
        ui_permissions = get_ui_permissions_for_user(scopes)
        accessible_servers = get_user_accessible_servers(scopes)
        accessible_services = get_accessible_services_for_user(ui_permissions)
        accessible_agents = get_accessible_agents_for_user(ui_permissions)
        can_modify = user_can_modify_servers(groups, scopes)

        user_context = {
            'username': username,
            'groups': groups,
            'scopes': scopes,
            'auth_method': auth_method,
            'provider': provider,
            'accessible_servers': accessible_servers,
            'accessible_services': accessible_services,
            'accessible_agents': accessible_agents,
            'ui_permissions': ui_permissions,
            'can_modify_servers': can_modify,
            'is_admin': user_has_wildcard_access(scopes)
        }
        logger.debug(f"User context for {username}: {user_context}")
        return user_context


class AuthenticationError(Exception):
    pass
