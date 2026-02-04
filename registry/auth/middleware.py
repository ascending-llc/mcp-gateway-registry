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
from registry.core.telemetry_decorators import AuthMetricsContext

class UnifiedAuthMiddleware(BaseHTTPMiddleware):
    """
    A unified authentication middleware that encapsulates the functionality of `enhanced_auth` and `nginx_proxied_auth`.

    It automatically attempts all authentication methods and stores the results in `request.state`.

    Path Matching Logic:
    --------------------
    1. public_paths_compiled: Paths that are PUBLICLY accessible (no authentication required)
       - These act as EXCEPTIONS to authenticated paths via double-check logic
       - Use specific patterns to carve out public endpoints from broader authenticated patterns
       - Example: "/api/{versions}/mcp/{server_name}/oauth/callback" is public despite matching broader MCP pattern

    How to Define Paths:
    --------------------
    public_paths_compiled:
      - Define SPECIFIC patterns that should be accessible without auth
      - These override authenticated patterns via double-check
      - Use more specific paths to carve out exceptions
      - Examples:
        * "/api/{versions}/mcp/{server_name}/oauth/callback" - Specific OAuth callback (public)
        * "/.well-known/{path:path}" - OAuth discovery endpoints (must be public per RFC)
        * "/health" - Health check endpoint (public)
    """

    def __init__(self, app):
        super().__init__(app)
        # Paths that require authentication (checked before public paths)
        # self.authenticated_paths_compiled = self._compile_patterns([
        #     "/api/auth/me",
        #     "/api/{versions}/servers/{path:path}",
        #     "/api/{versions}/servers",
        #     "/proxy/{path:path}",
        #     "/api/{versions}/mcp/{path:path}",
        #     "/api/search/{path:path}",
        # ])
        self.public_paths_compiled = self._compile_patterns([
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/static/{path:path}",
            "/redirect",
            "/redirect/{provider}",
            "/api/auth/providers",
            "/api/auth/config",
            f"/api/{settings.API_VERSION}/mcp/{{server_name}}/oauth/callback",  # OAuth callback is public
            "/.well-known/{path:path}",  # OAuth discovery endpoints must be public
        ])
        
        # =====================================================================
        # INTERNAL PATHS (Admin/Internal - Require Basic Auth)
        # =====================================================================
        # Define patterns for internal/admin endpoints that use Basic authentication.
        self.internal_paths_compiled = self._compile_patterns([
            "/api/internal/{path:path}",                   # Internal admin endpoints
        ])
        logger.info(
            f"Auth middleware initialized with Starlette routing: "
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
        if self._match_path(path, self.public_paths_compiled):
            logger.debug(f"Public path: {path}")
            return await call_next(request)
        else:
            logger.debug(f"Authenticated path: {path}")
            # Continue to authentication logic below

        # Use context manager for clean metrics tracking
        async with AuthMetricsContext() as auth_ctx:
            try:
                user_context = await self._authenticate(request)
                request.state.user = user_context
                request.state.is_authenticated = True
                auth_source = user_context.get("auth_source", "unknown")
                request.state.auth_source = auth_source

                # Update metrics context with auth result
                auth_ctx.set_mechanism(auth_source)
                auth_ctx.set_success(True)

                logger.info(f"User {user_context.get('username')} authenticated via {auth_source}")
                return await call_next(request)

            except AuthenticationError as e:
                auth_ctx.set_success(False)
                logger.warning(f"Auth failed for {path}: {e}")

                # Add WWW-Authenticate header for MCP OAuth discovery
                # Extract server name from path for MCP proxy requests
                server_name = None
                if path.startswith("/proxy/"):
                    server_name = path.split("/")[2] if len(path.split("/")) > 2 else None

                headers = {"Connection": "close"}
                if server_name:
                    # For MCP proxy paths, RFC 9728 (OAuth 2.0 Protected Resource Metadata)
                    registry_url = settings.registry_client_url.rstrip("/")
                    oauth_discovery = f"{registry_url}/.well-known/oauth-protected-resource/proxy/{server_name}"
                    headers["WWW-Authenticate"] = f'Bearer realm="mcp-registry", resource_metadata="{oauth_discovery}"'
                else:
                    # For other authenticated paths, use general OAuth discovery
                    headers["WWW-Authenticate"] = 'Bearer realm="mcp-registry"'

                return JSONResponse(status_code=401, content={"detail": str(e)}, headers=headers)

            except Exception as e:
                auth_ctx.set_success(False)
                logger.error(f"Auth error for {path}: {e}")
                return JSONResponse(status_code=500, content={"detail": "Authentication error"})

    def _match_path(self, path: str, compiled_patterns: List[Tuple]) -> bool:
        """
        Match path using Starlette route matcher
        """
        for original_pattern, path_regex, path_format, param_convertors in compiled_patterns:
            match = path_regex.match(path)
            if match:
                logger.debug(f"Path '{path}' matched pattern '{original_pattern}'")
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
        # Try JWT first, then fall back to session auth
        user_context = self._try_jwt_auth(request)
        if user_context:
            return user_context
        user_context = await self._try_session_auth(request)
        if user_context:
            return user_context
        raise AuthenticationError("JWT or session authentication required")

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
            if not auth_header:
                logger.debug("Missing Authorization header for JWT auth")
                return None
                        
            access_token = auth_header.split(" ")[1]
            if not access_token:
                logger.debug("Empty JWT token after split")
                return None
        
            # JWT validation parameters from auth_server/server.py
            # Extract kid from header first
            kid = None
            try:
                unverified_header = jwt.get_unverified_header(access_token)
                kid = unverified_header.get('kid')

                # Check if this is our self-signed token
                if kid and kid != settings.JWT_SELF_SIGNED_KID:
                    logger.debug(f"JWT token has wrong kid: {kid}, expected: {settings.JWT_SELF_SIGNED_KID}")
                    return None
            except Exception as e:
                logger.debug(f"Failed to decode JWT header: {e}")
                return None

            # Validate and decode token
            try:
                # For self-signed tokens (kid='mcp-self-signed'), skip audience validation
                # because the audience is now the resource URL (RFC 8707 Resource Indicators)
                # which varies per endpoint (/proxy/mcpgw, /proxy/server2, etc.)
                # Issuer validation provides sufficient security for self-signed tokens
                is_self_signed = (kid == settings.JWT_SELF_SIGNED_KID)
                
                decode_options = {
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "verify_aud": not is_self_signed  # Skip aud check for self-signed tokens
                }
                
                decode_kwargs = {
                    "algorithms": ['HS256'],
                    "issuer": settings.JWT_ISSUER,
                    "options": decode_options,
                    "leeway": 30  # 30 second leeway for clock skew
                }
                
                # Only validate audience for provider tokens (not self-signed)
                if not is_self_signed:
                    decode_kwargs["audience"] = settings.JWT_AUDIENCE
                else:
                    logger.info("Skipping audience validation for self-signed token (RFC 8707 Resource Indicators)")
                
                claims = jwt.decode(
                    access_token,
                    settings.secret_key,
                    **decode_kwargs
                )
                logger.info(f"JWT claims validated: sub={claims.get('sub')}, aud={claims.get('aud')}, scope={claims.get('scope')}")
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

            # Extract groups first
            groups = claims.get('groups', [])
            
            # Extract scopes from space-separated string
            scope_string = claims.get('scope', '')
            scopes = scope_string.split() if scope_string else []
            
            # If no scopes but has groups, map groups to scopes
            if not scopes and groups:
                from auth_server.utils.security_mask import map_groups_to_scopes
                from auth_server.core.config import settings as auth_settings
                scopes = map_groups_to_scopes(groups, auth_settings.scopes_config)
                logger.info(f"Mapped JWT groups {groups} to scopes: {scopes}")
            
            # Verify we have at least some scopes
            if not scopes:
                logger.debug(f"JWT token has no scopes and groups mapping failed. Groups: {groups}")
                return None
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
            logger.debug(f"jwt enhencement user id {user_id}")
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

    async def _try_session_auth(self, request: Request) -> Optional[Dict[str, Any]]:
        """JWT-based session authentication from httpOnly cookie with auto-refresh"""
        try:
            session_cookie = request.cookies.get(settings.session_cookie_name)
            if not session_cookie:
                return None
            
            # Try to verify JWT access token
            from registry.utils.crypto_utils import verify_access_token, verify_refresh_token
            claims = verify_access_token(session_cookie)
            
            if claims:
                # Valid access token - extract user info and build context
                username = claims.get('sub')
                user_id = claims.get('user_id')
                groups = claims.get('groups', [])
                auth_method = claims.get('auth_method', 'traditional')
                
                # Extract scopes from JWT (space-separated string)
                scope_string = claims.get('scope', '')
                scopes = scope_string.split() if scope_string else []
                
                # If no scopes but has groups, map groups to scopes
                if not scopes and groups:
                    from auth_server.utils.security_mask import map_groups_to_scopes
                    from auth_server.core.config import settings as auth_settings
                    scopes = map_groups_to_scopes(groups, auth_settings.scopes_config)
                    logger.info(f"Mapped session groups {groups} to scopes: {scopes}")
                
                logger.debug(f"JWT access token valid for user {username} (user_id: {user_id})")
                
                return self._build_user_context(
                    username=username,
                    groups=groups,
                    scopes=scopes,
                    auth_method=auth_method,
                    provider=claims.get('provider', 'local'),
                    auth_source='jwt_session_auth',
                    user_id=user_id
                )
            
            # Access token invalid/expired - try refresh token
            logger.debug("Access token expired or invalid, attempting refresh")
            refresh_token = request.cookies.get("jarvis_registry_refresh")
            
            if not refresh_token:
                logger.debug("No refresh token available")
                return None
            
            # Verify refresh token
            refresh_claims = verify_refresh_token(refresh_token)
            if not refresh_claims:
                logger.debug("Refresh token invalid or expired")
                return None
            
            # Refresh token valid - extract user info from refresh token claims
            user_id = refresh_claims.get('user_id')
            username = refresh_claims.get('sub')
            auth_method = refresh_claims.get('auth_method')
            provider = refresh_claims.get('provider')
            
            # Extract groups and scopes from refresh token
            groups = refresh_claims.get('groups', [])
            scope_string = refresh_claims.get('scope', '')
            scopes = scope_string.split() if scope_string else []
            
            # If no scopes but has groups, map groups to scopes
            if not scopes and groups:
                from auth_server.utils.security_mask import map_groups_to_scopes
                from auth_server.core.config import settings as auth_settings
                scopes = map_groups_to_scopes(groups, auth_settings.scopes_config)
                logger.info(f"Mapped refresh token groups {groups} to scopes: {scopes}")
            
            role = refresh_claims.get('role', 'user')
            email = refresh_claims.get('email', f"{username}@local")
            
            logger.info(f"Refresh token valid for user {username} ({auth_method}), generating new access token")
            logger.debug(f"User groups from refresh token: {groups}, scopes: {scopes}")
            
            # Validate that we have the required information
            if not scopes:
                logger.warning(f"Refresh token for user {username} has no scopes (groups: {groups}), cannot refresh")
                return None
            
            # Generate new access token using information from refresh token
            from registry.utils.crypto_utils import generate_access_token
            try:
                new_access_token = generate_access_token(
                    user_id=user_id,
                    username=username,
                    email=email,
                    groups=groups,
                    scopes=scopes,
                    role=role,
                    auth_method=auth_method,
                    provider=provider
                )
                
                # Store new access token in request state for response modification
                request.state.new_access_token = new_access_token
                
                logger.info(f"Successfully refreshed access token for user {username}")
                
                return self._build_user_context(
                    username=username,
                    groups=groups,
                    scopes=scopes,
                    auth_method=auth_method,
                    provider=provider,
                    auth_source='jwt_session_auth_refreshed',
                    user_id=user_id
                )
            except Exception as e:
                logger.error(f"Error generating new access token during refresh: {e}")
                return None

        except Exception as e:
            logger.debug(f"JWT session auth failed: {e}")
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
