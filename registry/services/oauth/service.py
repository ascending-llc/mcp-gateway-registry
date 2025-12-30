import asyncio
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field, asdict
from registry.utils.log import logger

DEFAULT_CONFIG_PATH = "/Users/dyl/ascending/code/mcp-gateway-registry/mcp_service.yaml"

@dataclass
class MCPServerConfig:
    """
    MCP server configuration
    TODO: 1. Replace mango solution
    """
    name: str
    type: str = "stdio"  # stdio, http, websocket
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    requires_oauth: bool = False
    oauth_config: Optional[Dict[str, Any]] = None
    custom_user_vars: Dict[str, str] = field(default_factory=dict)
    description: str = ""
    timeout_ms: int = 30000


class MCPConfigService:
    """MCP configuration service"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._configs: Dict[str, MCPServerConfig] = {}
        self._oauth_servers: Set[str] = set()
        self._last_modified: Optional[float] = None
        self._lock = asyncio.Lock()

    async def load_configs(self) -> None:
        """Load MCP server configurations"""
        async with self._lock:
            try:
                configs_loaded = False
                # 1. Load main configuration file
                config_file = Path(self.config_path)
                if config_file.exists():
                    configs_loaded = await self._load_mcp_service_file(config_file)

                if not configs_loaded:
                    # Configuration file does not exist, use default configurations
                    logger.warning(f"No config files found, using default configs")
                # Identify servers that require OAuth
                self._oauth_servers = {
                    name for name, config in self._configs.items()
                    if config.requires_oauth
                }
                logger.info( f"Total {len(self._configs)} MCP server configs loaded,"
                             f" {len(self._oauth_servers)} require OAuth")
            except Exception as e:
                logger.error(f"Failed to load MCP configs: {e}", exc_info=True)
                raise e

    async def _load_mcp_service_file(self, config_file: Path) -> bool:
        """Load mcp_service.yaml format configuration file"""
        try:
            # Load configuration from YAML file
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)

            if not config_data or 'mcpServers' not in config_data:
                logger.warning(f"No mcpServers found in {config_file}")
                return False

            for server_name, server_config in config_data.get('mcpServers', {}).items():
                try:
                    # Convert mcp_service.yaml format to standard format
                    oauth_config = None
                    if 'oauth' in server_config:
                        oauth = server_config['oauth']
                        oauth_config = {
                            'client_id': oauth.get('client_id'),
                            'client_secret': oauth.get('client_secret'),
                            'auth_url': oauth.get('authorization_url'),
                            'token_url': oauth.get('token_url'),
                            'scopes': oauth.get('scope', '').split(' ') if oauth.get('scope') else [],
                            'redirect_uri': None  # mcp_service.yaml format does not contain redirect_uri
                        }

                    config_obj = MCPServerConfig(
                        name=server_name,
                        type=server_config.get('type', 'streamable-http'),
                        url=server_config.get('url'),
                        command=None,  # mcp_service.yaml format does not support command
                        args=[],  # mcp_service.yaml format does not support args
                        env={},  # mcp_service.yaml format does not support env
                        requires_oauth=bool(oauth_config),
                        oauth_config=oauth_config,
                        custom_user_vars={},  # mcp_service.yaml format does not support custom_user_vars
                        description=f"MCP server from {config_file.name}",
                        timeout_ms=server_config.get('timeout', 30000)
                    )

                    # If configuration with same name already exists, merge (mcp_service.yaml has lower priority)
                    if server_name not in self._configs:
                        self._configs[server_name] = config_obj
                        logger.debug(f"Added server {server_name} from {config_file.name}")

                except Exception as e:
                    logger.error(f"Failed to parse mcp_service config for server {server_name}: {e}")
                    continue

            logger.info(f"Loaded {len(config_data.get('mcpServers', {}))} MCP server configs from {config_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to load mcp_service file {config_file}: {e}")
            return False

    def get_server_config(self, server_name: str) -> Optional[MCPServerConfig]:
        """Get server configuration"""
        return self._configs.get(server_name)

    def get_all_configs(self) -> Dict[str, MCPServerConfig]:
        """Get all server configurations"""
        return self._configs.copy()

    def get_oauth_configs(self) -> Dict[str, MCPServerConfig]:
        """Get server configurations that require OAuth"""
        return {name: config for name, config in self._configs.items()
                if config.requires_oauth}

    def is_oauth_server(self, server_name: str) -> bool:
        """Check if server requires OAuth"""
        return server_name in self._oauth_servers

    def validate_config(self, server_name: str) -> Tuple[bool, Optional[str]]:
        """Validate server configuration"""
        config = self.get_server_config(server_name)
        if not config:
            return False, f"Server '{server_name}' not found"

        # Validate configuration completeness
        if config.type == "http" and not config.url:
            return False, f"HTTP server '{server_name}' missing URL"

        if config.type == "stdio" and not config.command:
            return False, f"Stdio server '{server_name}' missing command"

        if config.requires_oauth and not config.oauth_config:
            return False, f"OAuth server '{server_name}' missing oauth_config"

        return True, None

    async def reload_configs(self) -> bool:
        """Reload configurations"""
        try:
            old_count = len(self._configs)
            await self.load_configs()
            new_count = len(self._configs)

            logger.info(f"Configs reloaded: {old_count} -> {new_count} servers")
            return True
        except Exception as e:
            logger.error(f"Failed to reload configs: {e}")
            return False


_config_service_instance: Optional[MCPConfigService] = None

async def get_config_service() -> MCPConfigService:
    """Get configuration service instance"""
    global _config_service_instance
    if _config_service_instance is None:
        _config_service_instance = MCPConfigService()
        await _config_service_instance.load_configs()
    return _config_service_instance
