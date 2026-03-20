from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Any

from .auth.oauth.flow_state_manager import FlowStateManager
from .auth.oauth.reconnection import OAuthReconnectionManager
from .health.service import HealthMonitoringService
from .services.a2a_agent_service import A2AAgentService
from .services.access_control_service import ACLService
from .services.agentcore_import_service import AgentCoreImportService
from .services.federation_service import FederationService
from .services.group_service import GroupService
from .services.oauth.connection_service import MCPConnectionService
from .services.oauth.mcp_service import MCPService
from .services.oauth.oauth_service import MCPOAuthService
from .services.oauth.status_resolver import ConnectionStatusResolver
from .services.oauth.token_service import TokenService
from .services.search.service import create_vector_search_service
from .services.server_service import ServerServiceV1
from .services.user_service import UserService

if TYPE_CHECKING:
    from .core.config import Settings

logger = logging.getLogger(__name__)


class RegistryContainer:
    """App-scoped container for registry infrastructure and domain services.

    This container owns services for MCP server records managed by the registry.
    It is distinct from the mounted FastMCP gateway application configured in
    ``app_factory.py``.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    @cached_property
    def vector_service(self) -> Any:
        return create_vector_search_service()

    @cached_property
    def health_service(self) -> Any:
        return HealthMonitoringService(server_service=self.server_service)

    @cached_property
    def federation_service(self) -> Any:
        return FederationService()

    @cached_property
    def user_service(self) -> Any:
        return UserService()

    @cached_property
    def group_service(self) -> Any:
        return GroupService()

    @cached_property
    def acl_service(self) -> Any:
        return ACLService(user_service=self.user_service, group_service=self.group_service)

    @cached_property
    def token_service(self) -> Any:
        return TokenService(user_service=self.user_service)

    @cached_property
    def flow_state_manager(self) -> Any:
        return FlowStateManager()

    @cached_property
    def oauth_service(self) -> Any:
        return MCPOAuthService(flow_manager=self.flow_state_manager, token_service_instance=self.token_service)

    @cached_property
    def connection_service(self) -> Any:
        return MCPConnectionService(server_service=self.server_service)

    @cached_property
    def mcp_service(self) -> Any:
        return MCPService(connection_service=self.connection_service, oauth_service=self.oauth_service)

    @cached_property
    def reconnection_manager(self) -> Any:
        return OAuthReconnectionManager(
            mcp_service=self.mcp_service,
            oauth_service=self.oauth_service,
            flow_state_manager=self.flow_state_manager,
            server_service=self.server_service,
        )

    @cached_property
    def status_resolver(self) -> Any:
        return ConnectionStatusResolver(
            flow_state_manager=self.flow_state_manager,
            reconnection_manager=self.reconnection_manager,
        )

    @cached_property
    def server_service(self) -> Any:
        return ServerServiceV1(
            user_service=self.user_service,
            token_service=self.token_service,
            oauth_service=self.oauth_service,
        )

    @cached_property
    def a2a_agent_service(self) -> Any:
        return A2AAgentService()

    @cached_property
    def agentcore_import_service(self) -> Any:
        return AgentCoreImportService(
            acl_service_instance=self.acl_service,
            server_service=self.server_service,
            user_service_instance=self.user_service,
        )

    @property
    def server_service_v1(self) -> Any:
        """Temporary compatibility alias for code paths not yet migrated off the old name."""
        return self.server_service

    async def startup(self) -> None:
        """Warm root services while keeping compatibility with existing singletons."""
        logger.info("Initializing services via registry container...")

        logger.info("Initializing vector search service...")
        await self.vector_service.initialize()
        if hasattr(self.vector_service, "_initialized") and self.vector_service._initialized:
            logger.info("Vector search service initialized successfully")
        else:
            logger.warning("Vector search service not initialized - index update skipped")
            logger.info("App will continue without vector search features")

        logger.info("Initializing health monitoring service...")
        await self.health_service.initialize()

        logger.info("Initializing MCP connection service...")
        await self.connection_service.initialize_app_connections()

        logger.info("Initializing MCP service...")
        await self.mcp_service.initialize()

        logger.info("Initializing federation service...")
        self._initialize_federation()

    async def shutdown(self) -> None:
        """Shutdown managed root services."""
        await self.health_service.shutdown()

    def _initialize_federation(self) -> None:
        federation_service = self.federation_service
        if federation_service.config.is_any_federation_enabled():
            logger.info("Federation enabled for: %s", ", ".join(federation_service.config.get_enabled_federations()))

            sync_on_startup = (
                federation_service.config.anthropic.enabled and federation_service.config.anthropic.sync_on_startup
            ) or (federation_service.config.asor.enabled and federation_service.config.asor.sync_on_startup)

            if sync_on_startup:
                logger.info("Syncing servers from federated registries on startup...")
                try:
                    sync_results = federation_service.sync_all()
                    for source, servers in sync_results.items():
                        logger.info("Synced %s servers from %s", len(servers), source)
                except Exception as exc:
                    logger.error("Federation sync failed (continuing with startup): %s", exc, exc_info=True)
        else:
            logger.info("Federation is disabled")
