"""
Embedded FAISS-based vector search service for MCPGW.

This implementation uses FAISS with sentence-transformers for local vector search.
It reads the FAISS index and metadata created by the registry service.
"""

import os
import json
import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

from .base import VectorSearchService

logger = logging.getLogger(__name__)

# Try to import heavy dependencies - they may not be installed if using external mode
try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    FAISS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"FAISS dependencies not available: {e}. Use TOOL_DISCOVERY_MODE=external or install dependencies.")
    FAISS_AVAILABLE = False
    faiss = None
    np = None
    SentenceTransformer = None
    cosine_similarity = None


class EmbeddedFaissService(VectorSearchService):
    """Embedded vector search using FAISS and sentence-transformers."""
    
    def __init__(
        self,
        registry_server_data_path: Path,
        embeddings_model_name: str = 'all-MiniLM-L6-v2',
        embedding_dimension: int = 384,
        check_interval: float = 5.0
    ):
        """
        Initialize the embedded FAISS service.
        
        Args:
            registry_server_data_path: Path to registry's server data directory
            embeddings_model_name: Name of the sentence-transformers model
            embedding_dimension: Expected embedding dimension
            check_interval: How often to check for file updates (seconds)
        """
        if not FAISS_AVAILABLE:
            raise ImportError(
                "FAISS dependencies not installed. "
                "Install with: pip install faiss-cpu sentence-transformers torch scikit-learn OR "
                "use TOOL_DISCOVERY_MODE=external in your configuration."
            )
        
        self.registry_server_data_path = registry_server_data_path
        self.embeddings_model_name = embeddings_model_name
        self.embedding_dimension = embedding_dimension
        self.check_interval = check_interval
        
        # FAISS index paths
        self.faiss_index_path = registry_server_data_path / "service_index.faiss"
        self.faiss_metadata_path = registry_server_data_path / "service_index_metadata.json"
        self.embeddings_model_dir = registry_server_data_path.parent / "models" / embeddings_model_name
        
        # State
        self._data_lock = asyncio.Lock()
        self._embedding_model: Optional[SentenceTransformer] = None
        self._faiss_index: Optional[faiss.Index] = None
        self._faiss_metadata: Optional[Dict[str, Any]] = None
        self._last_faiss_index_mtime: Optional[float] = None
        self._last_faiss_metadata_mtime: Optional[float] = None
        self._last_faiss_check_time: Optional[float] = None
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize the FAISS service - load model and index."""
        try:
            await self._load_embedding_model()
            await self._load_faiss_data()
            self._initialized = True
            logger.info("Embedded FAISS service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize embedded FAISS service: {e}", exc_info=True)
            self._initialized = False
            raise
    
    async def _load_embedding_model(self):
        """Load the sentence transformer model."""
        logger.info("Loading embedding model...")
        
        try:
            model_cache_path = self.registry_server_data_path.parent / ".cache"
            model_cache_path.mkdir(parents=True, exist_ok=True)
            
            # Set cache path for sentence transformers
            original_st_home = os.environ.get('SENTENCE_TRANSFORMERS_HOME')
            os.environ['SENTENCE_TRANSFORMERS_HOME'] = str(model_cache_path)
            
            # Check if local model exists
            model_path = self.embeddings_model_dir
            model_exists = model_path.exists() and any(model_path.iterdir()) if model_path.exists() else False
            
            if model_exists:
                logger.info(f"Loading SentenceTransformer model from local path: {self.embeddings_model_dir}")
                self._embedding_model = await asyncio.to_thread(SentenceTransformer, str(self.embeddings_model_dir))
            else:
                logger.info(f"Local model not found at {self.embeddings_model_dir}, downloading from Hugging Face")
                self._embedding_model = await asyncio.to_thread(SentenceTransformer, str(self.embeddings_model_name))
            
            # Restore original environment variable
            if original_st_home:
                os.environ['SENTENCE_TRANSFORMERS_HOME'] = original_st_home
            else:
                if 'SENTENCE_TRANSFORMERS_HOME' in os.environ:
                    del os.environ['SENTENCE_TRANSFORMERS_HOME']
                    
            logger.info("SentenceTransformer model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer model: {e}", exc_info=True)
            self._embedding_model = None
            raise
    
    async def _load_faiss_data(self):
        """Load FAISS index and metadata from disk."""
        async with self._data_lock:
            # Check FAISS index file
            index_file_changed = False
            if self.faiss_index_path.exists():
                try:
                    current_index_mtime = await asyncio.to_thread(os.path.getmtime, self.faiss_index_path)
                    if self._faiss_index is None or self._last_faiss_index_mtime is None or current_index_mtime > self._last_faiss_index_mtime:
                        logger.info(f"FAISS index file has changed or not loaded. Reloading from {self.faiss_index_path}")
                        self._faiss_index = await asyncio.to_thread(faiss.read_index, str(self.faiss_index_path))
                        self._last_faiss_index_mtime = current_index_mtime
                        index_file_changed = True
                        logger.info(f"FAISS index loaded. Total vectors: {self._faiss_index.ntotal}")
                        if self._faiss_index.d != self.embedding_dimension:
                            logger.warning(f"Loaded FAISS index dimension ({self._faiss_index.d}) differs from expected ({self.embedding_dimension})")
                    else:
                        logger.debug("FAISS index file unchanged since last load")
                except Exception as e:
                    logger.error(f"Failed to load FAISS index: {e}", exc_info=True)
                    self._faiss_index = None
            else:
                logger.warning(f"FAISS index file {self.faiss_index_path} does not exist")
                self._faiss_index = None
                self._last_faiss_index_mtime = None
            
            # Check FAISS metadata file
            if self.faiss_metadata_path.exists():
                try:
                    current_metadata_mtime = await asyncio.to_thread(os.path.getmtime, self.faiss_metadata_path)
                    if self._faiss_metadata is None or self._last_faiss_metadata_mtime is None or current_metadata_mtime > self._last_faiss_metadata_mtime or index_file_changed:
                        logger.info(f"FAISS metadata file has changed or not loaded. Reloading from {self.faiss_metadata_path}")
                        with open(self.faiss_metadata_path, "r") as f:
                            content = await asyncio.to_thread(f.read)
                            self._faiss_metadata = await asyncio.to_thread(json.loads, content)
                        self._last_faiss_metadata_mtime = current_metadata_mtime
                        logger.info(f"FAISS metadata loaded. Entries: {len(self._faiss_metadata.get('metadata', {}))}")
                    else:
                        logger.debug("FAISS metadata file unchanged since last load")
                except Exception as e:
                    logger.error(f"Failed to load FAISS metadata: {e}", exc_info=True)
                    self._faiss_metadata = None
            else:
                logger.warning(f"FAISS metadata file {self.faiss_metadata_path} does not exist")
                self._faiss_metadata = None
                self._last_faiss_metadata_mtime = None
    
    async def _check_and_reload_if_needed(self):
        """Check if FAISS files have been updated and reload if necessary."""
        current_time = time.time()
        should_check = (
            self._embedding_model is None or
            self._faiss_index is None or
            self._faiss_metadata is None or
            self._last_faiss_check_time is None or
            (current_time - self._last_faiss_check_time) >= self.check_interval
        )
        
        if should_check:
            await self._load_faiss_data()
            self._last_faiss_check_time = current_time
    
    async def search_tools(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_scopes: Optional[List[str]] = None,
        top_k_services: int = 3,
        top_n_tools: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Search for tools using natural language query and/or tags.
        
        Implements the full intelligent tool finder logic with FAISS semantic search,
        tag filtering, and scope-based access control.
        """
        # Import scope checking here to avoid circular imports
        from ..server import check_tool_access, load_scopes_config
        
        # Check and reload data if needed
        await self._check_and_reload_if_needed()
        
        # Validate dependencies
        if self._embedding_model is None:
            raise Exception("Embedding model is not available. Cannot perform search.")
        if self._faiss_index is None:
            raise Exception("FAISS index is not available. Cannot perform search.")
        if self._faiss_metadata is None or "metadata" not in self._faiss_metadata:
            raise Exception("FAISS metadata is not available. Cannot perform search.")
        
        # Input validation
        if not query and not tags:
            raise Exception("At least one of 'query' or 'tags' must be provided")
        
        # Normalize tags for case-insensitive matching
        normalized_tags = [tag.lower().strip() for tag in tags] if tags else []
        if normalized_tags:
            logger.info(f"Filtering by tags: {normalized_tags}")
        
        registry_faiss_metadata = self._faiss_metadata["metadata"]
        
        # Determine which services to process
        services_to_process = []
        use_semantic_ranking = False
        
        if query:
            use_semantic_ranking = True
            # Embed the query
            try:
                query_embedding = await asyncio.to_thread(self._embedding_model.encode, [query])
                query_embedding_np = np.array(query_embedding, dtype=np.float32)
            except Exception as e:
                logger.error(f"Error encoding query: {e}", exc_info=True)
                raise Exception(f"Error encoding query: {e}")
            
            # Search FAISS for top_k_services
            try:
                logger.info(f"Searching FAISS index for top {top_k_services} services matching query")
                distances, faiss_ids = await asyncio.to_thread(self._faiss_index.search, query_embedding_np, top_k_services)
            except Exception as e:
                logger.error(f"Error searching FAISS index: {e}", exc_info=True)
                raise Exception(f"Error searching FAISS index: {e}")
            
            # Create reverse map from FAISS ID to service path
            id_to_service_path_map = {}
            for svc_path, meta_item in registry_faiss_metadata.items():
                if "id" in meta_item:
                    id_to_service_path_map[meta_item["id"]] = svc_path
            
            # Extract service paths from FAISS results
            for i in range(len(faiss_ids[0])):
                faiss_id = faiss_ids[0][i]
                if faiss_id == -1:  # No more results
                    continue
                service_path = id_to_service_path_map.get(faiss_id)
                if service_path:
                    services_to_process.append(service_path)
            
            logger.info(f"Processing {len(services_to_process)} services from FAISS search")
        else:
            # Tags-only mode: process all services
            services_to_process = list(registry_faiss_metadata.keys())
            logger.info(f"Tags-only mode - processing all {len(services_to_process)} services")
        
        # Load scopes configuration for access control
        scopes_config = await load_scopes_config()
        if not user_scopes:
            logger.warning("No user scopes provided - user may not have access to any tools")
            user_scopes = []
        
        # Collect candidate tools
        candidate_tools = []
        tools_before_scope_filter = 0
        
        for service_path in services_to_process:
            service_metadata = registry_faiss_metadata.get(service_path)
            if not service_metadata or "full_server_info" not in service_metadata:
                logger.warning(f"Metadata or full_server_info not found for service path {service_path}")
                continue
            
            full_server_info = service_metadata["full_server_info"]
            
            if not full_server_info.get("is_enabled", False):
                logger.info(f"Service {service_path} is disabled. Skipping")
                continue
            
            # Apply tag filtering if tags specified
            if normalized_tags:
                server_tags = full_server_info.get("tags", "")
                if isinstance(server_tags, str):
                    server_tags_list = [tag.strip().lower() for tag in server_tags.split(",") if tag.strip()]
                else:
                    server_tags_list = [str(tag).lower().strip() for tag in server_tags] if server_tags else []
                
                # Check if all required tags are present (AND logic)
                if not all(tag in server_tags_list for tag in normalized_tags):
                    logger.info(f"Service {service_path} does not match required tags {normalized_tags}")
                    continue
            
            service_name = full_server_info.get("server_name", "Unknown Service")
            tool_list = full_server_info.get("tool_list", [])
            supported_transports = full_server_info.get("supported_transports", ["streamable-http"])
            auth_provider = full_server_info.get("auth_provider", None)
            
            for tool_info in tool_list:
                tool_name = tool_info.get("name", "Unknown Tool")
                parsed_desc = tool_info.get("parsed_description", {})
                main_desc = parsed_desc.get("main", "No description.")
                
                tools_before_scope_filter += 1
                
                # Check if user has access to this tool
                server_name = service_path.lstrip('/') if service_path.startswith('/') else service_path
                if user_scopes and not check_tool_access(server_name, tool_name, user_scopes, scopes_config):
                    logger.debug(f"User does not have access to tool {server_name}.{tool_name}")
                    continue
                
                # Create descriptive text for embedding
                tool_text_for_embedding = f"Service: {service_name}. Tool: {tool_name}. Description: {main_desc}"
                
                candidate_tools.append({
                    "text_for_embedding": tool_text_for_embedding,
                    "tool_name": tool_name,
                    "tool_parsed_description": parsed_desc,
                    "tool_schema": tool_info.get("schema", {}),
                    "service_path": service_path,
                    "service_name": service_name,
                    "supported_transports": supported_transports,
                    "auth_provider": auth_provider,
                })
        
        logger.info(f"Scope filtering results - {tools_before_scope_filter} tools found, {len(candidate_tools)} accessible after filtering")
        
        if not candidate_tools:
            logger.info("No accessible tools found")
            return []
        
        # Apply semantic ranking if we have a query
        if use_semantic_ranking:
            logger.info(f"Embedding {len(candidate_tools)} candidate tools for secondary ranking")
            try:
                tool_texts = [tool["text_for_embedding"] for tool in candidate_tools]
                tool_embeddings = await asyncio.to_thread(self._embedding_model.encode, tool_texts)
                tool_embeddings_np = np.array(tool_embeddings, dtype=np.float32)
            except Exception as e:
                logger.error(f"Error encoding tool descriptions: {e}", exc_info=True)
                raise Exception(f"Error encoding tool descriptions: {e}")
            
            # Calculate cosine similarity
            similarities = cosine_similarity(query_embedding_np, tool_embeddings_np)[0]
            
            # Add similarity score and sort
            ranked_tools = []
            for i, tool_data in enumerate(candidate_tools):
                ranked_tools.append({
                    **tool_data,
                    "overall_similarity_score": float(similarities[i])
                })
            
            ranked_tools.sort(key=lambda x: x["overall_similarity_score"], reverse=True)
        else:
            # Tags-only mode: no semantic ranking
            ranked_tools = candidate_tools
            logger.info(f"Tags-only mode - {len(ranked_tools)} tools found without semantic ranking")
        
        # Select top N tools
        final_results = ranked_tools[:top_n_tools]
        logger.info(f"Top {len(final_results)} tools found after filtering and ranking")
        
        # Log results
        for i, tool in enumerate(final_results):
            if 'overall_similarity_score' in tool:
                logger.info(f"  {i+1}. {tool['service_name']}.{tool['tool_name']} (similarity: {tool['overall_similarity_score']:.3f})")
            else:
                logger.info(f"  {i+1}. {tool['service_name']}.{tool['tool_name']} (tags-only mode)")
        
        # Remove temporary field
        for res in final_results:
            del res["text_for_embedding"]
        
        return final_results
    
    async def check_availability(self) -> bool:
        """Check if the embedded FAISS service is available and functional."""
        return (
            self._initialized and
            self._embedding_model is not None and
            self._faiss_index is not None and
            self._faiss_metadata is not None
        )
