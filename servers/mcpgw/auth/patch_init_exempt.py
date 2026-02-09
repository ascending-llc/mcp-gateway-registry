"""
Allow MCP 'initialize' requests without a JWT token in FastMCP 2.14.5.

Problem:
  FastMCP's RequireAuthMiddleware is hardcoded in create_streamable_http_app()
  and blocks ALL unauthenticated requests, including 'initialize'. The MCP spec
  expects 'initialize' to be accessible without auth so clients can discover
  server capabilities.

Solution:
  Monkey-patch fastmcp.server.http.RequireAuthMiddleware BEFORE creating the
  FastMCP server. This replaces it with a version that peeks at the JSON-RPC
  body and lets 'initialize' through without a Bearer token.

Usage:
    # IMPORTANT: call patch_init_exempt() BEFORE creating your FastMCP server

    from init_exempt_jwt import patch_init_exempt
    patch_init_exempt()

    from fastmcp import FastMCP
    from fastmcp.server.auth.providers.jwt import JWTVerifier

    verifier = JWTVerifier(
        jwks_uri="https://your-idp/.well-known/jwks.json",
        issuer="https://your-idp",
        audience="your-mcp-server",
    )

    mcp = FastMCP("My Server", auth=verifier)
    mcp.run(transport="streamable-http")
"""

from __future__ import annotations

import json
import logging

from starlette.types import Receive, Scope, Send

logger = logging.getLogger(__name__)

# MCP JSON-RPC methods that should be allowed without authentication (POST)
UNAUTHENTICATED_METHODS = frozenset(
    {
        "initialize",
        "ping",
        "notifications/initialized",
    }
)

# HTTP methods that are transport-level and should bypass auth entirely.
#   GET  → SSE listener (client opens long-lived connection for server→client msgs)
#   DELETE → session teardown
# These are MCP transport lifecycle operations, not tool/resource execution.
UNAUTHENTICATED_HTTP_METHODS = frozenset({"GET", "DELETE"})


def patch_init_exempt():
    """Monkey-patch FastMCP's RequireAuthMiddleware to exempt MCP lifecycle requests.

    Exempted from auth:
      - GET   /mcp  → SSE listener stream (transport lifecycle)
      - DELETE /mcp → session teardown (transport lifecycle)
      - POST  /mcp  → only for JSON-RPC methods in UNAUTHENTICATED_METHODS
                       (initialize, ping, notifications/initialized)

    All other POST requests (tools/list, tools/call, resources/*, etc.)
    still require a valid JWT Bearer token.

    Call this BEFORE importing/creating your FastMCP server.
    Safe to call multiple times (idempotent).
    """
    import fastmcp.server.http as http_module
    from fastmcp.server.auth.middleware import RequireAuthMiddleware as OriginalRequireAuth

    # Don't patch twice
    if getattr(http_module.RequireAuthMiddleware, "_init_exempt_patched", False):
        logger.debug("RequireAuthMiddleware already patched, skipping")
        return

    class InitExemptRequireAuthMiddleware(OriginalRequireAuth):
        """RequireAuthMiddleware that exempts MCP transport lifecycle from auth.

        In streamable-http, all MCP traffic hits the same route:
          - GET    → SSE listener (server→client event stream)
          - POST   → JSON-RPC requests/notifications
          - DELETE  → session teardown

        This subclass:
          1. Passes GET and DELETE through without auth (transport lifecycle)
          2. For POST, buffers the body, inspects the JSON-RPC method, and
             exempts handshake methods (initialize, ping, notifications/*)
          3. Everything else goes through normal JWT verification
        """

        _init_exempt_patched = True

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                await super().__call__(scope, receive, send)
                return

            # --- Check HTTP method ---
            http_method = scope.get("method", "").upper()

            # GET (SSE listener) and DELETE (session teardown) are transport-
            # level operations — let them through without auth.
            if http_method in UNAUTHENTICATED_HTTP_METHODS:
                logger.debug(
                    "Allowing unauthenticated %s request (transport lifecycle)",
                    http_method,
                )
                await self.app(scope, receive, send)
                return

            # --- For POST: inspect JSON-RPC body ---
            body_parts: list[bytes] = []
            body_complete = False

            async def buffering_receive() -> dict:
                nonlocal body_complete
                message = await receive()
                if message["type"] == "http.request":
                    body_parts.append(message.get("body", b""))
                    if not message.get("more_body", False):
                        body_complete = True
                return message

            # Read all body chunks
            while not body_complete:
                await buffering_receive()

            full_body = b"".join(body_parts)

            # Check if this is an exempt JSON-RPC method
            is_exempt = False
            try:
                payload = json.loads(full_body)
                method = payload.get("method") if isinstance(payload, dict) else None
                if method in UNAUTHENTICATED_METHODS:
                    is_exempt = True
                    logger.debug("Allowing unauthenticated MCP '%s' request", method)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

            # Create a replay receive so downstream can re-read the body
            body_sent = False

            async def replay_receive() -> dict:
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {
                        "type": "http.request",
                        "body": full_body,
                        "more_body": False,
                    }
                # After body is replayed, pass through for disconnect events etc.
                return await receive()

            if is_exempt:
                await self.app(scope, replay_receive, send)
            else:
                await super().__call__(scope, replay_receive, send)

    # Apply the patch
    http_module.RequireAuthMiddleware = InitExemptRequireAuthMiddleware  # type: ignore
    logger.info(
        "Patched RequireAuthMiddleware to exempt MCP lifecycle (GET, DELETE, and %s)",
        ", ".join(sorted(UNAUTHENTICATED_METHODS)),
    )
