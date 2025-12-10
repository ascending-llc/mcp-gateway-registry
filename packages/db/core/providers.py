"""
Simplified embeddings provider for Bedrock and OpenAI.

Supports AWS Bedrock and OpenAI embedding services via Weaviate modules.
"""

import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class EmbeddingsProvider:
    """
    Base class for embeddings providers.
    
    Each provider implements authentication and vectorizer configuration
    for a specific embeddings service.
    """
    
    def get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for authentication.
        
        Returns:
            Dictionary of headers to pass to Weaviate
        """
        pass
    
    def get_vectorizer_name(self) -> str:
        """
        Get the Weaviate vectorizer name for this provider.
        
        Returns:
            Vectorizer name (e.g., "text2vec-aws", "text2vec-openai")
        """
        pass
    
    def get_model_name(self) -> str:
        """
        Get the default model name for this provider.
        
        Returns:
            Model name (e.g., "amazon.titan-embed-text-v2:0")
        """
        pass


class BedrockProvider(EmbeddingsProvider):
    """
    AWS Bedrock embeddings provider.
    
    Supports AWS Bedrock embedding models via Weaviate's text2vec-aws module.
    """
    
    def __init__(
        self,
        access_key: str = "",
        secret_key: str = "",
        region: str = "us-east-1",
        session_token: Optional[str] = None,
        model: str = "amazon.titan-embed-text-v2:0"
    ):
        """
        Initialize Bedrock provider.
        
        Args:
            access_key: AWS access key ID (empty for IAM Role)
            secret_key: AWS secret access key (empty for IAM Role)
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
        """
        headers = {}
        
        if self.access_key and self.secret_key:
            headers['X-AWS-Access-Key'] = self.access_key
            headers['X-AWS-Secret-Key'] = self.secret_key
            
            if self.session_token:
                headers['X-AWS-Session-Token'] = self.session_token
                logger.debug("Using explicit AWS credentials with session token")
            else:
                logger.debug("Using explicit AWS credentials")
        else:
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
        
        Environment variables:
            AWS_ACCESS_KEY_ID: AWS access key (optional if using IAM Role)
            AWS_SECRET_ACCESS_KEY: AWS secret key (optional if using IAM Role)
            AWS_REGION: AWS region (default: us-east-1)
            AWS_SESSION_TOKEN: Session token (optional)
            EMBEDDINGS_MODEL: Model name (optional)
        """
        return cls(
            access_key=os.getenv("AWS_ACCESS_KEY_ID", ""),
            secret_key=os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            region=os.getenv("AWS_REGION", "us-east-1"),
            session_token=os.getenv("AWS_SESSION_TOKEN"),
            model=os.getenv("EMBEDDINGS_MODEL", "amazon.titan-embed-text-v2:0")
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
        """
        api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required for OpenAI provider")
        
        return cls(
            api_key=api_key,
            model=os.getenv("OPENAI_MODEL", "text-embedding-ada-002")
        )


def create_provider_from_env() -> EmbeddingsProvider:
    """
    Create provider from environment variables.
    
    Environment variables:
        EMBEDDINGS_PROVIDER: Provider name (bedrock or openai, default: bedrock)
    
    Returns:
        Provider instance configured from environment
    """
    provider_name = os.getenv("EMBEDDINGS_PROVIDER", "bedrock")
    
    if provider_name == "bedrock":
        return BedrockProvider.from_env()
    elif provider_name == "openai":
        return OpenAIProvider.from_env()
    else:
        raise ValueError(f"Invalid provider: {provider_name}. Supported: bedrock, openai")
