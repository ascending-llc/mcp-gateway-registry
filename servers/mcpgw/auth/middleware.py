import logging
from typing import Optional, List
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_http_request, get_http_headers
from core.scopes import extract_user_scopes_from_headers

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
            # Compatible with retrieving the range from auth or from the request header.
            user_scopes = await self._extract_user_scopes_for_user()
            #if len(user_scopes) == 0:
            #    user_scopes = await self._extract_user_scopes_for_headers(context)
            await self._store_auth_context(context, user_scopes)
        try:
            result = await call_next(context)
            return result
        except Exception as e:
            logger.error(f"Error processing request {method}: {type(e).__name__}: {e}")
            raise

    async def _extract_user_scopes_for_user(self):
        """
        Extract user's scopes from request.
        """
        user_scopes = []
        request = get_http_request()
        if request.user.is_authenticated:
            user_scopes = request.user.scopes
        logger.debug(f"extract_user_scopes_for_user: {user_scopes}")
        return user_scopes

    async def _extract_user_scopes_for_headers(self, context: MiddlewareContext) -> List[str]:
        """
        Extract user scopes from HTTP headers.
        
        Handles both HTTP and stdio transports gracefully.
        For HTTP transports, uses FastMCP's get_http_headers() helper.
        
        """
        user_scopes = []
        try:
            # Try to get HTTP headers (works even if MCP session not available)
            headers = get_http_headers()
            headers_dict = dict(headers) if hasattr(headers, '__iter__') else {}
            user_scopes = extract_user_scopes_from_headers(headers_dict)
            logger.info(f"_extract_user_scopes_for_headers: {user_scopes}", )
        except Exception as e:
            logger.error(f"Unexpected error extracting user scopes: {type(e).__name__}: {e}", exc_info=True)
        return user_scopes

    async def _store_auth_context(
            self,
            context: MiddlewareContext,
            user_scopes: List[str]
    ) -> None:
        """
        Store authentication context for downstream tools.
        
        Args:
            context: Middleware context
            user_scopes: List of user scopes
        """
        try:
            ctx = context.fastmcp_context
            if not hasattr(ctx, 'user_auth'):
                ctx.user_auth = {}
            ctx.user_auth['scopes'] = user_scopes
            logger.debug(f"Stored {len(user_scopes)} scopes in context")
        except Exception as e:
            logger.warning(f"Could not store auth context: {type(e).__name__}: {e}")
