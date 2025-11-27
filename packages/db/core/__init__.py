"""
Core modules for Weaviate client and registry management.
"""

from .client import WeaviateClient, WeaviateConfig, ManagedConnection
from .registry import WeaviateClientRegistry, init_weaviate, get_weaviate_client, close_weaviate
from .enums import LLMProvider, SearchType
from .exceptions import DoesNotExist, MultipleObjectsReturned

__all__ = [
    # Client
    'WeaviateClient',
    'WeaviateConfig',
    'ManagedConnection',
    # Registry
    'WeaviateClientRegistry',
    'init_weaviate',
    'get_weaviate_client',
    'close_weaviate',
    # Enums
    'LLMProvider',
    'SearchType',
    # Exceptions
    'DoesNotExist',
    'MultipleObjectsReturned',
]

