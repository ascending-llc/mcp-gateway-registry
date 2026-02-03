import importlib

from ...adapters.factory import register_embedding_creator
from ...config import BackendConfig, BedrockEmbeddingConfig, OpenAIEmbeddingConfig
from ...enum.enums import EmbeddingProvider
from ...enum.exceptions import DependencyMissingError


@register_embedding_creator(EmbeddingProvider.OPENAI.value)
def create_openai_embedding(config: BackendConfig):
    """Create OpenAI embedding model."""
    try:
        module = importlib.import_module("langchain_openai")
        embedding_class = module.OpenAIEmbeddings

        embed_config = config.embedding_model_config
        if not isinstance(embed_config, OpenAIEmbeddingConfig):
            raise ValueError("Expected OpenAIEmbeddingConfig")

        return embedding_class(api_key=embed_config.api_key, model=embed_config.model)

    except ImportError as e:
        raise DependencyMissingError(
            "langchain_openai",
            "Required embedding package 'langchain_openai' is not installed. "
            "Please install it with: pip install langchain_openai",
        ) from e


@register_embedding_creator(EmbeddingProvider.AWS_BEDROCK.value)
def create_bedrock_embedding(config: BackendConfig):
    """Create AWS Bedrock embedding model."""
    try:
        module = importlib.import_module("langchain_aws")
        embedding_class = module.BedrockEmbeddings

        embed_config = config.embedding_model_config
        if not isinstance(embed_config, BedrockEmbeddingConfig):
            raise ValueError("Expected BedrockEmbeddingConfig")

        kwargs = {"region_name": embed_config.region, "model_id": embed_config.model}

        if embed_config.access_key_id and embed_config.secret_access_key:
            kwargs["aws_access_key_id"] = embed_config.access_key_id
            kwargs["aws_secret_access_key"] = embed_config.secret_access_key

        return embedding_class(**kwargs)

    except ImportError as e:
        raise DependencyMissingError(
            "langchain_aws",
            "Required embedding package 'langchain_aws' is not installed. "
            "Please install it with: pip install langchain_aws",
        ) from e
