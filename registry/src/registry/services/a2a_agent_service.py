"""
A2A Agent Service - Business logic for A2A Agent Management API

This service handles all A2A agent-related operations using MongoDB and Beanie ODM.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from beanie import PydanticObjectId

from registry_pkgs.models.a2a_agent import A2AAgent, AgentSkill

from ..schemas.a2a_agent_api_schemas import AgentCreateRequest, AgentUpdateRequest

logger = logging.getLogger(__name__)


class A2AAgentService:
    """Service for A2A Agent operations"""

    async def list_agents(
        self,
        query: str | None = None,
        status: str | None = None,
        page: int = 1,
        per_page: int = 20,
        accessible_agent_ids: list[str] | None = None,
    ) -> tuple[list[A2AAgent], int]:
        """
        List agents with optional filtering and pagination.

        Args:
            query: Free-text search across name, description, tags, skills
            status: Filter by operational state (active, inactive, error)
            page: Page number (min: 1)
            per_page: Items per page (min: 1, max: 100)
            accessible_agent_ids: List of agent ID strings accessible to the user (from ACL)

        Returns:
            Tuple of (agents list, total count)
        """
        try:
            # Validate pagination parameters
            page = max(1, page)
            per_page = max(1, min(100, per_page))

            # Build query filters
            filters: dict[str, Any] = {}

            # Filter by accessible agent IDs (ACL)
            # If accessible_agent_ids is None, user has 'all' permission - no filtering
            # If accessible_agent_ids is an empty list, user has no access - will return empty
            if accessible_agent_ids is not None:
                # Convert string IDs to PydanticObjectId for MongoDB query
                object_ids = [PydanticObjectId(aid) for aid in accessible_agent_ids]
                filters["_id"] = {"$in": object_ids}

            # Filter by status if provided
            if status:
                filters["status"] = status

            # Build text search filter if query provided
            if query:
                # Search across name, description, tags, and skills
                filters["$or"] = [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"description": {"$regex": query, "$options": "i"}},
                    {"tags": {"$regex": query, "$options": "i"}},
                    {"skills.name": {"$regex": query, "$options": "i"}},
                    {"skills.description": {"$regex": query, "$options": "i"}},
                ]

            # Get total count
            total = await A2AAgent.find(filters).count()

            # Get paginated results
            skip = (page - 1) * per_page
            agents = await A2AAgent.find(filters).sort("-createdAt").skip(skip).limit(per_page).to_list()

            logger.info(f"Listed {len(agents)} agents (total: {total}, page: {page}, per_page: {per_page})")
            return agents, total

        except Exception as e:
            logger.error(f"Error listing agents: {e}", exc_info=True)
            raise

    async def get_stats(self) -> dict[str, Any]:
        """
        Get agent statistics.

        Returns:
            Statistics dictionary with agent counts and breakdowns
        """
        try:
            # Total counts
            total_agents = await A2AAgent.count()
            enabled_agents = await A2AAgent.find({"isEnabled": True}).count()
            disabled_agents = total_agents - enabled_agents

            # Count by status
            status_pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
            status_results = await A2AAgent.aggregate(status_pipeline).to_list()
            by_status = {result["_id"]: result["count"] for result in status_results}

            # Count by transport
            transport_pipeline = [{"$group": {"_id": "$preferredTransport", "count": {"$sum": 1}}}]
            transport_results = await A2AAgent.aggregate(transport_pipeline).to_list()
            by_transport = {result["_id"]: result["count"] for result in transport_results}

            # Total skills and average
            skills_pipeline = [
                {"$project": {"num_skills": {"$size": "$skills"}}},
                {"$group": {"_id": None, "total_skills": {"$sum": "$num_skills"}}},
            ]
            skills_results = await A2AAgent.aggregate(skills_pipeline).to_list()
            total_skills = skills_results[0]["total_skills"] if skills_results else 0
            average_skills = round(total_skills / total_agents, 1) if total_agents > 0 else 0.0

            stats = {
                "total_agents": total_agents,
                "enabled_agents": enabled_agents,
                "disabled_agents": disabled_agents,
                "by_status": by_status,
                "by_transport": by_transport,
                "total_skills": total_skills,
                "average_skills_per_agent": average_skills,
            }

            logger.info(f"Agent stats: {total_agents} total, {enabled_agents} enabled")
            return stats

        except Exception as e:
            logger.error(f"Error getting agent stats: {e}", exc_info=True)
            raise

    async def get_agent_by_id(self, agent_id: str) -> A2AAgent | None:
        """
        Get agent by ID.

        Args:
            agent_id: Agent ID

        Returns:
            Agent document or None if not found
        """
        try:
            agent = await A2AAgent.get(PydanticObjectId(agent_id))
            if agent:
                logger.debug(f"Retrieved agent: {agent.name} (ID: {agent_id})")
            return agent
        except Exception as e:
            logger.error(f"Error getting agent {agent_id}: {e}", exc_info=True)
            return None

    async def create_agent(self, data: AgentCreateRequest, user_id: str) -> A2AAgent:
        """
        Create a new agent.

        Args:
            data: Agent creation data
            user_id: User ID who creates the agent

        Returns:
            Created agent document

        Raises:
            ValueError: If path already exists or validation fails
        """
        try:
            # Check if path already exists
            existing = await A2AAgent.find_one({"path": data.path})
            if existing:
                raise ValueError(f"Agent with path '{data.path}' already exists")

            # Convert skills
            skills = [
                AgentSkill(
                    id=skill.id,
                    name=skill.name,
                    description=skill.description,
                    tags=skill.tags,
                    examples=skill.examples,
                    inputModes=skill.input_modes,
                    outputModes=skill.output_modes,
                    security=skill.security,
                )
                for skill in data.skills
            ]

            # Create provider
            provider = None
            if data.provider:
                from registry_pkgs.models.a2a_agent import AgentProvider

                provider = AgentProvider(organization=data.provider.organization, url=data.provider.url)

            # Create agent document
            agent = A2AAgent(
                path=data.path,
                name=data.name,
                description=data.description,
                url=data.url,
                version=data.version,
                protocolVersion=data.protocol_version,
                capabilities=data.capabilities,
                skills=skills,
                securitySchemes=data.security_schemes,
                preferredTransport=data.preferred_transport,
                defaultInputModes=data.default_input_modes,
                defaultOutputModes=data.default_output_modes,
                provider=provider,
                tags=data.tags,
                isEnabled=data.enabled,
                author=PydanticObjectId(user_id),
                registeredBy=None,  # Will be set from user context if needed
                registeredAt=datetime.now(UTC),
            )

            # Save to database
            await agent.insert()
            logger.info(f"Created agent: {agent.name} (ID: {agent.id}, path: {agent.path})")
            return agent

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error creating agent: {e}", exc_info=True)
            raise ValueError(f"Failed to create agent: {str(e)}")

    async def update_agent(self, agent_id: str, data: AgentUpdateRequest) -> A2AAgent:
        """
        Update an existing agent.

        Args:
            agent_id: Agent ID
            data: Agent update data (partial)

        Returns:
            Updated agent document

        Raises:
            ValueError: If agent not found or validation fails
        """
        try:
            agent = await A2AAgent.get(PydanticObjectId(agent_id))
            if not agent:
                raise ValueError(f"Agent not found: {agent_id}")

            # Update fields if provided
            update_data = data.model_dump(exclude_unset=True, by_alias=False)

            # Handle skills update
            if "skills" in update_data and update_data["skills"] is not None:
                skills = [
                    AgentSkill(
                        id=skill.id,
                        name=skill.name,
                        description=skill.description,
                        tags=skill.tags,
                        examples=skill.examples,
                        inputModes=skill.input_modes,
                        outputModes=skill.output_modes,
                        security=skill.security,
                    )
                    for skill in data.skills
                ]
                agent.skills = skills
                del update_data["skills"]

            # Handle provider update
            if "provider" in update_data and update_data["provider"] is not None:
                from registry_pkgs.models.a2a_agent import AgentProvider

                agent.provider = AgentProvider(organization=data.provider.organization, url=data.provider.url)
                del update_data["provider"]

            # Update other fields
            for key, value in update_data.items():
                # Convert camelCase to snake_case for model fields
                model_key = key
                if key == "security_schemes":
                    model_key = "securitySchemes"
                elif key == "preferred_transport":
                    model_key = "preferredTransport"
                elif key == "default_input_modes":
                    model_key = "defaultInputModes"
                elif key == "default_output_modes":
                    model_key = "defaultOutputModes"
                elif key == "enabled":
                    model_key = "isEnabled"

                if hasattr(agent, model_key):
                    setattr(agent, model_key, value)

            # Update timestamp
            agent.updatedAt = datetime.now(UTC)

            # Save changes
            await agent.save()
            logger.info(f"Updated agent: {agent.name} (ID: {agent_id})")
            return agent

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error updating agent {agent_id}: {e}", exc_info=True)
            raise ValueError(f"Failed to update agent: {str(e)}")

    async def delete_agent(self, agent_id: str) -> bool:
        """
        Delete an agent.

        Args:
            agent_id: Agent ID

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If agent not found
        """
        try:
            agent = await A2AAgent.get(PydanticObjectId(agent_id))
            if not agent:
                raise ValueError(f"Agent not found: {agent_id}")

            await agent.delete()
            logger.info(f"Deleted agent: {agent.name} (ID: {agent_id})")
            return True

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error deleting agent {agent_id}: {e}", exc_info=True)
            raise ValueError(f"Failed to delete agent: {str(e)}")

    async def toggle_agent_status(self, agent_id: str, enabled: bool) -> A2AAgent:
        """
        Toggle agent enabled/disabled status.

        Args:
            agent_id: Agent ID
            enabled: New enabled state

        Returns:
            Updated agent document

        Raises:
            ValueError: If agent not found
        """
        try:
            agent = await A2AAgent.get(PydanticObjectId(agent_id))
            if not agent:
                raise ValueError(f"Agent not found: {agent_id}")

            agent.isEnabled = enabled
            agent.updatedAt = datetime.now(UTC)
            await agent.save()

            logger.info(f"Toggled agent {agent.name} to {'enabled' if enabled else 'disabled'}")
            return agent

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error toggling agent {agent_id}: {e}", exc_info=True)
            raise ValueError(f"Failed to toggle agent: {str(e)}")

    async def sync_wellknown(self, agent_id: str) -> dict[str, Any]:
        """
        Sync agent configuration from .well-known/agent-card.json endpoint.

        Args:
            agent_id: Agent ID

        Returns:
            Sync result with status and changes

        Raises:
            ValueError: If agent not found, well-known not enabled, or sync fails
        """
        try:
            agent = await A2AAgent.get(PydanticObjectId(agent_id))
            if not agent:
                raise ValueError(f"Agent not found: {agent_id}")

            # Check if well-known is enabled
            if not agent.wellKnown or not agent.wellKnown.enabled:
                raise ValueError("Well-known sync is not enabled for this agent")

            if not agent.wellKnown.url:
                raise ValueError("Well-known URL is not configured")

            # Fetch agent card from well-known endpoint
            logger.info(f"Fetching agent card from {agent.wellKnown.url}")
            timeout = httpx.Timeout(10.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(str(agent.wellKnown.url))
                response.raise_for_status()
                agent_card = response.json()

            # Track changes
            changes = []

            # Update version if changed
            old_version = agent.version
            new_version = agent_card.get("version", agent.version)
            if old_version != new_version:
                agent.version = new_version
                changes.append(f"Updated version from {old_version} to {new_version}")

            # Update description if changed
            old_description = agent.description
            new_description = agent_card.get("description", agent.description)
            if old_description != new_description:
                agent.description = new_description
                changes.append("Updated description")

            # Update skills if changed
            old_skill_count = len(agent.skills)
            new_skills_data = agent_card.get("skills", [])
            if new_skills_data:
                new_skills = [
                    AgentSkill(
                        id=skill.get("id"),
                        name=skill.get("name"),
                        description=skill.get("description", ""),
                        tags=skill.get("tags", []),
                        examples=skill.get("examples"),
                        inputModes=skill.get("inputModes"),
                        outputModes=skill.get("outputModes"),
                        security=skill.get("security"),
                    )
                    for skill in new_skills_data
                ]
                agent.skills = new_skills
                if len(new_skills) != old_skill_count:
                    changes.append(f"Updated skills count from {old_skill_count} to {len(new_skills)}")

            # Update capabilities if changed
            new_capabilities = agent_card.get("capabilities", {})
            if new_capabilities and new_capabilities != agent.capabilities:
                agent.capabilities = new_capabilities
                changes.append("Updated capabilities")

            # Update well-known sync metadata
            agent.wellKnown.lastSyncAt = datetime.now(UTC)
            agent.wellKnown.lastSyncStatus = "success"
            agent.wellKnown.lastSyncVersion = new_version
            agent.wellKnown.syncError = None

            # Update timestamp
            agent.updatedAt = datetime.now(UTC)

            # Save changes
            await agent.save()

            logger.info(f"Successfully synced agent {agent.name} from well-known endpoint: {len(changes)} changes")

            return {
                "message": "Well-known configuration synced successfully",
                "sync_status": "success",
                "synced_at": agent.wellKnown.lastSyncAt,
                "version": new_version,
                "changes": changes if changes else ["No changes detected"],
            }

        except httpx.HTTPError as e:
            # Update sync error status
            if agent and agent.wellKnown:
                agent.wellKnown.lastSyncStatus = "failed"
                agent.wellKnown.syncError = f"HTTP error: {str(e)}"
                await agent.save()

            logger.error(f"HTTP error syncing agent {agent_id}: {e}", exc_info=True)
            raise ValueError(f"Failed to fetch agent card: {str(e)}")

        except ValueError:
            raise
        except Exception as e:
            # Update sync error status
            if agent and agent.wellKnown:
                agent.wellKnown.lastSyncStatus = "failed"
                agent.wellKnown.syncError = str(e)
                await agent.save()

            logger.error(f"Error syncing agent {agent_id}: {e}", exc_info=True)
            raise ValueError(f"Failed to sync well-known configuration: {str(e)}")


# Singleton instance
a2a_agent_service = A2AAgentService()
