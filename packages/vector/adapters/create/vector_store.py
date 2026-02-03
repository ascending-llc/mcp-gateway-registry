import importlib

from ...adapters.adapter import VectorStoreAdapter
from ...adapters.factory import register_vector_store_creator
from ...backends.weaviate_store import WeaviateStore
from ...config import BackendConfig, WeaviateConfig
from ...enum.enums import VectorStoreType
from ...enum.exceptions import DependencyMissingError


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
                "collection_prefix": vector_store_config.collection_prefix,
                "embedding_provider": config.embedding_provider,
            },
            "embedding_config": config.get_embedding_model_config_dict(),
        }

        return WeaviateStore(**adapter_config)

    except ImportError as e:
        raise DependencyMissingError(
            "langchain_weaviate",
            "Required database package 'langchain_weaviate' is not installed. "
            "Please install it with: pip install langchain_weaviate",
        ) from e
