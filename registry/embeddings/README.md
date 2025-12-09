# Embeddings Module

Vendor-agnostic embeddings generation for MCP Gateway Registry's semantic search functionality.

## Overview

This module provides a unified interface for generating text embeddings from multiple providers, supporting both local models (sentence-transformers) and cloud-based APIs (via LiteLLM).

## Features

- **Vendor-agnostic**: Switch between embeddings providers with configuration changes
- **Local & Cloud Support**: Use local models or cloud APIs (OpenAI, Cohere, Amazon Bedrock, etc.)
- **Backward Compatible**: Works seamlessly with existing FAISS indices
- **Easy Configuration**: Simple environment variable setup
- **Extensible**: Easy to add new providers

## Architecture

```
EmbeddingsClient (Abstract Base Class)
├── SentenceTransformersClient (Local models)
└── LiteLLMClient (Cloud APIs via LiteLLM)
```

## Quick Start

### Using Sentence Transformers (Default)

```bash
# In .env
EMBEDDINGS_PROVIDER=sentence-transformers
EMBEDDINGS_MODEL_NAME=all-MiniLM-L6-v2
EMBEDDINGS_MODEL_DIMENSIONS=384
```

```python
from registry.embeddings import create_embeddings_client

client = create_embeddings_client(
    provider="sentence-transformers",
    model_name="all-MiniLM-L6-v2",
    embedding_dimension=384,
)

embeddings = client.encode(["Hello world", "This is a test"])
print(embeddings.shape)  # (2, 384)
```

### Using LiteLLM with OpenAI

```bash
# In .env
EMBEDDINGS_PROVIDER=litellm
EMBEDDINGS_MODEL_NAME=openai/text-embedding-3-small
EMBEDDINGS_MODEL_DIMENSIONS=1536
EMBEDDINGS_API_KEY=your_openai_api_key
```

```python
from registry.embeddings import create_embeddings_client

client = create_embeddings_client(
    provider="litellm",
    model_name="openai/text-embedding-3-small",
    api_key="your_openai_api_key",
    embedding_dimension=1536,
)

embeddings = client.encode(["Hello world", "This is a test"])
print(embeddings.shape)  # (2, 1536)
```

### Using LiteLLM with Amazon Bedrock

Amazon Bedrock uses the standard AWS credential chain for authentication.

```bash
# In .env
EMBEDDINGS_PROVIDER=litellm
EMBEDDINGS_MODEL_NAME=bedrock/amazon.titan-embed-text-v1
EMBEDDINGS_MODEL_DIMENSIONS=1536
EMBEDDINGS_AWS_REGION=us-east-1
```

**Configure AWS credentials via standard methods:**

**Option 1: IAM Roles (Recommended for EC2/EKS)**
```bash
# No additional configuration needed
# EC2 instance or EKS pod automatically uses attached IAM role
```

**Option 2: Environment Variables**
```bash
export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
export AWS_REGION=us-east-1
```

**Option 3: AWS Credentials File**
```bash
# ~/.aws/credentials
[default]
aws_access_key_id = AKIAIOSFODNN7EXAMPLE
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

# ~/.aws/config
[default]
region = us-east-1
```

**Python Usage:**
```python
from registry.embeddings import create_embeddings_client

# Uses standard AWS credential chain
client = create_embeddings_client(
    provider="litellm",
    model_name="bedrock/amazon.titan-embed-text-v1",
    aws_region="us-east-1",
    embedding_dimension=1536,
)

embeddings = client.encode(["Hello world", "This is a test"])
print(embeddings.shape)  # (2, 1536)
```

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `EMBEDDINGS_PROVIDER` | Provider type: `sentence-transformers` or `litellm` | `sentence-transformers` | No |
| `EMBEDDINGS_MODEL_NAME` | Model identifier | `all-MiniLM-L6-v2` | Yes |
| `EMBEDDINGS_MODEL_DIMENSIONS` | Embedding dimension | `384` | Yes |
| `EMBEDDINGS_API_KEY` | API key for cloud provider (OpenAI, Cohere, etc.) | - | For cloud* |
| `EMBEDDINGS_API_BASE` | Custom API endpoint (LiteLLM only) | - | No |
| `EMBEDDINGS_AWS_REGION` | AWS region for Bedrock (LiteLLM only) | - | For Bedrock |

*Not required for AWS Bedrock - use standard AWS credential chain (IAM roles, environment variables, ~/.aws/credentials)

### Supported Models

#### Sentence Transformers (Local)

- `all-MiniLM-L6-v2` (384 dimensions) - Fast, lightweight
- `all-mpnet-base-v2` (768 dimensions) - High quality
- `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions) - Multilingual
- Any model from [Hugging Face sentence-transformers](https://huggingface.co/models?library=sentence-transformers)

#### LiteLLM (Cloud-based)

**OpenAI:**
- `openai/text-embedding-3-small` (1536 dimensions)
- `openai/text-embedding-3-large` (3072 dimensions)
- `openai/text-embedding-ada-002` (1536 dimensions)

**Cohere:**
- `cohere/embed-english-v3.0` (1024 dimensions)
- `cohere/embed-multilingual-v3.0` (1024 dimensions)

**Amazon Bedrock:**
- `bedrock/amazon.titan-embed-text-v1` (1536 dimensions)
- `bedrock/cohere.embed-english-v3` (1024 dimensions)
- `bedrock/cohere.embed-multilingual-v3` (1024 dimensions)

## API Reference

### EmbeddingsClient (Abstract)

Base class for all embeddings clients.

**Methods:**
- `encode(texts: List[str]) -> np.ndarray`: Generate embeddings for texts
- `get_embedding_dimension() -> int`: Get embedding dimension

### SentenceTransformersClient

Local embeddings using sentence-transformers library.

**Constructor:**
```python
SentenceTransformersClient(
    model_name: str,
    model_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
)
```

**Parameters:**
- `model_name`: Hugging Face model identifier
- `model_dir`: Local directory with pre-downloaded model (optional)
- `cache_dir`: Cache directory for models (optional)

### LiteLLMClient

Cloud-based embeddings via LiteLLM.

**Constructor:**
```python
LiteLLMClient(
    model_name: str,
    api_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    api_base: Optional[str] = None,
    aws_region: Optional[str] = None,
    embedding_dimension: Optional[int] = None,
)
```

**Parameters:**
- `model_name`: Provider-prefixed model (e.g., `openai/text-embedding-3-small`, `bedrock/amazon.titan-embed-text-v1`)
- `api_key`: API key for the provider (OpenAI, Cohere, etc.; not used for Bedrock)
- `api_base`: Custom API endpoint URL (optional)
- `aws_region`: AWS region for Bedrock (required for Bedrock)
- `embedding_dimension`: Expected dimension for validation (optional)

**AWS Bedrock Notes:**
- Uses standard AWS credential chain for authentication (IAM roles, environment variables, ~/.aws/credentials)
- The `api_key` parameter is not used for Bedrock authentication
- The `aws_region` parameter is required for Bedrock

### Factory Function

```python
create_embeddings_client(
    provider: str,
    model_name: str,
    model_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    api_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    api_base: Optional[str] = None,
    aws_region: Optional[str] = None,
    embedding_dimension: Optional[int] = None,
) -> EmbeddingsClient
```

Creates an embeddings client based on the provider type.

**Parameters:**
- `provider`: "sentence-transformers" or "litellm"
- `model_name`: Model identifier
- `model_dir`: Local model directory (sentence-transformers only)
- `cache_dir`: Cache directory (sentence-transformers only)
- `api_key`: API key (litellm only; not used for Bedrock)
- `api_base`: Custom API endpoint (litellm only)
- `aws_region`: AWS region (litellm with Bedrock only)
- `embedding_dimension`: Expected dimension

## Integration with FAISS Service

The embeddings module integrates seamlessly with the existing FAISS search service:

```python
# In registry/search/service.py
from registry.embeddings import create_embeddings_client

class FaissService:
    async def _load_embedding_model(self):
        self.embedding_model = create_embeddings_client(
            provider=settings.embeddings_provider,
            model_name=settings.embeddings_model_name,
            # ... other parameters from settings
        )
```

## Migration Guide

### From Direct SentenceTransformer Usage

**Before:**
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings = model.encode(texts)
```

**After:**
```python
from registry.embeddings import create_embeddings_client

client = create_embeddings_client(
    provider="sentence-transformers",
    model_name="all-MiniLM-L6-v2",
)
embeddings = client.encode(texts)
```

### Switching to Cloud Provider

Just update your `.env` file:

```bash
# From
EMBEDDINGS_PROVIDER=sentence-transformers
EMBEDDINGS_MODEL_NAME=all-MiniLM-L6-v2
EMBEDDINGS_MODEL_DIMENSIONS=384

# To
EMBEDDINGS_PROVIDER=litellm
EMBEDDINGS_MODEL_NAME=openai/text-embedding-3-small
EMBEDDINGS_MODEL_DIMENSIONS=1536
EMBEDDINGS_API_KEY=your_openai_api_key
```

No code changes required!

## Performance Considerations

### Local Models (Sentence Transformers)
- **Pros**: No API costs, privacy, no network latency
- **Cons**: CPU/GPU requirements, model download size
- **Best for**: High-volume usage, sensitive data, offline operation

### Cloud APIs (LiteLLM)
- **Pros**: No local resources, higher quality models, instant availability
- **Cons**: API costs, network dependency, data leaves premises
- **Best for**: Low-volume usage, rapid prototyping, maximum quality

## Troubleshooting

### LiteLLM Not Installed

```
RuntimeError: LiteLLM is not installed. Install it with: uv add litellm
```

**Solution:**
```bash
uv add litellm
```

### Dimension Mismatch

```
WARNING: Embedding dimension mismatch: expected 384, got 1536
```

**Solution:** Update `EMBEDDINGS_MODEL_DIMENSIONS` to match your model's actual output.

### API Authentication Errors

For cloud providers, ensure your API key is correctly set:
- OpenAI: Set `EMBEDDINGS_API_KEY`
- Cohere: Set `EMBEDDINGS_API_KEY`
- Bedrock: Configure AWS credentials via standard AWS methods

## Testing

Run the test suite to verify the integration:

```bash
# Create a test file
cat > test_embeddings.py << 'EOF'
from registry.embeddings import create_embeddings_client

# Test sentence-transformers
client = create_embeddings_client(
    provider="sentence-transformers",
    model_name="all-MiniLM-L6-v2",
)
embeddings = client.encode(["test"])
print(f"✓ Embeddings shape: {embeddings.shape}")
EOF

# Run test
uv run python test_embeddings.py
```

## Contributing

To add a new embeddings provider:

1. Create a new client class inheriting from `EmbeddingsClient`
2. Implement `encode()` and `get_embedding_dimension()` methods
3. Update `create_embeddings_client()` factory function
4. Add configuration options to `registry/core/config.py`
5. Document in this README

## License

Apache 2.0 - See LICENSE file for details
