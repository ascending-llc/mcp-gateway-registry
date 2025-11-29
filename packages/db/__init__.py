# Core
from .core import (
    # Client
    WeaviateClient,
    ManagedConnection,
    
    # Configuration
    ConnectionConfig,
    TimeoutConfig,
    
    # Providers
    EmbeddingsProvider,
    BedrockProvider,
    OpenAIProvider,
    ProviderFactory,
    
    # Registry
    WeaviateClientRegistry,
    init_weaviate,
    get_weaviate_client,
    close_weaviate,
    
    # Enums
    LLMProvider,
    SearchType,
    
    # Exceptions (all of them)
    WeaviateORMException,
    ConnectionException,
    ConnectionFailed,
    ConfigurationException,
    InvalidProvider,
    MissingCredentials,
    QueryException,
    DoesNotExist,
    MultipleObjectsReturned,
    ValidationException,
    FieldValidationError,
    CollectionException,
    CollectionNotFound
)

# Models
from .models import (
    # Model base
    Model,
    
    # Field types
    TextField,
    IntField,
    FloatField,
    BooleanField,
    DateTimeField,
    UUIDField,
    TextArrayField,
    IntArrayField,
    
    # Validators
    FieldValidator,
    RequiredValidator,
    MaxLengthValidator,
    MinLengthValidator,
    RangeValidator,
    PatternValidator,
    ChoicesValidator,
    EmailValidator,
    URLValidator,
    
    # Converters
    FieldConverter,
    DateTimeConverter,
    JSONConverter,
    EnumConverter,
    BoolConverter
)

# Managers
from .managers import (
    BatchResult,
    CollectionManager,
    ObjectManager,
)

# Search
from .search import (
    # Core search
    Q,
    and_,
    or_,
    not_,
    QueryBuilder,
    UnifiedSearchInterface,
    get_search_interface,
    search_model,
    search_collection,
    
    # Advanced
    AggregationBuilder,
    FilterOperatorRegistry,
    SearchStrategyFactory,
    
    # Targets
    SearchTarget,
    ModelTarget,
    CollectionTarget,
)

__all__ = [
    # Core - Client
    'WeaviateClient',
    'ManagedConnection',
    
    # Core - Configuration
    'ConnectionConfig',
    'TimeoutConfig',
    
    # Core - Providers
    'EmbeddingsProvider',
    'BedrockProvider',
    'OpenAIProvider',
    'ProviderFactory',
    
    # Core - Registry
    'WeaviateClientRegistry',
    'init_weaviate',
    'get_weaviate_client',
    'close_weaviate',
    
    # Core - Enums
    'LLMProvider',
    'SearchType',
    
    # Core - Exceptions
    'WeaviateORMException',
    'ConnectionException',
    'ConnectionFailed',
    'ConfigurationException',
    'InvalidProvider',
    'MissingCredentials',
    'QueryException',
    'DoesNotExist',
    'MultipleObjectsReturned',
    'ValidationException',
    'FieldValidationError',
    'CollectionException',
    'CollectionNotFound',
    'InsertFailed',
    'UpdateFailed',
    'DeleteFailed',
    
    # Models - Base
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
    
    # Models - Validators
    'FieldValidator',
    'RequiredValidator',
    'MaxLengthValidator',
    'MinLengthValidator',
    'RangeValidator',
    'PatternValidator',
    'ChoicesValidator',
    'EmailValidator',
    'URLValidator',
    
    # Models - Converters
    'FieldConverter',
    'DateTimeConverter',
    'JSONConverter',
    'EnumConverter',
    'BoolConverter',
    
    # Managers
    'BatchResult',
    'CollectionManager',
    'ObjectManager',
    
    # Search - Core
    'Q',
    'and_',
    'or_',
    'not_',
    'QueryBuilder',
    'UnifiedSearchInterface',
    'get_search_interface',
    'search_model',
    'search_collection',
    
    # Search - Advanced
    'AggregationBuilder',
    'FilterOperatorRegistry',
    'SearchStrategyFactory',
    'SearchTarget',
    'ModelTarget',
    'CollectionTarget',
]

__version__ = '2.0.0'
