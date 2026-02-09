import logging

from fastapi import HTTPException
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware, MiddlewareContext

from config import settings

logger = logging.getLogger(__name__)


class HeaderSwapMiddleware(Middleware):
    """
    Middleware to swap custom authentication header to Authorization header.

    This allows FastMCP to process tokens from custom headers like X-Jarvis-Auth.
    Must be added BEFORE AuthMiddleware in the middleware stack.

    Usage:
        mcp.add_middleware(HeaderSwapMiddleware(custom_header="X-Jarvis-Auth"))
        mcp.add_middleware(AuthMiddleware())
    """

    def __init__(self, custom_header: str | None = None):
        """
        Initialize the header swap middleware.

        Args:
            custom_header: Header name to swap to Authorization (default: settings.INTERNAL_AUTH_HEADER)
        """
        super().__init__()
        self.custom_header = (custom_header or settings.INTERNAL_AUTH_HEADER).lower()
        logger.debug(f"HeaderSwapMiddleware initialized: {self.custom_header} -> Authorization")

    async def on_request(self, context: MiddlewareContext, call_next):
        """
        Swap custom header to Authorization before FastMCP processes the request.
        """
        try:
            request = get_http_request()
            headers = dict(request.headers)

            auth_header = "authorization"

            # Check if custom header exists
            if self.custom_header in headers:
                # Preserve original Authorization header if it exists
                if auth_header in headers:
                    headers["x-original-authorization"] = headers[auth_header]
                    logger.debug("Preserved original Authorization -> X-Original-Authorization")

                # Move custom header to Authorization
                headers[auth_header] = headers[self.custom_header]
                logger.debug(f"Swapped {self.custom_header} -> Authorization")

                # Update request headers
                request._headers = headers

        except Exception as e:
            logger.warning(f"Failed to swap auth headers: {e}")

        return await call_next(context)


class AuthMiddleware(Middleware):
    """
    Authentication and authorization middleware for MCP Gateway.

    Extracts user context from authenticated requests and stores it for downstream tools.
    Use HeaderSwapMiddleware before this if using custom auth headers.
    """

    def __init__(self, allowed_methods_without_auth: list[str] | None = None):
        """
        Initialize the authentication middleware.

        Args:
            allowed_methods_without_auth: List of MCP methods that don't require auth
        """
        super().__init__()
        self.allowed_methods_without_auth = allowed_methods_without_auth or [
            "initialize",
            "ping",
            "notifications/initialized",
        ]

    async def on_request(self, context: MiddlewareContext, call_next):
        """
        Process MCP requests with authentication.

        Extracts user context from authenticated requests and makes it available
        to downstream tools via context.fastmcp_context.user_auth.
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
                    logger.debug(
                        f"Extracted user context from access token claims: "
                        f"sub={user_context.get('sub')}, "
                        f"user_id={user_context.get('user_id')}, "
                        f"scopes={len(user_context.get('scopes', []))}, "
                        f"groups={len(user_context.get('groups', []))}"
                    )

                    if not user_context.get("user_id"):
                        x_user_id = request.headers.get("x-user-id")
                        if x_user_id:
                            user_context["user_id"] = x_user_id
                            logger.debug(f"Extracted user_id from x-user-id header: {x_user_id}")
                        else:
                            logger.error("user_id missing in JWT claims and x-user-id header")
                            raise HTTPException(
                                status_code=401, detail="Invalid token: missing user_id (Registry enrichment failed)"
                            )
                else:
                    raise HTTPException(status_code=401, detail="Authenticated request missing access_token.claims")
        except HTTPException:
            # Re-raise authentication/authorization errors (fail-fast)
            raise
        except Exception as e:
            logger.error(f"Failed to extract user context: {type(e).__name__}: {e}")
            raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

        return user_context

    async def _store_auth_context(self, context: MiddlewareContext, user_context: dict) -> None:
        """
        Store authentication context for downstream tools.

        Args:
            context: Middleware context
            user_context: Dictionary with user authentication context
        """
        try:
            ctx = context.fastmcp_context
            if not hasattr(ctx, "user_auth"):
                ctx.user_auth = {}

            # Store full user context
            ctx.user_auth.update(user_context)

            logger.debug(
                f"Stored user context: username={user_context.get('username')}, "
                f"scopes={len(user_context.get('scopes', []))}, "
                f"groups={len(user_context.get('groups', []))}"
            )
        except Exception as e:
            logger.warning(f"Could not store auth context: {type(e).__name__}: {e}")
