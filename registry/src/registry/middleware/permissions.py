import asyncio
import logging
import re
from collections.abc import Iterable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import compile_path

from registry.auth.dependencies import load_scopes_config, map_cognito_groups_to_scopes
from registry.core.config import settings
from registry.utils.scopes_cache import ScopesConfigCache

logger = logging.getLogger(__name__)

_SCOPES_CACHE = ScopesConfigCache()


def _normalize_path(path: str) -> list[str]:
    """
    Normalize request paths to match scopes.yml endpoints.
    Returns candidate paths for matching (original + stripped prefixes).
    Examples:
      - /api/v1/servers -> /api/v1/servers, /servers
      - /api/servers -> /api/servers, /servers
    """
    candidates = [path]
    api_prefix = f"/api/{settings.API_VERSION}/"
    if path.startswith(api_prefix):
        candidates.append(path[len(api_prefix) - 1 :])
    if path.startswith("/api/"):
        candidates.append(path[len("/api") :])
    return list(dict.fromkeys(candidates))  # preserve order, dedupe


def _normalize_endpoint_pattern(endpoint: str) -> str:
    """
    Normalize scopes.yml endpoint patterns to match FastAPI paths.
    - Replace `{path}` with `{path:path}` to allow slashes.
    """
    endpoint = endpoint.strip()
    endpoint = re.sub(r"\{path\}", "{path:path}", endpoint)
    return endpoint


def _parse_methods(method_value: str) -> set[str] | None:
    """
    Parse method field from scopes.yml.
    Returns:
      - None for wildcard "*"
      - set of methods for comma-separated lists
      - empty set for empty/invalid input
    """
    if not method_value:
        return set()
    method_value = method_value.strip()
    if method_value == "*":
        return None
    parts = [m.strip().upper() for m in method_value.split(",") if m.strip()]
    return set(parts)


class ScopePermissionMiddleware(BaseHTTPMiddleware):
    """
    Enforce endpoint/method permissions based on scopes.yml.

    If an endpoint pattern matches the request path, user must have at least
    one scope whose rules intersect (method + endpoint).

    Notes:
      - Rules are loaded lazily on the first authenticated request so Redis
        has time to initialize during lifespan/startup.
      - Path matching is done against normalized candidates so both /api/*
        and /api/{version} prefixes work.
    """

    def __init__(self, app):
        super().__init__(app)
        self._rules: list[dict[str, Any]] = []
        self._loaded = False
        self._load_lock = asyncio.Lock()

    def _load_rules(self) -> None:
        """
        Load and compile rules from scopes.yml into in-memory structures.
        Should only be called via _ensure_loaded to avoid duplicate loads.
        """
        config = _SCOPES_CACHE.get_or_load(load_scopes_config) or {}
        rules = []

        for scope_name, scope_rules in config.items():
            if scope_name == "group_mappings":
                continue
            if not isinstance(scope_rules, list):
                continue

            for rule in scope_rules:
                if not isinstance(rule, dict):
                    continue
                endpoint = rule.get("endpoint", "").strip()
                method = rule.get("method", "").strip().upper()

                if not endpoint:
                    continue

                if endpoint == "*":
                    compiled = None
                else:
                    pattern = _normalize_endpoint_pattern(endpoint)
                    compiled = compile_path(pattern)[0]

                methods = _parse_methods(method)
                rules.append(
                    {
                        "scope": scope_name,
                        "methods": methods,  # None = wildcard
                        "endpoint": endpoint,
                        "compiled": compiled,  # None = wildcard
                    }
                )

        self._rules = rules
        self._loaded = True
        logger.info("ScopePermissionMiddleware loaded %d rules", len(rules))

    async def _ensure_loaded(self) -> None:
        """
        Ensure rules are loaded exactly once, with a lock to avoid
        concurrent reloads under load.
        """
        if self._loaded:
            return
        async with self._load_lock:
            if not self._loaded:
                self._load_rules()

    def _effective_scopes(self, user_context: dict[str, Any]) -> list[str]:
        """
        Determine scopes for the request.
        Prefer explicit scopes on the JWT; otherwise map groups to scopes.
        """
        scopes = user_context.get("scopes") or []
        if scopes:
            return scopes

        groups = user_context.get("groups") or []
        if groups:
            return map_cognito_groups_to_scopes(groups)

        return []

    def _rule_matches(self, rule: dict[str, Any], path: str, method: str) -> bool:
        """
        Check if a rule matches by both method and endpoint.
        """
        # method match
        methods = rule["methods"]
        if methods is not None and method not in methods:
            return False

        # endpoint match
        return self._endpoint_matches(rule, path)

    def _endpoint_matches(self, rule: dict[str, Any], path: str) -> bool:
        """
        Check if the path matches the rule's endpoint pattern.
        """
        if rule["compiled"] is None:
            return True
        return rule["compiled"].match(path) is not None

    def _has_permission(self, user_scopes: Iterable[str], path: str, method: str) -> bool:
        """
        Determine if any scope grants access to the given path+method.
        """
        # superuser compatibility
        if "registry-admin" in user_scopes:
            return True

        for rule in self._rules:
            if rule["scope"] not in user_scopes:
                continue
            if self._rule_matches(rule, path, method):
                return True
        return False

    def _path_is_guarded(self, path: str, method: str) -> bool:
        """
        Only enforce when the path matches at least one rule, regardless
        of method. This prevents method-mismatch from bypassing checks.
        """
        return any(self._endpoint_matches(rule, path) for rule in self._rules)

    async def dispatch(self, request: Request, call_next):
        """
        Enforce scope permissions for authenticated requests.
        Public (unauthenticated) requests pass through.
        """
        # If auth middleware didn't set user, allow through (public routes).
        if not getattr(request.state, "is_authenticated", False):
            return await call_next(request)

        await self._ensure_loaded()

        method = request.method.upper()
        candidate_paths = _normalize_path(request.url.path)
        logger.debug(f"candidate_paths: {candidate_paths}, method: {method}")

        # Check if any rule applies to this path; if not, allow through.
        if not any(self._path_is_guarded(p, method) for p in candidate_paths):
            return await call_next(request)

        user_context = getattr(request.state, "user", {}) or {}
        user_scopes = self._effective_scopes(user_context)

        if not user_scopes:
            return JSONResponse(status_code=403, content={"detail": "Insufficient permissions"})

        if any(self._has_permission(user_scopes, p, method) for p in candidate_paths):
            return await call_next(request)

        return JSONResponse(status_code=403, content={"detail": "Insufficient permissions"})
