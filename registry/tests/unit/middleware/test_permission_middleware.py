from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from registry.middleware.permissions import ScopePermissionMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/servers")
    def list_servers():
        return {"servers": []}

    @app.post("/agents/register")
    def register_agent():
        return {"ok": True}

    @app.get("/servers/{server_id}")
    def get_server(server_id: str):
        return {"id": server_id}

    @app.get("/agents/{path:path}")
    def get_agent(path: str):
        return {"path": path}

    @app.put("/permissions/{resource_type}/{resource_id}")
    def update_permissions(resource_type: str, resource_id: str):
        return {"resource_type": resource_type, "resource_id": resource_id}

    return app


def _auth_middleware_factory(user_context: dict[str, Any]):
    class _AuthMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                scope.setdefault("state", {})
                scope["state"]["user"] = user_context
                scope["state"]["is_authenticated"] = True
            await self.app(scope, receive, send)

    return _AuthMiddleware


@pytest.mark.unit
class TestScopePermissionMiddleware:
    def test_allows_when_rule_matches_scope(self, monkeypatch):
        """Allows access when scope + endpoint + method match."""
        from registry.middleware import permissions as perms

        def _mock_config():
            return {
                "group_mappings": {"jarvis-register-user": ["servers-read"]},
                "servers-read": [
                    {"action": "list_servers", "method": "GET", "endpoint": "/servers"},
                ],
            }

        monkeypatch.setattr(perms, "_SCOPES_CACHE", perms.ScopesConfigCache(redis_key="test:scopes"))
        monkeypatch.setattr(perms, "load_scopes_config", _mock_config)

        app = _build_app()
        app.add_middleware(ScopePermissionMiddleware)
        app.add_middleware(_auth_middleware_factory({"scopes": ["servers-read"]}))

        client = TestClient(app)
        # Matching scope + endpoint + method allows access.
        resp = client.get("/servers")
        assert resp.status_code == 200

    def test_denies_when_no_scope_match(self, monkeypatch):
        """Denies access when user lacks matching scope."""
        from registry.middleware import permissions as perms

        def _mock_config():
            return {
                "servers-read": [
                    {"action": "list_servers", "method": "GET", "endpoint": "/servers"},
                ],
            }

        monkeypatch.setattr(perms, "_SCOPES_CACHE", perms.ScopesConfigCache(redis_key="test:scopes"))
        monkeypatch.setattr(perms, "load_scopes_config", _mock_config)

        app = _build_app()
        app.add_middleware(ScopePermissionMiddleware)
        app.add_middleware(_auth_middleware_factory({"scopes": ["agents-read"]}))

        client = TestClient(app)
        # Scope does not match rule -> 403.
        resp = client.get("/servers")
        assert resp.status_code == 403

    def test_denies_when_method_mismatch(self, monkeypatch):
        """Denies access when HTTP method does not match rule."""
        from registry.middleware import permissions as perms

        def _mock_config():
            return {
                "servers-read": [
                    {"action": "list_servers", "method": "GET", "endpoint": "/servers"},
                ],
            }

        monkeypatch.setattr(perms, "_SCOPES_CACHE", perms.ScopesConfigCache(redis_key="test:scopes"))
        monkeypatch.setattr(perms, "load_scopes_config", _mock_config)

        app = _build_app()
        app.add_middleware(ScopePermissionMiddleware)
        app.add_middleware(_auth_middleware_factory({"scopes": ["servers-read"]}))

        client = TestClient(app)
        # Method mismatch should be denied.
        resp = client.post("/servers")
        assert resp.status_code == 403

    def test_matches_path_param(self, monkeypatch):
        """Matches simple path parameters like /servers/{server_id}."""
        from registry.middleware import permissions as perms

        def _mock_config():
            return {
                "servers-read": [
                    {"action": "get_server", "method": "GET", "endpoint": "/servers/{server_id}"},
                ],
            }

        monkeypatch.setattr(perms, "_SCOPES_CACHE", perms.ScopesConfigCache(redis_key="test:scopes"))
        monkeypatch.setattr(perms, "load_scopes_config", _mock_config)

        app = _build_app()
        app.add_middleware(ScopePermissionMiddleware)
        app.add_middleware(_auth_middleware_factory({"scopes": ["servers-read"]}))

        client = TestClient(app)
        # Path params should compile and match.
        resp = client.get("/servers/abc123")
        assert resp.status_code == 200

    def test_matches_path_wildcard(self, monkeypatch):
        """Matches wildcard {path} for nested agent paths."""
        from registry.middleware import permissions as perms

        def _mock_config():
            return {
                "agents-read": [
                    {"action": "get_agent", "method": "GET", "endpoint": "/agents/{path}"},
                ],
            }

        monkeypatch.setattr(perms, "_SCOPES_CACHE", perms.ScopesConfigCache(redis_key="test:scopes"))
        monkeypatch.setattr(perms, "load_scopes_config", _mock_config)

        app = _build_app()
        app.add_middleware(ScopePermissionMiddleware)
        app.add_middleware(_auth_middleware_factory({"scopes": ["agents-read"]}))

        client = TestClient(app)
        # {path} should match nested paths.
        resp = client.get("/agents/foo/bar")
        assert resp.status_code == 200

    def test_allows_when_endpoint_wildcard(self, monkeypatch):
        """Allows access when endpoint is wildcard '*'."""
        from registry.middleware import permissions as perms

        def _mock_config():
            return {
                "servers-read": [
                    {"action": "all_servers", "method": "GET", "endpoint": "*"},
                ],
            }

        monkeypatch.setattr(perms, "_SCOPES_CACHE", perms.ScopesConfigCache(redis_key="test:scopes"))
        monkeypatch.setattr(perms, "load_scopes_config", _mock_config)

        app = _build_app()
        app.add_middleware(ScopePermissionMiddleware)
        app.add_middleware(_auth_middleware_factory({"scopes": ["servers-read"]}))

        client = TestClient(app)
        # Endpoint wildcard allows all endpoints for the method.
        resp = client.get("/servers")
        assert resp.status_code == 200

    def test_allows_when_method_wildcard(self, monkeypatch):
        """Allows access when method is wildcard '*'."""
        from registry.middleware import permissions as perms

        def _mock_config():
            return {
                "agents-write": [
                    {"action": "all_agents", "method": "*", "endpoint": "/agents/register"},
                ],
            }

        monkeypatch.setattr(perms, "_SCOPES_CACHE", perms.ScopesConfigCache(redis_key="test:scopes"))
        monkeypatch.setattr(perms, "load_scopes_config", _mock_config)

        app = _build_app()
        app.add_middleware(ScopePermissionMiddleware)
        app.add_middleware(_auth_middleware_factory({"scopes": ["agents-write"]}))

        client = TestClient(app)
        # Method wildcard allows any HTTP verb for the endpoint.
        resp = client.post("/agents/register")
        assert resp.status_code == 200

    def test_allows_share_server_permissions(self, monkeypatch):
        """Allows sharing MCP server ACL via servers-share scope."""
        from registry.middleware import permissions as perms

        def _mock_config():
            return {
                "servers-share": [
                    {"action": "share_service", "method": "PUT", "endpoint": "/permissions/mcpServer/{resource_id}"},
                ],
            }

        monkeypatch.setattr(perms, "_SCOPES_CACHE", perms.ScopesConfigCache(redis_key="test:scopes"))
        monkeypatch.setattr(perms, "load_scopes_config", _mock_config)

        app = _build_app()
        app.add_middleware(ScopePermissionMiddleware)
        app.add_middleware(_auth_middleware_factory({"scopes": ["servers-share"]}))

        client = TestClient(app)
        # servers-share should allow PUT on mcpServer ACL endpoint.
        resp = client.put("/permissions/mcpServer/abc123")
        assert resp.status_code == 200

    def test_allows_share_agent_permissions(self, monkeypatch):
        """Allows sharing agent ACL via agents-share scope."""
        from registry.middleware import permissions as perms

        def _mock_config():
            return {
                "agents-share": [
                    {"action": "share_agent", "method": "PUT", "endpoint": "/permissions/agent/{resource_id}"},
                ],
            }

        monkeypatch.setattr(perms, "_SCOPES_CACHE", perms.ScopesConfigCache(redis_key="test:scopes"))
        monkeypatch.setattr(perms, "load_scopes_config", _mock_config)

        app = _build_app()
        app.add_middleware(ScopePermissionMiddleware)
        app.add_middleware(_auth_middleware_factory({"scopes": ["agents-share"]}))

        client = TestClient(app)
        # agents-share should allow PUT on agent ACL endpoint.
        resp = client.put("/permissions/agent/xyz789")
        assert resp.status_code == 200

    def test_uses_group_mappings_when_scopes_empty(self, monkeypatch):
        """Maps groups to scopes when explicit scopes missing."""
        from registry.middleware import permissions as perms

        def _mock_config():
            return {
                "group_mappings": {"jarvis-register-user": ["servers-read"]},
                "servers-read": [
                    {"action": "list_servers", "method": "GET", "endpoint": "/servers"},
                ],
            }

        monkeypatch.setattr(perms, "_SCOPES_CACHE", perms.ScopesConfigCache(redis_key="test:scopes"))
        monkeypatch.setattr(perms, "load_scopes_config", _mock_config)

        app = _build_app()
        app.add_middleware(_auth_middleware_factory({"scopes": [], "groups": ["jarvis-register-user"]}))
        app.add_middleware(ScopePermissionMiddleware)

        client = TestClient(app)
        # Group-to-scope mapping should be honored.
        resp = client.get("/servers")
        assert resp.status_code == 200

    def test_allows_when_path_not_guarded(self, monkeypatch):
        """Allows access to unguarded paths even without scopes."""
        from registry.middleware import permissions as perms

        def _mock_config():
            return {
                "servers-read": [
                    {"action": "list_servers", "method": "GET", "endpoint": "/servers"},
                ],
            }

        monkeypatch.setattr(perms, "_SCOPES_CACHE", perms.ScopesConfigCache(redis_key="test:scopes"))
        monkeypatch.setattr(perms, "load_scopes_config", _mock_config)

        app = _build_app()
        app.add_middleware(ScopePermissionMiddleware)
        app.add_middleware(_auth_middleware_factory({"scopes": []}))

        client = TestClient(app)
        # Unguarded path should pass through even without scopes.
        resp = client.get("/health")
        assert resp.status_code == 200
