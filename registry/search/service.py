import json
import asyncio
import logging
from datetime import datetime
import re
from pathlib import Path
from typing import (
    Dict,
    Any,
    Optional,
    List,
    Tuple
)

import faiss
import numpy as np
from pydantic import HttpUrl

from ..core.config import settings
from ..core.schemas import ServerInfo
from ..schemas.agent_models import AgentCard
from ..embeddings import (
    EmbeddingsClient,
    create_embeddings_client,
)

logger = logging.getLogger(__name__)


class _PydanticAwareJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Pydantic and standard types."""

    def default(
        self,
        o: Any,
    ) -> Any:
        """Convert non-serializable types to JSON-compatible formats."""
        if isinstance(o, HttpUrl):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


class FaissService:
    """Service for managing FAISS vector database operations."""

    def __init__(self):
        self.embedding_model: Optional[EmbeddingsClient] = None
        self.faiss_index: Optional[faiss.IndexIDMap] = None
        self.metadata_store: Dict[str, Dict[str, Any]] = {}
        self.next_id_counter: int = 0
        
    async def initialize(self):
        """Initialize the FAISS service - load model and index."""
        await self._load_embedding_model()
        await self._load_faiss_data()
        
    async def _load_embedding_model(self):
        """Load the embeddings model using the configured provider."""
        logger.info(
            f"Loading embedding model with provider: {settings.embeddings_provider}"
        )

        # Ensure servers directory exists
        settings.servers_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Prepare cache directory for sentence-transformers
            model_cache_path = settings.container_registry_dir / ".cache"
            model_cache_path.mkdir(parents=True, exist_ok=True)

            # Create embeddings client using factory
            self.embedding_model = create_embeddings_client(
                provider=settings.embeddings_provider,
                model_name=settings.embeddings_model_name,
                model_dir=settings.embeddings_model_dir
                if settings.embeddings_provider == "sentence-transformers"
                else None,
                cache_dir=model_cache_path
                if settings.embeddings_provider == "sentence-transformers"
                else None,
                api_key=settings.embeddings_api_key
                if settings.embeddings_provider == "litellm"
                else None,
                api_base=settings.embeddings_api_base
                if settings.embeddings_provider == "litellm"
                else None,
                aws_region=settings.embeddings_aws_region
                if settings.embeddings_provider == "litellm"
                else None,
                embedding_dimension=settings.embeddings_model_dimensions,
            )

            # Get and log the embedding dimension
            embedding_dim = self.embedding_model.get_embedding_dimension()
            logger.info(
                f"Embedding model loaded successfully. Provider: {settings.embeddings_provider}, "
                f"Model: {settings.embeddings_model_name}, Dimension: {embedding_dim}"
            )

            # Warn if dimension doesn't match configuration
            if embedding_dim != settings.embeddings_model_dimensions:
                logger.warning(
                    f"Embedding dimension mismatch: configured={settings.embeddings_model_dimensions}, "
                    f"actual={embedding_dim}. Using actual dimension."
                )
                settings.embeddings_model_dimensions = embedding_dim

        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}", exc_info=True)
            self.embedding_model = None
            
    async def _load_faiss_data(self):
        """Load existing FAISS index and metadata or create new ones."""
        if settings.faiss_index_path.exists() and settings.faiss_metadata_path.exists():
            try:
                logger.info(f"Loading FAISS index from {settings.faiss_index_path}")
                self.faiss_index = faiss.read_index(str(settings.faiss_index_path))
                
                logger.info(f"Loading FAISS metadata from {settings.faiss_metadata_path}")
                with open(settings.faiss_metadata_path, "r") as f:
                    loaded_metadata = json.load(f)
                    self.metadata_store = loaded_metadata.get("metadata", {})
                    self.next_id_counter = loaded_metadata.get("next_id", 0)
                    
                logger.info(f"FAISS data loaded. Index size: {self.faiss_index.ntotal if self.faiss_index else 0}. Next ID: {self.next_id_counter}")
                
                # Check dimension compatibility
                if self.faiss_index and self.faiss_index.d != settings.embeddings_model_dimensions:
                    logger.warning(f"Loaded FAISS index dimension ({self.faiss_index.d}) differs from expected ({settings.embeddings_model_dimensions}). Re-initializing.")
                    self._initialize_new_index()
                    
            except Exception as e:
                logger.error(f"Error loading FAISS data: {e}. Re-initializing.", exc_info=True)
                self._initialize_new_index()
        else:
            logger.info("FAISS index or metadata not found. Initializing new.")
            self._initialize_new_index()
            
    def _initialize_new_index(self):
        """Initialize a new FAISS index with Inner Product (IP) for cosine similarity.

        Uses IndexFlatIP instead of IndexFlatL2 to enable cosine similarity search.
        When embeddings are normalized to unit length, inner product equals cosine similarity.
        """
        self.faiss_index = faiss.IndexIDMap(faiss.IndexFlatIP(settings.embeddings_model_dimensions))
        self.metadata_store = {}
        self.next_id_counter = 0
        logger.info(f"Initialized FAISS IndexFlatIP with {settings.embeddings_model_dimensions} dimensions for cosine similarity")
        
    async def save_data(self):
        """Save FAISS index and metadata to disk."""
        if self.faiss_index is None:
            logger.error("FAISS index is not initialized. Cannot save.")
            return
            
        try:
            # Ensure directory exists
            settings.servers_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Saving FAISS index to {settings.faiss_index_path} (Size: {self.faiss_index.ntotal})")
            faiss.write_index(self.faiss_index, str(settings.faiss_index_path))
            
            logger.info(f"Saving FAISS metadata to {settings.faiss_metadata_path}")
            with open(settings.faiss_metadata_path, "w") as f:
                json.dump({
                    "metadata": self.metadata_store,
                    "next_id": self.next_id_counter
                }, f, indent=2, cls=_PydanticAwareJSONEncoder)
                
            logger.info("FAISS data saved successfully.")
        except Exception as e:
            logger.error(f"Error saving FAISS data: {e}", exc_info=True)
            
    def _get_text_for_embedding(self, server_info: Dict[str, Any]) -> str:
        """Prepare text string from server info (including tools) for embedding."""
        name = server_info.get("server_name", "")
        description = server_info.get("description", "")
        tags = server_info.get("tags", [])
        tag_string = ", ".join(tags)
        tool_list = server_info.get("tool_list") or []
        tool_snippets = []
        for tool in tool_list:
            tool_name = tool.get("name", "")
            parsed_description = tool.get("parsed_description", {}) or {}
            tool_desc = parsed_description.get("main") or tool.get("description", "")
            tool_args = parsed_description.get("args", "")
            snippet = f"Tool: {tool_name}. Description: {tool_desc}. Args: {tool_args}"
            tool_snippets.append(snippet.strip())

        tools_section = "\n".join(tool_snippets)
        return (
            f"Name: {name}\n"
            f"Description: {description}\n"
            f"Tags: {tag_string}\n"
            f"Tools:\n{tools_section}"
        ).strip()

    def _get_text_for_agent(self, agent_card: AgentCard) -> str:
        """Prepare text string from agent card for embedding."""
        name = agent_card.name
        description = agent_card.description

        skills_text = ""
        if agent_card.skills:
            skill_names = [skill.name for skill in agent_card.skills]
            skill_descriptions = [
                f"{skill.name}: {skill.description}"
                for skill in agent_card.skills
            ]
            skills_text = "Skills: " + ", ".join(skill_names)
            skills_text += "\nSkill Details: " + " | ".join(skill_descriptions)

        tags = agent_card.tags
        tag_string = ", ".join(tags) if tags else ""

        text_parts = [
            f"Name: {name}",
            f"Description: {description}",
        ]

        if skills_text:
            text_parts.append(skills_text)

        if tag_string:
            text_parts.append(f"Tags: {tag_string}")

        return "\n".join(text_parts)

        
    async def add_or_update_service(self, service_path: str, server_info: Dict[str, Any], is_enabled: bool = False):
        """Add or update a service in the FAISS index."""
        if self.embedding_model is None or self.faiss_index is None:
            logger.error("Embedding model or FAISS index not initialized. Cannot add/update service in FAISS.")
            return
            
        logger.info(f"Attempting to add/update service '{service_path}' in FAISS.")
        text_to_embed = self._get_text_for_embedding(server_info)
        
        current_faiss_id = -1
        needs_new_embedding = True
        
        existing_entry = self.metadata_store.get(service_path)
        
        if existing_entry:
            current_faiss_id = existing_entry["id"]
            if existing_entry.get("text_for_embedding") == text_to_embed:
                needs_new_embedding = False
                logger.info(f"Text for embedding for '{service_path}' has not changed. Will update metadata store only if server_info differs.")
            else:
                logger.info(f"Text for embedding for '{service_path}' has changed. Re-embedding required.")
        else:
            # New service
            current_faiss_id = self.next_id_counter
            self.next_id_counter += 1
            logger.info(f"New service '{service_path}'. Assigning new FAISS ID: {current_faiss_id}.")
            needs_new_embedding = True
            
        if needs_new_embedding:
            try:
                # Run model encoding in a separate thread
                embedding = await asyncio.to_thread(self.embedding_model.encode, [text_to_embed])
                embedding_np = np.array([embedding[0]], dtype=np.float32)

                # Normalize embedding for cosine similarity (IndexFlatIP)
                normalized_embedding = self._normalize_embedding(embedding_np[0])
                embedding_np = np.array([normalized_embedding], dtype=np.float32)
                logger.debug(f"Normalized embedding for '{service_path}' (norm check: {np.linalg.norm(normalized_embedding):.4f})")

                ids_to_remove = np.array([current_faiss_id])
                if existing_entry:
                    try:
                        num_removed = self.faiss_index.remove_ids(ids_to_remove)
                        if num_removed > 0:
                            logger.info(f"Removed {num_removed} old vector(s) for FAISS ID {current_faiss_id} ({service_path}).")
                        else:
                            logger.info(f"No old vector found for FAISS ID {current_faiss_id} ({service_path}) during update, or ID not in index.")
                    except Exception as e_remove:
                        logger.warning(f"Issue removing FAISS ID {current_faiss_id} for {service_path}: {e_remove}. Proceeding to add.")
                
                self.faiss_index.add_with_ids(embedding_np, np.array([current_faiss_id]))
                logger.info(f"Added/Updated vector for '{service_path}' with FAISS ID {current_faiss_id}.")
            except Exception as e:
                logger.error(f"Error encoding or adding embedding for '{service_path}': {e}", exc_info=True)
                return
                
        # Update metadata store
        enriched_server_info = server_info.copy()
        enriched_server_info["is_enabled"] = is_enabled

        if (
            existing_entry is None
            or needs_new_embedding
            or existing_entry.get("full_server_info") != enriched_server_info
        ):

            self.metadata_store[service_path] = {
                "id": current_faiss_id,
                "text_for_embedding": text_to_embed,
                "full_server_info": enriched_server_info,
                "entity_type": server_info.get("entity_type", "mcp_server")
            }
            logger.debug(f"Updated faiss_metadata_store for '{service_path}'.")
            await self.save_data()
        else:
            logger.debug(
                f"No changes to FAISS vector or enriched full_server_info for '{service_path}'. Skipping save."
            )


    async def remove_service(self, service_path: str):
        """Remove a service from the FAISS index and metadata store."""
        try:
            # Check if service exists in metadata
            if service_path not in self.metadata_store:
                logger.warning(f"Service '{service_path}' not found in FAISS metadata store")
                return

            # Get the FAISS ID for this service
            service_id = self.metadata_store[service_path].get("id")
            if service_id is not None and self.faiss_index:
                # Remove from FAISS index
                # Note: FAISS doesn't support direct removal, but we can remove from metadata
                # The vector will remain in the index but won't be accessible via metadata
                logger.info(
                    f"Removing service '{service_path}' with FAISS ID {service_id} from index"
                )

            # Remove from metadata store
            del self.metadata_store[service_path]
            logger.info(f"Removed service '{service_path}' from FAISS metadata store")

            # Save the updated metadata
            await self.save_data()

        except Exception as e:
            logger.error(
                f"Failed to remove service '{service_path}' from FAISS: {e}",
                exc_info=True,
            )

    async def add_or_update_agent(
        self,
        agent_path: str,
        agent_card: AgentCard,
        is_enabled: bool = False,
    ) -> None:
        """Add or update an agent in the FAISS index."""
        if self.embedding_model is None or self.faiss_index is None:
            logger.error(
                "Embedding model or FAISS index not initialized. Cannot add/update agent in FAISS."
            )
            return

        logger.info(f"Attempting to add/update agent '{agent_path}' in FAISS.")
        text_to_embed = self._get_text_for_agent(agent_card)

        current_faiss_id = -1
        needs_new_embedding = True

        existing_entry = self.metadata_store.get(agent_path)

        if existing_entry:
            current_faiss_id = existing_entry["id"]
            if existing_entry.get("text_for_embedding") == text_to_embed:
                needs_new_embedding = False
                logger.info(
                    f"Text for embedding for '{agent_path}' has not changed. Will update metadata store only if agent_card differs."
                )
            else:
                logger.info(
                    f"Text for embedding for '{agent_path}' has changed. Re-embedding required."
                )
        else:
            # New agent
            current_faiss_id = self.next_id_counter
            self.next_id_counter += 1
            logger.info(
                f"New agent '{agent_path}'. Assigning new FAISS ID: {current_faiss_id}."
            )
            needs_new_embedding = True

        if needs_new_embedding:
            try:
                # Run model encoding in a separate thread
                embedding = await asyncio.to_thread(
                    self.embedding_model.encode,
                    [text_to_embed],
                )
                embedding_np = np.array([embedding[0]], dtype=np.float32)

                # Normalize embedding for cosine similarity (IndexFlatIP)
                normalized_embedding = self._normalize_embedding(embedding_np[0])
                embedding_np = np.array([normalized_embedding], dtype=np.float32)
                logger.debug(f"Normalized embedding for '{agent_path}' (norm check: {np.linalg.norm(normalized_embedding):.4f})")

                ids_to_remove = np.array([current_faiss_id])
                if existing_entry:
                    try:
                        num_removed = self.faiss_index.remove_ids(ids_to_remove)
                        if num_removed > 0:
                            logger.info(
                                f"Removed {num_removed} old vector(s) for FAISS ID {current_faiss_id} ({agent_path})."
                            )
                        else:
                            logger.info(
                                f"No old vector found for FAISS ID {current_faiss_id} ({agent_path}) during update, or ID not in index."
                            )
                    except Exception as e_remove:
                        logger.warning(
                            f"Issue removing FAISS ID {current_faiss_id} for {agent_path}: {e_remove}. Proceeding to add."
                        )

                self.faiss_index.add_with_ids(
                    embedding_np,
                    np.array([current_faiss_id]),
                )
                logger.info(
                    f"Added/Updated vector for '{agent_path}' with FAISS ID {current_faiss_id}."
                )
            except Exception as e:
                logger.error(
                    f"Error encoding or adding embedding for '{agent_path}': {e}",
                    exc_info=True,
                )
                return

        # Update metadata store
        agent_card_dict = agent_card.model_dump()

        if (
            existing_entry is None
            or needs_new_embedding
            or existing_entry.get("full_agent_card") != agent_card_dict
        ):

            self.metadata_store[agent_path] = {
                "id": current_faiss_id,
                "entity_type": "a2a_agent",
                "text_for_embedding": text_to_embed,
                "full_agent_card": agent_card_dict,
            }
            logger.debug(f"Updated faiss_metadata_store for agent '{agent_path}'.")
            await self.save_data()
        else:
            logger.debug(
                f"No changes to FAISS vector or agent card for '{agent_path}'. Skipping save."
            )

    async def remove_agent(self, agent_path: str) -> None:
        """Remove an agent from the FAISS index and metadata store."""
        try:
            # Check if agent exists in metadata
            if agent_path not in self.metadata_store:
                logger.warning(
                    f"Agent '{agent_path}' not found in FAISS metadata store"
                )
                return

            # Get the FAISS ID for this agent
            agent_id = self.metadata_store[agent_path].get("id")
            if agent_id is not None and self.faiss_index:
                logger.info(
                    f"Removing agent '{agent_path}' with FAISS ID {agent_id} from index"
                )

            # Remove from metadata store
            del self.metadata_store[agent_path]
            logger.info(f"Removed agent '{agent_path}' from FAISS metadata store")

            # Save the updated metadata
            await self.save_data()

        except Exception as e:
            logger.error(
                f"Failed to remove agent '{agent_path}' from FAISS: {e}",
                exc_info=True,
            )

    async def search_agents(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search for agents in the FAISS index."""
        results = await self.search_mixed(
            query=query,
            entity_types=["a2a_agent"],
            max_results=max_results,
        )
        return results.get("agents", [])


    async def add_or_update_entity(
        self,
        entity_path: str,
        entity_info: Dict[str, Any],
        entity_type: str,
        is_enabled: bool = False,
    ) -> None:
        """
        Wrapper method for adding or updating an entity.

        Routes agents to appropriate methods based on entity_type.
        """
        if entity_type == "a2a_agent":
            agent_card = AgentCard(**entity_info)
            await self.add_or_update_agent(entity_path, agent_card, is_enabled)
        elif entity_type == "mcp_server":
            await self.add_or_update_service(entity_path, entity_info, is_enabled)


    async def remove_entity(
        self,
        entity_path: str,
    ) -> None:
        """
        Wrapper method for removing an entity.

        Attempts to remove as agent first, then server.
        """
        try:
            await self.remove_agent(entity_path)
        except Exception:
            try:
                await self.remove_service(entity_path)
            except Exception as e:
                logger.warning(f"Could not remove entity {entity_path}: {e}")


    async def search_entities(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        enabled_only: bool = False,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Wrapper method for searching entities.

        Searches both agents and servers, returns list of matching entities.
        """
        if entity_types is None:
            entity_types = ["a2a_agent", "mcp_server", "tool"]

        results = await self.search_mixed(
            query=query,
            entity_types=entity_types,
            max_results=max_results,
        )

        combined: List[Dict[str, Any]] = []
        requested = set(entity_types)

        if "agents" in results and "a2a_agent" in requested:
            for agent in results["agents"]:
                if enabled_only and not agent.get("is_enabled", False):
                    continue
                combined.append(agent)

        if "servers" in results and "mcp_server" in requested:
            for server in results["servers"]:
                if enabled_only and not server.get("is_enabled", False):
                    continue
                combined.append(server)

        if "tools" in results and "tool" in requested:
            combined.extend(results["tools"])

        return combined[:max_results]


    def _distance_to_relevance(self, distance: float) -> float:
        """Convert FAISS Inner Product distance to cosine similarity score (0-1).

        FAISS IndexFlatIP behavior depends on index configuration:
        - Standard IndexFlatIP: Returns (1 - inner_product) as distance
          Example: inner_product=0.95 → distance=0.05 → similarity=0.95
        - With negated scores: Returns -inner_product as distance
          Example: inner_product=0.95 → distance=-0.95 → similarity=0.95

        For normalized vectors: inner_product = cosine_similarity

        This function handles both cases:
        - Positive distances (0 to 1): similarity = 1 - distance
        - Negative distances (-1 to 0): similarity = -distance

        Expected behavior:
        - distance=0.05 → similarity=0.95 (95% match)
        - distance=-0.95 → similarity=0.95 (95% match)
        - distance=0.50 → similarity=0.50 (50% match)
        - distance=-0.50 → similarity=0.50 (50% match)

        Args:
            distance: Distance from FAISS IndexFlatIP

        Returns:
            Cosine similarity score in range 0-1
        """
        try:
            dist = float(distance)

            # Handle both positive and negative distance conventions
            if dist < 0:
                # Negative distance: negate to get similarity
                similarity = -dist
            else:
                # Positive distance: convert from (1-IP) to similarity
                similarity = 1.0 - dist

            # Clamp to 0-1 range (handle edge cases)
            clamped_similarity = max(0.0, min(1.0, similarity))

            # Log conversion for debugging
            logger.info(
                f"IP-to-similarity conversion: "
                f"faiss_distance={distance:.4f}, similarity={similarity:.4f}, "
                f"clamped={clamped_similarity:.4f}, percentage={clamped_similarity*100:.1f}%"
            )

            return clamped_similarity
        except Exception as e:
            logger.error(
                f"Error in _distance_to_relevance: faiss_distance={distance}, "
                f"exception={str(e)}",
                exc_info=True
            )
            return 0.0


    def _normalize_embedding(
        self,
        embedding: np.ndarray,
    ) -> np.ndarray:
        """Normalize embedding vector to unit length for cosine similarity.

        Converts any embedding vector to unit length (L2 norm = 1).
        This allows FAISS IndexFlatIP to compute cosine similarity via inner product.

        Args:
            embedding: Input embedding vector (numpy array)

        Returns:
            Normalized embedding with L2 norm = 1
        """
        norm = np.linalg.norm(embedding)
        if norm == 0:
            logger.warning("Zero-norm embedding detected, returning as-is")
            return embedding
        return embedding / norm


    def _calculate_keyword_boost(
        self,
        query: str,
        server_info: Dict[str, Any],
    ) -> float:
        """Calculate keyword match boost for hybrid search.

        Boosts semantic similarity score when query keywords appear in:
        - Server name (highest boost)
        - Tool names (high boost)
        - Tags (medium boost)
        - Description (low boost)

        Args:
            query: Search query
            server_info: Server information dict

        Returns:
            Boost multiplier (1.0 = no boost, up to 2.0 = maximum boost)
        """
        # Filter out stopwords to prevent false matches
        stopwords = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "can", "to", "of", "in", "on", "at", "by",
            "for", "with", "about", "as", "into", "through", "from", "what", "when",
            "where", "who", "which", "how", "why", "get", "set", "put"
        }

        query_lower = query.lower()
        query_tokens = set(
            token for token in re.split(r"\W+", query_lower)
            if token and len(token) > 2 and token not in stopwords
        )

        if not query_tokens:
            return 1.0

        boost = 1.0
        boost_reasons = []

        # Server name exact match: +0.5 boost
        server_name = server_info.get("server_name", "").lower()
        if any(token in server_name for token in query_tokens):
            boost += 0.5
            boost_reasons.append(f"name({server_name}):+0.5")

        # Tool name matches: +0.3 boost per matching tool (max +0.6)
        tools = server_info.get("tool_list") or []
        tool_matches = 0
        matching_tool_names = []
        for tool in tools:
            tool_name = tool.get("name", "").lower()
            if any(token in tool_name for token in query_tokens):
                tool_matches += 1
                matching_tool_names.append(tool_name)

        tool_boost = min(0.6, tool_matches * 0.3)
        if tool_boost > 0:
            boost += tool_boost
            boost_reasons.append(f"tools({','.join(matching_tool_names[:2])}):+{tool_boost:.1f}")

        # Tag matches: +0.2 boost per matching tag (max +0.4)
        tags = server_info.get("tags", [])
        tag_matches = sum(1 for tag in tags if any(token in tag.lower() for token in query_tokens))
        tag_boost = min(0.4, tag_matches * 0.2)
        if tag_boost > 0:
            boost += tag_boost
            boost_reasons.append(f"tags:{tag_matches}:+{tag_boost:.1f}")

        # Description keyword density: +0.1 to +0.2 based on match ratio
        description = server_info.get("description", "").lower()
        if description:
            desc_matches = sum(1 for token in query_tokens if token in description)
            match_ratio = desc_matches / len(query_tokens)
            desc_boost = match_ratio * 0.2
            if desc_boost > 0.01:  # Only log if significant
                boost += desc_boost
                boost_reasons.append(f"desc:{desc_matches}/{len(query_tokens)}:+{desc_boost:.2f}")

        # Log boost reasoning if there's any boost
        if boost_reasons:
            logger.info(f"  Keyword boost breakdown: {' | '.join(boost_reasons)}")

        # Cap total boost at 2.0 (100% increase)
        return min(2.0, boost)


    def _extract_matching_tools(self, query: str, server_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract tool matches using simple keyword overlap."""
        tools = server_info.get("tool_list") or []
        if not tools:
            return []

        # Filter out stopwords and short tokens to improve matching quality
        stopwords = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "can", "to", "of", "in", "on", "at", "by",
            "for", "with", "about", "as", "into", "through", "from", "what", "when",
            "where", "who", "which", "how", "why", "get", "set", "put"
        }

        tokens = [
            token for token in re.split(r"\W+", query.lower())
            if token and len(token) > 2 and token not in stopwords
        ]
        if not tokens:
            return []

        matches: List[Tuple[float, Dict[str, Any]]] = []
        for tool in tools:
            tool_name = tool.get("name", "")
            parsed_description = tool.get("parsed_description", {}) or {}
            tool_desc = (
                parsed_description.get("main")
                or tool.get("description")
                or parsed_description.get("summary")
                or ""
            )
            tool_args = parsed_description.get("args") or ""

            # Ensure all values are strings to avoid NoneType errors
            tool_name = tool_name or ""
            tool_desc = tool_desc or ""
            tool_args = tool_args or ""

            searchable_text = f"{tool_name} {tool_desc} {tool_args}".lower()
            if not searchable_text.strip():
                continue

            # Calculate matches with higher weight for tool name matches
            tool_name_lower = tool_name.lower()
            name_matches = sum(1 for token in tokens if token in tool_name_lower)
            desc_matches = sum(1 for token in tokens if token in tool_desc.lower() or token in tool_args.lower())

            # Weight tool name matches more heavily (2x)
            weighted_matches = (name_matches * 2.0) + desc_matches
            max_possible_score = len(tokens) * 2.0  # If all tokens match in name

            if weighted_matches == 0:
                continue

            # Normalize to 0-1 range, with name matches getting higher scores
            coverage = min(1.0, weighted_matches / max_possible_score)
            matches.append(
                (
                    coverage,
                    {
                        "tool_name": tool_name,
                        "description": tool_desc,
                        "match_context": (tool_desc or tool_args or "")[:180],
                        "schema": tool.get("schema", {}),
                        "raw_score": coverage,
                    },
                )
            )

        matches.sort(key=lambda item: item[0], reverse=True)
        return [match for _, match in matches]

    async def search_mixed(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        max_results: int = 20,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Run a semantic search across MCP servers, their tools, and A2A agents.

        Args:
            query: Natural language query text
            entity_types: Optional list of entity filters ("mcp_server", "tool", "a2a_agent")
            max_results: Maximum results to return per entity collection

        Returns:
            Dict with "servers", "tools", and "agents" result lists
        """
        if not query or not query.strip():
            raise ValueError("Query text is required for semantic search")

        if self.embedding_model is None or self.faiss_index is None:
            raise RuntimeError("FAISS search service is not initialized")

        max_results = max(1, min(max_results, 50))
        requested_entity_types = set(entity_types or ["mcp_server", "tool", "a2a_agent"])
        allowed_entity_types = {"mcp_server", "tool", "a2a_agent"}
        entity_filter = requested_entity_types & allowed_entity_types
        if not entity_filter:
            entity_filter = allowed_entity_types

        total_vectors = self.faiss_index.ntotal if self.faiss_index else 0
        if total_vectors == 0:
            return {"servers": [], "tools": [], "agents": []}

        top_k = min(max_results, total_vectors)
        query_embedding = await asyncio.to_thread(
            self.embedding_model.encode, [query.strip()]
        )
        query_np = np.array([query_embedding[0]], dtype=np.float32)

        # Normalize query embedding for cosine similarity (IndexFlatIP)
        normalized_query = self._normalize_embedding(query_np[0])
        query_np = np.array([normalized_query], dtype=np.float32)
        logger.debug(f"Normalized query embedding (norm check: {np.linalg.norm(normalized_query):.4f})")

        distances, indices = self.faiss_index.search(query_np, top_k)
        distance_row = distances[0]
        id_row = indices[0]

        id_to_path = {
            entry.get("id"): path for path, entry in self.metadata_store.items()
        }

        server_results: List[Dict[str, Any]] = []
        tool_results: List[Dict[str, Any]] = []
        agent_results: List[Dict[str, Any]] = []

        for distance, faiss_id in zip(distance_row, id_row):
            if faiss_id == -1:
                continue

            path = id_to_path.get(int(faiss_id))
            if not path:
                continue

            metadata_entry = self.metadata_store.get(path, {})
            entity_type = metadata_entry.get("entity_type", "mcp_server")
            base_relevance = self._distance_to_relevance(distance)

            if entity_type == "mcp_server":
                server_info = metadata_entry.get("full_server_info", {})
                if not server_info:
                    continue

                # Apply keyword boost for hybrid search
                keyword_boost = self._calculate_keyword_boost(query, server_info)
                relevance = min(1.0, base_relevance * keyword_boost)

                match_context = (
                    server_info.get("description")
                    or ", ".join(server_info.get("tags", []))
                    or server_info.get("path")
                )

                matching_tools: List[Dict[str, Any]] = []
                if "tool" in entity_filter:
                    matching_tools = self._extract_matching_tools(query, server_info)[:5]

                # Comprehensive trace for search debugging
                logger.info(
                    f"[SEARCH] Server: {server_info.get('server_name')} | "
                    f"Distance: {distance:.4f} | "
                    f"Base Similarity: {base_relevance:.2%} | "
                    f"Keyword Boost: {keyword_boost:.2f}x | "
                    f"Final Score: {relevance:.2%} | "
                    f"Matching Tools: {len(matching_tools)}"
                )
                if matching_tools:
                    for tool in matching_tools[:3]:  # Show top 3 matching tools
                        logger.info(
                            f"  └─ Tool: {tool.get('tool_name')} | "
                            f"Coverage: {tool.get('raw_score', 0):.2%}"
                        )

                if "mcp_server" in entity_filter:
                    server_results.append(
                        {
                            "entity_type": "mcp_server",
                            "path": path,
                            "server_name": server_info.get("server_name", path.strip("/")),
                            "description": server_info.get("description", ""),
                            "tags": server_info.get("tags", []),
                            "num_tools": server_info.get("num_tools", 0),
                            "is_enabled": server_info.get("is_enabled", False),
                            "relevance_score": relevance,
                            "match_context": match_context,
                            "matching_tools": [
                                {
                                    "tool_name": tool.get("tool_name", ""),
                                    "description": tool.get("description", ""),
                                    "relevance_score": min(
                                        1.0, (relevance + tool.get("raw_score", 0)) / 2
                                    ),
                                    "match_context": tool.get("match_context", ""),
                                }
                                for tool in matching_tools
                            ],
                        }
                    )

                if "tool" in entity_filter and matching_tools:
                    for tool in matching_tools:
                        tool_results.append(
                            {
                                "entity_type": "tool",
                                "server_path": path,
                                "server_name": server_info.get("server_name", path.strip("/")),
                                "tool_name": tool.get("tool_name", ""),
                                "description": tool.get("description", ""),
                                "match_context": tool.get("match_context", ""),
                                "relevance_score": min(
                                    1.0, (relevance + tool.get("raw_score", 0)) / 2
                                ),
                            }
                        )

            elif entity_type == "a2a_agent":
                if "a2a_agent" not in entity_filter:
                    continue

                agent_card = metadata_entry.get("full_agent_card", {})
                if not agent_card:
                    continue

                # Apply keyword boost for agents (using base_relevance from line 831)
                # For agents, check name, description, skills, and tags
                agent_info_for_boost = {
                    "server_name": agent_card.get("name", ""),
                    "description": agent_card.get("description", ""),
                    "tags": agent_card.get("tags", []),
                    "tool_list": [{"name": skill.get("name", "")} for skill in agent_card.get("skills", []) if isinstance(skill, dict)]
                }
                keyword_boost = self._calculate_keyword_boost(query, agent_info_for_boost)
                agent_relevance = min(1.0, base_relevance * keyword_boost)

                skills = [
                    skill.get("name")
                    for skill in agent_card.get("skills", [])
                    if isinstance(skill, dict)
                ]
                match_context = (
                    agent_card.get("description")
                    or ", ".join(skills)
                    or ", ".join(agent_card.get("tags", []))
                )

                # Comprehensive trace for agent search debugging
                logger.info(
                    f"[SEARCH] Agent: {agent_card.get('name')} | "
                    f"Distance: {distance:.4f} | "
                    f"Base Similarity: {base_relevance:.2%} | "
                    f"Keyword Boost: {keyword_boost:.2f}x | "
                    f"Final Score: {agent_relevance:.2%} | "
                    f"Skills: {len(skills)}"
                )

                agent_results.append(
                    {
                        "entity_type": "a2a_agent",
                        "path": path,
                        "agent_name": agent_card.get("name", path.strip("/")),
                        "description": agent_card.get("description", ""),
                        "tags": agent_card.get("tags", []),
                        "skills": skills,
                        "visibility": agent_card.get("visibility", "public"),
                        "trust_level": agent_card.get("trust_level"),
                        "is_enabled": agent_card.get("is_enabled", False),
                        "relevance_score": agent_relevance,
                        "match_context": match_context,
                        "agent_card": agent_card,
                    }
                )

        server_results.sort(key=lambda item: item["relevance_score"], reverse=True)
        tool_results.sort(key=lambda item: item["relevance_score"], reverse=True)
        agent_results.sort(key=lambda item: item["relevance_score"], reverse=True)

        return {
            "servers": server_results[:max_results],
            "tools": tool_results[:max_results],
            "agents": agent_results[:max_results],
        }

# Global service instance
faiss_service = FaissService() 
