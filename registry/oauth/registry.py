from typing import Dict, Optional, Set
from dataclasses import dataclass, field
import asyncio
from cachetools import TTLCache
from async_lru import alru_cache


@dataclass
class ParsedServerConfig:
    """Server configuration"""
    name: str
    command: Optional[str] = None
    args: Optional[list] = field(default_factory=list)
    env: Optional[Dict[str, str]] = field(default_factory=dict)
    requires_oauth: bool = False
    oauth: Optional[dict] = None
    custom_user_vars: Optional[Dict[str, str]] = None


class SimpleCache:
    """Simple cache using cachetools"""

    def __init__(self, name: str, maxsize: int = 1000, ttl: int = 3600):
        self.name = name
        # Uses TTLCache with automatic expiration
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = asyncio.Lock()

    async def add(self, key: str, value: ParsedServerConfig):
        async with self._lock:
            self._cache[key] = value

    async def update(self, key: str, value: ParsedServerConfig):
        async with self._lock:
            if key not in self._cache:
                raise KeyError(f"Key '{key}' not found")
            self._cache[key] = value

    async def remove(self, key: str):
        async with self._lock:
            self._cache.pop(key, None)

    async def get(self, key: str) -> Optional[ParsedServerConfig]:
        async with self._lock:
            return self._cache.get(key)

    async def get_all(self) -> Dict[str, ParsedServerConfig]:
        async with self._lock:
            return dict(self._cache)

    async def reset(self):
        async with self._lock:
            self._cache.clear()


class MCPServersRegistry:
    """MCP servers registry - using existing cache package"""

    def __init__(self):
        self.shared_app_servers = SimpleCache('App')
        self.shared_user_servers = SimpleCache('User')
        self._private_caches: Dict[str, SimpleCache] = {}
        self._raw_configs: Dict[str, ParsedServerConfig] = {}

    def set_raw_configs(self, configs: Dict[str, ParsedServerConfig]):
        self._raw_configs = configs

    def _get_user_cache(self, user_id: str) -> SimpleCache:
        """Get or create user cache"""
        if user_id not in self._private_caches:
            self._private_caches[user_id] = SimpleCache(f'User({user_id})')
        return self._private_caches[user_id]

    async def add_private_user_server(self, user_id: str, server_name: str, config: ParsedServerConfig):
        cache = self._get_user_cache(user_id)
        await cache.add(server_name, config)

    async def update_private_user_server(self, user_id: str, server_name: str, config: ParsedServerConfig):
        if user_id not in self._private_caches:
            raise ValueError(f"No private servers found for user '{user_id}'")
        await self._private_caches[user_id].update(server_name, config)

    async def remove_private_user_server(self, user_id: str, server_name: str):
        if user_id in self._private_caches:
            await self._private_caches[user_id].remove(server_name)

    # Optimize frequent queries using cache decorator
    @alru_cache(maxsize=128, ttl=60)  # Cache for 1 minute
    async def get_server_config(self, server_name: str, user_id: Optional[str] = None) -> Optional[ParsedServerConfig]:
        """Get server configuration"""
        # 1. Shared app servers
        config = await self.shared_app_servers.get(server_name)
        if config:
            return config

        # 2. Shared user servers
        config = await self.shared_user_servers.get(server_name)
        if config:
            return config

        # 3. User private servers
        if user_id and user_id in self._private_caches:
            config = await self._private_caches[user_id].get(server_name)
            if config:
                return config

        # 4. Raw configurations
        return self._raw_configs.get(server_name)

    async def get_all_server_configs(self, user_id: Optional[str] = None) -> Dict[str, ParsedServerConfig]:
        """Get all server configurations"""
        all_configs = self._raw_configs.copy()
        all_configs.update(await self.shared_app_servers.get_all())
        all_configs.update(await self.shared_user_servers.get_all())

        if user_id and user_id in self._private_caches:
            all_configs.update(await self._private_caches[user_id].get_all())

        return all_configs

    async def get_oauth_servers(self, user_id: Optional[str] = None) -> Set[str]:
        all_servers = await self.get_all_server_configs(user_id)
        return {name for name, config in all_servers.items() if config.requires_oauth}

    async def reset(self):
        """Reset all caches"""
        await self.shared_app_servers.reset()
        await self.shared_user_servers.reset()
        for cache in self._private_caches.values():
            await cache.reset()
        self._private_caches.clear()
        self._raw_configs.clear()

        # Clear method cache
        self.get_server_config.cache_clear()


mcp_servers_registry = MCPServersRegistry()
