import os
from typing import Dict, Type, Optional
from pydantic import BaseModel, Field
from ..enum.enums import VectorStoreType, EmbeddingProvider


class VectorStoreConfig(BaseModel):
    """Base class for vector store configuration."""
    type: str
    
    @classmethod
    def from_env(cls) -> "VectorStoreConfig":
        """Create config instance from environment variables."""
        raise NotImplementedError(f"{cls.__name__} must implement from_env method")


class EmbeddingModelConfig(BaseModel):
    """Base class for embedding model configuration."""
    provider: str
    
    @classmethod
    def from_env(cls) -> "EmbeddingModelConfig":
        """Create config instance from environment variables."""
        raise NotImplementedError(f"{cls.__name__} must implement from_env method")


# Registry for configuration classes
_VECTOR_STORE_REGISTRY: Dict[str, Type[VectorStoreConfig]] = {}
_EMBEDDING_MODEL_REGISTRY: Dict[str, Type[EmbeddingModelConfig]] = {}


def register_vector_store_config(name: str):
    """Decorator to register vector store config class."""
    def decorator(config_class: Type[VectorStoreConfig]):
        _VECTOR_STORE_REGISTRY[name] = config_class
        return config_class
    return decorator


def register_embedding_model_config(name: str):
    """Decorator to register embedding model config class."""
    def decorator(config_class: Type[EmbeddingModelConfig]):
        _EMBEDDING_MODEL_REGISTRY[name] = config_class
        return config_class
    return decorator


def get_vector_store_config_class(name: str) -> Type[VectorStoreConfig]:
    """Get vector store config class by name."""
    if name not in _VECTOR_STORE_REGISTRY:
        available = list(_VECTOR_STORE_REGISTRY.keys())
        raise ValueError(f"Unknown vector store type: {name}. Available: {available}")
    return _VECTOR_STORE_REGISTRY[name]


def get_embedding_model_config_class(name: str) -> Type[EmbeddingModelConfig]:
    """Get embedding model config class by name."""
    if name not in _EMBEDDING_MODEL_REGISTRY:
        available = list(_EMBEDDING_MODEL_REGISTRY.keys())
        raise ValueError(f"Unknown embedding provider: {name}. Available: {available}")
    return _EMBEDDING_MODEL_REGISTRY[name]


def get_registered_vector_stores() -> list:
    """Get list of registered vector store types."""
    return list(_VECTOR_STORE_REGISTRY.keys())


def get_registered_embedding_models() -> list:
    """Get list of registered embedding providers."""
    return list(_EMBEDDING_MODEL_REGISTRY.keys())


@register_vector_store_config(VectorStoreType.WEAVIATE.value)
class WeaviateConfig(VectorStoreConfig):
    """Weaviate vector store configuration."""
    host: str = Field(description="Weaviate host")
    port: int = Field(description="Weaviate port")
    api_key: Optional[str] = Field(default=None, description="API key")
    collection_prefix: Optional[str] = Field(default=None, description="Collection prefix")
    
    @classmethod
    def from_env(cls) -> "WeaviateConfig":
        """Create Weaviate config from environment variables."""
        host = os.getenv("WEAVIATE_HOST")
        port = os.getenv("WEAVIATE_PORT")
        collection_prefix = os.getenv("WEAVIATE_COLLECTION_PREFIX")
        
        if not host:
            raise ValueError("WEAVIATE_HOST environment variable must be set")
        if not port:
            raise ValueError("WEAVIATE_PORT environment variable must be set")

        try:
            port_int = int(port)
        except ValueError:
            raise ValueError(f"WEAVIATE_PORT must be integer, got: {port}")
        
        return cls(
            type=VectorStoreType.WEAVIATE.value,
            host=host,
            port=port_int,
            api_key=os.getenv("WEAVIATE_API_KEY"),
            collection_prefix=collection_prefix
        )


@register_vector_store_config(VectorStoreType.CHROMA.value)
class ChromaConfig(VectorStoreConfig):
    """Chroma vector store configuration."""
    persist_directory: str = Field(description="Persistence directory")
    collection_name: str = Field(description="Collection name")
    
    @classmethod
    def from_env(cls) -> "ChromaConfig":
        """Create Chroma config from environment variables."""
        persist_directory = os.getenv("CHROMA_PERSIST_DIRECTORY")
        collection_name = os.getenv("CHROMA_COLLECTION_NAME")
        
        if not persist_directory:
            raise ValueError("CHROMA_PERSIST_DIRECTORY environment variable must be set")
        if not collection_name:
            raise ValueError("CHROMA_COLLECTION_NAME environment variable must be set")
        
        return cls(
            type="chroma",
            persist_directory=persist_directory,
            collection_name=collection_name
        )


@register_embedding_model_config(EmbeddingProvider.OPENAI.value)
class OpenAIEmbeddingConfig(EmbeddingModelConfig):
    """OpenAI embedding model configuration."""
    api_key: str = Field(description="OpenAI API key")
    model: str = Field(description="Model name")
    
    @classmethod
    def from_env(cls) -> "OpenAIEmbeddingConfig":
        """Create OpenAI config from environment variables."""
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL")
        
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable must be set")
        if not model:
            raise ValueError("OPENAI_MODEL environment variable must be set")
        
        return cls(
            provider=EmbeddingProvider.OPENAI.value,
            api_key=api_key,
            model=model
        )


@register_embedding_model_config(EmbeddingProvider.AWS_BEDROCK.value)
class BedrockEmbeddingConfig(EmbeddingModelConfig):
    """AWS Bedrock embedding model configuration."""
    region: str = Field(description="AWS region")
    model: str = Field(description="Bedrock model ID")
    access_key_id: Optional[str] = Field(default=None, description="AWS access key ID")
    secret_access_key: Optional[str] = Field(default=None, description="AWS secret access key")
    
    @classmethod
    def from_env(cls) -> "BedrockEmbeddingConfig":
        """Create AWS Bedrock config from environment variables."""
        region = os.getenv("AWS_REGION")
        model = os.getenv("EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
        
        if not region:
            raise ValueError("AWS_REGION environment variable must be set")
        return cls(
            provider=EmbeddingProvider.AWS_BEDROCK.value,
            region=region,
            model=model,
            access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )


class BackendConfig(BaseModel):
    """Unified backend configuration."""
    
    vector_store_config: VectorStoreConfig
    embedding_model_config: EmbeddingModelConfig
    
    @classmethod
    def from_env(cls) -> "BackendConfig":
        """Create unified config from environment variables."""
        vector_store_type = os.getenv("VECTOR_STORE_TYPE")
        embedding_provider = os.getenv("EMBEDDING_PROVIDER")
        
        if not vector_store_type:
            raise ValueError("VECTOR_STORE_TYPE environment variable must be set")
        if not embedding_provider:
            raise ValueError("EMBEDDING_PROVIDER environment variable must be set")
        
        vector_store_class = get_vector_store_config_class(vector_store_type)
        embedding_class = get_embedding_model_config_class(embedding_provider)
        
        return cls(
            vector_store_config=vector_store_class.from_env(),
            embedding_model_config=embedding_class.from_env()
        )
    
    @property
    def vector_store_type(self) -> str:
        """Get vector store type."""
        return self.vector_store_config.type
    
    @property
    def embedding_provider(self) -> str:
        """Get embedding provider."""
        return self.embedding_model_config.provider
    
    def get_vector_store_config_dict(self) -> dict:
        """Get vector store config as dictionary."""
        return self.vector_store_config.model_dump()
    
    def get_embedding_model_config_dict(self) -> dict:
        """Get embedding model config as dictionary."""
        return self.embedding_model_config.model_dump()
