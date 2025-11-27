# Weaviate Django-like ORM

A Django-inspired ORM framework for Weaviate with AWS Bedrock support and semantic search capabilities.

1. **Model-based** (recommended for structured data): `Article.objects.smart_search(...)`
2. **Direct search** (suitable for dynamic collections): `DirectSearchManager.smart_search("CollectionName", ...)`

👉 For detailed usage guide, see [DIRECT_SEARCH_USAGE.md](./DIRECT_SEARCH_USAGE.md)

## Directory Structure

```
packages/db/
├── core/          # Client, registry, exceptions
├── models/        # Model base class and field types
├── managers/      # CRUD and query operations
│   └── data.py    # DirectDataManager - Direct data management (no model required)
└── search/        # Semantic and hybrid search
    ├── base.py    # BaseSearchOperations - Base search operations (shared)
    ├── manager.py # SearchManager - Model-based search
    └── direct.py  # DirectSearchManager - Direct search (no model required)
```

---

## 🚀 Quick Examples

### Approach 1: Model-based (Recommended)

```python
from packages.db import Model, TextField

class Article(Model):
    title = TextField()
    content = TextField()

# Search
results = Article.objects.smart_search(query="AI")
```

### Approach 2: Direct Search (No Model Required) ✨ NEW

```python
from packages.db import DirectSearchManager, DirectDataManager, get_weaviate_client

client = get_weaviate_client()
search_mgr = DirectSearchManager(client)
data_mgr = DirectDataManager(client)

# Search any collection directly, no model definition needed
results = search_mgr.smart_search("Article", query="AI", limit=10)

# Direct data operations
data_mgr.insert("Article", {"title": "New Article", "content": "..."})
```

---

## Quick Start

### 1. Create WeaviateClient

```python
from packages.db import WeaviateClient

# From environment variables (recommended)
client = WeaviateClient()

# With custom parameters
client = WeaviateClient(
    host="localhost",
    port=8099,
    api_key="my-key",
    embeddings_provider="bedrock",
    aws_access_key="your-key",
    aws_secret_key="your-secret",
    aws_region="us-east-1"
)
```

**Environment Variables:**
```bash
WEAVIATE_HOST=127.0.0.1
WEAVIATE_PORT=8099
WEAVIATE_API_KEY=your-api-key
EMBEDDINGS_PROVIDER=bedrock
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
```

### 2. Define Model

```python
from packages.db import Model, TextField, BooleanField

class Article(Model):
    title = TextField(description="Article title")
    content = TextField(description="Article content")
    published = BooleanField(description="Published status")
    
    class Meta:
        collection_name = "Articles"
        vectorizer = "text2vec-aws"  # AWS Bedrock
```

### 3. Create Collection

```python
if not Article.collection_exists():
    Article.create_collection()
```

### 4. CRUD Operations

```python
# Create
article = Article.objects.create(
    title="Hello World",
    content="Article content",
    published=True
)

# Read
all_articles = Article.objects.all().all()
published_articles = Article.objects.filter(published=True).all()

# Update
Article.objects.update(article, title="New Title")

# Delete
article.delete()
```

### 5. Search

#### Approach A: Model-based Search

```python
# Smart search (hybrid: 70% semantic + 30% keyword)
results = Article.objects.smart_search(
    query="python programming",
    field_filters={"published": True},
    limit=10
)

# Semantic search
results = Article.objects.near_text_search(
    text="machine learning",
    limit=5
)

# NEW: Universal search with SearchType
from packages.db import SearchType

# Semantic search
results = Article.objects.search_by_type(
    SearchType.NEAR_TEXT,
    text="machine learning",
    limit=10
)

# Hybrid search
results = Article.objects.search_by_type(
    SearchType.HYBRID,
    text="deep learning",
    alpha=0.7,
    limit=10
)

# Using string instead of enum
results = Article.objects.search_by_type(
    "near_text",  # String works too
    text="AI research",
    limit=10
)
```

#### Approach B: Direct Search (No Model Required)

```python
from packages.db import DirectSearchManager, get_weaviate_client

search_mgr = DirectSearchManager(get_weaviate_client())

# Smart search - directly by collection name
results = search_mgr.smart_search(
    "Articles",  # collection name
    query="python programming",
    field_filters={"published": True},
    limit=10
)

# Semantic search
results = search_mgr.near_text(
    "Articles",
    text="machine learning",
    limit=5
)

# BM25 keyword search
results = search_mgr.bm25(
    "Articles",
    text="python tutorial",
    limit=10
)

# Hybrid search
results = search_mgr.hybrid(
    "Articles",
    text="deep learning",
    alpha=0.7,  # 0.0 = BM25, 1.0 = semantic
    limit=10
)
```

📖 **More search examples and advanced usage**: [DIRECT_SEARCH_USAGE.md](./DIRECT_SEARCH_USAGE.md)

---

## 🚀 Advanced Search Features

### Universal Search with SearchType

The framework now provides a universal search API that accepts a `SearchType` parameter, allowing you to dynamically select search strategies at runtime.

#### Available Search Types

```python
from packages.db import SearchType

# Available search types:
SearchType.NEAR_TEXT      # Semantic search using text
SearchType.NEAR_VECTOR    # Semantic search using vector
SearchType.NEAR_IMAGE     # Image similarity search
SearchType.BM25           # Keyword search (BM25F)
SearchType.HYBRID         # Hybrid search (BM25 + semantic)
SearchType.FETCH_OBJECTS  # Simple object fetch with filters
SearchType.FUZZY          # Fuzzy search (typo-tolerant)
```

#### Understanding Search Types: BM25 vs Hybrid vs Semantic

**1. BM25 (Keyword Search)**
- **How it works**: Traditional keyword matching algorithm based on term frequency (TF) and inverse document frequency (IDF)
- **Best for**: Exact term matching, technical keywords, product codes, IDs
- **Pros**: Fast, deterministic, works well with precise terminology
- **Cons**: Cannot understand meaning, synonyms, or context
- **Example use case**: Searching for "Python 3.11.5" or specific product SKU

```python
# BM25 finds documents with exact keyword matches
results = Article.objects.search_by_type(
    SearchType.BM25,
    text="Python programming tutorial",  # Matches "Python", "programming", "tutorial"
    limit=10
)
```

**2. NEAR_TEXT (Semantic Search)**
- **How it works**: Uses AI embeddings to understand meaning and context
- **Best for**: Conceptual queries, natural language, finding similar meanings
- **Pros**: Understands context, synonyms, and semantic similarity
- **Cons**: Slower, may miss exact keyword matches, requires vectorization
- **Example use case**: "How to learn coding for beginners" finds articles about programming tutorials

```python
# Semantic search understands meaning
results = Article.objects.search_by_type(
    SearchType.NEAR_TEXT,
    text="learning to code",  # Also finds "programming tutorial", "beginner coding"
    limit=10
)
```

**3. HYBRID (Best of Both Worlds)**
- **How it works**: Combines BM25 keyword matching + semantic understanding
- **Best for**: General-purpose search, balanced precision and recall
- **Pros**: Gets both exact matches AND similar meanings
- **Cons**: Slightly slower than BM25, requires tuning alpha parameter
- **Example use case**: Most production search applications

```python
# Hybrid search combines both approaches
results = Article.objects.search_by_type(
    SearchType.HYBRID,
    text="Python machine learning",
    alpha=0.7,  # 0.0 = pure BM25, 1.0 = pure semantic, 0.7 = balanced toward semantic
    limit=10
)
```

**Alpha Parameter in Hybrid Search:**
- `alpha=0.0`: 100% BM25 (keyword matching only)
- `alpha=0.3`: 30% semantic, 70% keyword (good for technical content)
- `alpha=0.5`: Balanced (50-50 split)
- `alpha=0.7`: 70% semantic, 30% keyword (good for natural language)
- `alpha=1.0`: 100% semantic (meaning-based only)

**Comparison Table:**

| Feature | BM25 | NEAR_TEXT | HYBRID |
|---------|------|-----------|--------|
| **Speed** | ⚡ Fastest | 🐢 Slower | ⚡ Fast |
| **Exact matches** | ✅ Excellent | ❌ May miss | ✅ Good |
| **Semantic understanding** | ❌ None | ✅ Excellent | ✅ Good |
| **Synonyms** | ❌ No | ✅ Yes | ✅ Yes |
| **Technical terms** | ✅ Excellent | ⚠️ Variable | ✅ Good |
| **Natural language** | ⚠️ Limited | ✅ Excellent | ✅ Good |
| **Typos** | ❌ Fails | ⚠️ Sometimes | ⚠️ Sometimes |

**When to Use Each:**

| Scenario | Recommended Type | Reason |
|----------|-----------------|--------|
| Product SKU search | BM25 | Need exact matching |
| Academic paper search | NEAR_TEXT | Conceptual understanding |
| E-commerce search | HYBRID (α=0.5) | Balance precision and discovery |
| Technical docs search | HYBRID (α=0.3) | Favor exact terms but allow semantic |
| FAQ/Support search | HYBRID (α=0.7) | Natural language queries |
| Code search | BM25 | Exact function/variable names |
| Blog/article search | NEAR_TEXT or HYBRID (α=0.7) | Content similarity |

**Practical Example:**

```python
query = "machine learning algorithms"

# BM25: Finds documents with those exact words
bm25_results = Article.objects.search_by_type(SearchType.BM25, text=query)
# Found: "Machine Learning Algorithms", "ML Algorithms Guide"

# NEAR_TEXT: Finds conceptually similar content
semantic_results = Article.objects.search_by_type(SearchType.NEAR_TEXT, text=query)
# Found: "Neural Networks Tutorial", "Deep Learning Basics", "AI Model Training"

# HYBRID: Gets both exact matches AND related content
hybrid_results = Article.objects.search_by_type(
    SearchType.HYBRID, 
    text=query, 
    alpha=0.7  # Favor semantic but include keyword matches
)
# Found: "Machine Learning Algorithms" (exact), "Neural Networks" (related), 
#        "AI Model Training" (related), "ML Algorithms Guide" (exact)
```

#### Universal Search API

The `search_by_type()` method is available in both approaches:

**Model-based:**

```python
from packages.db import Model, TextField, SearchType

class Article(Model):
    title = TextField()
    content = TextField()

# Use search_by_type() with any search strategy
results = Article.objects.search_by_type(
    SearchType.HYBRID,  # Dynamically select search type
    text="machine learning",
    alpha=0.7,
    limit=10
)

# Or use string instead of enum
results = Article.objects.search_by_type(
    "near_text",  # String works too
    text="deep learning",
    limit=10
)
```

**Direct search (no model):**

```python
from packages.db import DirectSearchManager, SearchType, get_weaviate_client

search_mgr = DirectSearchManager(get_weaviate_client())

# Use search_by_type() with any search strategy
results = search_mgr.search_by_type(
    "Articles",  # Collection name
    SearchType.HYBRID,
    text="machine learning",
    alpha=0.7,
    limit=10
)

# Or use string instead of enum
results = search_mgr.search_by_type(
    "Articles",
    "near_text",
    text="deep learning",
    limit=10
)
```

#### Dynamic Search Strategy Selection

```python
from packages.db import SearchType

# Select search strategy based on user preference
user_preference = "precise"  # or "fuzzy" or "comprehensive"

if user_preference == "precise":
    search_type = SearchType.BM25
elif user_preference == "fuzzy":
    search_type = SearchType.FUZZY
else:
    search_type = SearchType.HYBRID

# Execute search with selected strategy

# Model-based approach:
results = Article.objects.search_by_type(
    search_type,
    text="python programming",
    limit=10
)

# Direct search approach:
search_mgr = DirectSearchManager(get_weaviate_client())
results = search_mgr.search_by_type(
    "Articles",
    search_type,
    text="python programming",
    limit=10
)
```

### Cross-Collection Search

Search across multiple collections concurrently with automatic result merging and sorting.

#### Grouped Results by Collection

```python
from packages.db import DirectSearchManager, SearchType, get_weaviate_client

search_mgr = DirectSearchManager(get_weaviate_client())

# Search multiple collections, get results grouped by collection
results = search_mgr.search_multiple_collections(
    ["Articles", "Documents", "Notes"],
    SearchType.NEAR_TEXT,
    text="machine learning",
    limit_per_collection=5
)

# Access results by collection
for collection, items in results.items():
    print(f"{collection}: {len(items)} results")
    for item in items:
        print(f"  - {item['title']} (from {item['_collection']})")
```

#### Merged and Sorted Results

```python
# Search multiple collections, get merged results sorted by relevance
results = search_mgr.search_multiple_collections_merged(
    ["Articles", "Documents", "Notes"],
    SearchType.HYBRID,
    text="python programming",
    total_limit=10,  # Top 10 across all collections
    alpha=0.7
)

# Results are automatically sorted by relevance
for result in results:
    print(f"[{result['_collection']}] {result['title']}")
    print(f"  Score: {result.get('_score', 0):.4f}")
```

#### Compare Search Strategies

Both model-based and direct search support easy comparison:

```python
from packages.db import SearchType

query = "data science"
strategies = [
    (SearchType.NEAR_TEXT, "Semantic"),
    (SearchType.BM25, "Keyword"),
    (SearchType.HYBRID, "Hybrid"),
]

# Model-based approach:
for search_type, name in strategies:
    results = Article.objects.search_by_type(
        search_type,
        text=query,
        limit=5
    )
    print(f"{name}: {len(results)} results")

# Direct search approach:
for search_type, name in strategies:
    results = search_mgr.search_by_type(
        "Articles",
        search_type,
        text=query,
        limit=5
    )
    print(f"{name}: {len(results)} results")
```

### Key Benefits

✅ **Single unified API** for all search types  
✅ **Works with both model-based and direct search**  
✅ **Dynamic strategy selection** at runtime  
✅ **Concurrent cross-collection search**  
✅ **Automatic result merging and sorting**  
✅ **Easy comparison** of different search methods  
✅ **Type-safe with models, flexible without models**  

### Complete Example

**Model-based approach:**

```python
from packages.db import Model, TextField, SearchType

class Product(Model):
    name = TextField()
    description = TextField()
    
    class Meta:
        collection_name = "Products"

# 1. Universal search with different strategies
results = Product.objects.search_by_type(
    SearchType.HYBRID,
    text="wireless headphones",
    alpha=0.7,
    limit=10
)

# 2. Compare strategies
for search_type in [SearchType.NEAR_TEXT, SearchType.BM25, SearchType.HYBRID]:
    results = Product.objects.search_by_type(
        search_type,
        text="bluetooth audio",
        limit=5
    )
    print(f"{search_type.value}: {len(results)} results")

# 3. Dynamic selection
user_mode = "semantic"
search_type = SearchType.NEAR_TEXT if user_mode == "semantic" else SearchType.BM25
results = Product.objects.search_by_type(search_type, text="speakers", limit=10)
```

**Direct search approach (no model required):**

```python
from packages.db import DirectSearchManager, SearchType, get_weaviate_client

# Initialize
search_mgr = DirectSearchManager(get_weaviate_client())

# 1. Universal search with different strategies
results = search_mgr.search_by_type(
    "Products",
    SearchType.HYBRID,
    text="wireless headphones",
    alpha=0.7,
    limit=10
)

# 2. Cross-collection search
results = search_mgr.search_multiple_collections(
    ["Products", "Reviews", "Docs"],
    SearchType.NEAR_TEXT,
    text="noise cancellation",
    limit_per_collection=5
)

# 3. Merged cross-collection search
top_results = search_mgr.search_multiple_collections_merged(
    ["Products", "Reviews", "Docs"],
    SearchType.HYBRID,
    text="bluetooth audio",
    total_limit=20,
    alpha=0.6
)
```

For more examples, see `packages/examples/advanced_search_example.py`

---

## WeaviateClient Configuration

### All Parameters

```python
client = WeaviateClient(
    # Connection
    host="127.0.0.1",              # Weaviate host
    port=8099,                      # Weaviate port
    api_key="test-secret-key",     # API key
    
    # Embeddings
    embeddings_provider="bedrock",  # "bedrock" or "openai"
    
    # AWS (for Bedrock)
    aws_access_key="...",
    aws_secret_key="...",
    aws_session_token=None,         # Optional
    aws_region="us-east-1",
    
    # OpenAI (alternative)
    openai_api_key=None,
    
    # Performance
    session_pool_connections=10,
    session_pool_maxsize=10,
    init_timeout=10,
    query_timeout=60,
    insert_timeout=60
)
```

### Parameter Priority

1. **Passed parameters** (highest)
2. **Environment variables**
3. **Default values** (lowest)

---

## Model Definition

### Field Types

```python
from packages.db import (
    TextField,        # Text field
    IntField,        # Integer
    FloatField,      # Float
    BooleanField,    # Boolean
    DateTimeField,   # DateTime
    TextArrayField,  # Text array
    IntArrayField    # Integer array
)
```

### Example Model

```python
class Product(Model):
    name = TextField(description="Product name")
    price = IntField(description="Price in cents")
    tags = TextArrayField(description="Tags")
    in_stock = BooleanField(description="In stock")
    
    class Meta:
        collection_name = "Products"
        vectorizer = "text2vec-aws"
```

---

## Query Operations

### Basic Queries

```python
# Get all
products = Product.objects.all().all()

# Filter
active = Product.objects.filter(in_stock=True).all()

# Exclude
not_keyboards = Product.objects.exclude(name="Keyboard").all()

# Chaining
results = (Product.objects
           .filter(in_stock=True)
           .limit(20)
           .offset(10)
           .all())

# Count
total = Product.objects.filter(in_stock=True).count()

# Get one
product = Product.objects.get(name="Laptop")
```

### Bulk Operations

```python
# Bulk create from instances
products = [
    Product(name="Laptop", price=129999),
    Product(name="Mouse", price=2999),
]
Product.objects.bulk_create(products)

# Bulk create from dicts (simpler)
Product.objects.bulk_create_from_dicts([
    {"name": "Monitor", "price": 49999},
    {"name": "Webcam", "price": 7999},
])
```

---

## Search Operations

### 1. Smart Search (Recommended)

Automatically selects hybrid search (if query) or filtered fetch (no query).

```python
# With query: hybrid search (70% semantic + 30% keyword)
results = Article.objects.smart_search(
    query="machine learning",
    limit=10,
    field_filters={"published": True},
    list_filters={"tags": ["ai", "ml"]},
    alpha=0.7  # Higher = more semantic
)

# Without query: filtered fetch only
results = Article.objects.smart_search(
    limit=20,
    field_filters={"published": True}
)
```

### 2. Semantic Search (Vector)

```python
results = Article.objects.near_text_search(
    text="deep learning neural networks",
    limit=5,
    return_distance=True
)

# Access similarity scores
for article in results:
    print(f"{article.title}: {article._distance}")
```

### 3. Keyword Search (BM25)

```python
results = Article.objects.bm25_search(
    text="python tutorial",
    limit=10
)
```

### 4. Hybrid Search

```python
results = Article.objects.hybrid_search_advanced(
    text="database optimization",
    alpha=0.5,  # 0.0=pure BM25, 1.0=pure vector
    limit=10
)
```

---

## Real-World Examples

### Example 1: Direct Model Usage

```python
from packages.db import Model, TextField, TextArrayField, BooleanField, WeaviateClient

# Define model
class MCPTool(Model):
    tool_name = TextField(description="Tool name")
    server_path = TextField(description="Server path")
    description_main = TextField(description="Description")
    tags = TextArrayField(description="Tags")
    is_enabled = BooleanField(description="Enabled")
    
    class Meta:
        collection_name = "MCP_GATEWAY"
        vectorizer = "text2vec-aws"

# Initialize client (from env vars)
client = WeaviateClient()

# Create collection
if not MCPTool.collection_exists():
    MCPTool.create_collection()

# Add tools
tools = MCPTool.objects.bulk_create_from_dicts([
    {
        "tool_name": "get_weather",
        "server_path": "/weather",
        "description_main": "Get weather data",
        "tags": ["weather", "api"],
        "is_enabled": True
    }
])

# Search with filters
results = MCPTool.objects.smart_search(
    query="weather forecast",
    field_filters={"is_enabled": True},
    list_filters={"tags": ["weather"]},
    limit=10
)

# Remove by service
tools = MCPTool.objects.filter(server_path="/weather").all()
for tool in tools:
    tool.delete()
```

### Example 2: Vector Search Service

```python
from packages.db import WeaviateClient


class VectorSearchService:
    """Service wrapper using packages.db"""

    def __init__(self):
        """Initialize from environment variables (no params needed!)"""
        # WeaviateClient automatically created from env vars
        # Singleton pattern ensures only one instance
        pass

    async def initialize(self):
        """Initialize and ensure collection exists"""
        from registry.search.models import McpTool

        if not McpTool.collection_exists():
            McpTool.create_collection()

    async def add_service(self, service_path, server_info, is_enabled=True):
        """Add or update service tools"""
        from registry.search.models import McpTool

        # Remove old tools
        old_tools = McpTool.objects.filter(server_path=service_path).all()
        for tool in old_tools:
            tool.delete()

        # Add new tools
        tools = McpTool.bulk_create_from_server_info(
            service_path, server_info, is_enabled
        )
        return len(tools)

    async def search(self, query, tags=None, limit=10):
        """Search with vector similarity"""
        from registry.search.models import McpTool

        tools = McpTool.objects.smart_search(
            query=query,
            field_filters={"is_enabled": True},
            list_filters={"tags": tags} if tags else None,
            limit=limit,
            alpha=0.7  # 70% semantic, 30% keyword
        )

        return [
            {
                "tool_name": t.tool_name,
                "server_path": t.server_path,
                "distance": getattr(t, '_distance', None)
            }
            for t in tools
        ]


# Usage
service = VectorSearchService()
await service.initialize()

# Add tools
count = await service.add_service("/weather", server_info, True)

# Search
results = await service.search("weather forecast", tags=["weather"])
```

---

## Import Guide

### Recommended Imports

```python
from packages.db import (
    WeaviateClient,
    Model,
    TextField, BooleanField, TextArrayField,
    DoesNotExist, MultipleObjectsReturned
)
```

### Module-Specific Imports

```python
from packages.db.core import WeaviateClient
from packages.db.models import Model
from packages.db.managers import ObjectManager, QuerySet
from packages.db.search import SearchManager
```

---

## API Reference

### WeaviateClient

```python
WeaviateClient(
    host=None,                    # Weaviate host
    port=None,                    # Weaviate port
    api_key=None,                 # API key
    embeddings_provider=None,     # "bedrock" or "openai"
    aws_access_key=None,         # AWS credentials
    aws_secret_key=None,
    aws_region=None,
    # ... more parameters
)
```

### Model Methods

```python
# Collection management
Model.create_collection() -> bool
Model.delete_collection() -> bool
Model.collection_exists() -> bool
Model.get_collection_info() -> Dict

# Instance methods
instance.save() -> Model
instance.delete() -> bool
```

### ObjectManager (Model.objects)

```python
# CRUD
Model.objects.create(**kwargs) -> Model
Model.objects.bulk_create(instances) -> List[Model]
Model.objects.bulk_create_from_dicts(data_list) -> List[Model]
Model.objects.get(**kwargs) -> Model
Model.objects.update(instance, **kwargs) -> Model
Model.objects.delete(instance) -> bool

# Query
Model.objects.all() -> QuerySet
Model.objects.filter(**kwargs) -> QuerySet
Model.objects.exclude(**kwargs) -> QuerySet

# Search
Model.objects.smart_search(query, limit, field_filters, list_filters, alpha)
Model.objects.near_text_search(text, limit, **kwargs)
Model.objects.bm25_search(text, limit, **kwargs)
Model.objects.hybrid_search_advanced(text, alpha, limit, **kwargs)
```

---

## Best Practices

### 1. Use Environment Variables

```python
# Good: Production config via env vars
client = WeaviateClient()
```

### 2. Use Bulk Operations

```python
# Good: Bulk create
Model.objects.bulk_create(instances)

# Avoid: Individual saves
for instance in instances:
    instance.save()  # Slow
```

### 3. Use Smart Search

```python
# Good: Automatic method selection
results = Model.objects.smart_search(query="...", limit=10)

# Also good: Specific when needed
results = Model.objects.near_text_search(text="...", limit=10)
```

### 4. Always Specify Limits

```python
# Good
results = Model.objects.filter(field=value).limit(100).all()

# Bad: May return too many results
results = Model.objects.filter(field=value).all()
```

---

## Summary

**Simple, powerful, parameter-driven:**

```python
from packages.db import WeaviateClient, Model, TextField

# Create client from env vars
client = WeaviateClient()

# Define model
class MyModel(Model):
    name = TextField()
    class Meta:
        vectorizer = "text2vec-aws"

# Use it
MyModel.create_collection()
results = MyModel.objects.smart_search(query="test", limit=10)
```

**Clean, modular, Django-like ORM for Weaviate! 🚀**
