"""Embeddings module for vendor-agnostic embeddings generation."""

from .client import (
    EmbeddingsClient,
    SentenceTransformersClient,
    LiteLLMClient,
    create_embeddings_client,
)

__all__ = [
    "EmbeddingsClient",
    "SentenceTransformersClient",
    "LiteLLMClient",
    "create_embeddings_client",
]
