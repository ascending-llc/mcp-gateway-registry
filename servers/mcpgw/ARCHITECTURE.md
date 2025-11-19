# MCPGW Vector Search Architecture

## Module Structure

```
servers/mcpgw/
│
├── server.py                      # Main MCP server
│   └── intelligent_tool_finder()  # Uses vector_search_service
│
└── search/                        # Vector search module
    ├── __init__.py               # Exports: vector_search_service
    ├── base.py                   # Abstract: VectorSearchService
    ├── service.py                # Factory: create_vector_search_service()
    ├── embedded_service.py       # Impl: EmbeddedFaissService
    └── external_service.py       # Impl: ExternalVectorSearchService
```

## Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     MCPGW Server (server.py)                │
│                                                             │
│  ┌────────────────────────────────────────────────────┐   │
│  │  intelligent_tool_finder(query, tags, scopes...)   │   │
│  │                                                     │   │
│  │  1. Extract user scopes from headers              │   │
│  │  2. Call vector_search_service.search_tools()     │   │
│  │  3. Return filtered results                       │   │
│  └─────────────────┬───────────────────────────────────┘   │
│                    │                                        │
└────────────────────┼────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │  vector_search_service │ (Global Singleton)
         │   (from search/)      │
         └───────────┬────────────┘
                     │
         ┌───────────┴────────────┐
         │                        │
         ▼                        ▼
┌─────────────────┐      ┌──────────────────────┐
│ Embedded Mode   │      │  External Mode       │
│ (default)       │      │  (lightweight)       │
└─────────────────┘      └──────────────────────┘

EMBEDDED MODE                    EXTERNAL MODE
────────────────                 ─────────────
┌───────────────────────┐       ┌──────────────────────┐
│ EmbeddedFaissService  │       │ExternalVectorSearch  │
│                       │       │      Service         │
├───────────────────────┤       ├──────────────────────┤
│ • Load FAISS index    │       │ • HTTP client        │
│ • Load embeddings     │       │ • Auth management    │
│ • Encode queries      │       │ • API calls          │
│ • Search vectors      │       │ • Result parsing     │
│ • Apply scope filter  │       │                      │
│ • Rank results        │       │                      │
└──────┬────────────────┘       └──────┬───────────────┘
       │                               │
       │                               │
       ▼                               ▼
┌──────────────────┐          ┌────────────────────┐
│ Local Resources: │          │ Remote API Call:   │
│                  │          │                    │
│ • service_index  │          │ POST /api/search/  │
│   .faiss         │          │      semantic      │
│ • service_index  │          │                    │
│   _metadata.json │          │ {                  │
│ • embedding      │          │   query,           │
│   model files    │          │   tags,            │
│ • scopes.yml     │          │   user_scopes,     │
│                  │          │   top_k_services,  │
└──────────────────┘          │   top_n_tools      │
                              │ }                  │
                              │                    │
                              │ ↓                  │
                              │                    │
                              │ Registry performs: │
                              │ • Vector search    │
                              │ • Scope filtering  │
                              │ • Result ranking   │
                              │                    │
                              └────────────────────┘
```

## Configuration Flow

```
                ┌────────────────────┐
                │  Environment Vars  │
                │                    │
                │ MCPGW_VECTOR_      │
                │ SEARCH_MODE=?      │
                └─────────┬──────────┘
                          │
             ┌────────────┴────────────┐
             │                         │
             ▼                         ▼
    ┌────────────────┐        ┌───────────────┐
    │   "embedded"   │        │  "external"   │
    └────────┬───────┘        └───────┬───────┘
             │                        │
             ▼                        ▼
┌─────────────────────────┐  ┌────────────────────┐
│ Load Dependencies:      │  │ Load Dependencies: │
│                         │  │                    │
│ • faiss-cpu             │  │ • httpx only       │
│ • sentence-transformers │  │                    │
│ • torch                 │  │                    │
│ • scikit-learn          │  │                    │
│ • numpy                 │  │                    │
└─────────────────────────┘  └────────────────────┘
```

## Request Flow Comparison

### Embedded Mode
```
Client Request
    │
    ▼
intelligent_tool_finder()
    │
    ▼
EmbeddedFaissService.search_tools()
    │
    ├─→ Load FAISS index (cached)
    ├─→ Encode query (local)
    ├─→ Search vectors (local)
    ├─→ Filter by tags (local)
    ├─→ Check scopes (local)
    └─→ Rank results (local)
    │
    ▼
Return results
    │
    ▼
Client Response

Time: ~50-100ms
Network: None
Memory: ~2GB
```

### External Mode
```
Client Request
    │
    ▼
intelligent_tool_finder()
    │
    ▼
ExternalVectorSearchService.search_tools()
    │
    ├─→ Prepare API request
    ├─→ HTTP POST to registry
    │   │
    │   └──→ Registry Service
    │           ├─→ Load FAISS index
    │           ├─→ Encode query
    │           ├─→ Search vectors
    │           ├─→ Filter by tags
    │           ├─→ Check scopes
    │           └─→ Rank results
    │   ┌───────┘
    │   │
    ├─→ Parse response
    └─→ Format results
    │
    ▼
Return results
    │
    ▼
Client Response

Time: ~200-300ms
Network: 1 HTTP call
Memory: ~50MB
```

## Interface Contract

```python
# Abstract base class that both implementations follow
class VectorSearchService(ABC):
    
    @abstractmethod
    async def initialize(self) -> None:
        """Called once at startup"""
        
    @abstractmethod
    async def search_tools(
        query: Optional[str],
        tags: Optional[List[str]],
        user_scopes: Optional[List[str]],
        top_k_services: int,
        top_n_tools: int
    ) -> List[Dict[str, Any]]:
        """Main search method"""
        
    @abstractmethod
    async def check_availability(self) -> bool:
        """Health check"""
```

## Factory Pattern

```python
# service.py creates the appropriate implementation
def create_vector_search_service() -> VectorSearchService:
    mode = os.environ.get('TOOL_DISCOVERY_MODE', 'embedded')
    
    if mode == 'external':
        return ExternalVectorSearchService(
            registry_base_url=REGISTRY_BASE_URL,
            registry_username=REGISTRY_USERNAME,
            registry_password=REGISTRY_PASSWORD
        )
    else:
        return EmbeddedFaissService(
            registry_server_data_path=PATH,
            embeddings_model_name=MODEL_NAME,
            embedding_dimension=DIMENSION
        )

# Global singleton
vector_search_service = create_vector_search_service()
```

## Deployment Scenarios

### Scenario 1: Monolithic (Embedded)
```
┌──────────────────────┐
│   Single Container   │
│                      │
│  ┌────────────────┐ │
│  │ MCPGW Server   │ │
│  │                │ │
│  │ + FAISS        │ │
│  │ + Models       │ │
│  │ + Registry API │ │
│  └────────────────┘ │
└──────────────────────┘

Pros: Simple, fast
Cons: Heavy, single point
```

### Scenario 2: Microservices (External)
```
┌─────────────┐    ┌─────────────┐
│ MCPGW #1    │    │ MCPGW #2    │
│ (Light)     │    │ (Light)     │
└──────┬──────┘    └──────┬──────┘
       │                  │
       └────────┬─────────┘
                │
         ┌──────▼──────┐
         │  Registry   │
         │  (FAISS)    │
         └─────────────┘

Pros: Scalable, maintainable
Cons: Network latency
```

## Key Architectural Decisions

1. **Interface-based Design**
   - Enables switching implementations
   - Makes testing easier
   - Open for extensions

2. **Factory Pattern**
   - Single configuration point
   - Hides implementation details
   - Runtime flexibility

3. **Shared Dependencies**
   - Both modes use same scopes logic
   - Consistent error handling
   - Unified logging

4. **Backward Compatibility**
   - Default mode matches original
   - No breaking changes
   - Gradual migration path

## Summary

This architecture provides:
- **Flexibility** via mode selection
- **Maintainability** via clean separation
- **Scalability** via external option
- **Testability** via interface abstraction
- **Performance** optimized for each mode
