# Core
from .core import (
    WeaviateClient, WeaviateConfig, WeaviateClientRegistry,
    init_weaviate, get_weaviate_client, close_weaviate,
    LLMProvider, SearchType,
    DoesNotExist, MultipleObjectsReturned
)

# Models
from .models import (
    Model,
    TextField, IntField, FloatField, BooleanField,
    DateTimeField, UUIDField, TextArrayField, IntArrayField
)

# Managers
from .managers import (
    CollectionManager, QuerySet, ObjectManager, DirectDataManager
)

# Search
from .search import SearchManager, AdvancedQuerySet, DirectSearchManager, BaseSearchOperations

__all__ = [
    # Core - Client
    'WeaviateClient',
    'WeaviateConfig',
    'WeaviateClientRegistry',
    
    # Core - Registry
    'init_weaviate',
    'get_weaviate_client',
    'close_weaviate',
    
    # Core - Enums
    'LLMProvider',
    'SearchType',
    
    # Core - Exceptions
    'DoesNotExist',
    'MultipleObjectsReturned',
    
    # Models
    'Model',
    
    # Models - Fields
    'TextField',
    'IntField',
    'FloatField',
    'BooleanField',
    'DateTimeField',
    'UUIDField',
    'TextArrayField',
    'IntArrayField',
    
    # Managers
    'CollectionManager',
    'QuerySet',
    'ObjectManager',
    'DirectDataManager',
    
    # Search
    'SearchManager',
    'AdvancedQuerySet',
    'DirectSearchManager',
    'BaseSearchOperations',
]
