import base64
import os
import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from itsdangerous import SignatureExpired, BadSignature
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, Dict, Any, List, Tuple
from starlette.routing import compile_path
from registry.utils.log import logger

from registry.auth.dependencies import (map_cognito_groups_to_scopes, signer, get_ui_permissions_for_user,
                                        get_user_accessible_servers, get_accessible_services_for_user,
                                        get_accessible_agents_for_user, user_can_modify_servers,
                                        user_has_wildcard_access)
from registry.core.config import settings


class UnifiedAuthMiddleware(BaseHTTPMiddleware):
    """
        A unified authentication middleware that encapsulates the functionality of `enhanced_auth` and `nginx_proxied_auth`.

        It automatically attempts all authentication methods and stores the results in `request.state`.
    """

    def __init__(self, app):
        super().__init__(app)
        # Paths that require authentication (checked before public paths)
        self.authenticated_paths_compiled = self._compile_patterns([
            "/api/auth/me",
            "/api/{versions}/servers/{path:path}",
            "/api/{versions}/servers",
            "/proxy/{path:path}",
            "/api/mcp/{path:path}",
        ])
        self.public_paths_compiled = self._compile_patterns([
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/static/{path:path}",
            "/api/auth/{path:path}",  # Most auth endpoints are public
            "/api/mcp/{versions}/{server_name}/oauth/callback",  # OAuth callback is public
            "/api/mcp/{versions}/oauth/success",  # OAuth success page
            "/api/mcp/{versions}/oauth/error",  # OAuth error page
        ])
        # note: admin
        self.internal_paths_compiled = self._compile_patterns([
            "/api/internal/{path:path}",
        ])
        logger.info(
            f"Auth middleware initialized with Starlette routing: "
            f"{len(self.authenticated_paths_compiled)} authenticated, "
            f"{len(self.public_paths_compiled)} public, "
            f"{len(self.internal_paths_compiled)} internal, "
        )

    def _compile_patterns(self, patterns: List[str]) -> List[Tuple]:
        """
        Compile path patterns into Starlette route matchers
        """
        compiled = []
        for pattern in patterns:
            try:
                path_regex, path_format, param_convertors = compile_path(pattern)
                compiled.append((pattern, path_regex, path_format, param_convertors))
                logger.debug(f"Compiled pattern: {pattern} -> {path_regex.pattern}")
            except Exception as e:
                logger.error(f"Failed to compile pattern '{pattern}': {e}")
        return compiled

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Check authenticated paths first (these override public patterns)
        if self._match_path(path, self.authenticated_paths_compiled):
            logger.debug(f"Authenticated path: {path}")
            # Continue to authentication logic below
        elif self._match_path(path, self.public_paths_compiled):
            logger.debug(f"Public path: {path}")
            return await call_next(request)

        try:
            user_context = await self._authenticate(request)
            request.state.user = user_context
            request.state.is_authenticated = True
            request.state.auth_source = user_context.get('auth_source', 'unknown')
            logger.info(f"User {user_context.get('username')} authenticated via {user_context.get('auth_source')}")
            return await call_next(request)
        except AuthenticationError as e:
            logger.warning(f"Auth failed for {path}: {e}")
            return JSONResponse(status_code=401, content={"detail": str(e)})
        except Exception as e:
            logger.error(f"Auth error for {path}: {e}")
            return JSONResponse(status_code=500, content={"detail": "Authentication error"})

    def _match_path(self, path: str, compiled_patterns: List[Tuple]) -> bool:
        """
        Match path using Starlette route matcher
        """
        for original_pattern, path_regex, path_format, param_convertors in compiled_patterns:
            match = path_regex.match(path)
            if match:
                logger.info(f"Path '{path}' matched pattern '{original_pattern}'")
                return True
        return False

    async def _authenticate(self, request: Request) -> Dict[str, Any]:
        """
        Unified authentication logic (simple and efficient)
        
        1. Internal paths (/api/internal/*) → Basic Auth
        2. Authenticated paths (including /api/auth/me, /api/servers/*, /proxy/*, /api/mcp/*) → JWT or Session Auth
        3. Other paths → Session Auth
        """
        path = request.url.path

        if self._match_path(path, self.internal_paths_compiled):
            user_context = self._try_basic_auth(request)
            if user_context:
                return user_context
            raise AuthenticationError("Basic authentication required")

        if self._match_path(path, self.authenticated_paths_compiled):
            # Try JWT first, then fall back to session auth
            user_context = self._try_jwt_auth(request)
            if user_context:
                return user_context
            user_context = self._try_session_auth(request)
            if user_context:
                return user_context
            raise AuthenticationError("JWT or session authentication required")

        # Default: session Auth
        user_context = self._try_session_auth(request)
        if user_context:
            return user_context
        raise AuthenticationError("Session authentication required")

    def _try_basic_auth(self, request: Request) -> Optional[Dict[str, Any]]:
        """Basic authentication for internal endpoints"""
        try:
            # Get Authorization header
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Basic "):
                return None

            # Decode Basic Auth credentials
            try:
                encoded_credentials = auth_header.split(" ")[1]
                decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
                username, password = decoded_credentials.split(":", 1)
            except (IndexError, ValueError, Exception) as e:
                logger.debug(f"Basic auth decoding failed: {e}")
                return None

            # Verify admin credentials from environment
            admin_user = os.environ.get("ADMIN_USER", "admin")
            admin_password = os.environ.get("ADMIN_PASSWORD")

            if not admin_password:
                logger.error("ADMIN_PASSWORD environment variable not set")
                return None

            if username != admin_user or password != admin_password:
                logger.debug(f"Basic auth failed: invalid credentials for {username}")
                return None
            # Return user context for admin user
            return self._build_user_context(
                username=username,
                groups=['mcp-registry-admin'],
                scopes=['mcp-registry-admin', 'mcp-servers-unrestricted/read', 'mcp-servers-unrestricted/execute'],
                auth_method='basic',
                provider='basic',
                auth_source="basic_auth"
            )

        except Exception as e:
            logger.debug(f"Basic auth failed: {e}")
            return None

    def _try_jwt_auth(self, request: Request) -> Optional[Dict[str, Any]]:
        """JWT token authentication for /api/servers endpoints"""
        try:
            # Get Authorization header
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                logger.debug("Missing or invalid Authorization header for JWT auth")
                return None
            access_token = auth_header.split(" ")[1]
            if not access_token:
                logger.debug("Empty JWT token")
                return None
            # JWT validation parameters from auth_server/server.py
            try:
                unverified_header = jwt.get_unverified_header(access_token)
                kid = unverified_header.get('kid')

                # Check if this is our self-signed token
                if kid and kid != settings.JWT_SELF_SIGNED_KID:
                    logger.debug(f"JWT token has wrong kid: {kid}, expected: {settings.JWT_SELF_SIGNED_KID}")
                    return None
            except Exception as e:
                logger.debug(f"Failed to decode JWT header: {e}")

            # Validate and decode token
            try:
                claims = jwt.decode(
                    access_token,
                    settings.secret_key,
                    algorithms=['HS256'],
                    issuer=settings.JWT_ISSUER,
                    audience=settings.JWT_AUDIENCE,
                    options={
                        "verify_exp": True,
                        "verify_iat": True,
                        "verify_iss": True,
                        "verify_aud": True
                    },
                    leeway=30  # 30 second leeway for clock skew
                )
                logger.info(f"JWT claims: {claims}")
            except jwt.ExpiredSignatureError:
                logger.debug("JWT token has expired")
                return None
            except jwt.InvalidTokenError as e:
                logger.debug(f"Invalid JWT token: {e}")
                return None
            except Exception as e:
                logger.debug(f"JWT validation error: {e}")
                return None

            # Extract user information from claims
            username = claims.get('sub', '')
            if not username:
                logger.debug("JWT token missing 'sub' claim")
                return None

            # Extract scopes from space-separated string
            scope_string = claims.get('scope', '')
            scopes = scope_string.split() if scope_string else []

            # Verify we have at least some scopes
            if not scopes:
                logger.debug("JWT token has no scopes")
                return None
            groups = claims.get('groups', [])
            # Optional: Verify client_id if present
            client_id = claims.get('client_id')
            if client_id and client_id != 'user-generated':
                logger.debug(f"JWT token has unexpected client_id: {client_id}")

            # Log token validation success with additional details
            token_type = claims.get('token_type', 'unknown')
            description = claims.get('description', '')
            logger.info(f"JWT token validated for user: {username}, type: {token_type}, scopes: {scopes}")
            if description:
                logger.debug(f"Token description: {description}")
            user_id = claims.get('user_id')
            # Return user context similar to _try_basic_auth
            return self._build_user_context(
                user_id=user_id,
                username=username,
                groups=groups,
                scopes=scopes,
                auth_method='jwt',
                provider='jwt',
                auth_source="jwt_auth"
            )
        except Exception as e:
            logger.debug(f"JWT auth failed: {e}")
            return None

    def _try_session_auth(self, request: Request) -> Optional[Dict[str, Any]]:
        """Session authentication (original enhanced_auth logic)"""
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

            # Process permissions according to enhanced_auth logic
            if auth_method == 'oauth2':
                scopes = map_cognito_groups_to_scopes(groups)
                logger.info(f"OAuth2 user {username} with groups {groups} mapped to scopes: {scopes}")
                if not groups:
                    logger.warning(f"OAuth2 user {username} has no groups!")
            else:
                # Traditional users dynamically mapped to admin
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
                provider=session_data.get('provider', 'local'),
                auth_source='session_auth',
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

        except SignatureExpired as e:
            logger.warning(f"Session cookie expired: {e}")
            return None
        except BadSignature as e:
            logger.warning(f"Session cookie has invalid signature (likely from different server): {e}")
            return None
        except Exception as e:
            logger.warning(f"Session cookie parse error: {e}")
            return None

    def _build_user_context(self, username: str, groups: list, scopes: list,
                            auth_method: str, provider: str,
                            auth_source: str = None, user_id: str = None) -> Dict[str, Any]:
        """
            Construct the complete user context (from the original enhanced_auth logic).
        """
        ui_permissions = get_ui_permissions_for_user(scopes)
        accessible_servers = get_user_accessible_servers(scopes)
        accessible_services = get_accessible_services_for_user(ui_permissions)
        accessible_agents = get_accessible_agents_for_user(ui_permissions)
        can_modify = user_can_modify_servers(groups, scopes)

        user_context = {
            "user_id": user_id,
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
            'is_admin': user_has_wildcard_access(scopes),
            "auth_source": auth_source,
        }
        logger.debug(f"User context for {username}: {user_context}")
        return user_context


class AuthenticationError(Exception):
    pass
