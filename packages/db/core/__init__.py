"""
Core modules for Weaviate client and registry management.
"""

from .client import WeaviateClient, ManagedConnection
from .config import ConnectionConfig, TimeoutConfig
from .providers import EmbeddingsProvider, BedrockProvider, OpenAIProvider, ProviderFactory
from .registry import WeaviateClientRegistry, init_weaviate, get_weaviate_client, close_weaviate
from .enums import LLMProvider, SearchType
from .exceptions import (
    WeaviateORMException,
    ConnectionException,
    ConnectionTimeout,
    ConnectionFailed,
    ConfigurationException,
    InvalidProvider,
    MissingCredentials,
    InvalidConfiguration,
    QueryException,
    DoesNotExist,
    MultipleObjectsReturned,
    InvalidQuery,
    ValidationException,
    FieldValidationError,
    RequiredFieldMissing,
    ModelValidationError,
    CollectionException,
    CollectionNotFound,
    CollectionAlreadyExists,
    CollectionCreationFailed,
    DataOperationException,
    InsertFailed,
    UpdateFailed,
    DeleteFailed
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
    'ProviderFactory',
    
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
    'ConnectionTimeout',
    'ConnectionFailed',
    'ConfigurationException',
    'InvalidProvider',
    'MissingCredentials',
    'InvalidConfiguration',
    'QueryException',
    'DoesNotExist',
    'MultipleObjectsReturned',
    'InvalidQuery',
    'ValidationException',
    'FieldValidationError',
    'RequiredFieldMissing',
    'ModelValidationError',
    'CollectionException',
    'CollectionNotFound',
    'CollectionAlreadyExists',
    'CollectionCreationFailed',
    'DataOperationException',
    'InsertFailed',
    'UpdateFailed',
    'DeleteFailed',
]

