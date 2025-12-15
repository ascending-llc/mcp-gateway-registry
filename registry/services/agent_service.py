"""
Service for managing A2A agent registration and state.

This module provides CRUD operations for agent cards following the A2A protocol,
with file-based storage and enable/disable state management.

Based on: registry/services/server_service.py
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..schemas.agent_models import AgentCard, AgentInfo


# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


def _path_to_filename(
    path: str,
) -> str:
    """
    Convert agent path to safe filename.

    Args:
        path: Agent path (e.g., /code-reviewer)

    Returns:
        Safe filename with _agent.json extension
    """
    normalized = path.lstrip("/").replace("/", "_")
    if not normalized.endswith("_agent.json"):
        if normalized.endswith(".json"):
            normalized = normalized.replace(".json", "_agent.json")
        else:
            normalized += "_agent.json"
    return normalized


def _load_agent_from_file(
    file_path: Path,
) -> Optional[Dict[str, Any]]:
    """
    Load agent card from JSON file.

    Args:
        file_path: Path to agent JSON file

    Returns:
        Agent card dictionary or None if invalid
    """
    try:
        with open(file_path, "r") as f:
            agent_data = json.load(f)

            if not isinstance(agent_data, dict):
                logger.warning(f"Invalid agent data format in {file_path}")
                return None

            if "path" not in agent_data or "name" not in agent_data:
                logger.warning(f"Missing required fields in {file_path}")
                return None

            return agent_data

    except FileNotFoundError:
        logger.error(f"Agent file not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Could not parse JSON from {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading {file_path}: {e}", exc_info=True)
        return None


def _load_state_file(
    state_file: Path,
) -> Dict[str, List[str]]:
    """
    Load agent state from disk.

    Args:
        state_file: Path to agent_state.json

    Returns:
        Dictionary with 'enabled' and 'disabled' lists
    """
    logger.info(f"Loading agent state from {state_file}...")

    try:
        if state_file.exists():
            with open(state_file, "r") as f:
                state_data = json.load(f)

            if not isinstance(state_data, dict):
                logger.warning(f"Invalid state format in {state_file}")
                return {"enabled": [], "disabled": []}

            if "enabled" not in state_data:
                state_data["enabled"] = []
            if "disabled" not in state_data:
                state_data["disabled"] = []

            logger.info(f"Loaded state: {len(state_data['enabled'])} enabled, {len(state_data['disabled'])} disabled")
            return state_data
        else:
            logger.info(f"No state file found at {state_file}, initializing empty state")
            return {"enabled": [], "disabled": []}

    except json.JSONDecodeError as e:
        logger.error(f"Could not parse JSON from {state_file}: {e}")
        return {"enabled": [], "disabled": []}
    except Exception as e:
        logger.error(f"Failed to read state file {state_file}: {e}", exc_info=True)
        return {"enabled": [], "disabled": []}


def _persist_state_to_disk(
    state_data: Dict[str, List[str]],
    state_file: Path,
) -> None:
    """
    Persist agent state to disk.

    Args:
        state_data: State dictionary with enabled/disabled lists
        state_file: Path to agent_state.json
    """
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)

        with open(state_file, "w") as f:
            json.dump(state_data, f, indent=2)

        logger.info(f"Persisted agent state to {state_file}")

    except Exception as e:
        logger.error(f"ERROR: Failed to persist state to {state_file}: {e}")


def _save_agent_to_disk(
    agent_card: AgentCard,
    agents_dir: Path,
) -> bool:
    """
    Save agent card to individual JSON file.

    Args:
        agent_card: Agent card to save
        agents_dir: Directory for agent storage

    Returns:
        True if successful, False otherwise
    """
    try:
        agents_dir.mkdir(parents=True, exist_ok=True)

        filename = _path_to_filename(agent_card.path)
        file_path = agents_dir / filename

        # Convert to dict for JSON serialization
        agent_dict = agent_card.model_dump(mode="json")

        with open(file_path, "w") as f:
            json.dump(agent_dict, f, indent=2)

        logger.info(f"Successfully saved agent '{agent_card.name}' to {file_path}")
        return True

    except Exception as e:
        logger.error(
            f"Failed to save agent '{agent_card.name}' to disk: {e}",
            exc_info=True,
        )
        return False


class AgentService:
    """Service for managing A2A agent registration and state."""

    def __init__(self):
        """Initialize agent service with empty state."""
        self.registered_agents: Dict[str, AgentCard] = {}
        self.agent_state: Dict[str, List[str]] = {"enabled": [], "disabled": []}


    def load_agents_and_state(self) -> None:
        """Load agent cards and persisted state from disk."""
        logger.info(f"Loading agent cards from {settings.agents_dir}...")

        # Create agents directory if it doesn't exist
        settings.agents_dir.mkdir(parents=True, exist_ok=True)

        temp_agents = {}
        # Only load files matching *_agent.json pattern (excludes FAISS metadata files)
        agent_files = list(settings.agents_dir.glob("**/*_agent.json"))

        # Additionally filter out agent_state.json if it somehow matches pattern
        agent_files = [
            f for f in agent_files
            if f.name != settings.agent_state_file_path.name
        ]

        logger.info(f"Found {len(agent_files)} agent files in {settings.agents_dir}")

        for file in agent_files:
            logger.debug(f"Loading agent from {file.relative_to(settings.agents_dir)}")

        if not agent_files:
            logger.warning(
                f"No agent definition files found in {settings.agents_dir}. "
                "Initializing empty agent registry."
            )
            self.registered_agents = {}
        else:
            for agent_file in agent_files:
                agent_data = _load_agent_from_file(agent_file)

                if agent_data:
                    agent_path = agent_data["path"]

                    if agent_path in temp_agents:
                        logger.warning(
                            f"Duplicate agent path in {agent_file}: {agent_path}. "
                            "Overwriting previous definition."
                        )

                    try:
                        # Validate by creating AgentCard instance
                        agent_card = AgentCard(**agent_data)
                        temp_agents[agent_path] = agent_card

                    except Exception as e:
                        logger.error(
                            f"Failed to validate agent card from {agent_file}: {e}"
                        )

            self.registered_agents = temp_agents
            logger.info(f"Successfully loaded {len(self.registered_agents)} agent cards")

        # Load persisted state
        self._load_agent_state()


    def _load_agent_state(self) -> None:
        """Load persisted agent state from disk."""
        state_data = _load_state_file(settings.agent_state_file_path)

        # Initialize state for all registered agents
        for path in self.registered_agents.keys():
            if path in state_data["enabled"]:
                continue
            elif path in state_data["disabled"]:
                continue
            else:
                # New agent not in state file - add to disabled
                state_data["disabled"].append(path)

        self.agent_state = state_data
        logger.info(
            f"Agent state initialized: {len(state_data['enabled'])} enabled, "
            f"{len(state_data['disabled'])} disabled"
        )


    def _persist_state(self) -> None:
        """Persist agent state to disk."""
        _persist_state_to_disk(self.agent_state, settings.agent_state_file_path)


    def register_agent(
        self,
        agent_card: AgentCard,
    ) -> AgentCard:
        """
        Register a new agent.

        Args:
            agent_card: Agent card to register

        Returns:
            Registered agent card

        Raises:
            ValueError: If agent path already exists
        """
        path = agent_card.path

        # Check if path already exists
        if path in self.registered_agents:
            logger.error(f"Agent registration failed: path '{path}' already exists")
            raise ValueError(f"Agent path '{path}' already exists")

        # Set registration metadata
        if not agent_card.registered_at:
            agent_card.registered_at = datetime.now(timezone.utc)
        if not agent_card.updated_at:
            agent_card.updated_at = datetime.now(timezone.utc)

        # Save to disk
        if not _save_agent_to_disk(agent_card, settings.agents_dir):
            raise ValueError(f"Failed to save agent '{agent_card.name}' to disk")

        # Add to in-memory registry and default to disabled
        self.registered_agents[path] = agent_card
        self.agent_state["disabled"].append(path)

        # Persist state
        self._persist_state()

        logger.info(
            f"New agent registered: '{agent_card.name}' at path '{path}' "
            f"(disabled by default)"
        )

        return agent_card


    def get_agent(
        self,
        path: str,
    ) -> AgentCard:
        """
        Get agent card by path.

        Args:
            path: Agent path

        Returns:
            Agent card

        Raises:
            ValueError: If agent not found
        """
        agent = self.registered_agents.get(path)

        if not agent:
            # Try alternate form (with/without trailing slash)
            if path.endswith("/"):
                alternate_path = path.rstrip("/")
            else:
                alternate_path = path + "/"

            agent = self.registered_agents.get(alternate_path)

        if not agent:
            raise ValueError(f"Agent not found at path: {path}")

        return agent


    def list_agents(self) -> List[AgentCard]:
        """
        List all registered agents.

        Returns:
            List of all agent cards
        """
        return list(self.registered_agents.values())

    def update_rating(
        self,
        path: str,
        username: str,
        rating: int,
    ) -> float:
        """
        Log a user rating for an agent. If the user has already rated, update their rating.

        Args:
            path: Agent path
            username: The user who submitted rating
            rating: integer between 1-5

        Return:
            Updated average rating

        Raises:
            ValueError: If agent not found or invalid rating
        """
        from . import rating_service

        if path not in self.registered_agents:
            logger.error(f"Cannot update agent at path '{path}': not found")
            raise ValueError(f"Agent not found at path: {path}")

        # Validate rating using shared service
        rating_service.validate_rating(rating)

        # Get existing agent (Pydantic model)
        existing_agent = self.registered_agents[path]

        # Convert to dict for modification
        agent_dict = existing_agent.model_dump()

        # Ensure rating_details is a list
        if "rating_details" not in agent_dict or agent_dict["rating_details"] is None:
            agent_dict["rating_details"] = []

        # Update rating details using shared service
        updated_details, is_new_rating = rating_service.update_rating_details(
            agent_dict["rating_details"],
            username,
            rating
        )
        agent_dict["rating_details"] = updated_details

        # Calculate average rating using shared service
        agent_dict["num_stars"] = rating_service.calculate_average_rating(
            agent_dict["rating_details"]
        )

        # Validate updated agent
        try:
            updated_agent = AgentCard(**agent_dict)
        except Exception as e:
            logger.error(f"Failed to validate updated agent: {e}")
            raise ValueError(f"Invalid agent update: {e}")

        # Save to disk
        if not _save_agent_to_disk(updated_agent, settings.agents_dir):
            raise ValueError("Failed to save updated agent to disk")

        # Update in-memory registry
        self.registered_agents[path] = updated_agent

        logger.info(
            f"Agent '{updated_agent.name}' ({path}) updated with rating {rating} "
            f"from user {username}, new average: {agent_dict['num_stars']:.2f}"
        )

        return agent_dict["num_stars"]

    def update_agent(
        self,
        path: str,
        updates: Dict[str, Any],
    ) -> AgentCard:
        """
        Update an existing agent.

        Args:
            path: Agent path
            updates: Dictionary of fields to update

        Returns:
            Updated agent card

        Raises:
            ValueError: If agent not found
        """
        if path not in self.registered_agents:
            logger.error(f"Cannot update agent at path '{path}': not found")
            raise ValueError(f"Agent not found at path: {path}")

        # Get existing agent
        existing_agent = self.registered_agents[path]

        # Merge updates with existing data
        agent_dict = existing_agent.model_dump()
        agent_dict.update(updates)

        # Ensure path is consistent
        agent_dict["path"] = path

        # Update timestamp
        agent_dict["updated_at"] = datetime.now(timezone.utc)

        # Validate updated agent
        try:
            updated_agent = AgentCard(**agent_dict)
        except Exception as e:
            logger.error(f"Failed to validate updated agent: {e}")
            raise ValueError(f"Invalid agent update: {e}")

        # Save to disk
        if not _save_agent_to_disk(updated_agent, settings.agents_dir):
            raise ValueError(f"Failed to save updated agent to disk")

        # Update in-memory registry
        self.registered_agents[path] = updated_agent

        logger.info(f"Agent '{updated_agent.name}' ({path}) updated")

        return updated_agent


    def delete_agent(
        self,
        path: str,
    ) -> bool:
        """
        Delete an agent from registry.

        Args:
            path: Agent path

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If agent not found
        """
        if path not in self.registered_agents:
            logger.error(f"Cannot delete agent at path '{path}': not found")
            raise ValueError(f"Agent not found at path: {path}")

        try:
            # Remove from file system
            filename = _path_to_filename(path)
            file_path = settings.agents_dir / filename

            if file_path.exists():
                file_path.unlink()
                logger.info(f"Removed agent file: {file_path}")
            else:
                logger.warning(f"Agent file not found: {file_path}")

            # Remove from in-memory registry
            agent_name = self.registered_agents[path].name
            del self.registered_agents[path]

            # Remove from state
            if path in self.agent_state["enabled"]:
                self.agent_state["enabled"].remove(path)
            if path in self.agent_state["disabled"]:
                self.agent_state["disabled"].remove(path)

            # Persist updated state
            self._persist_state()

            logger.info(f"Successfully deleted agent '{agent_name}' from path '{path}'")
            return True

        except Exception as e:
            logger.error(f"Failed to delete agent at path '{path}': {e}", exc_info=True)
            raise ValueError(f"Failed to delete agent: {e}")


    def enable_agent(
        self,
        path: str,
    ) -> None:
        """
        Enable an agent.

        Args:
            path: Agent path

        Raises:
            ValueError: If agent not found
        """
        if path not in self.registered_agents:
            raise ValueError(f"Agent not found at path: {path}")

        if path in self.agent_state["enabled"]:
            logger.info(f"Agent '{path}' is already enabled")
            return

        # Move from disabled to enabled
        if path in self.agent_state["disabled"]:
            self.agent_state["disabled"].remove(path)

        self.agent_state["enabled"].append(path)

        # Persist state
        self._persist_state()

        agent_name = self.registered_agents[path].name
        logger.info(f"Enabled agent '{agent_name}' ({path})")


    def disable_agent(
        self,
        path: str,
    ) -> None:
        """
        Disable an agent.

        Args:
            path: Agent path

        Raises:
            ValueError: If agent not found
        """
        if path not in self.registered_agents:
            raise ValueError(f"Agent not found at path: {path}")

        if path in self.agent_state["disabled"]:
            logger.info(f"Agent '{path}' is already disabled")
            return

        # Move from enabled to disabled
        if path in self.agent_state["enabled"]:
            self.agent_state["enabled"].remove(path)

        self.agent_state["disabled"].append(path)

        # Persist state
        self._persist_state()

        agent_name = self.registered_agents[path].name
        logger.info(f"Disabled agent '{agent_name}' ({path})")


    def is_agent_enabled(
        self,
        path: str,
    ) -> bool:
        """
        Check if agent is enabled.

        Args:
            path: Agent path

        Returns:
            True if enabled, False otherwise
        """
        # Try exact match first
        if path in self.agent_state["enabled"]:
            return True

        # Try alternate form (with/without trailing slash)
        if path.endswith("/"):
            alternate_path = path.rstrip("/")
        else:
            alternate_path = path + "/"

        return alternate_path in self.agent_state["enabled"]


    def get_enabled_agents(self) -> List[str]:
        """
        Get list of enabled agent paths.

        Returns:
            List of enabled agent paths
        """
        return list(self.agent_state["enabled"])


    def get_disabled_agents(self) -> List[str]:
        """
        Get list of disabled agent paths.

        Returns:
            List of disabled agent paths
        """
        return list(self.agent_state["disabled"])


    async def index_agent(
        self,
        agent_card: AgentCard,
    ) -> None:
        """
        Add agent to FAISS search index.

        Args:
            agent_card: Agent card to index
        """
        try:
            from ..search.service import faiss_service

            # Prepare agent data for indexing
            agent_data = agent_card.model_dump(mode="json")

            # Add to FAISS index
            await faiss_service.add_or_update_entity(
                entity_path=agent_card.path,
                entity_info=agent_data,
                entity_type="a2a_agent",
                is_enabled=self.is_agent_enabled(agent_card.path),
            )

            logger.info(f"Indexed agent '{agent_card.name}' in FAISS")

        except Exception as e:
            logger.error(f"Failed to index agent in FAISS: {e}", exc_info=True)


    def get_agent_info(
        self,
        path: str,
    ) -> Optional[AgentCard]:
        """
        Get agent by path (returns None if not found).

        Args:
            path: Agent path

        Returns:
            Agent card or None if not found
        """
        try:
            return self.get_agent(path)
        except ValueError:
            return None


    def get_all_agents(self) -> List[AgentCard]:
        """
        Get all registered agents.

        Returns:
            List of all agent cards
        """
        return self.list_agents()


    def remove_agent(
        self,
        path: str,
    ) -> bool:
        """
        Remove an agent from registry.

        Args:
            path: Agent path

        Returns:
            True if successful, False otherwise
        """
        try:
            self.delete_agent(path)
            return True
        except ValueError:
            return False


    def toggle_agent(
        self,
        path: str,
        enabled: bool,
    ) -> bool:
        """
        Toggle agent enabled/disabled state.

        Args:
            path: Agent path
            enabled: New enabled state

        Returns:
            True if successful, False otherwise
        """
        try:
            if enabled:
                self.enable_agent(path)
            else:
                self.disable_agent(path)
            return True
        except ValueError:
            return False


# Global service instance
agent_service = AgentService()
