"""
Core modules for Weaviate client and registry management.
"""

from .client import WeaviateClient, ManagedConnection
from .config import ConnectionConfig, TimeoutConfig
from .providers import EmbeddingsProvider, BedrockProvider, OpenAIProvider, create_provider_from_env
from .registry import WeaviateClientRegistry, init_weaviate, get_weaviate_client, close_weaviate
from .enums import LLMProvider, SearchType
from .exceptions import (
    WeaviateORMException,
    ConnectionException,
    ConfigurationException,
    QueryException,
    DoesNotExist,
    MultipleObjectsReturned,
    ValidationException,
    FieldValidationError,
    CollectionException,
    CollectionNotFound,
    DataOperationException,
    InsertFailed
)

__all__ = [
    # Client
    'WeaviateClient',
    'ManagedConnection',
    
    # Configuration
    'ConnectionConfig',
    'TimeoutConfig',
    
    # Providers
    'EmbeddingsProvider',
    'BedrockProvider',
    'OpenAIProvider',
    'create_provider_from_env',
    
    # Registry
    'WeaviateClientRegistry',
    'init_weaviate',
    'get_weaviate_client',
    'close_weaviate',
    
    # Enums
    'LLMProvider',
    'SearchType',
    
    # Exceptions
    'WeaviateORMException',
    'ConnectionException',
    'ConfigurationException',
    'QueryException',
    'DoesNotExist',
    'MultipleObjectsReturned',
    'ValidationException',
    'FieldValidationError',
    'CollectionException',
    'CollectionNotFound',
    'DataOperationException',
    'InsertFailed',
]
