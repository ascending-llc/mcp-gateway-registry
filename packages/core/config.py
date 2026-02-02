from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """
    Unified configuration for MCP Gateway Registry.
    
    Environment variables are loaded from .env file.
    """
    
    # ========== Text Chunking Configuration ==========
    MAX_CHUNK_SIZE: Optional[int] = Field(
        default=2048,
        description="Maximum size of text chunks for vectorization"
    )
    CHUNK_OVERLAP: Optional[int] = Field(
        default=200,
        description="Overlap size between consecutive chunks"
    )

    # ========== Vector Store Configuration ==========
    VECTOR_STORE_TYPE: Optional[str] = Field(
        default="weaviate",
        description="Vector database type (supported: weaviate)"
    )
    EMBEDDING_PROVIDER: Optional[str] = Field(
        default="aws_bedrock",
        description="Embedding provider (supported: openai, aws_bedrock)"
    )

    # ========== Weaviate Configuration ==========
    WEAVIATE_HOST: Optional[str] = Field(
        default="127.0.0.1",
        description="Weaviate server host address"
    )
    WEAVIATE_PORT: Optional[str] = Field(
        default="8080",
        description="Weaviate server port"
    )
    WEAVIATE_API_KEY: Optional[str] = Field(
        default="",
        description="Weaviate API key for authentication (optional)"
    )
    WEAVIATE_COLLECTION_PREFIX: Optional[str] = Field(
        default="",
        description="Prefix for Weaviate collection names (optional)"
    )

    # ========== OpenAI Configuration ==========
    OPENAI_API_KEY: Optional[str] = Field(
        default="",
        description="OpenAI API key (required when EMBEDDING_PROVIDER=openai)"
    )
    OPENAI_MODEL: Optional[str] = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model name"
    )

    # ========== AWS Bedrock Configuration ==========
    AWS_REGION: Optional[str] = Field(
        default="us-east-1",
        description="AWS region for Bedrock service"
    )
    BEDROCK_MODEL: Optional[str] = Field(
        default="amazon.titan-embed-text-v2:0",
        description="AWS Bedrock embedding model name"
    )
    AWS_ACCESS_KEY_ID: Optional[str] = Field(
        default="",
        description="AWS access key ID (optional, uses default credentials chain if not set)"
    )
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(
        default="",
        description="AWS secret access key (optional, uses default credentials chain if not set)"
    )

    # ========== MongoDB Configuration ==========
    MONGO_URI: Optional[str] = Field(
        default="mongodb://127.0.0.1:27017/jarvis",
        description="MongoDB connection URI (format: mongodb://host:port/dbname)"
    )
    MONGODB_USERNAME: Optional[str] = Field(
        default="",
        description="MongoDB username for authentication (optional)"
    )
    MONGODB_PASSWORD: Optional[str] = Field(
        default="",
        description="MongoDB password for authentication (optional)"
    )

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="allow"  # Allow extra fields
    )


settings = Settings()
