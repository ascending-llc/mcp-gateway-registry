import importlib

from ... import BackendConfig, DependencyMissingError
from ...adapters.adapter import VectorStoreAdapter
from ...adapters.factory import register_vector_store_creator
from ...backends.chroma_store import ChromaStore
from ...backends.weaviate_store import WeaviateStore
from ...config import ChromaConfig, WeaviateConfig
from ...enum.enums import VectorStoreType


@register_vector_store_creator(VectorStoreType.WEAVIATE.value)
def create_weaviate_adapter(config: BackendConfig, embedding) -> VectorStoreAdapter:
    """Create Weaviate adapter."""
    try:
        importlib.import_module("langchain_weaviate")
        vector_store_config = config.vector_store_config
        if not isinstance(vector_store_config, WeaviateConfig):
            raise ValueError("Expected WeaviateConfig")

        adapter_config = {
            "embedding": embedding,
            "config": {
                "host": vector_store_config.host,
                "port": vector_store_config.port,
                "api_key": vector_store_config.api_key,
                "collection_prefix": vector_store_config.collection_prefix
            },
            "embedding_config": config.get_embedding_model_config_dict()
        }

        return WeaviateStore(**adapter_config)

    except ImportError as e:
        raise DependencyMissingError(
            "langchain_weaviate",
            f"Required database package 'langchain_weaviate' is not installed. "
            f"Please install it with: pip install langchain_weaviate"
        ) from e


@register_vector_store_creator(VectorStoreType.CHROMA.value)
def create_chroma_adapter(config: BackendConfig, embedding) -> VectorStoreAdapter:
    """Create Chroma adapter."""
    try:
        importlib.import_module("langchain_chroma")
        vector_store_config = config.vector_store_config
        if not isinstance(vector_store_config, ChromaConfig):
            raise ValueError("Expected ChromaConfig")

        adapter_config = {
            "embedding": embedding,
            "config": {
                "persist_directory": vector_store_config.persist_directory,
                "collection_name": vector_store_config.collection_name
            },
            "embedding_config": config.get_embedding_model_config_dict()
        }

        return ChromaStore(**adapter_config)

    except ImportError as e:
        raise DependencyMissingError(
            "langchain_chroma",
            f"Required database package 'langchain_chroma' is not installed. "
            f"Please install it with: pip install langchain_chroma"
        ) from e