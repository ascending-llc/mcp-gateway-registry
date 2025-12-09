"""
Unified Search Framework for Weaviate

This module provides a comprehensive search framework that unifies model-based
and collection-based search operations with advanced filtering capabilities.

Key Components:
- Q: Query objects for complex filtering with logical operators
- QueryBuilder: Fluent interface for building search queries
- SearchTarget: Adapter pattern for unified model/collection handling
- SearchStrategy: Pluggable search strategies
- UnifiedSearchInterface: High-level search API

Example:
    # Model-based search
    results = Article.objects.filter(category="tech").search("AI").all()
    
    # Collection-based search
    results = search.collection("Articles").filter(status="published").all()
    
    # Complex filtering
    results = Article.objects.filter(
        Q(category="tech") | Q(category="science")
    ).filter(views__gt=1000).all()
"""

# Core filtering
from .filters import (
    Q,
    FilterOperatorRegistry,
    and_,
    or_,
    not_
)

# Query building
from .query_state import QueryState
from .query_builder import QueryBuilder, QueryExecutor, create_query
from .strategies import (
    SearchStrategy,
    SearchStrategyFactory,
    BM25Strategy,
    NearTextStrategy,
    NearVectorStrategy,
    HybridStrategy,
    FuzzyStrategy,
    FetchObjectsStrategy,
    NearImageStrategy
)

# Target adapters
from .targets import (
    SearchTarget,
    ModelTarget,
    CollectionTarget
)

# Unified interface
from .unified import (
    UnifiedSearchInterface,
    get_search_interface,
    search_model,
    search_collection
)

# Advanced features
from .aggregation import AggregationBuilder, AggregationType, MetricDefinition
from .advanced import (
    GenerativeConfig,
    RerankConfig,
    GenerativeSearchMixin,
    RerankMixin,
    MultiVectorMixin,
    ImageSearchMixin
)

__all__ = [
    # Filtering
    'Q',
    'FilterOperatorRegistry',
    'and_',
    'or_',
    'not_',
    
    # Query building
    'QueryState',
    'QueryBuilder',
    'QueryExecutor',
    'create_query',
    
    # Strategies
    'SearchStrategy',
    'SearchStrategyFactory',
    'BM25Strategy',
    'NearTextStrategy',
    'NearVectorStrategy',
    'HybridStrategy',
    'FuzzyStrategy',
    'FetchObjectsStrategy',
    'NearImageStrategy',
    
    # Targets
    'SearchTarget',
    'ModelTarget',
    'CollectionTarget',
    
    # Unified interface
    'UnifiedSearchInterface',
    'get_search_interface',
    'search_model',
    'search_collection',
    
    # Advanced features
    'AggregationBuilder',
    'AggregationType',
    'MetricDefinition',
    'GenerativeConfig',
    'RerankConfig',
    'GenerativeSearchMixin',
    'RerankMixin',
    'MultiVectorMixin',
    'ImageSearchMixin',
]
