"""
Federation service for managing federated registry integrations.

Handles:
- Loading federation configuration
- Syncing servers from federated registries
- Caching federated server data with TTL
- Periodic sync scheduling
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..schemas.federation_schema import (
    AnthropicFederationConfig,
    FederatedServer,
    FederationConfig,
)
from .federation.anthropic_client import AnthropicFederationClient
from .federation.asor_client import AsorFederationClient


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


class FederationService:
    """Service for managing federated registry integrations."""

    def __init__(
        self,
        config_path: Optional[str] = None
    ):
        """
        Initialize federation service.

        Args:
            config_path: Path to federation.json config file
        """
        # Set default paths
        if config_path is None:
            config_path = os.getenv(
                "FEDERATION_CONFIG_PATH",
                "/app/config/federation.json"
            )

        self.config_path = config_path

        # Load configuration
        self.config = self._load_config()

        # Initialize clients
        self.anthropic_client: Optional[AnthropicFederationClient] = None
        if self.config.anthropic.enabled:
            self.anthropic_client = AnthropicFederationClient(
                endpoint=self.config.anthropic.endpoint
            )

        self.asor_client: Optional[AsorFederationClient] = None
        if self.config.asor.enabled:
            # Extract tenant URL from endpoint or use default
            tenant_url = self.config.asor.endpoint.split("/api")[0] if "/api" in self.config.asor.endpoint else self.config.asor.endpoint

            self.asor_client = AsorFederationClient(
                endpoint=self.config.asor.endpoint,
                auth_env_var=self.config.asor.auth_env_var,
                tenant_url=tenant_url
            )

        logger.info(f"Federation service initialized with config: {config_path}")
        if self.config.is_any_federation_enabled():
            logger.info(f"Enabled federations: {', '.join(self.config.get_enabled_federations())}")
        else:
            logger.info("No federations enabled")

    def _load_config(self) -> FederationConfig:
        """
        Load federation configuration from JSON file.

        Returns:
            FederationConfig instance
        """
        config_file = Path(self.config_path)

        if not config_file.exists():
            logger.warning(f"Federation config not found at {self.config_path}, using defaults")
            return FederationConfig()

        try:
            with open(config_file, "r") as f:
                config_data = json.load(f)

            # Remove JSON comments if present
            config_data.pop("_comment", None)
            config_data.pop("_description", None)

            config = FederationConfig(**config_data)
            logger.info(f"Loaded federation config from {self.config_path}")
            return config

        except Exception as e:
            logger.error(f"Failed to load federation config: {e}")
            return FederationConfig()

    def sync_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Sync servers from all enabled federated registries.

        Returns:
            Dictionary mapping source name to list of synced servers
        """
        results = {}

        if self.config.anthropic.enabled:
            logger.info("Syncing servers from Anthropic MCP Registry...")
            anthropic_servers = self._sync_anthropic()
            results["anthropic"] = anthropic_servers
            logger.info(f"Synced {len(anthropic_servers)} servers from Anthropic")

        # Sync ASOR agents
        logger.info("Syncing agents from ASOR...")
        asor_agents = self._sync_asor()
        results["asor"] = asor_agents
        logger.info(f"Synced {len(asor_agents)} agents from ASOR")

        return results

    def _sync_anthropic(self) -> List[Dict[str, Any]]:
        """
        Sync servers from Anthropic MCP Registry.

        Returns:
            List of synced server data
        """
        if not self.anthropic_client:
            logger.error("Anthropic client not initialized")
            return []

        # Fetch servers
        servers = self.anthropic_client.fetch_all_servers(
            self.config.anthropic.servers
        )

        # Save servers as files to external mount
        from pathlib import Path
        import json
        from ..core.config import settings
        
        for server_data in servers:
            try:
                # Create filename from server name
                server_name = server_data.get("server_name", "unknown-server")
                filename = server_name.replace("/", "-").replace(".", "-") + ".json"
                file_path = settings.servers_dir / filename
                
                # Save to file
                with open(file_path, "w") as f:
                    json.dump(server_data, f, indent=2)
                
                # Update server_state.json to enable the server
                server_path = server_data.get("path", f"/{server_name.replace('/', '-')}")
                self._update_server_state(server_path, True)
                
                logger.info(f"Saved Anthropic server file: {server_name} -> {file_path}")
                
            except Exception as e:
                logger.error(f"Failed to save Anthropic server {server_data.get('server_name', 'unknown')}: {e}")

        return servers

    def _sync_asor(self) -> List[Dict[str, Any]]:
        """
        Sync agents from Workday ASOR.

        Returns:
            List of synced agent data
        """
        if not self.asor_client:
            logger.error("ASOR client not initialized")
            return []

        # Fetch agents
        agents = self.asor_client.fetch_all_agents(
            self.config.asor.agents
        )

        # Register agents with the agent service
        from ..services.agent_service import agent_service
        from ..schemas.agent_models import AgentCard
        from datetime import datetime, timezone
        
        for agent_data in agents:
            # Extract agent info from ASOR data structure
            agent_name = agent_data.get("name", "Unknown ASOR Agent")
            agent_path = f"/{agent_name.lower().replace('_', '-')}"
            agent_url = agent_data.get("url", "")
            agent_description = agent_data.get("description", "Agent synced from ASOR")
            if agent_description == "None":
                agent_description = f"ASOR agent: {agent_name}"
            
            # Extract skills
            skills_data = agent_data.get("skills", [])
            skills = []
            for skill in skills_data:
                skills.append({
                    "name": skill.get("name", ""),
                    "description": skill.get("description", ""),
                    "id": skill.get("id", "")
                })
            
            # Convert ASOR agent data to AgentCard format
            agent_card = AgentCard(
                protocol_version="1.0",  # Required A2A field
                name=agent_name,
                path=agent_path,
                url=agent_url,
                description=agent_description,
                version=agent_data.get("version", "1.0.0"),
                provider="ASOR",  # Add provider field
                author="ASOR",
                license="Unknown",
                skills=skills,
                tags=["asor", "federated", "workday"],
                visibility="public",
                registered_by="asor-federation",
                registered_at=datetime.now(timezone.utc)
            )
            
            try:
                # Check if agent already exists
                if agent_path in agent_service.registered_agents:
                    logger.debug(f"ASOR agent {agent_path} already exists, skipping registration")
                    continue
                
                # Register the agent using the proper method
                agent_service.register_agent(agent_card)
                logger.info(f"Registered ASOR agent: {agent_card.name} at {agent_card.path}")
                
            except Exception as e:
                logger.error(f"Failed to register ASOR agent {agent_data.get('name', 'unknown')}: {e}")

        return agents

    def get_federated_servers(
        self,
        source: Optional[str] = None,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get federated servers by syncing from sources.

        Args:
            source: Filter by source (anthropic, asor, etc.) or None for all
            force_refresh: Ignored (always syncs fresh)

        Returns:
            List of federated server data
        """
        servers = []

        if source is None or source == "anthropic":
            servers.extend(self._sync_anthropic())

        if source is None or source == "asor":
            servers.extend(self._sync_asor())

        return servers

    def get_federated_items(
        self,
        source: Optional[str] = None,
        force_refresh: bool = False
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get both federated servers and agents from specified source or all sources.
        
        Args:
            source: Federation source name (e.g., "anthropic", "asor") or None for all
            force_refresh: Ignored (always syncs fresh)
            
        Returns:
            Dict with 'servers' and 'agents' keys containing respective federated items
        """
        result = {"servers": [], "agents": []}

        if source is None or source == "anthropic":
            result["servers"].extend(self._sync_anthropic())

        if source is None or source == "asor":
            # ASOR provides agents, not servers
            asor_agents = self._sync_asor()
            result["agents"].extend(asor_agents)

        return result

    def _update_server_state(self, server_path: str, enabled: bool) -> None:
        """
        Update server_state.json to enable/disable a server.
        
        Args:
            server_path: Server path (e.g., "/ai.klavis-strata")
            enabled: Whether to enable the server
        """
        try:
            from ..core.config import settings
            state_file = settings.servers_dir / "server_state.json"
            
            # Load existing state
            state = {}
            if state_file.exists():
                with open(state_file, "r") as f:
                    state = json.load(f)
            
            # Update state
            state[server_path] = enabled
            
            # Save state
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)
                
            logger.info(f"Updated server state: {server_path} = {enabled}")
            
        except Exception as e:
            logger.error(f"Failed to update server state for {server_path}: {e}")


# Global instance
_federation_service: Optional[FederationService] = None


def get_federation_service() -> FederationService:
    """
    Get global federation service instance (singleton).

    Returns:
        FederationService instance
    """
    global _federation_service

    if _federation_service is None:
        _federation_service = FederationService()

    return _federation_service
