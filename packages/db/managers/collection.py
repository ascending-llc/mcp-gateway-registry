import logging
from typing import Any, Dict, Optional, Type, TypeVar

from ..core.client import WeaviateClient

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='Model')


class CollectionManager:
    """Manages Weaviate collection lifecycle and configuration"""
    
    def __init__(self, client: WeaviateClient):
        self.client = client
    
    def create_collection(self, model_class: Type[T]) -> bool:
        """
        Create a Weaviate collection from model definition.
        
        Args:
            model_class: Model class with schema definition
            
        Returns:
            bool: True if creation successful, False otherwise
        """
        try:
            with self.client.managed_connection() as client:
                collection_name = model_class.get_collection_name()
                properties = model_class.get_properties()
                vectorizer_config = model_class.get_vectorizer_config()
                vector_index_config = model_class.get_vector_index_config()
                generative_config = model_class.get_generative_config()
                
                # Check if collection already exists
                if client.client.collections.exists(collection_name):
                    logger.info(f"Collection {collection_name} already exists")
                    return True
                
                # Create collection using new API format to avoid deprecation warnings
                create_kwargs = {
                    "name": collection_name,
                    "properties": properties,
                }
                
                # Use new vector_config parameter (Weaviate 1.24+)
                # vector_config must be in list format with required name field
                if vectorizer_config or vector_index_config:
                    vector_config = [{
                        "name": "default",  # Required name field
                        "vectorizer": vectorizer_config,
                        "vector_index_config": vector_index_config
                    }]
                    create_kwargs["vector_config"] = vector_config
                
                # Add generative configuration if provided
                if generative_config:
                    create_kwargs["generative_config"] = generative_config
                
                collection = client.client.collections.create(**create_kwargs)
                logger.info(f"Collection {collection_name} created successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to create collection {model_class.get_collection_name()}: {e}")
            return False
    
    def delete_collection(self, model_class: Type[T]) -> bool:
        """
        Delete a Weaviate collection.
        
        Args:
            model_class: Model class
            
        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            with self.client.managed_connection() as client:
                collection_name = model_class.get_collection_name()
                
                if not client.client.collections.exists(collection_name):
                    logger.warning(f"Collection {collection_name} does not exist")
                    return True
                
                client.client.collections.delete(collection_name)
                logger.info(f"Collection {collection_name} deleted successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete collection {model_class.get_collection_name()}: {e}")
            return False
    
    def collection_exists(self, model_class: Type[T]) -> bool:
        """
        Check if a collection exists in Weaviate.
        
        Args:
            model_class: Model class
            
        Returns:
            bool: True if collection exists, False otherwise
        """
        try:
            with self.client.managed_connection() as client:
                collection_name = model_class.get_collection_name()
                return client.client.collections.exists(collection_name)
        except Exception as e:
            logger.error(f"Failed to check collection existence: {e}")
            return False
    
    def get_collection_info(self, model_class: Type[T]) -> Optional[Dict[str, Any]]:
        """
        Get collection configuration and metadata.
        
        Args:
            model_class: Model class
            
        Returns:
            Optional[Dict]: Collection information or None if not found
        """
        try:
            with self.client.managed_connection() as client:
                collection_name = model_class.get_collection_name()
                
                if not client.client.collections.exists(collection_name):
                    return None
                
                collection = client.client.collections.get(collection_name)
                config = collection.config.get()
                
                # Handle new vector_config structure
                vectorizer = None
                distance_metric = "cosine"
                vector_index_type = "hnsw"
                
                if config.vector_config and 'default' in config.vector_config:
                    vector_config = config.vector_config['default']
                    if hasattr(vector_config, 'vectorizer') and vector_config.vectorizer:
                        vectorizer = vector_config.vectorizer.vectorizer.value if hasattr(vector_config.vectorizer, 'vectorizer') else str(vector_config.vectorizer)
                    
                    if hasattr(vector_config, 'vector_index_config') and vector_config.vector_index_config:
                        if hasattr(vector_config.vector_index_config, 'distance_metric'):
                            distance_metric = vector_config.vector_index_config.distance_metric.value
                
                return {
                    "name": collection_name,
                    "properties": [prop.name for prop in config.properties],
                    "vectorizer": vectorizer,
                    "vector_index_type": vector_index_type,
                    "distance_metric": distance_metric
                }
                
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return None

