"""
Embeddings provider strategy pattern.

Provides pluggable providers for different embedding services (Bedrock, OpenAI, etc.)
Each provider knows how to configure authentication and get the appropriate vectorizer.
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Type

from .exceptions import InvalidProvider, MissingCredentials

logger = logging.getLogger(__name__)


class EmbeddingsProvider(ABC):
    """
    Abstract base class for embeddings providers.
    
    Each provider implements authentication and vectorizer configuration
    for a specific embeddings service.
    """
    
    @abstractmethod
    def get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for authentication.
        
        Returns:
            Dictionary of headers to pass to Weaviate
        """
        pass
    
    @abstractmethod
    def get_vectorizer_name(self) -> str:
        """
        Get the Weaviate vectorizer name for this provider.
        
        Returns:
            Vectorizer name (e.g., "text2vec-aws", "text2vec-openai")
        """
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """
        Get the default model name for this provider.
        
        Returns:
            Model name (e.g., "amazon.titan-embed-text-v2:0")
        """
        pass
    
    @classmethod
    @abstractmethod
    def from_env(cls) -> 'EmbeddingsProvider':
        """
        Create provider instance from environment variables.
        
        Returns:
            Provider instance configured from environment
            
        Raises:
            MissingCredentials: If required credentials are not found
        """
        pass


class BedrockProvider(EmbeddingsProvider):
    """
    AWS Bedrock embeddings provider.
    
    Supports AWS Bedrock embedding models via Weaviate's text2vec-aws module.
    """
    
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        session_token: Optional[str] = None,
        model: str = "amazon.titan-embed-text-v2:0"
    ):
        """
        Initialize Bedrock provider.
        
        Args:
            access_key: AWS access key ID
            secret_key: AWS secret access key
            region: AWS region
            session_token: Optional session token for temporary credentials
            model: Bedrock model name
        """
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.session_token = session_token
        self.model = model
    
    def get_headers(self) -> Dict[str, str]:
        """
        Get AWS authentication headers.
        
        If access_key and secret_key are provided, use explicit credentials.
        If not provided (empty strings), returns empty dict to enable IAM Role auth.
        
        Returns:
            Dictionary of authentication headers
        """
        headers = {}
        
        # Only add headers if explicit credentials are provided
        if self.access_key and self.secret_key:
            headers['X-AWS-Access-Key'] = self.access_key
            headers['X-AWS-Secret-Key'] = self.secret_key
            
            if self.session_token:
                headers['X-AWS-Session-Token'] = self.session_token
                logger.debug("Using explicit AWS credentials with session token")
            else:
                logger.debug("Using explicit AWS credentials")
        else:
            # No headers = use IAM Role / instance profile
            logger.debug("Using IAM Role authentication (no explicit credentials)")
        
        return headers
    
    def get_vectorizer_name(self) -> str:
        """Get Weaviate vectorizer name for Bedrock."""
        return "text2vec-aws"
    
    def get_model_name(self) -> str:
        """Get Bedrock model name."""
        return self.model
    
    @classmethod
    def from_env(cls) -> 'BedrockProvider':
        """
        Create Bedrock provider from environment variables.
        
        Supports two authentication methods:
        1. Explicit credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        2. IAM Role (EC2/ECS/EKS instance profile) - no explicit credentials needed
        
        Environment variables:
            AWS_ACCESS_KEY_ID: AWS access key (optional if using IAM Role)
            AWS_SECRET_ACCESS_KEY: AWS secret key (optional if using IAM Role)
            AWS_REGION: AWS region (default: us-east-1)
            AWS_SESSION_TOKEN: Session token (optional)
            RAG_EMBEDDINGS_MODEL: Model name (optional)
        
        Returns:
            BedrockProvider instance
        
        Note:
            If credentials are not provided, assumes IAM Role authentication.
            The underlying AWS SDK will automatically fetch credentials from
            instance metadata service.
        """
        access_key = os.getenv("AWS_ACCESS_KEY_ID", "")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "")
        
        # If no explicit credentials, use empty strings to enable IAM Role authentication
        # Weaviate's AWS integration will use boto3's default credential chain
        return cls(
            access_key=access_key,
            secret_key=secret_key,
            region=os.getenv("AWS_REGION", "us-east-1"),
            session_token=os.getenv("AWS_SESSION_TOKEN"),
            model=os.getenv("RAG_EMBEDDINGS_MODEL", "amazon.titan-embed-text-v2:0")
        )


class OpenAIProvider(EmbeddingsProvider):
    """
    OpenAI embeddings provider.
    
    Supports OpenAI embedding models via Weaviate's text2vec-openai module.
    """
    
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-ada-002"
    ):
        """
        Initialize OpenAI provider.
        
        Args:
            api_key: OpenAI API key
            model: OpenAI model name
        """
        self.api_key = api_key
        self.model = model
    
    def get_headers(self) -> Dict[str, str]:
        """Get OpenAI authentication headers."""
        return {'X-OpenAI-Api-Key': self.api_key}
    
    def get_vectorizer_name(self) -> str:
        """Get Weaviate vectorizer name for OpenAI."""
        return "text2vec-openai"
    
    def get_model_name(self) -> str:
        """Get OpenAI model name."""
        return self.model
    
    @classmethod
    def from_env(cls) -> 'OpenAIProvider':
        """
        Create OpenAI provider from environment variables.
        
        Environment variables:
            OPENAI_API_KEY: OpenAI API key (required)
            OPENAI_MODEL: Model name (optional)
        
        Returns:
            OpenAIProvider instance
            
        Raises:
            MissingCredentials: If API key not found
        """
        api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise MissingCredentials("openai", ["OPENAI_API_KEY"])
        
        return cls(
            api_key=api_key,
            model=os.getenv("OPENAI_MODEL", "text-embedding-ada-002")
        )


class ProviderFactory:
    """
    Factory for creating embeddings providers.
    
    Allows registration of custom providers for extensibility.
    """
    
    _providers: Dict[str, Type[EmbeddingsProvider]] = {
        'bedrock': BedrockProvider,
        'openai': OpenAIProvider
    }
    
    @classmethod
    def register(cls, name: str, provider_class: Type[EmbeddingsProvider]):
        """
        Register a custom provider.
        
        Args:
            name: Provider name (e.g., "cohere", "custom")
            provider_class: Provider class
        """
        cls._providers[name] = provider_class
        logger.info(f"Registered embeddings provider: {name}")
    
    @classmethod
    def create(cls, name: str, **kwargs) -> EmbeddingsProvider:
        """
        Create provider instance by name.
        
        Args:
            name: Provider name
            **kwargs: Provider-specific arguments
        
        Returns:
            Provider instance
            
        Raises:
            InvalidProvider: If provider name is not registered
        """
        provider_class = cls._providers.get(name)
        
        if not provider_class:
            available = list(cls._providers.keys())
            raise InvalidProvider(name, available)
        
        return provider_class(**kwargs)
    
    @classmethod
    def from_env(cls) -> EmbeddingsProvider:
        """
        Create provider from environment variables.
        
        Environment variables:
            EMBEDDINGS_PROVIDER: Provider name (default: bedrock)
        
        Returns:
            Provider instance configured from environment
            
        Raises:
            InvalidProvider: If provider name is invalid
            MissingCredentials: If credentials are missing
        """
        provider_name = os.getenv("EMBEDDINGS_PROVIDER", "bedrock")
        provider_class = cls._providers.get(provider_name)
        
        if not provider_class:
            available = list(cls._providers.keys())
            raise InvalidProvider(provider_name, available)
        
        return provider_class.from_env()
    
    @classmethod
    def list_providers(cls) -> list:
        """List all registered providers."""
        return list(cls._providers.keys())

