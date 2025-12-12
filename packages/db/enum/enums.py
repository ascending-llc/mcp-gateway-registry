from enum import Enum


class VectorStoreType(str, Enum):
    """Supported vector store types."""
    WEAVIATE = "weaviate"
    CHROMA = "chroma"


class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""
    OPENAI = "openai"
    AWS_BEDROCK = "aws_bedrock"


class LLMProvider(str, Enum):
    """LLM provider enum (backward compatibility)."""
    BEDROCK = "bedrock"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    COHERE = "cohere"
    HUGGINGFACE = "huggingface"
    LOCAL = "local"
