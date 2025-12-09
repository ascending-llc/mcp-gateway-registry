"""
Embeddings client abstraction for vendor-agnostic embeddings generation.

This module provides a unified interface for generating embeddings from multiple
providers including local sentence-transformers models and cloud-based APIs via LiteLLM.
"""

import logging
import os
from abc import (
    ABC,
    abstractmethod,
)
from pathlib import Path
from typing import (
    List,
    Optional,
)

import numpy as np


logger = logging.getLogger(__name__)


class EmbeddingsClient(ABC):
    """Abstract base class for embeddings generation clients."""

    @abstractmethod
    def encode(
        self,
        texts: List[str],
    ) -> np.ndarray:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to encode

        Returns:
            NumPy array of embeddings with shape (len(texts), embedding_dimension)

        Raises:
            RuntimeError: If encoding fails
        """
        pass

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this client.

        Returns:
            Integer dimension of embedding vectors
        """
        pass


class SentenceTransformersClient(EmbeddingsClient):
    """Client for local sentence-transformers models."""

    def __init__(
        self,
        model_name: str,
        model_dir: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
    ):
        """
        Initialize the SentenceTransformers client.

        Args:
            model_name: Name of the sentence-transformers model
            model_dir: Optional local directory containing the model
            cache_dir: Optional cache directory for downloaded models
        """
        self.model_name = model_name
        self.model_dir = model_dir
        self.cache_dir = cache_dir
        self._model: Optional["SentenceTransformer"] = None
        self._dimension: Optional[int] = None

    def _load_model(self) -> None:
        """Load the sentence-transformers model."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            # Set cache directory if provided
            original_st_home = os.environ.get("SENTENCE_TRANSFORMERS_HOME")
            if self.cache_dir:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(self.cache_dir)

            # Check if local model exists
            model_exists = (
                self.model_dir.exists() and any(self.model_dir.iterdir())
                if self.model_dir and self.model_dir.exists()
                else False
            )

            if model_exists:
                logger.info(
                    f"Loading SentenceTransformer model from local path: {self.model_dir}"
                )
                self._model = SentenceTransformer(str(self.model_dir))
            else:
                logger.info(
                    f"Local model not found, downloading from Hugging Face: {self.model_name}"
                )
                self._model = SentenceTransformer(self.model_name)

            # Restore original environment variable
            if original_st_home:
                os.environ["SENTENCE_TRANSFORMERS_HOME"] = original_st_home
            elif "SENTENCE_TRANSFORMERS_HOME" in os.environ:
                del os.environ["SENTENCE_TRANSFORMERS_HOME"]

            # Get embedding dimension
            self._dimension = self._model.get_sentence_embedding_dimension()

            logger.info(
                f"SentenceTransformer model loaded successfully. Dimension: {self._dimension}"
            )

        except Exception as e:
            logger.error(
                f"Failed to load SentenceTransformer model: {e}", exc_info=True
            )
            raise RuntimeError(f"Failed to load SentenceTransformer model: {e}") from e

    def encode(
        self,
        texts: List[str],
    ) -> np.ndarray:
        """
        Generate embeddings using sentence-transformers.

        Args:
            texts: List of text strings to encode

        Returns:
            NumPy array of embeddings

        Raises:
            RuntimeError: If encoding fails
        """
        if self._model is None:
            self._load_model()

        try:
            embeddings = self._model.encode(texts)
            return np.array(embeddings, dtype=np.float32)
        except Exception as e:
            logger.error(f"Failed to encode texts: {e}", exc_info=True)
            raise RuntimeError(f"Failed to encode texts: {e}") from e

    def get_embedding_dimension(self) -> int:
        """
        Get the embedding dimension.

        Returns:
            Integer dimension of embedding vectors

        Raises:
            RuntimeError: If model is not loaded
        """
        if self._dimension is None:
            self._load_model()
        return self._dimension


class LiteLLMClient(EmbeddingsClient):
    """Client for cloud-based embeddings via LiteLLM."""

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        aws_region: Optional[str] = None,
        embedding_dimension: Optional[int] = None,
    ):
        """
        Initialize the LiteLLM client.

        Args:
            model_name: LiteLLM model identifier (e.g., 'bedrock/amazon.titan-embed-text-v1',
                       'openai/text-embedding-3-small', 'cohere/embed-english-v3.0')
            api_key: Optional API key for the provider
            api_base: Optional API base URL for the provider
            aws_region: Optional AWS region for Bedrock
            embedding_dimension: Expected embedding dimension (will be validated)

        Note:
            For AWS Bedrock, this client uses the standard AWS credential chain
            (IAM roles, ~/.aws/credentials, environment variables). The api_key
            parameter is not used for Bedrock authentication.
        """
        self.model_name = model_name
        self.api_key = api_key
        self.api_base = api_base
        self.aws_region = aws_region
        self._embedding_dimension = embedding_dimension
        self._validated_dimension: Optional[int] = None

        # Set environment variables for LiteLLM
        if self.api_key:
            self._set_api_key_env()
        if self.aws_region:
            os.environ["AWS_REGION_NAME"] = self.aws_region

    def _set_api_key_env(self) -> None:
        """Set the appropriate API key environment variable based on provider."""
        provider = self.model_name.split("/")[0].lower()

        # AWS Bedrock uses standard AWS credential chain (IAM roles, env vars, ~/.aws/credentials)
        # No need to set API key environment variable for Bedrock
        if provider == "bedrock":
            logger.info(
                "Using standard AWS credential chain for Bedrock authentication"
            )
            return

        # Handle other providers with API keys
        env_var_mapping = {
            "openai": "OPENAI_API_KEY",
            "cohere": "COHERE_API_KEY",
            "azure": "AZURE_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }

        env_var = env_var_mapping.get(provider)
        if env_var and self.api_key:
            os.environ[env_var] = self.api_key
            logger.debug(f"Set {env_var} environment variable for {provider}")

    def encode(
        self,
        texts: List[str],
    ) -> np.ndarray:
        """
        Generate embeddings using LiteLLM.

        Args:
            texts: List of text strings to encode

        Returns:
            NumPy array of embeddings

        Raises:
            RuntimeError: If encoding fails or LiteLLM is not installed
        """
        try:
            from litellm import embedding
        except ImportError as e:
            logger.error("LiteLLM is not installed. Install it with: uv add litellm")
            raise RuntimeError(
                "LiteLLM is not installed. Install it with: uv add litellm"
            ) from e

        try:
            # LiteLLM expects 'input' parameter
            kwargs = {"model": self.model_name, "input": texts}

            if self.api_base:
                kwargs["api_base"] = self.api_base

            logger.debug(
                f"Calling LiteLLM embedding API with model: {self.model_name}"
            )
            response = embedding(**kwargs)

            # Extract embeddings from response
            embeddings_list = [item["embedding"] for item in response["data"]]
            embeddings_array = np.array(embeddings_list, dtype=np.float32)

            # Validate dimension on first call
            if self._validated_dimension is None:
                self._validated_dimension = embeddings_array.shape[1]
                if (
                    self._embedding_dimension
                    and self._validated_dimension != self._embedding_dimension
                ):
                    logger.warning(
                        f"Embedding dimension mismatch: expected {self._embedding_dimension}, "
                        f"got {self._validated_dimension}"
                    )

            logger.debug(
                f"Generated {len(embeddings_list)} embeddings with dimension {self._validated_dimension}"
            )
            return embeddings_array

        except Exception as e:
            logger.error(f"Failed to generate embeddings via LiteLLM: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate embeddings via LiteLLM: {e}") from e

    def get_embedding_dimension(self) -> int:
        """
        Get the embedding dimension.

        Returns:
            Integer dimension of embedding vectors

        Raises:
            RuntimeError: If dimension cannot be determined
        """
        # If we have a validated dimension from actual API calls, use that
        if self._validated_dimension is not None:
            return self._validated_dimension

        # Otherwise, use the configured dimension if provided
        if self._embedding_dimension is not None:
            return self._embedding_dimension

        # As a last resort, make a test call with a simple string
        logger.info(
            "Embedding dimension not known, making test call to determine dimension"
        )
        try:
            test_embedding = self.encode(["test"])
            return test_embedding.shape[1]
        except Exception as e:
            logger.error(
                f"Failed to determine embedding dimension: {e}", exc_info=True
            )
            raise RuntimeError(
                f"Failed to determine embedding dimension: {e}. "
                "Consider setting EMBEDDINGS_DIMENSION in configuration."
            ) from e


def create_embeddings_client(
    provider: str,
    model_name: str,
    model_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    aws_region: Optional[str] = None,
    embedding_dimension: Optional[int] = None,
) -> EmbeddingsClient:
    """
    Factory function to create an embeddings client based on provider.

    Args:
        provider: Provider type ('sentence-transformers' or 'litellm')
        model_name: Model identifier
        model_dir: Optional local model directory (sentence-transformers only)
        cache_dir: Optional cache directory (sentence-transformers only)
        api_key: Optional API key (litellm only)
        api_base: Optional API base URL (litellm only)
        aws_region: Optional AWS region (litellm with Bedrock only)
        embedding_dimension: Optional embedding dimension

    Returns:
        EmbeddingsClient instance

    Raises:
        ValueError: If provider is not supported

    Note:
        For AWS Bedrock, AWS credentials should be configured via standard AWS
        credential chain (IAM roles, environment variables, ~/.aws/credentials).
    """
    provider_lower = provider.lower()

    if provider_lower == "sentence-transformers":
        logger.info(
            f"Creating SentenceTransformersClient with model: {model_name}"
        )
        return SentenceTransformersClient(
            model_name=model_name,
            model_dir=model_dir,
            cache_dir=cache_dir,
        )

    elif provider_lower == "litellm":
        # Validate that model name has provider prefix
        if "/" not in model_name:
            raise ValueError(
                f"Invalid model name for LiteLLM provider: '{model_name}'. "
                f"LiteLLM requires provider-prefixed model names. "
                f"Examples: 'openai/text-embedding-3-small', 'bedrock/amazon.titan-embed-text-v1', "
                f"'cohere/embed-english-v3.0'. "
                f"If you want to use '{model_name}', set EMBEDDINGS_PROVIDER=sentence-transformers"
            )

        logger.info(f"Creating LiteLLMClient with model: {model_name}")
        return LiteLLMClient(
            model_name=model_name,
            api_key=api_key,
            api_base=api_base,
            aws_region=aws_region,
            embedding_dimension=embedding_dimension,
        )

    else:
        raise ValueError(
            f"Unsupported embeddings provider: {provider}. "
            "Supported providers: 'sentence-transformers', 'litellm'"
        )
