from enum import Enum


class LLMProvider(Enum):
    """LLM provider options for embeddings"""
    BEDROCK = "bedrock"
    OPENAI = "openai"


class SearchType(Enum):
    """Search type options for different search strategies"""
    NEAR_TEXT = "near_text"  # Semantic search using text
    NEAR_VECTOR = "near_vector"  # Semantic search using vector
    NEAR_IMAGE = "near_image"  # Image similarity search
    BM25 = "bm25"  # Keyword search (BM25F)
    HYBRID = "hybrid"  # Hybrid search (BM25 + semantic)
    FETCH_OBJECTS = "fetch_objects"  # Simple object fetch with filters
    FUZZY = "fuzzy"  # Fuzzy search (hybrid optimized for fuzzy matching)
