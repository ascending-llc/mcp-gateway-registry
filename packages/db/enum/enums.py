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


class SearchType(Enum):
    """Search type options for different search strategies"""
    NEAR_TEXT = "near_text"  # Semantic search using text
    BM25 = "bm25"  # Keyword search (BM25F)
    HYBRID = "hybrid"  # Hybrid search (BM25 + semantic)
#  NEAR_VECTOR = "near_vector"  # Semantic search using vector
#  NEAR_IMAGE = "near_image"  # Image similarity search
#  FETCH_OBJECTS = "fetch_objects"  # Simple object fetch with filters
