# Vector Database Interface

Unified interface for vector databases with multiple embedding providers (OpenAI, AWS Bedrock).

This package is built on top of [LangChain Vector Stores](https://docs.langchain.com/oss/python/integrations/vectorstores), providing a unified abstraction layer that supports any LangChain-compatible vector store. Currently implemented with Weaviate, but can easily be extended to support other vector stores such as Pinecone, Qdrant, Milvus, FAISS, and more.

## Quick Start

```python
from packages.db import initialize_database
from packages.shared.models import McpTool

# Initialize
db = initialize_database()

# Get repository for model (recommended)
mcp_tools = db.for_model(McpTool)

# ORM-style operations
tool = McpTool(
    tool_name="weather",
    server_path="/weather",
    server_name="Weather API"
)
tool_id = mcp_tools.save(tool)
tool = mcp_tools.get(tool_id)
results = mcp_tools.search("weather forecast", k=10)
mcp_tools.update(tool)
mcp_tools.delete(tool_id)

# Bulk operations
result = mcp_tools.bulk_save([tool1, tool2, tool3])
deleted = mcp_tools.delete_by_filter({'server_path': '/weather'})

# Close connection
db.close()
```

## Configuration

**Required environment variables:**
```bash
VECTOR_STORE_TYPE=weaviate     # weaviate
EMBEDDING_PROVIDER=aws_bedrock # openai | aws_bedrock
```

**Database-specific:**
```bash
# Weaviate (required)
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8099            # Must be 1-65535
```

**Embedding-specific:**
```bash
# AWS Bedrock (required)
AWS_REGION=us-east-1          # Must be valid region
EMBEDDING_MODEL=amazon.titan-embed-text-v2:0  # Optional

# OpenAI (required)
OPENAI_API_KEY=sk-...         # Must start with 'sk-'
OPENAI_MODEL=text-embedding-3-small  # Default: text-embedding-3-small
```

**Enums:**
```python
from packages.db.enum.enums import VectorStoreType, EmbeddingProvider

VectorStoreType.WEAVIATE      # "weaviate"

EmbeddingProvider.OPENAI      # "openai"
EmbeddingProvider.AWS_BEDROCK # "aws_bedrock"
```

## API Layers

### Repository API (Recommended)

Type-safe ORM-style API for daily development:

```python
mcp_tools = db.for_model(McpTool)

tool_id = mcp_tools.save(tool)
tool = mcp_tools.get(tool_id)
results = mcp_tools.search("query", k=10)
mcp_tools.update(tool)
mcp_tools.delete(tool_id)
```

### Filtering (Smart Conversion)

**Simple dict (auto-converted):**

```python
# Works with Weaviate
filters = {"is_enabled": True}
tools = mcp_tools.search("weather", filters=filters)

# With operators
filters = {"points": {"$gt": 500}}
tools = mcp_tools.filter(filters, limit=50)
```

**Native format (for power users):**

```python
# Weaviate
from weaviate.classes.query import Filter

filters = Filter.by_property("is_enabled").equal(True) &
          Filter.by_property("points").greater_than(500)

tools = mcp_tools.search("weather", filters=filters)
```

**Conversion location:** VectorStoreAdapter layer (transparent to business code)

### Adapter API (Advanced)

Direct access to adapter for fine-grained control:

```python
from langchain_core.documents import Document

adapter = db.adapter

doc = Document(page_content="content", metadata={'key': 'value'})

ids = adapter.add_documents(
    collection_name='MCP_GATEWAY',
    documents=[doc]
)

# With filters
results = adapter.similarity_search(
    collection_name='MCP_GATEWAY',
    query='weather',
    k=10,
    filters=filters  # Use native format
)

adapter.delete_documents(collection_name='MCP_GATEWAY', ids=ids)
```

**Use cases:**

- Direct Document operations
- Database-specific features
- Performance optimization

## Custom Model

Implement `to_document()` and `from_document()`:

```python
from langchain_core.documents import Document


class MyModel:
    COLLECTION_NAME = "MY_COLLECTION"

    def __init__(self, name: str):
        self.id = str(uuid.uuid4())
        self.name = name

    def to_document(self) -> Document:
        return Document(
            page_content=self.name,
            metadata={'name': self.name},
            id=self.id
        )

    @classmethod
    def from_document(cls, doc: Document):
        return cls(name=doc.metadata.get('name', ''))


# Use it
my_models = db.for_model(MyModel)
id = my_models.save(MyModel("test"))
```

## Repository Methods

```python
repo = db.for_model(YourModel)

# CRUD
repo.save(instance)  # -> str
repo.get(id)  # -> Optional[Model]
repo.update(instance)  # -> bool
repo.delete(id)  # -> bool

# Search
repo.search(query, k=10, filters={})  # -> List[Model]
repo.filter(filters, limit=100)  # -> List[Model]

# Bulk
repo.bulk_save(instances)  # -> BatchResult
repo.delete_by_filter(filters)  # -> int
```

## Architecture

Three-layer design maximizing LangChain VectorStore utilization:

```
Repository (Business API)
    ↓
VectorStoreAdapter (Proxy + Extension)
    ↓
LangChain VectorStore (WeaviateVectorStore)
```

**DatabaseClient**: Configuration, lifecycle, repository factory  
**Repository**: Type-safe Model API, Model ↔ Document conversion  
**VectorStoreAdapter**: Proxy VectorStore methods + extend missing features  
**VectorStore**: Native database operations (from LangChain)

### Directory Structure

```
packages/
├── shared/
│   ├── models.py          # Data models (McpTool, etc.)
│   └── batch_result.py    # BatchResult
└── db/
    ├── client.py          # DatabaseClient (Facade)
    ├── repository.py      # Generic Repository[T]
    ├── adapters/
    │   ├── adapter.py     # VectorStoreAdapter (Base)
    │   ├── factory.py     # Adapter factory
    │   └── create/        # Creator functions
    ├── backends/
    │   └── weaviate_store.py  # WeaviateStore
    ├── config/            # Configuration classes
    └── enum/              # Enums and exceptions
```

## Examples

### Repository API

```python
from packages.db import initialize_database
from packages.shared.models import McpTool

db = initialize_database()

try:
    tools_repo = db.for_model(McpTool)

    # Save
    tool = McpTool(
        tool_name="get_weather",
        server_path="/weather",
        server_name="Weather Service"
    )
    tool_id = tools_repo.save(tool)

    # Search with filters
    from weaviate.classes.query import Filter

    filters = Filter.by_property("is_enabled").equal(True)

    results = tools_repo.search("weather forecast", filters=filters, k=5)

    # Filter only
    enabled = tools_repo.filter(filters, limit=10)

    # Bulk save
    result = tools_repo.bulk_save([tool1, tool2, tool3])

finally:
    db.close()
```

### Adapter API

```python
from langchain_core.documents import Document

db = initialize_database()

try:
    adapter = db.adapter

    # Add documents
    docs = [Document(page_content="content", metadata={"key": "value"})]
    ids = adapter.add_documents(documents=docs, collection_name="CUSTOM")

    # Search with filters
    docs = adapter.similarity_search(
        query="query",
        k=10,
        filters=filters,
        collection_name="CUSTOM"
    )

    # Extended features
    doc = adapter.get_by_id("doc-id-123", collection_name="CUSTOM")
    collections = adapter.list_collections()

    # Get underlying VectorStore
    store = adapter.get_vector_store("CUSTOM")

finally:
    db.close()
```

## API Reference

### DatabaseClient

| Method                  | Description                          |
|-------------------------|--------------------------------------|
| `initialize(config?)`   | Initialize database                  |
| `close()`               | Close connection                     |
| `is_initialized()`      | Check if initialized                 |
| `for_model(ModelClass)` | Get repository for model             |
| `adapter`               | Access underlying adapter (property) |
| `get_info()`            | Get client info                      |

### Repository[T]

| Method                       | Description                      |
|------------------------------|----------------------------------|
| `save(instance)`             | Save instance → str              |
| `get(id)`                    | Get by ID → Optional[Model]      |
| `update(instance)`           | Update instance → bool           |
| `delete(id)`                 | Delete by ID → bool              |
| `search(query, k, filters?)` | Semantic search → List[Model]    |
| `filter(filters, limit)`     | Filter by metadata → List[Model] |
| `bulk_save(instances)`       | Bulk save → BatchResult          |
| `delete_by_filter(filters)`  | Delete by filter → int           |

### VectorStoreAdapter

#### Standard Operations (Proxied to VectorStore)

| Method                                                    | Description                    |
|-----------------------------------------------------------|--------------------------------|
| `similarity_search(query, k, filters?, collection_name?)` | Vector search → List[Document] |
| `add_documents(documents, collection_name?)`              | Add documents → List[str]      |
| `delete(ids, collection_name?)`                           | Delete documents → bool        |

#### Extended Operations (Database-specific)

| Method                                                 | Description                           |
|--------------------------------------------------------|---------------------------------------|
| `get_by_id(doc_id, collection_name?)`                  | Get by ID → Optional[Document]        |
| `filter_by_metadata(filters, limit, collection_name?)` | Pure metadata filter → List[Document] |
| `list_collections()`                                   | List all collections → List[str]      |
| `collection_exists(name)`                              | Check existence → bool                |
| `get_vector_store(collection_name?)`                   | Get LangChain VectorStore             |
| `describe()`                                           | Get adapter info → Dict               |
| `close()`                                              | Close connection                      |

## Extending the System

### Supported Vector Stores

This package leverages [LangChain's vector store integrations](https://docs.langchain.com/oss/python/integrations/vectorstores), which means you can easily extend it to support any of the following vector stores:

**Popular Options:**
- **Weaviate** (currently implemented)
- **Pinecone** - Managed vector database
- **Qdrant** - Open-source vector search engine
- **Milvus** - Scalable vector database
- **FAISS** - Facebook AI Similarity Search
- **PGVector** - PostgreSQL extension
- **MongoDB Atlas** - Vector search in MongoDB
- **Elasticsearch** - Full-text and vector search
- **Astra DB** - Cassandra-based vector store
- **Azure Cosmos DB** - NoSQL and Mongo vCore
- **OpenSearch** - Amazon's search service

See the [complete list of supported vector stores](https://docs.langchain.com/oss/python/integrations/vectorstores) in the LangChain documentation.

### Register New Vector Store

3 steps to add a new vector store (e.g., Pinecone):

**1. Add enum:**

```python
# packages/db/enum/enums.py
class VectorStoreType(str, Enum):
    WEAVIATE = "weaviate"
    PINECONE = "pinecone"  # ← Add new
```

**2. Create adapter:**

```python
# packages/db/backends/pinecone_store.py
from langchain_core.vectorstores import VectorStore
from ..adapters.adapter import VectorStoreAdapter


class PineconeStore(VectorStoreAdapter):
    def _create_vector_store(self, collection_name: str) -> VectorStore:
        from langchain_pinecone import PineconeVectorStore
        return PineconeVectorStore(
            index_name=collection_name,
            embedding=self.embedding
        )

    def close(self):
        self._stores.clear()

    # Implement extended features
    def get_by_id(self, doc_id: str, ...) -> Optional[Document]:
        # Use Pinecone API
        ...

    def filter_by_metadata(self, filters: Any, ...) -> List[Document]:
        # Use Pinecone metadata filtering
        ...
```

**3. Register creator:**

```python
# packages/db/adapters/create/vector_store.py
@register_vector_store_creator(VectorStoreType.PINECONE.value)
def create_pinecone_adapter(config: BackendConfig, embedding) -> VectorStoreAdapter:
    return PineconeStore(
        embedding=embedding,
        config={
            "api_key": config.vector_store_config.api_key,
            "index_name": config.vector_store_config.index_name
        }
    )
```

Done! Use with `VECTOR_STORE_TYPE=pinecone`

### Register New Embedding Provider

Similar 3-step process:

**1. Add enum:**

```python
# packages/db/enum/enums.py
class EmbeddingProvider(str, Enum):
    OPENAI = "openai"
    AWS_BEDROCK = "aws_bedrock"
    COHERE = "cohere"  # ← Add new
```

**2. Create config:**

```python
# packages/db/config/config.py
@register_embedding_model_config(EmbeddingProvider.COHERE.value)
class CohereEmbeddingConfig(EmbeddingModelConfig):
    api_key: str
    model: str = "embed-english-v3.0"

    @classmethod
    def from_env(cls):
        return cls(
            provider=EmbeddingProvider.COHERE.value,
            api_key=os.getenv("COHERE_API_KEY"),
            model=os.getenv("COHERE_MODEL", "embed-english-v3.0")
        )
```

**3. Register creator:**

```python
# packages/db/adapters/create/embedding.py
@register_embedding_creator(EmbeddingProvider.COHERE.value)
def create_cohere_embedding(config: BackendConfig):
    from langchain_cohere import CohereEmbeddings
    return CohereEmbeddings(
        cohere_api_key=config.embedding_model_config.api_key,
        model=config.embedding_model_config.model
    )
```
