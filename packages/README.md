# MCP Gateway Registry - Packages

Unified vector database interface with three-layer architecture.

## Architecture

```
Repository (Type-safe Model API)
    ↓
VectorStoreAdapter (Proxy + Extension)
    ↓
LangChain VectorStore (Native DB)
```

**Key principles:**
- Maximize LangChain utilization
- Native filter support (no conversion)
- Direct method proxying
- Minimal abstraction

## Quick Start

```python
from db import initialize_database
from shared.models import McpTool

# Initialize
db = initialize_database()
tools_repo = db.for_model(McpTool)

# Search with native filters
if db.get_info()['adapter_type'] == 'WeaviateStore':
    from weaviate.classes.query import Filter
    filters = Filter.by_property("is_enabled").equal(True)
else:  # Chroma
    filters = {"is_enabled": True}

results = tools_repo.search("weather api", filters=filters, k=10)

# Close
db.close()
```

## Structure

```
packages/
├── db/                    # Vector database layer
│   ├── client.py          # DatabaseClient (facade)
│   ├── repository.py      # Generic Repository[T]
│   ├── adapters/
│   │   ├── adapter.py     # VectorStoreAdapter (base)
│   │   ├── factory.py     # Factory + registry
│   │   └── create/        # Creator functions
│   ├── backends/
│   │   ├── weaviate_store.py  # Weaviate implementation
│   │   └── chroma_store.py    # Chroma implementation
│   ├── config/            # Configuration classes
│   └── enum/              # Enums and exceptions
├── shared/
│   ├── models.py          # McpTool model
│   └── batch_result.py    # BatchResult
└── registry/
    └── search/
        └── external_service.py  # Search service
```

## Key Features

### 1. Repository API (Recommended)

```python
repo = db.for_model(McpTool)

# CRUD
tool_id = repo.save(tool)
tool = repo.get(tool_id)
repo.update(tool)
repo.delete(tool_id)

# Search
results = repo.search("query", filters=filters, k=10)
results = repo.filter(filters, limit=50)

# Bulk
result = repo.bulk_save([tool1, tool2])
count = repo.delete_by_filter(filters)
```

### 2. Smart Filter Conversion

**Dict format (auto-converted):**
```python
# Simple - works with any database
filters = {"is_enabled": True, "points": {"$gt": 500}}
results = repo.search("query", filters=filters)
```

**Native format (for complex queries):**
```python
# Weaviate
from weaviate.classes.query import Filter
filters = Filter.by_property("is_enabled").equal(True)

# Chroma (dict is native)
filters = {"$and": [{"is_enabled": True}, {"points": {"$gt": 500}}]}
```

**Conversion happens in VectorStoreAdapter** - business code stays clean.

### 3. Extended Features

```python
adapter = db.adapter

# Get by ID
doc = adapter.get_by_id("doc-id-123")

# Filter by metadata (no vector search)
docs = adapter.filter_by_metadata(filters, limit=50)

# List collections
collections = adapter.list_collections()

# Get VectorStore
store = adapter.get_vector_store("MCP_GATEWAY")
```

## Configuration

```bash
# Required
VECTOR_STORE_TYPE=weaviate  # or chroma
EMBEDDING_PROVIDER=aws_bedrock  # or openai

# Weaviate
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8099

# AWS Bedrock
AWS_REGION=us-east-1
EMBEDDING_MODEL=amazon.titan-embed-text-v2:0

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=text-embedding-3-small
```

## Documentation

- [db/README.md](./db/README.md) - Complete API reference
- [db/ARCHITECTURE.md](./db/ARCHITECTURE.md) - Design details (if exists)
- [db/FILTERS.md](./db/FILTERS.md) - Filter guide (if exists)

## Testing

```bash
uv run pytest tests/ -v
```

## Extending

See [db/README.md#extending-the-system](./db/README.md#extending-the-system) for:
- Adding new vector stores
- Adding new embedding providers
