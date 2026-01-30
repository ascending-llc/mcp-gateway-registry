import logging
from typing import Optional, List
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_http_request, get_http_headers
from fastapi import HTTPException
from packages.models import IUser

logger = logging.getLogger(__name__)


class AuthMiddleware(Middleware):
    """
    Authentication and authorization middleware for MCP Gateway.
    """

    def __init__(
            self,
            allowed_methods_without_auth: Optional[List[str]] = None
    ):
        """
        Initialize the authentication middleware.
        
        Args:
            allowed_methods_without_auth: List of MCP methods that don't require auth
        """
        super().__init__()
        self.allowed_methods_without_auth = allowed_methods_without_auth or [
            "initialize",
            "ping",
            "notifications/initialized"
        ]

    async def on_request(self, context: MiddlewareContext, call_next):
        """
        Process MCP requests with authentication.
        """
        method = context.method
        logger.debug(f"MCP request: {method}")
        if method not in self.allowed_methods_without_auth:
            # Extract full user context from request
            user_context = await self._extract_user_context()
            await self._store_auth_context(context, user_context)
        try:
            result = await call_next(context)
            return result
        except Exception as e:
            logger.error(f"Error processing request {method}: {type(e).__name__}: {e}")
            raise

    async def _extract_user_context(self):
        """
        Extract full user context from FastMCP session token claims.
        
        Returns:
            Dictionary with user authentication context (JWT claims)
            
        Raises:
            ValueError: If user_id is missing and cannot be resolved from database
        """
        user_context = {}
        
        # Extract user claims from FastMCP request.user.access_token.claims
        try:
            request = get_http_request()
            if request.user.is_authenticated:
                # Extract claims from access_token
                if hasattr(request.user, "access_token") and hasattr(request.user.access_token, "claims"):
                    # Get all claims from the access token
                    user_context = dict(request.user.access_token.claims)                    
                    logger.debug(f"Extracted user context from access token claims: "
                               f"sub={user_context.get('sub')}, "
                               f"user_id={user_context.get('user_id')}, "
                               f"scopes={len(user_context.get('scopes', []))}, "
                               f"groups={len(user_context.get('groups', []))}")
                    
                    # TODO: It's computing expensive however third party OAuth tokens may not have user_id in our application
                    # We should probably think about caching it by session id in future
                    if not user_context.get('user_id'):
                        sub = user_context.get('sub')
                        if not sub:
                            raise HTTPException(
                                status_code=401,
                                detail="JWT claims missing both 'user_id' and 'sub' - cannot authenticate user"
                            )
                        
                        logger.debug(f"user_id missing in JWT claims, attempting MongoDB lookup for sub: {sub}")
                        user = await IUser.find_one({"email": sub})
                        if not user:
                            raise HTTPException(
                                status_code=401,
                                detail=f"User not found in database for email/sub: {sub}"
                            )
                        user_context['user_id'] = str(user.id)
                        logger.debug(f"✓ Resolved user_id from MongoDB: {user_context['user_id']} for sub: {sub}")
                else:
                    raise HTTPException(
                        status_code=401,
                        detail="Authenticated request missing access_token.claims"
                    )
        except HTTPException:
            # Re-raise authentication/authorization errors (fail-fast)
            raise
        except Exception as e:
            logger.error(f"Failed to extract user context: {type(e).__name__}: {e}")
            raise HTTPException(
                status_code=401,
                detail=f"Authentication failed: {str(e)}"
            )
        
        return user_context

    async def _store_auth_context(
            self,
            context: MiddlewareContext,
            user_context: dict
    ) -> None:
        """
        Store authentication context for downstream tools.
        
        Args:
            context: Middleware context
            user_context: Dictionary with user authentication context
        """
        try:
            ctx = context.fastmcp_context
            if not hasattr(ctx, 'user_auth'):
                ctx.user_auth = {}
            
            # Store full user context
            ctx.user_auth.update(user_context)
            
            logger.debug(f"Stored user context: username={user_context.get('username')}, "
                        f"scopes={len(user_context.get('scopes', []))}, "
                        f"groups={len(user_context.get('groups', []))}")
        except Exception as e:
            logger.warning(f"Could not store auth context: {type(e).__name__}: {e}")
