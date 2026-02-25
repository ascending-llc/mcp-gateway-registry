# Vector Database Package

Unified interface for vector databases with multiple embedding providers (OpenAI, AWS Bedrock).

Built on [LangChain Vector Stores](https://docs.langchain.com/oss/python/integrations/vectorstores), providing a unified abstraction layer that supports any LangChain-compatible vector store. Currently implemented with Weaviate.

## Architecture Overview

Modern four-layer architecture with specialized repositories for domain-specific operations:

```
Service Layer (Business Logic)
    ↓
Specialized Repository (MCPServerRepository)  ← Domain operations, sync logic
    ↓
Generic Repository[T] (ORM)                   ← CRUD, Search, Bulk operations
    ↓
VectorStoreAdapter (Unified Interface)        ← Database abstraction
    ↓
LangChain VectorStore (Weaviate)              ← Native DB operations
```

### Design Principles

1. **Single Responsibility**: Each layer has a clear, focused purpose
2. **DRY**: Vector DB operations centralized in repository layer
3. **Separation of Concerns**: Service delegates to repository for all vector DB ops
4. **Type Safety**: Generic Repository[T] ensures compile-time type checking
5. **Domain Modeling**: Specialized repositories encapsulate business logic

## Quick Start

### Use Case 1: Service Layer Integration (Recommended)

This is how services should interact with vector DB - through specialized repositories:

```python
from registry_pkgs.vector.repositories.mcp_server_repository import get_mcp_server_repo
from registry_pkgs.models import ExtendedMCPServer

# Service layer code
class ServerService:
    def __init__(self):
        self.mcp_server_repo = get_mcp_server_repo()

    async def toggle_server_status(self, server: ExtendedMCPServer, enabled: bool):
        """
        Toggle server status and sync to vector DB.

        enabled=True: Upsert to vector DB (create or update)
        enabled=False: Delete from vector DB
        """
        # Update MongoDB
        server.config['enabled'] = enabled
        await server.save()

        # Sync to vector DB (non-blocking)
        asyncio.create_task(
            self.mcp_server_repo.sync_by_enabled_status(
                server=server,
                enabled=enabled,
                fields_changed={'enabled'}
            )
        )

    async def update_server(self, server: ExtendedMCPServer, fields_changed: set):
        """
        Update server and sync changes to vector DB.
        """
        # Update MongoDB
        await server.save()

        # Smart sync to vector DB (non-blocking)
        enabled = server.config.get('enabled', False)
        asyncio.create_task(
            self.mcp_server_repo.sync_by_enabled_status(
                server=server,
                enabled=enabled,
                fields_changed=fields_changed
            )
        )

    async def delete_server(self, server_id: str, server_name: str):
        """
        Delete server from MongoDB and vector DB.
        """
        # Delete from MongoDB
        await server.delete()

        # Remove from vector DB (non-blocking)
        asyncio.create_task(
            self.mcp_server_repo.delete_by_server_id(server_id, server_name)
        )
```

### Use Case 2: Direct Repository Usage (For Scripts/Tools)

For standalone scripts, CLI tools, or data migration:

```python
from registry_pkgs.vector.repositories.mcp_server_repository import get_mcp_server_repo
from registry_pkgs.models import ExtendedMCPServer

# Get singleton repository
repo = get_mcp_server_repo()

# Sync server to vector DB
await repo.sync_by_enabled_status(
    server=server_instance,
    enabled=True,
    fields_changed={'description', 'tags'}
)

# Query by MongoDB server ID
server = await repo.get_by_server_id("507f1f77bcf86cd799439011")

# Query by path
server = await repo.get_by_path("/github")

# Delete by MongoDB ID
await repo.delete_by_server_id("507f1f77bcf86cd799439011", "GitHub Copilot")
```

## Configuration

### Required Environment Variables

```bash
# Vector Store
VECTOR_STORE_TYPE=weaviate

# Embedding Provider
EMBEDDING_PROVIDER=aws_bedrock  # or openai

# Weaviate Configuration
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8099

# AWS Bedrock (if using aws_bedrock)
AWS_REGION=us-east-1
EMBEDDING_MODEL=amazon.titan-embed-text-v2:0  # Optional

# OpenAI (if using openai)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=text-embedding-3-small  # Optional
```

## MCPServerRepository API

The specialized repository for MCP Server operations.

### Core Methods

#### `sync_by_enabled_status(server, enabled, fields_changed)`

Smart sync based on enabled status - the main method for keeping vector DB in sync.

**Parameters:**
- `server`: ExtendedMCPServer instance
- `enabled`: bool - True to upsert, False to delete
- `fields_changed`: Optional[Set[str]] - Changed field names for optimization

**Returns:** bool - Success status

**Usage:**
```python
# Enable server: Upsert to vector DB
await repo.sync_by_enabled_status(server, enabled=True, fields_changed={'enabled'})

# Disable server: Delete from vector DB
await repo.sync_by_enabled_status(server, enabled=False, fields_changed={'enabled'})

# Update server: Smart sync
await repo.sync_by_enabled_status(server, enabled=True, fields_changed={'description'})
```

**Smart Features:**
- Metadata-only changes: Fast update without re-vectorization
- Content changes: Full update with re-vectorization
- Auto-detection: If `fields_changed` is None, analyzes changes automatically

#### `delete_by_server_id(server_id, server_name)`

Delete server from vector DB by MongoDB ID.

**Parameters:**
- `server_id`: str - MongoDB ObjectId as string
- `server_name`: Optional[str] - For better logging

**Returns:** bool - Success status

**Usage:**
```python
await repo.delete_by_server_id("507f1f77bcf86cd799439011", "GitHub Copilot")
```

#### `get_by_server_id(server_id)`

Get server by MongoDB ID from vector DB.

**Parameters:**
- `server_id`: str - MongoDB ObjectId as string

**Returns:** Optional[ExtendedMCPServer]

**Usage:**
```python
server = await repo.get_by_server_id("507f1f77bcf86cd799439011")
if server:
    print(f"Found: {server.serverName}")
```

#### `get_by_path(path)`

Get server by path from vector DB.

**Parameters:**
- `path`: str - Server path (e.g., "/github")

**Returns:** Optional[ExtendedMCPServer]

**Usage:**
```python
server = await repo.get_by_path("/github")
```

### Generic Repository Methods (Inherited)

MCPServerRepository extends `Repository[ExtendedMCPServer]`, so it also has:

```python
# CRUD Operations
await repo.save(server)                    # Save new server
await repo.get(weaviate_uuid)              # Get by Weaviate UUID
await repo.update(server, fields_changed)  # Update existing
await repo.upsert(server, fields_changed)  # Create or update
await repo.delete(weaviate_uuid)           # Delete by Weaviate UUID

# Search Operations
results = await repo.search("semantic query", k=10, filters={...})
results = await repo.filter(filters={'enabled': True}, limit=50)

# Bulk Operations
result = await repo.bulk_save([server1, server2, server3])
deleted = await repo.delete_by_filter({'server_id': 'some-id'})
```

## Best Practices

### 1. Service Layer Pattern

**✅ DO: Use specialized repository methods**

```python
# Good: Clear, centralized logic
async def toggle_server_status(server, enabled):
    await server.save()  # MongoDB
    asyncio.create_task(
        self.mcp_server_repo.sync_by_enabled_status(server, enabled)
    )
```

**❌ DON'T: Implement vector DB logic in service**

```python
# Bad: Duplicated logic, hard to maintain
async def toggle_server_status(server, enabled):
    await server.save()
    if enabled:
        existing = await vector_db.filter(...)
        if existing:
            await vector_db.delete(...)
        await vector_db.save(server)
    else:
        await vector_db.delete_by_filter(...)
```

### 2. Smart Update Optimization

**Metadata-only changes** (fast - no re-vectorization):
```python
# Only tags/rating changed
server.tags = ['popular', 'recommended']
server.rating = 4.5

await repo.sync_by_enabled_status(
    server,
    enabled=True,
    fields_changed={'tags', 'rating'}  # Metadata only
)
```

**Content changes** (slower - requires re-vectorization):
```python
# Description changed - affects searchability
server.description = "New comprehensive description"

await repo.sync_by_enabled_status(
    server,
    enabled=True,
    fields_changed={'description'}  # Content field
)
```

**Auto-detection** (when unsure):
```python
# Repository determines what changed
await repo.sync_by_enabled_status(server, enabled=True)
```

### 3. Non-Blocking Background Tasks

For service layer - fire and forget:

```python
# Non-blocking: Request returns immediately
asyncio.create_task(
    self.mcp_server_repo.sync_by_enabled_status(server, enabled, fields_changed)
)

# Response to user
return {"status": "success", "message": "Server updated"}
```

### 4. Error Handling

```python
try:
    success = await repo.sync_by_enabled_status(server, enabled=True)

    if not success:
        logger.warning(f"Failed to sync {server.serverName}")
        # Optional: Queue for retry, alert admin, etc.

except Exception as e:
    logger.error(f"Unexpected sync error: {e}", exc_info=True)
    # Handle critical errors
```

### 5. Query Patterns

```python
# By MongoDB ID (most common)
server = await repo.get_by_server_id(str(server.id))

# By path (for lookups)
server = await repo.get_by_path("/github")

# Semantic search (for discovery)
results = await repo.search("GitHub integration", k=10)

# Filter by metadata (for listings)
enabled_servers = await repo.filter({'enabled': True}, limit=100)
```

## Common Scenarios

### Scenario 1: Enable/Disable Server

```python
async def toggle_server(server_id: str, enabled: bool):
    """Toggle server status and sync to vector DB."""
    # Get server from MongoDB
    server = await ExtendedMCPServer.get(server_id)

    # Update status
    server.config['enabled'] = enabled
    await server.save()

    # Sync to vector DB
    await mcp_server_repo.sync_by_enabled_status(
        server=server,
        enabled=enabled,
        fields_changed={'enabled'}
    )
```

### Scenario 2: Update Server Metadata

```python
async def update_server_tags(server_id: str, tags: List[str]):
    """Update server tags (metadata-only, fast)."""
    server = await ExtendedMCPServer.get(server_id)

    server.tags = tags
    await server.save()

    # Fast metadata update (no re-vectorization)
    enabled = server.config.get('enabled', False)
    await mcp_server_repo.sync_by_enabled_status(
        server=server,
        enabled=enabled,
        fields_changed={'tags'}  # Metadata only
    )
```

### Scenario 3: Update Server Description

```python
async def update_server_description(server_id: str, description: str):
    """Update server description (content change, requires re-vectorization)."""
    server = await ExtendedMCPServer.get(server_id)

    server.description = description
    await server.save()

    # Full update with re-vectorization
    enabled = server.config.get('enabled', False)
    await mcp_server_repo.sync_by_enabled_status(
        server=server,
        enabled=enabled,
        fields_changed={'description'}  # Content field
    )
```

### Scenario 4: Delete Server

```python
async def delete_server(server_id: str):
    """Delete server from MongoDB and vector DB."""
    server = await ExtendedMCPServer.get(server_id)

    # Delete from MongoDB
    await server.delete()

    # Delete from vector DB
    await mcp_server_repo.delete_by_server_id(
        server_id=server_id,
        server_name=server.serverName
    )
```

### Scenario 5: Search Servers

```python
async def search_servers(query: str, enabled_only: bool = True):
    """Semantic search for servers."""
    filters = {'enabled': True} if enabled_only else {}

    results = await mcp_server_repo.search(
        query=query,
        k=10,
        filters=filters
    )

    return results
```

## Advanced: Custom Models

To use the generic repository with custom models, implement the document conversion interface:

```python
from langchain_core.documents import Document
import uuid

class MyCustomModel:
    """Custom model example."""

    # Required: Collection name
    COLLECTION_NAME = "MY_CUSTOM_COLLECTION"

    def __init__(self, name: str, description: str):
        self.id = str(uuid.uuid4())
        self.name = name
        self.description = description

    def to_document(self) -> Document:
        """Convert model to LangChain Document for vectorization."""
        return Document(
            page_content=f"{self.name} - {self.description}",  # Content to vectorize
            metadata={
                'name': self.name,
                'custom_id': self.id,
                # ... other metadata fields
            },
            id=self.id  # Weaviate UUID
        )

    @classmethod
    def from_document(cls, doc: Document):
        """Reconstruct model from LangChain Document."""
        return cls(
            name=doc.metadata.get('name', ''),
            description=doc.page_content.split(' - ', 1)[-1]
        )

# Use with generic repository
from registry_pkgs.vector import initialize_database

db = initialize_database()
repo = db.for_model(MyCustomModel)

# Now you can use ORM-style operations
model = MyCustomModel("Test", "Description")
model_id = await repo.save(model)
results = await repo.search("query", k=10)
```

## Directory Structure

```
registry-pkgs/src/registry_pkgs/
├── models/
│   ├── extended_mcp_server.py        # Main domain model
│   ├── extended_acl_entry.py         # ACL model
│   └── enums.py                      # Domain enums
└── vector/
    ├── __init__.py                   # Public API exports
    ├── client.py                     # DatabaseClient (initialization)
    ├── repository.py                 # Generic Repository[T]
    ├── repositories/                 # Specialized repositories
    │   └── mcp_server_repository.py  # MCPServerRepository
    ├── adapters/
    │   ├── adapter.py                # VectorStoreAdapter base
    │   ├── factory.py                # Adapter factory
    │   └── create/                   # Creator functions
    │       ├── embedding.py          # Embedding creators
    │       └── vector_store.py       # Vector store creators
    ├── backends/
    │   └── weaviate_store.py         # Weaviate implementation
    ├── retrievers/
    │   └── reranker.py               # Reranker factory (FlashRank)
    ├── config/
    │   └── config.py                 # Configuration classes
    └── enum/
        └── enums.py                  # Vector DB enums
```

## Extending the System

### Add New Vector Store (e.g., Pinecone)

**1. Add enum:**
```python
# reigstry_pkgs/vector/enum/enums.py
class VectorStoreType(str, Enum):
    WEAVIATE = "weaviate"
    PINECONE = "pinecone"  # Add new
```

**2. Create adapter:**
```python
# registry_pkgs/vector/backends/pinecone_store.py
from ..adapters.adapter import VectorStoreAdapter

class PineconeStore(VectorStoreAdapter):
    def _create_vector_store(self, collection_name: str):
        from langchain_pinecone import PineconeVectorStore
        return PineconeVectorStore(
            index_name=collection_name,
            embedding=self.embedding
        )

    # Implement required methods
    def get_by_id(self, doc_id: str, ...) -> Optional[Document]:
        # Pinecone-specific implementation
        ...
```

**3. Register creator:**
```python
# registry_pkgs/vector/adapters/create/vector_store.py
@register_vector_store_creator(VectorStoreType.PINECONE.value)
def create_pinecone_adapter(config, embedding):
    return PineconeStore(embedding=embedding, config=...)
```

Done! Use with `VECTOR_STORE_TYPE=pinecone`

## API Reference

### MCPServerRepository

| Method | Signature | Description |
|--------|-----------|-------------|
| `sync_by_enabled_status()` | `(server, enabled, fields_changed?) → bool` | Smart sync: upsert if enabled, delete if not |
| `delete_by_server_id()` | `(server_id, server_name?) → bool` | Delete by MongoDB ID |
| `get_by_server_id()` | `(server_id) → Optional[Server]` | Get by MongoDB ID |
| `get_by_path()` | `(path) → Optional[Server]` | Get by server path |
| `update_server_smart()` | `(server, fields_changed?) → bool` | Smart update with change detection |

### Generic Repository[T]

| Method | Signature | Description |
|--------|-----------|-------------|
| `save()` | `(instance) → str` | Save new instance |
| `get()` | `(id) → Optional[T]` | Get by Weaviate UUID |
| `update()` | `(instance, fields_changed?, create_if_missing?) → bool` | Update existing |
| `upsert()` | `(instance, fields_changed?) → bool` | Create or update |
| `delete()` | `(id) → bool` | Delete by Weaviate UUID |
| `search()` | `(query, k, filters?) → List[T]` | Semantic search |
| `filter()` | `(filters, limit) → List[T]` | Filter by metadata |
| `bulk_save()` | `(instances) → BatchResult` | Bulk save |
| `delete_by_filter()` | `(filters) → int` | Bulk delete |

### VectorStoreAdapter

| Method | Description |
|--------|-------------|
| `add_documents()` | Add documents to collection |
| `delete()` | Delete documents by IDs |
| `get_by_id()` | Get document by ID |
| `get_by_ids()` | Get multiple documents by IDs |
| `similarity_search()` | Vector similarity search |
| `search_with_rerank()` | Search with reranking (FlashRank) |
| `filter_by_metadata()` | Pure metadata filtering |
| `list_collections()` | List all collections |
| `collection_exists()` | Check if collection exists |

## Troubleshooting

### Common Issues

**Issue: "Repository.upsert() got an unexpected keyword argument 'server'"**

**Solution:** Use `instance=` parameter name:
```python
# ❌ Wrong
await repo.aupsert(server=server)

# ✅ Correct
await repo.aupsert(instance=server)
```

**Issue: "Failed to get collection: None"**

**Solution:** Ensure collection name is properly set in model:
```python
class ExtendedMCPServer:
    COLLECTION_NAME = "MCP_GATEWAY"  # Required
```

**Issue: Slow updates**

**Solution:** Use `fields_changed` to optimize:
```python
# Fast: Metadata-only update
await repo.sync_by_enabled_status(server, True, fields_changed={'tags'})

# Slow: Full re-vectorization
await repo.sync_by_enabled_status(server, True)  # No fields_changed
```

## Performance Tips

1. **Use `fields_changed`**: Significantly faster for metadata-only updates
2. **Batch operations**: Use `bulk_save()` for multiple documents
3. **Background tasks**: Use `asyncio.create_task()` for non-blocking ops
4. **Proper filtering**: Use metadata filters before semantic search to reduce candidates
5. **Reranking**: Use `search_with_rerank()` for better relevance with acceptable performance

## Support

For issues or questions:
- Check the troubleshooting section above
- Review the common scenarios
- Inspect logs for detailed error messages
