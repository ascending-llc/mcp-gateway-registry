import pytest
import time
import sys
import os
import asyncio

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from registry.oauth.registry import (
    ParsedServerConfig,
    SimpleCache,
    MCPServersRegistry,
    mcp_servers_registry
)


@pytest.mark.unit
@pytest.mark.oauth
class TestParsedServerConfig:
    """Test suite for ParsedServerConfig dataclass."""

    def test_default_values(self):
        """Test initialization with default values."""
        config = ParsedServerConfig(name="test-server")
        
        assert config.name == "test-server"
        assert config.command is None
        assert config.args == []
        assert config.env == {}
        assert config.requires_oauth is False
        assert config.oauth is None
        assert config.custom_user_vars is None

    def test_with_all_fields(self):
        """Test initialization with all fields provided."""
        config = ParsedServerConfig(
            name="test-server",
            command="python",
            args=["-m", "server"],
            env={"KEY": "value"},
            requires_oauth=True,
            oauth={"provider": "google"},
            custom_user_vars={"var1": "val1"}
        )
        
        assert config.name == "test-server"
        assert config.command == "python"
        assert config.args == ["-m", "server"]
        assert config.env == {"KEY": "value"}
        assert config.requires_oauth is True
        assert config.oauth == {"provider": "google"}
        assert config.custom_user_vars == {"var1": "val1"}

    def test_field_default_factories(self):
        """Test that default factories create new instances."""
        config1 = ParsedServerConfig(name="server1")
        config2 = ParsedServerConfig(name="server2")
        
        # Should be different list instances
        assert config1.args is not config2.args
        assert config1.env is not config2.env


@pytest.mark.unit
@pytest.mark.oauth
class TestSimpleCache:
    """Test suite for SimpleCache class."""

    @pytest.mark.asyncio
    async def test_init_default_values(self):
        """Test initialization with default values."""
        cache = SimpleCache("test-cache")
        
        assert cache.name == "test-cache"
        assert cache._cache.maxsize == 1000
        assert cache._cache.ttl == 3600

    @pytest.mark.asyncio
    async def test_init_custom_values(self):
        """Test initialization with custom values."""
        cache = SimpleCache("test-cache", maxsize=500, ttl=1800)
        
        assert cache.name == "test-cache"
        assert cache._cache.maxsize == 500
        assert cache._cache.ttl == 1800

    @pytest.mark.asyncio
    async def test_add_and_get(self):
        """Test adding and retrieving items."""
        cache = SimpleCache("test-cache")
        config = ParsedServerConfig(name="test-server")
        
        await cache.add("key1", config)
        result = await cache.get("key1")
        
        assert result == config
        assert result is not None
        assert result.name == "test-server"

    @pytest.mark.asyncio
    async def test_add_duplicate_key(self):
        """Test adding item with duplicate key (should overwrite)."""
        cache = SimpleCache("test-cache")
        config1 = ParsedServerConfig(name="server1")
        config2 = ParsedServerConfig(name="server2")
        
        await cache.add("key1", config1)
        await cache.add("key1", config2)  # Should overwrite
        
        result = await cache.get("key1")
        assert result is not None
        assert result.name == "server2"

    @pytest.mark.asyncio
    async def test_update_existing_key(self):
        """Test updating an existing key."""
        cache = SimpleCache("test-cache")
        config1 = ParsedServerConfig(name="server1")
        config2 = ParsedServerConfig(name="server2")
        
        await cache.add("key1", config1)
        await cache.update("key1", config2)
        
        result = await cache.get("key1")
        assert result is not None
        assert result.name == "server2"

    @pytest.mark.asyncio
    async def test_update_nonexistent_key(self):
        """Test updating a non-existent key (should raise KeyError)."""
        cache = SimpleCache("test-cache")
        config = ParsedServerConfig(name="test-server")
        
        with pytest.raises(KeyError, match="Key 'key1' not found"):
            await cache.update("key1", config)

    @pytest.mark.asyncio
    async def test_remove_existing_key(self):
        """Test removing an existing key."""
        cache = SimpleCache("test-cache")
        config = ParsedServerConfig(name="test-server")
        
        await cache.add("key1", config)
        assert await cache.get("key1") is not None
        
        await cache.remove("key1")
        assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_key(self):
        """Test removing a non-existent key (should not raise error)."""
        cache = SimpleCache("test-cache")
        
        # Should not raise any exception
        await cache.remove("key1")

    @pytest.mark.asyncio
    async def test_get_all(self):
        """Test retrieving all items."""
        cache = SimpleCache("test-cache")
        config1 = ParsedServerConfig(name="server1")
        config2 = ParsedServerConfig(name="server2")
        
        await cache.add("key1", config1)
        await cache.add("key2", config2)
        
        all_items = await cache.get_all()
        
        assert len(all_items) == 2
        assert all_items["key1"] == config1
        assert all_items["key2"] == config2

    @pytest.mark.asyncio
    async def test_reset(self):
        """Test resetting the cache."""
        cache = SimpleCache("test-cache")
        config = ParsedServerConfig(name="test-server")
        
        await cache.add("key1", config)
        assert await cache.get("key1") is not None
        
        await cache.reset()
        assert await cache.get("key1") is None
        assert await cache.get_all() == {}

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        """Test TTL expiration behavior."""
        cache = SimpleCache("test-cache", ttl=1)  # 1 second TTL
        config = ParsedServerConfig(name="test-server")
        
        await cache.add("key1", config)
        
        # Item should exist immediately
        assert await cache.get("key1") is not None
        
        # Wait for TTL to expire
        time.sleep(1.1)
        
        # Item should be expired and return None
        assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test concurrent access with lock."""
        cache = SimpleCache("test-cache")
        config = ParsedServerConfig(name="test-server")
        
        # Simulate concurrent access
        async def add_item(key, value):
            await cache.add(key, value)
        
        async def get_item(key):
            return await cache.get(key)
        
        # Run concurrent operations
        await asyncio.gather(
            add_item("key1", config),
            add_item("key2", config),
            get_item("key1"),
            get_item("key2")
        )
        
        # Verify all operations completed without deadlock
        assert await cache.get("key1") == config
        assert await cache.get("key2") == config


@pytest.mark.unit
@pytest.mark.oauth
class TestMCPServersRegistry:
    """Test suite for MCPServersRegistry class."""

    @pytest.mark.asyncio
    async def test_init(self):
        """Test initialization."""
        registry = MCPServersRegistry()
        
        assert registry.shared_app_servers.name == "App"
        assert registry.shared_user_servers.name == "User"
        assert registry._private_caches == {}
        assert registry._raw_configs == {}

    @pytest.mark.asyncio
    async def test_set_raw_configs(self):
        """Test setting raw configurations."""
        registry = MCPServersRegistry()
        configs = {
            "server1": ParsedServerConfig(name="server1"),
            "server2": ParsedServerConfig(name="server2")
        }
        
        registry.set_raw_configs(configs)
        
        assert registry._raw_configs == configs
        assert len(registry._raw_configs) == 2

    @pytest.mark.asyncio
    async def test_add_private_user_server(self):
        """Test adding private user server."""
        registry = MCPServersRegistry()
        user_id = "user1"
        server_name = "private-server"
        config = ParsedServerConfig(name=server_name)
        
        await registry.add_private_user_server(user_id, server_name, config)
        
        # Verify cache was created
        assert user_id in registry._private_caches
        cache = registry._private_caches[user_id]
        assert cache.name == f"User({user_id})"
        
        # Verify server was added
        result = await cache.get(server_name)
        assert result == config

    @pytest.mark.asyncio
    async def test_update_private_user_server(self):
        """Test updating private user server."""
        registry = MCPServersRegistry()
        user_id = "user1"
        server_name = "private-server"
        config1 = ParsedServerConfig(name=server_name, command="cmd1")
        config2 = ParsedServerConfig(name=server_name, command="cmd2")
        
        # First add the server
        await registry.add_private_user_server(user_id, server_name, config1)
        
        # Then update it
        await registry.update_private_user_server(user_id, server_name, config2)
        
        # Verify update
        cache = registry._private_caches[user_id]
        result = await cache.get(server_name)
        assert result is not None
        assert result.command == "cmd2"

    @pytest.mark.asyncio
    async def test_update_private_user_server_nonexistent_user(self):
        """Test updating private server for non-existent user."""
        registry = MCPServersRegistry()
        user_id = "nonexistent-user"
        server_name = "private-server"
        config = ParsedServerConfig(name=server_name)
        
        with pytest.raises(ValueError, match=f"No private servers found for user '{user_id}'"):
            await registry.update_private_user_server(user_id, server_name, config)

    @pytest.mark.asyncio
    async def test_remove_private_user_server(self):
        """Test removing private user server."""
        registry = MCPServersRegistry()
        user_id = "user1"
        server_name = "private-server"
        config = ParsedServerConfig(name=server_name)
        
        # Add the server
        await registry.add_private_user_server(user_id, server_name, config)
        assert user_id in registry._private_caches
        
        # Remove the server
        await registry.remove_private_user_server(user_id, server_name)
        
        # Verify removal
        cache = registry._private_caches[user_id]
        assert await cache.get(server_name) is None

    @pytest.mark.asyncio
    async def test_remove_private_user_server_nonexistent_user(self):
        """Test removing private server for non-existent user."""
        registry = MCPServersRegistry()
        user_id = "nonexistent-user"
        server_name = "private-server"
        
        # Should not raise any exception
        await registry.remove_private_user_server(user_id, server_name)

    @pytest.mark.asyncio
    async def test_get_server_config_priority_order(self):
        """Test server config lookup priority order."""
        registry = MCPServersRegistry()
        
        # Create configs for each level
        raw_config = ParsedServerConfig(name="test-server", command="raw")
        shared_user_config = ParsedServerConfig(name="test-server", command="shared_user")
        shared_app_config = ParsedServerConfig(name="test-server", command="shared_app")
        private_config = ParsedServerConfig(name="test-server", command="private")
        
        # Set up each level
        registry.set_raw_configs({"test-server": raw_config})
        await registry.shared_user_servers.add("test-server", shared_user_config)
        await registry.shared_app_servers.add("test-server", shared_app_config)
        await registry.add_private_user_server("user1", "test-server", private_config)
        
        # Test priority: shared_app > shared_user > private > raw
        # 1. Should return shared_app config (highest priority)
        result = await registry.get_server_config("test-server", "user1")
        assert result is not None
        assert result.command == "shared_app"

        # 2. Remove shared_app, should return shared_user
        await registry.shared_app_servers.remove("test-server")
        # Clear cache to ensure fresh lookup
        registry.get_server_config.cache_clear()
        result = await registry.get_server_config("test-server", "user1")
        assert result is not None
        assert result.command == "shared_user"
        
        # 3. Remove shared_user, should return private
        await registry.shared_user_servers.remove("test-server")
        # Clear cache to ensure fresh lookup
        registry.get_server_config.cache_clear()
        result = await registry.get_server_config("test-server", "user1")
        assert result is not None
        assert result.command == "private"
        
        # 4. Remove private (by using different user), should return raw
        result = await registry.get_server_config("test-server", "user2")
        assert result is not None
        assert result.command == "raw"
        
        # 5. Remove raw, should return None
        registry.set_raw_configs({})
        # Clear cache to ensure fresh lookup
        registry.get_server_config.cache_clear()
        result = await registry.get_server_config("test-server", "user2")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_server_config_without_user_id(self):
        """Test getting server config without user ID."""
        registry = MCPServersRegistry()
        config = ParsedServerConfig(name="test-server", command="test")
        
        await registry.shared_app_servers.add("test-server", config)
        
        result = await registry.get_server_config("test-server")
        assert result is not None
        assert result.command == "test"

    @pytest.mark.asyncio
    async def test_get_server_config_cache_decorator(self):
        """Test the @alru_cache decorator on get_server_config."""
        registry = MCPServersRegistry()
        config = ParsedServerConfig(name="test-server", command="test")
        
        await registry.shared_app_servers.add("test-server", config)
        
        # Clear any existing cache
        registry.get_server_config.cache_clear()
        
        # First call should populate cache
        result1 = await registry.get_server_config("test-server")
        # Second call should use cache
        result2 = await registry.get_server_config("test-server")
        
        # Both should return the same result
        assert result1 == result2
        assert result1 is not None
        assert result1.command == "test"
        
        # Test cache clear
        registry.get_server_config.cache_clear()

    @pytest.mark.asyncio
    async def test_get_all_server_configs(self):
        """Test getting all server configs."""
        registry = MCPServersRegistry()
        
        # Create configs at different levels
        raw_config = ParsedServerConfig(name="raw-server", command="raw")
        shared_user_config = ParsedServerConfig(name="shared-user-server", command="shared_user")
        shared_app_config = ParsedServerConfig(name="shared-app-server", command="shared_app")
        private_config = ParsedServerConfig(name="private-server", command="private")
        
        # Set up each level
        registry.set_raw_configs({"raw-server": raw_config})
        await registry.shared_user_servers.add("shared-user-server", shared_user_config)
        await registry.shared_app_servers.add("shared-app-server", shared_app_config)
        await registry.add_private_user_server("user1", "private-server", private_config)
        
        # Get all configs for user1
        all_configs = await registry.get_all_server_configs("user1")
        
        # Should include all configs
        assert len(all_configs) == 4
        assert all_configs["raw-server"].command == "raw"
        assert all_configs["shared-user-server"].command == "shared_user"
        assert all_configs["shared-app-server"].command == "shared_app"
        assert all_configs["private-server"].command == "private"

    @pytest.mark.asyncio
    async def test_get_all_server_configs_without_user_id(self):
        """Test getting all server configs without user ID."""
        registry = MCPServersRegistry()
        
        raw_config = ParsedServerConfig(name="raw-server", command="raw")
        shared_config = ParsedServerConfig(name="shared-server", command="shared")
        
        registry.set_raw_configs({"raw-server": raw_config})
        await registry.shared_app_servers.add("shared-server", shared_config)
        
        all_configs = await registry.get_all_server_configs()
        
        # Should not include private servers
        assert len(all_configs) == 2
        assert "raw-server" in all_configs
        assert "shared-server" in all_configs

    @pytest.mark.asyncio
    async def test_get_oauth_servers(self):
        """Test getting OAuth servers."""
        registry = MCPServersRegistry()
        
        # Create servers with and without OAuth
        oauth_server1 = ParsedServerConfig(name="oauth1", requires_oauth=True)
        oauth_server2 = ParsedServerConfig(name="oauth2", requires_oauth=True)
        non_oauth_server = ParsedServerConfig(name="non-oauth", requires_oauth=False)
        
        # Set up servers at different levels
        registry.set_raw_configs({"oauth1": oauth_server1})
        await registry.shared_user_servers.add("oauth2", oauth_server2)
        await registry.shared_app_servers.add("non-oauth", non_oauth_server)
        
        # Get OAuth servers
        oauth_servers = await registry.get_oauth_servers()
        
        # Should only include servers with requires_oauth=True
        assert len(oauth_servers) == 2
        assert "oauth1" in oauth_servers
        assert "oauth2" in oauth_servers
        assert "non-oauth" not in oauth_servers

    @pytest.mark.asyncio
    async def test_get_oauth_servers_with_user_id(self):
        """Test getting OAuth servers for specific user."""
        registry = MCPServersRegistry()
        
        # Create servers
        oauth_server1 = ParsedServerConfig(name="oauth1", requires_oauth=True)
        oauth_server2 = ParsedServerConfig(name="oauth2", requires_oauth=True)
        non_oauth_server = ParsedServerConfig(name="non-oauth", requires_oauth=False)
        
        # Set up servers including private user server
        registry.set_raw_configs({"oauth1": oauth_server1})
        await registry.shared_user_servers.add("oauth2", oauth_server2)
        await registry.add_private_user_server("user1", "non-oauth", non_oauth_server)
        
        # Get OAuth servers for user1
        oauth_servers = await registry.get_oauth_servers("user1")
        
        # Should include both OAuth servers (private non-oauth server should be excluded)
        assert len(oauth_servers) == 2
        assert "oauth1" in oauth_servers
        assert "oauth2" in oauth_servers

    @pytest.mark.asyncio
    async def test_reset(self):
        """Test resetting the registry."""
        registry = MCPServersRegistry()
        
        # Populate the registry
        config = ParsedServerConfig(name="test-server")
        registry.set_raw_configs({"test-server": config})
        await registry.shared_app_servers.add("app-server", config)
        await registry.shared_user_servers.add("user-server", config)
        await registry.add_private_user_server("user1", "private-server", config)
        
        # Verify registry is populated
        assert len(registry._raw_configs) == 1
        assert len(registry._private_caches) == 1
        
        # Reset the registry
        await registry.reset()
        
        # Verify everything is cleared
        assert registry._raw_configs == {}
        assert registry._private_caches == {}
        
        # Verify caches are empty
        app_cache_all = await registry.shared_app_servers.get_all()
        user_cache_all = await registry.shared_user_servers.get_all()
        assert app_cache_all == {}
        assert user_cache_all == {}

    @pytest.mark.asyncio
    async def test_reset_with_cache_clear(self):
        """Test reset clears method cache."""
        registry = MCPServersRegistry()
        config = ParsedServerConfig(name="test-server", command="test")
        
        await registry.shared_app_servers.add("test-server", config)
        
        # Call get_server_config to populate cache
        result1 = await registry.get_server_config("test-server")
        assert result1 is not None
        
        # Reset should clear all caches including shared_app_servers
        await registry.reset()
        
        # After reset, the server should no longer be in the cache
        result2 = await registry.get_server_config("test-server")
        assert result2 is None

    @pytest.mark.asyncio
    async def test_concurrent_registry_access(self):
        """Test concurrent access to registry."""
        registry = MCPServersRegistry()
        config = ParsedServerConfig(name="test-server")
        
        async def add_server(user_id, server_name):
            await registry.add_private_user_server(user_id, server_name, config)
        
        async def get_server(user_id, server_name):
            return await registry.get_server_config(server_name, user_id)
        
        # Run concurrent operations
        await asyncio.gather(
            add_server("user1", "server1"),
            add_server("user2", "server2"),
            get_server("user1", "server1"),
            get_server("user2", "server2")
        )
        
        # Verify all operations completed
        assert "user1" in registry._private_caches
        assert "user2" in registry._private_caches


@pytest.mark.unit
@pytest.mark.oauth
class TestGlobalRegistryInstance:
    """Test suite for the global mcp_servers_registry instance."""

    def test_global_instance_exists(self):
        """Test that the global instance exists."""
        assert mcp_servers_registry is not None
        assert isinstance(mcp_servers_registry, MCPServersRegistry)

    @pytest.mark.asyncio
    async def test_global_instance_functionality(self):
        """Test basic functionality of the global instance."""
        config = ParsedServerConfig(name="global-test-server", command="test")
        
        # Add a server to the global instance
        await mcp_servers_registry.shared_app_servers.add("global-test", config)
        
        # Retrieve it
        result = await mcp_servers_registry.get_server_config("global-test")
        
        assert result is not None
        assert result.name == "global-test-server"
        assert result.command == "test"
        
        # Clean up
        await mcp_servers_registry.reset()

    @pytest.mark.asyncio
    async def test_global_instance_independence(self):
        """Test that global instance is independent from new instances."""
        # Create a new instance
        new_registry = MCPServersRegistry()
        config = ParsedServerConfig(name="test-server")
        
        # Add to new instance
        await new_registry.shared_app_servers.add("test", config)
        
        # Should not affect global instance
        global_result = await mcp_servers_registry.get_server_config("test")
        new_result = await new_registry.get_server_config("test")
        
        assert global_result is None  # Not in global instance
        assert new_result is not None  # Is in new instance
        
        # Clean up
        await new_registry.reset()
