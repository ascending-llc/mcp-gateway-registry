# Weaviate Django-ORM Framework

A lightweight Django-inspired ORM framework for Weaviate with essential search capabilities.

## Features

- 🎯 Django-like API with `Model.objects` pattern
- 🔍 Core search (BM25, semantic, hybrid)
- 📊 Aggregation (group by, count, avg, sum, min, max)
- ✅ Field validation and type conversion
- 🔧 Clean configuration
- 📦 Batch operations with error reporting
- ⚡ High performance (optimized queries, caching)

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

# AWS Bedrock
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-key  # Optional for IAM Role
AWS_SECRET_ACCESS_KEY=your-secret  # Optional for IAM Role

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
│   ├── providers.py        # EmbeddingsProvider
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
    ├── filters.py          # Q objects
    ├── query_builder.py    # QueryBuilder, QueryExecutor
    ├── strategies.py       # Search strategies
    ├── aggregation.py      # Aggregation support
    └── advanced.py         # Advanced features
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
```

---

## Search Operations

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

# Delete collection
Article.delete_collection()
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

# Connection exceptions
try:
    client = WeaviateClient(
        connection=ConnectionConfig(host="invalid", port=9999)
    )
except ConnectionFailed as e:
    print(f"{e.host}:{e.port} - {e.reason}")
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

# Search tests
python -m pytest tests/search/ -v

# Core tests
python -m pytest tests/core/ -v

# Managers tests
python -m pytest tests/managers/ -v
```

### Expected Results

```
Search:     29 passed ✅
Core:       48 passed ✅
Managers:   23 passed ✅
Total:      100+ passed ✅
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

## Best Practices

1. **Use environment variables** for configuration
2. **Enable field validation** for data integrity
3. **Use batch operations** for multiple objects
4. **Set appropriate limits** in queries
5. **Use get_by_id** when you have the UUID
6. **Handle BatchResult errors** in production
7. **Use progress callbacks** for large imports

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
