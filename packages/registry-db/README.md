# MCP Gateway Registry - Packages

Unified vector database interface with three-layer architecture and model generation tools.

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

## Generating Models

Generate Beanie ODM models from JSON schemas stored in GitHub releases.

### Prerequisites

Install GitHub CLI (optional but recommended for private repositories):
```bash
# macOS
brew install gh

# Authenticate with GitHub
gh auth login
```

### Installation

Install the packages module in editable mode:
```bash
cd packages
uv pip install -e .
```

### Generate Models

Download schemas from a GitHub release and generate Python models:
```bash
# Using GitHub CLI authentication (recommended for private repos)
uv run import-schemas --tag asc0.4.0 \
  --files user.json token.json \
  --output-dir ./models \
  --token $(gh auth token)

**Available options:**
- `--tag`: GitHub release version/tag (required)
- `--files`: Space-separated list of JSON schema files (required)
- `--output-dir`: Output directory for generated models (default: ./models)
- `--repo`: GitHub repository (default: ascending-llc/jarvis-api)
- `--token`: GitHub Personal Access Token for private repos

## Structure

```
packages/
├── models/                # Data models and schemas
│   ├── __init__.py        # Exports all models
│   ├── ..(models).py      # project specific models
│   ├── enums.py           # Enums (ToolDiscoveryMode, etc.)
│   ├── import_schemas.py  # Schema import tool
│   └── _generated/        # Auto-generated models (gitignored)
│       ├── README.md      # Generation instructions
│       ├── .schema-version # Version tracking
│       └── *.py           # Generated Beanie models
├── vector/                # Vector database layer
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

## Testing

```bash
uv run pytest tests/ -v
```

## Documentation

- [db/README.md](./db/README.md) - Complete API reference
- [db/ARCHITECTURE.md](./db/ARCHITECTURE.md) - Design details (if exists)
- [db/FILTERS.md](./db/FILTERS.md) - Filter guide (if exists)

## Extending

See [db/README.md#extending-the-system](./db/README.md#extending-the-system) for:
- Adding new vector stores
- Adding new embedding providers
