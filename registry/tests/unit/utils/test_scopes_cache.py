from typing import Any

from registry.utils.scopes_cache import ScopesConfigCache


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.last_set_kwargs: dict[str, Any] | None = None

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str, **kwargs):
        self.store[key] = value
        self.last_set_kwargs = kwargs

    def delete(self, key: str):
        self.store.pop(key, None)


def _loader_factory(result: dict[str, Any], calls: list[int]):
    def _loader():
        calls.append(1)
        return result

    return _loader


def test_scopes_cache_in_memory_fallback(monkeypatch):
    calls: list[int] = []
    cache = ScopesConfigCache(redis_key="test:scopes")

    def _no_redis():
        return None

    monkeypatch.setattr("registry.utils.scopes_cache.get_redis_client", _no_redis)

    loader = _loader_factory({"group_mappings": {}}, calls)
    first = cache.get_or_load(loader)
    second = cache.get_or_load(loader)

    assert first == {"group_mappings": {}}
    assert second == {"group_mappings": {}}
    assert len(calls) == 1


def test_scopes_cache_uses_redis(monkeypatch):
    calls: list[int] = []
    cache = ScopesConfigCache(redis_key="test:scopes", ttl_seconds=120)
    redis = _FakeRedis()

    def _redis_client():
        return redis

    monkeypatch.setattr("registry.utils.scopes_cache.get_redis_client", _redis_client)

    loader = _loader_factory({"group_mappings": {"a": ["b"]}}, calls)
    first = cache.get_or_load(loader)
    assert first["group_mappings"]["a"] == ["b"]
    assert len(calls) == 1
    assert redis.last_set_kwargs == {"ex": 120}

    # New cache instance should read from redis and skip loader
    cache2 = ScopesConfigCache(redis_key="test:scopes")
    second = cache2.get_or_load(loader)
    assert second["group_mappings"]["a"] == ["b"]
    assert len(calls) == 1


def test_scopes_cache_redis_error_fallback(monkeypatch):
    calls: list[int] = []
    cache = ScopesConfigCache(redis_key="test:scopes")

    class _BrokenRedis:
        def get(self, key: str):
            raise RuntimeError("boom")

        def set(self, key: str, value: str, **kwargs):
            raise RuntimeError("boom")

        def delete(self, key: str):
            raise RuntimeError("boom")

    def _redis_client():
        return _BrokenRedis()

    monkeypatch.setattr("registry.utils.scopes_cache.get_redis_client", _redis_client)

    loader = _loader_factory({"group_mappings": {}}, calls)
    result = cache.get_or_load(loader)
    assert result == {"group_mappings": {}}
    assert len(calls) == 1


def test_scopes_cache_refresh_clears_redis(monkeypatch):
    cache = ScopesConfigCache(redis_key="test:scopes")
    redis = _FakeRedis()
    redis.set("test:scopes", '{"group_mappings": {}}')

    def _redis_client():
        return redis

    monkeypatch.setattr("registry.utils.scopes_cache.get_redis_client", _redis_client)

    cache.refresh()
    assert "test:scopes" not in redis.store
