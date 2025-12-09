# Weaviate Django-ORM Framework

A Django-inspired ORM framework for Weaviate with advanced search capabilities.

## Features

- 🎯 Django-like API with `Model.objects` pattern
- 🔍 Advanced search (BM25, semantic, hybrid, fuzzy)
- 📊 Aggregation (group by, count, avg, sum, min, max)
- ✅ Field validation and type conversion
- 🔧 Clean configuration (3 objects vs 17 parameters)
- 🔌 Extensible providers, validators, and search strategies
- 📦 Batch operations with error reporting
- 🤖 Generative search (RAG) and reranking
- ⚡ High performance (optimized queries, caching, parallel execution)

---

## Quick Start

### Installation

```bash
pip install -e ./packages
```

### Environment Variables

```bash
# Weaviate Connection
WEAVIATE_HOST=127.0.0.1
WEAVIATE_PORT=8099
WEAVIATE_API_KEY=your-api-key

# Embeddings Provider
EMBEDDINGS_PROVIDER=bedrock  # or openai

# AWS Bedrock - Option 1: Explicit credentials
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret

# AWS Bedrock - Option 2: IAM Role (EC2/ECS/EKS)
# No AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY needed
# The SDK will automatically use instance profile credentials
AWS_REGION=us-east-1

# OpenAI
OPENAI_API_KEY=sk-your-key
```

### Basic Usage

```python
from db import WeaviateClient, Model, TextField, IntField

# 1. Initialize client
client = WeaviateClient()

# 2. Define model
class Article(Model):
    title = TextField(required=True, max_length=200)
    content = TextField(required=True)
    views = IntField(min_value=0)
    
    class Meta:
        collection_name = "Articles"

# 3. Create collection
Article.create_collection()

# 4. CRUD operations
article = Article.objects.create(title="Test", content="...")
article = Article.objects.get_by_id("uuid")
Article.objects.update(article, title="Updated")
article.delete()

# 5. Search
results = Article.objects.search("AI").limit(10).all()

# 6. Batch operations
result = Article.objects.bulk_create(articles, batch_size=200)
print(f"Success: {result.successful}/{result.total}")
```

---

## Architecture

```
db/
├── core/                   # Client, configuration, providers
│   ├── client.py           # WeaviateClient
│   ├── config.py           # ConnectionConfig, TimeoutConfig
│   ├── providers.py        # EmbeddingsProvider (strategy pattern)
│   ├── registry.py         # Singleton registry
│   └── exceptions.py       # Exception hierarchy
│
├── models/                 # Model definitions
│   ├── model.py            # Model base class
│   ├── base.py             # Field types
│   ├── descriptors.py      # ObjectManagerDescriptor
│   ├── validators.py       # Field validators
│   └── converters.py       # Type converters
│
├── managers/               # CRUD operations
│   ├── batch.py            # BatchResult
│   ├── collection.py       # CollectionManager
│   ├── object.py           # ObjectManager
│   └── data.py             # DirectDataManager
│
└── search/                 # Search framework
    ├── filters.py          # Q objects, FilterOperatorRegistry
    ├── query_builder.py    # QueryBuilder, QueryExecutor
    ├── strategies.py       # Search strategies
    ├── unified.py          # UnifiedSearchInterface
    ├── aggregation.py      # Aggregation support
    ├── advanced.py         # Generative, reranking
    ├── performance.py      # Caching, optimization
    └── plugins.py          # Plugin system
```

**Design Patterns:**
- Strategy (providers, search strategies)
- Adapter (search targets)
- Builder (query building)
- Descriptor (lazy initialization)
- Plugin (extensibility)

---

## Configuration

### Simple (Environment Variables)

```python
from db import WeaviateClient

client = WeaviateClient()  # Uses environment variables

# Health check
if client.is_ready():
    print("✅ Client ready")
```

### Custom Configuration

```python
from db import WeaviateClient, ConnectionConfig, BedrockProvider, TimeoutConfig

# With explicit AWS credentials
client = WeaviateClient(
    connection=ConnectionConfig(
        host="localhost",
        port=8099,
        api_key="secret",
        pool_connections=20
    ),
    provider=BedrockProvider(
        access_key="aws-key",
        secret_key="aws-secret",
        region="us-east-1"
    ),
    timeouts=TimeoutConfig(query=120)
)

# Using IAM Role (no credentials needed)
client = WeaviateClient(
    connection=ConnectionConfig(host="localhost", port=8099),
    provider=BedrockProvider(
        access_key="",  # Empty = use IAM Role
        secret_key="",
        region="us-east-1"
    )
)

# Or simply (from env, supports both methods)
client = WeaviateClient()  # Auto-detects IAM Role if no credentials in env
```

### Custom Provider

```python
from db.core.providers import EmbeddingsProvider, ProviderFactory

class CustomProvider(EmbeddingsProvider):
    def get_headers(self):
        return {'X-Custom-Key': self.api_key}
    
    def get_vectorizer_name(self):
        return "text2vec-custom"
    
    def get_model_name(self):
        return "custom-model"
    
    @classmethod
    def from_env(cls):
        import os
        return cls(os.getenv("CUSTOM_KEY"))

ProviderFactory.register('custom', CustomProvider)
```

---

## Model Definition

### Basic Model

```python
from db import Model, TextField, IntField, BooleanField, DateTimeField

class Article(Model):
    title = TextField(required=True)
    content = TextField(required=True)
    views = IntField()
    published = BooleanField()
    created_at = DateTimeField()
    
    class Meta:
        collection_name = "Articles"
        vectorizer = "text2vec-openai"
```

### Model with Validation

```python
from db import TextField, IntField, FloatField, EmailValidator, RangeValidator

class User(Model):
    username = TextField(required=True, min_length=3, max_length=50)
    email = TextField(required=True, validators=[EmailValidator()])
    age = IntField(min_value=0, max_value=150)
    rating = FloatField(validators=[RangeValidator(0.0, 5.0)])
```

### Available Validators

- `RequiredValidator` - Not None
- `MaxLengthValidator(max)` - String max length
- `MinLengthValidator(min)` - String min length
- `RangeValidator(min, max)` - Numeric range
- `PatternValidator(regex)` - Regex pattern
- `ChoicesValidator(choices)` - Allowed values
- `EmailValidator()` - Email format
- `URLValidator()` - URL format

### Available Converters

- `DateTimeConverter` - datetime ↔ ISO string
- `JSONConverter` - dict/list ↔ JSON string
- `EnumConverter(enum_class)` - Enum ↔ string
- `BoolConverter` - Flexible bool conversion

---

## CRUD Operations

### Single Operations

```python
# Create
article = Article.objects.create(title="Test", content="...")

# Get by ID (fast)
article = Article.objects.get_by_id("uuid-123")

# Get by field
article = Article.objects.get(title="Test")

# Update
Article.objects.update(article, title="Updated", views=100)

# Delete
article.delete()
```

### Batch Operations

```python
# Bulk create with error reporting
articles = [Article(title=f"Article {i}") for i in range(1000)]
result = Article.objects.bulk_create(articles, batch_size=200)

print(f"Success: {result.successful}/{result.total}")
print(f"Failed: {result.failed}")
print(f"Success rate: {result.success_rate}%")

if result.has_errors:
    for error in result.errors[:5]:
        print(f"  {error['uuid']}: {error['message']}")

# Bulk import with progress tracking
data_list = [{"title": f"Title {i}", "content": "..."} for i in range(10000)]

def show_progress(current, total):
    print(f"\rProgress: {current}/{total} ({current/total*100:.1f}%)", end="")

result = Article.objects.bulk_import(
    data_list,
    batch_size=200,
    use_dynamic=True,  # Auto-optimize batch size
    on_progress=show_progress
)

print(f"\n✅ Imported {result.successful}/{result.total}")

# Bulk update
updates = [
    {'id': 'uuid-1', 'views': 100},
    {'id': 'uuid-2', 'views': 200}
]
result = Article.objects.bulk_update(updates)

# Bulk delete by ID
result = Article.objects.bulk_delete(['uuid-1', 'uuid-2'])

# Delete by condition
count = Article.objects.delete_where(status="draft", views__lt=10)
print(f"Deleted {count} objects")
```

---

## Search Operations

### Unified Search by Type

The `search_by_type()` method provides a unified interface for all search types:

```python
from db import SearchType

# Works with models
results = Article.objects.search_by_type(
    SearchType.HYBRID,
    query="machine learning"
).all()

# Works with collections (no model needed)
from db.search import get_search_interface

search = get_search_interface()
results = search.collection("Articles").search_by_type(
    SearchType.BM25,
    query="python"
).all()

# Dynamic type selection
def smart_search(query: str, mode: str):
    type_map = {
        'exact': SearchType.BM25,
        'semantic': SearchType.NEAR_TEXT,
        'balanced': SearchType.HYBRID
    }
    return Article.objects.search_by_type(
        type_map.get(mode, SearchType.HYBRID),
        query=query
    ).all()
```

### Basic Search

```python
# Hybrid search (default)
results = Article.objects.search("machine learning").limit(10).all()

# BM25 keyword search
results = Article.objects.bm25("Python 3.11").all()

# Semantic search
results = Article.objects.near_text("artificial intelligence").all()

# Hybrid with alpha control
results = Article.objects.hybrid("AI", alpha=0.7).all()

# Fuzzy search (typo-tolerant)
results = Article.objects.fuzzy("machin lernin").all()

# Unified search by type (recommended for dynamic selection)
from db import SearchType

results = Article.objects.search_by_type(
    SearchType.HYBRID,
    query="machine learning"
).all()

results = Article.objects.search_by_type(
    SearchType.BM25,
    query="Python 3.11"
).all()
```

### Filtering

```python
from db import Q

# Simple filters
results = Article.objects.filter(category="tech", published=True).all()

# Field lookups
results = Article.objects.filter(
    views__gt=1000,
    tags__contains_any=["python", "ai"],
    created_at__gte="2024-01-01"
).all()

# Q objects with logical operators
results = Article.objects.filter(
    Q(category="tech") | Q(category="science")
).filter(views__gt=100).all()

# Complex conditions
results = Article.objects.filter(
    (Q(category="tech") | Q(category="science")) &
    Q(published=True) &
    ~Q(status="draft")
).all()
```

### Field Lookups

```python
# Comparison
Article.objects.filter(views__gt=1000)
Article.objects.filter(views__gte=1000)
Article.objects.filter(views__lt=100)
Article.objects.filter(views__lte=100)
Article.objects.filter(status__ne="draft")

# Arrays
Article.objects.filter(tags__contains_any=["python", "java"])
Article.objects.filter(tags__contains_all=["python", "web"])
Article.objects.filter(category__in=["tech", "science"])

# Strings
Article.objects.filter(title__like="*Python*")

# Nulls
Article.objects.filter(deleted_at__is_null=True)
Article.objects.filter(deleted_at__not_null=True)
```

### Aggregation

```python
# Group by with metrics
stats = Article.objects.aggregate()\
    .group_by("category")\
    .count()\
    .avg("views")\
    .sum("likes")\
    .execute()

# Result: [
#   {"group": "tech", "count": 150, "avg_views": 1200},
#   {"group": "science", "count": 80, "avg_views": 900}
# ]

# Overall statistics
stats = Article.objects.aggregate()\
    .count()\
    .avg("views")\
    .max("views")\
    .execute()

# Filtered aggregation
stats = Article.objects.aggregate()\
    .filter(published=True)\
    .group_by("author")\
    .count()\
    .execute()
```

### Advanced Features

```python
# Generative search (RAG)
results = Article.objects.near_text("AI ethics").generative(
    single_prompt="Summarize: {content}"
).all()

# Reranking
results = Article.objects.search("ML").rerank(
    property="content",
    query="deep learning"
).all()

# Cross-collection search
from db.search import get_search_interface

search = get_search_interface()
results = search.across(["Articles", "Documents"])\
    .search("python")\
    .all()

# Dynamic search type selection
from db import SearchType

def search_with_mode(query: str, mode: str):
    """Select search type based on mode."""
    search_type_map = {
        'exact': SearchType.BM25,
        'semantic': SearchType.NEAR_TEXT,
        'balanced': SearchType.HYBRID,
        'fuzzy': SearchType.FUZZY
    }
    search_type = search_type_map.get(mode, SearchType.HYBRID)
    
    return Article.objects.search_by_type(search_type, query=query).all()

# Use
results = search_with_mode("python programming", mode="balanced")
```

---

## Collection Management

```python
from db.managers import CollectionManager
from weaviate.classes.config import DataType

manager = CollectionManager(client)

# Create collection
Article.create_collection()

# Check if exists
exists = Article.collection_exists()

# List all collections
collections = manager.list_all_collections()
print(f"Collections: {collections}")

# Add property dynamically
manager.add_property(
    Article,
    "featured",
    DataType.BOOL,
    description="Is featured"
)

# Get collection stats
stats = manager.get_collection_stats(Article)
print(f"Objects: {stats['object_count']}")
print(f"Properties: {stats['property_count']}")

# Batch create collections
results = manager.batch_create_collections([Article, Product, User])

# Delete collection
Article.delete_collection()

# Clear cache
manager.clear_cache()
```

---

## Exception Handling

```python
from db import (
    DoesNotExist,
    MultipleObjectsReturned,
    FieldValidationError,
    CollectionNotFound,
    MissingCredentials,
    ConnectionFailed
)

# Query exceptions
try:
    article = Article.objects.get(title="Nonexistent")
except DoesNotExist as e:
    print(f"Not found: {e.model_name} with {e.filters}")

# Validation exceptions
try:
    article = Article(title="X")  # Too short
    article.save()
except FieldValidationError as e:
    print(f"{e.field_name}: {e.reason}")

# Configuration exceptions
try:
    provider = ProviderFactory.create("invalid")
except InvalidProvider as e:
    print(f"Available: {e.available}")

# Connection exceptions
try:
    client = WeaviateClient(
        connection=ConnectionConfig(host="invalid", port=9999)
    )
except ConnectionFailed as e:
    print(f"{e.host}:{e.port} - {e.reason}")
```

---

## Extensibility

### Custom Filter Operator

```python
from db.search import FilterOperatorRegistry
from weaviate.classes.query import Filter

def between(field, value):
    min_val, max_val = value
    return (Filter.by_property(field).greater_or_equal(min_val) &
            Filter.by_property(field).less_or_equal(max_val))

FilterOperatorRegistry.register("between", between)

# Use
Article.objects.filter(price__between=(10, 100)).all()
```

### Custom Validator

```python
from db.models.validators import FieldValidator

class ISBNValidator(FieldValidator):
    def validate(self, value):
        return value and len(str(value)) in (10, 13)
    
    def get_error_message(self, value):
        return "Invalid ISBN format"

# Use in model
class Book(Model):
    isbn = TextField(validators=[ISBNValidator()])
```

### Search Plugin

```python
from db.search.plugins import SearchPlugin, get_plugin_manager

class TimingPlugin(SearchPlugin):
    def on_before_search(self, state):
        self.start = time.time()
        return None
    
    def on_after_search(self, state, results, duration):
        print(f"Search took {duration:.2f}s")
        return None
    
    def on_error(self, state, error):
        print(f"Error: {error}")

get_plugin_manager().register(TimingPlugin())
```

---

## Performance

### Query Caching

```python
from db.search.performance import get_cache

cache = get_cache(max_size=1000, ttl=300)

# Queries are automatically cached
results = Article.objects.search("AI").all()  # Cached
results = Article.objects.search("AI").all()  # From cache

# Cache stats
print(cache.stats())
# {'hits': 50, 'misses': 10, 'hit_rate': '83.33%'}
```

### Batch Configuration

```python
# Fixed batch size
result = Article.objects.bulk_create(articles, batch_size=500)

# Dynamic batching (auto-optimized)
result = Article.objects.bulk_import(
    data_list,
    use_dynamic=True  # Weaviate auto-tunes batch size
)
```

---

## Testing

### Run Tests

```bash
cd packages
source .venv/bin/activate

# All tests
python -m pytest tests/ -v

# By module
python -m pytest tests/search/ -v      # 186 tests
python -m pytest tests/core/ -v        # 48 tests
python -m pytest tests/managers/ -v    # 23 tests

# Quick run
python -m pytest tests/ -q
```

### Expected Results

```
Search:     186 passed ✅
Core:        48 passed ✅
Managers:    23 passed ✅
Total:      257 passed ✅
Time:       ~1.6 seconds
```

---

## API Reference

### WeaviateClient

```python
client = WeaviateClient(connection, provider, timeouts)
client.is_ready() -> bool
client.ping() -> bool
client.close()
```

### ConnectionConfig

```python
config = ConnectionConfig(
    host="127.0.0.1",
    port=8099,
    api_key=None,
    pool_connections=10,
    pool_maxsize=10
)
config = ConnectionConfig.from_env()
```

### Model

```python
Model.create_collection() -> bool
Model.delete_collection() -> bool
Model.collection_exists() -> bool
Model.get_collection_info() -> Dict
Model.objects -> ObjectManager
```

### ObjectManager

**CRUD:**
```python
.create(**kwargs) -> T
.save(instance) -> T
.get(**kwargs) -> T
.get_by_id(uuid) -> T
.update(instance, **kwargs) -> T
.delete(instance) -> bool
```

**Batch:**
```python
.bulk_create(instances, batch_size, on_error) -> BatchResult
.bulk_create_from_dicts(data_list) -> BatchResult
.bulk_import(data_list, batch_size, use_dynamic, on_progress, on_error) -> BatchResult
.bulk_update(updates, batch_size) -> BatchResult
.bulk_delete(ids, batch_size) -> BatchResult
.delete_where(**filters) -> int
```

**Query:**
```python
.all() -> QueryBuilder
.filter(**kwargs) -> QueryBuilder
.exclude(**kwargs) -> QueryBuilder
```

**Search:**
```python
.search(query) -> QueryBuilder
.bm25(query) -> QueryBuilder
.near_text(text) -> QueryBuilder
.hybrid(query, alpha) -> QueryBuilder
.fuzzy(query) -> QueryBuilder
```

**Aggregation:**
```python
.aggregate() -> AggregationBuilder
```

### QueryBuilder

```python
.filter(**kwargs) -> QueryBuilder
.exclude(**kwargs) -> QueryBuilder
.search(query) -> QueryBuilder
.bm25(query) -> QueryBuilder
.near_text(text) -> QueryBuilder
.hybrid(query, alpha) -> QueryBuilder
.limit(n) -> QueryBuilder
.offset(n) -> QueryBuilder
.only(*fields) -> QueryBuilder
.all() -> List
.first() -> Optional
.count() -> int
.exists() -> bool
```

### CollectionManager

```python
manager = CollectionManager(client)
manager.create_collection(model_class, if_not_exists) -> bool
manager.delete_collection(model_class, if_exists) -> bool
manager.collection_exists(model_class) -> bool
manager.get_collection_info(model_class, use_cache) -> Dict
manager.get_collection_stats(model_class) -> Dict
manager.batch_create_collections(model_classes) -> Dict
manager.add_property(model_class, name, data_type, **options) -> bool
manager.list_all_collections() -> List[str]
manager.clear_cache()
```

### BatchResult

```python
result.total -> int
result.successful -> int
result.failed -> int
result.errors -> List[Dict]
result.success_rate -> float
result.is_complete_success -> bool
result.has_errors -> bool
```

---

## Examples

### E-commerce Product Search

```python
class Product(Model):
    name = TextField(required=True, max_length=100)
    price = IntField(required=True, min_value=0)
    in_stock = BooleanField()

# Search products
results = Product.objects.filter(
    in_stock=True,
    price__gte=100,
    price__lte=500
).search("wireless headphones").limit(20).all()
```

### Blog with Statistics

```python
# Get article stats by category
stats = Article.objects.aggregate()\
    .filter(published=True)\
    .group_by("category")\
    .count()\
    .avg("views")\
    .sum("likes")\
    .execute()

for stat in stats:
    print(f"{stat['group']}: {stat['count']} articles, {stat['avg_views']} avg views")
```

### Large Data Import

```python
import csv

# Read from CSV
data_list = []
with open('articles.csv') as f:
    reader = csv.DictReader(f)
    data_list = list(reader)

# Import with progress
result = Article.objects.bulk_import(
    data_list,
    batch_size=500,
    use_dynamic=True,
    on_progress=lambda c, t: print(f"\r{c}/{t}", end="")
)

print(f"\nImported: {result.successful}/{result.total}")
if result.has_errors:
    print(f"Failed: {result.failed}")
```

---

## Best Practices

1. **Use environment variables** for configuration
2. **Enable field validation** for data integrity
3. **Use batch operations** for multiple objects
4. **Set appropriate limits** in queries
5. **Use get_by_id** when you have the UUID
6. **Handle BatchResult errors** in production
7. **Use progress callbacks** for large imports
8. **Monitor with plugins** for observability

---

## Troubleshooting

### Connection Issues

```python
client = WeaviateClient()

if not client.is_ready():
    print("Client not connected")

if not client.ping():
    print("Server not responding")
```

### Validation Errors

```python
try:
    article = Article(title="X")  # Too short
    article.save()
except FieldValidationError as e:
    print(f"{e.field_name}: {e.reason}")
```

### Batch Failures

```python
result = Article.objects.bulk_create(articles)

if result.has_errors:
    print(f"Failed: {result.failed}/{result.total}")
    for error in result.errors:
        print(f"  {error['uuid']}: {error['message']}")
```

---

## Documentation

- **README.md** - This file (usage guide)
- **tests/** - Test examples and patterns
- **db/example/search_examples.py** - Usage examples

---

**Version**: 2.0.0  
**Tests**: 257/257 passing ✅  
**Status**: Production Ready  

Built for high-performance vector search applications.
