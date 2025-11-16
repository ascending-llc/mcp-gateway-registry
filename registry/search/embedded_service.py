"""
Embedded FAISS-based vector search service.

This implementation uses FAISS with sentence-transformers for local vector search.
Requires heavy dependencies: torch, sentence-transformers, faiss-cpu.
"""

import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from .base import VectorSearchService

logger = logging.getLogger(__name__)

# Try to import heavy dependencies - they may not be installed if using external mode
try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    FAISS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"FAISS dependencies not available: {e}. Use discovery_mode=external or install dependencies.")
    FAISS_AVAILABLE = False
    faiss = None
    np = None
    SentenceTransformer = None


class EmbeddedFaissService(VectorSearchService):
    """Embedded vector search using FAISS and sentence-transformers."""
    
    def __init__(self, settings):
        """
        Initialize the embedded FAISS service.
        
        Args:
            settings: Application settings object
        """
        if not FAISS_AVAILABLE:
            raise ImportError(
                "FAISS dependencies not installed. "
                "Install with: pip install faiss-cpu sentence-transformers torch OR "
                "use discovery_mode=external in your configuration."
            )
        
        self.settings = settings
        self.embedding_model: Optional[SentenceTransformer] = None
        self.faiss_index: Optional[faiss.IndexIDMap] = None
        self.metadata_store: Dict[str, Dict[str, Any]] = {}
        self.next_id_counter: int = 0
        
    async def initialize(self):
        """Initialize the FAISS service - load model and index."""
        await self._load_embedding_model()
        await self._load_faiss_data()
        
    async def _load_embedding_model(self):
        """Load the sentence transformer model."""
        logger.info("Loading FAISS data and embedding model...")
        
        # Ensure servers directory exists
        self.settings.servers_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            model_cache_path = self.settings.container_registry_dir / ".cache"
            model_cache_path.mkdir(parents=True, exist_ok=True)
            
            # Set cache path for sentence transformers
            import os
            original_st_home = os.environ.get('SENTENCE_TRANSFORMERS_HOME')
            os.environ['SENTENCE_TRANSFORMERS_HOME'] = str(model_cache_path)
            
            # Check if local model exists
            model_path = self.settings.embeddings_model_dir
            model_exists = model_path.exists() and any(model_path.iterdir()) if model_path.exists() else False
            
            if model_exists:
                logger.info(f"Loading SentenceTransformer model from local path: {self.settings.embeddings_model_dir}")
                self.embedding_model = SentenceTransformer(str(self.settings.embeddings_model_dir))
            else:
                logger.info(f"Local model not found at {self.settings.embeddings_model_dir}, downloading from Hugging Face")
                self.embedding_model = SentenceTransformer(str(self.settings.embeddings_model_name))
            
            # Restore original environment variable
            if original_st_home:
                os.environ['SENTENCE_TRANSFORMERS_HOME'] = original_st_home
            else:
                del os.environ['SENTENCE_TRANSFORMERS_HOME']
                
            logger.info("SentenceTransformer model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer model: {e}", exc_info=True)
            self.embedding_model = None
            raise
            
    async def _load_faiss_data(self):
        """Load existing FAISS index and metadata or create new ones."""
        if self.settings.faiss_index_path.exists() and self.settings.faiss_metadata_path.exists():
            try:
                logger.info(f"Loading FAISS index from {self.settings.faiss_index_path}")
                self.faiss_index = faiss.read_index(str(self.settings.faiss_index_path))
                
                logger.info(f"Loading FAISS metadata from {self.settings.faiss_metadata_path}")
                with open(self.settings.faiss_metadata_path, "r") as f:
                    loaded_metadata = json.load(f)
                    self.metadata_store = loaded_metadata.get("metadata", {})
                    self.next_id_counter = loaded_metadata.get("next_id", 0)
                    
                logger.info(f"FAISS data loaded. Index size: {self.faiss_index.ntotal if self.faiss_index else 0}. Next ID: {self.next_id_counter}")
                
                # Check dimension compatibility
                if self.faiss_index and self.faiss_index.d != self.settings.embeddings_model_dimensions:
                    logger.warning(f"Loaded FAISS index dimension ({self.faiss_index.d}) differs from expected ({self.settings.embeddings_model_dimensions}). Re-initializing.")
                    self._initialize_new_index()
                    
            except Exception as e:
                logger.error(f"Error loading FAISS data: {e}. Re-initializing.", exc_info=True)
                self._initialize_new_index()
        else:
            logger.info("FAISS index or metadata not found. Initializing new.")
            self._initialize_new_index()
            
    def _initialize_new_index(self):
        """Initialize a new FAISS index."""
        self.faiss_index = faiss.IndexIDMap(faiss.IndexFlatL2(self.settings.embeddings_model_dimensions))
        self.metadata_store = {}
        self.next_id_counter = 0
        
    async def save_data(self):
        """Save FAISS index and metadata to disk."""
        if self.faiss_index is None:
            logger.error("FAISS index is not initialized. Cannot save.")
            return
            
        try:
            # Ensure directory exists
            self.settings.servers_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Saving FAISS index to {self.settings.faiss_index_path} (Size: {self.faiss_index.ntotal})")
            faiss.write_index(self.faiss_index, str(self.settings.faiss_index_path))
            
            logger.info(f"Saving FAISS metadata to {self.settings.faiss_metadata_path}")
            with open(self.settings.faiss_metadata_path, "w") as f:
                json.dump({
                    "metadata": self.metadata_store,
                    "next_id": self.next_id_counter
                }, f, indent=2)
                
            logger.info("FAISS data saved successfully.")
        except Exception as e:
            logger.error(f"Error saving FAISS data: {e}", exc_info=True)
            
    def _get_text_for_embedding(self, server_info: Dict[str, Any]) -> str:
        """Prepare text string from server info for embedding."""
        name = server_info.get("server_name", "")
        description = server_info.get("description", "")
        tags = server_info.get("tags", [])
        tag_string = ", ".join(tags)
        return f"Name: {name}\nDescription: {description}\nTags: {tag_string}"
        
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
        
        if (existing_entry is None or 
            needs_new_embedding or 
            existing_entry.get("full_server_info") != enriched_server_info):
            
            self.metadata_store[service_path] = {
                "id": current_faiss_id,
                "text_for_embedding": text_to_embed,
                "full_server_info": enriched_server_info
            }
            logger.debug(f"Updated faiss_metadata_store for '{service_path}'.")
            await self.save_data()
        else:
            logger.debug(f"No changes to FAISS vector or enriched full_server_info for '{service_path}'. Skipping save.")

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
                logger.info(f"Removing service '{service_path}' with FAISS ID {service_id} from index")

            # Remove from metadata store
            del self.metadata_store[service_path]
            logger.info(f"Removed service '{service_path}' from FAISS metadata store")

            # Save the updated metadata
            await self.save_data()

        except Exception as e:
            logger.error(f"Failed to remove service '{service_path}' from FAISS: {e}", exc_info=True)
    
    async def search(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for services using FAISS semantic search and/or tag filtering.
        
        Note: This is a simplified interface. The full implementation in mcpgw/server.py
        has more sophisticated ranking logic. This is mainly for compatibility.
        """
        if not query and not tags:
            logger.warning("Search called with no query or tags")
            return []
        
        results = []
        
        # Simple tag filtering
        if tags:
            for service_path, entry in self.metadata_store.items():
                server_info = entry.get("full_server_info", {})
                service_tags = server_info.get("tags", [])
                
                # Check if all requested tags are present
                if all(tag in service_tags for tag in tags):
                    results.append({
                        "service_path": service_path,
                        "server_info": server_info,
                        "score": 1.0
                    })
        
        # Semantic search with FAISS
        elif query and self.embedding_model and self.faiss_index:
            try:
                # Encode query
                query_embedding = await asyncio.to_thread(self.embedding_model.encode, [query])
                query_embedding_np = np.array(query_embedding, dtype=np.float32)
                
                # Search FAISS
                distances, faiss_ids = await asyncio.to_thread(
                    self.faiss_index.search,
                    query_embedding_np,
                    min(top_k, self.faiss_index.ntotal) if self.faiss_index.ntotal > 0 else 1
                )
                
                # Convert results
                for distance, faiss_id in zip(distances[0], faiss_ids[0]):
                    if faiss_id < 0:  # Invalid ID
                        continue
                    
                    # Find service by FAISS ID
                    for service_path, entry in self.metadata_store.items():
                        if entry["id"] == int(faiss_id):
                            results.append({
                                "service_path": service_path,
                                "server_info": entry.get("full_server_info", {}),
                                "score": float(1.0 / (1.0 + distance))  # Convert distance to similarity
                            })
                            break
            except Exception as e:
                logger.error(f"FAISS search failed: {e}", exc_info=True)
        
        return results[:top_k]
    
    async def cleanup(self):
        """Save data and cleanup resources."""
        await self.save_data()
        logger.info("Embedded FAISS service cleanup complete")
