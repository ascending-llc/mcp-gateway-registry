# Packages

## Overview

The `packages` directory contains shared Python libraries and utilities used as common dependencies across various services in the MCP Gateway Registry project. These packages provide reusable functionality that can be imported and used by multiple services, promoting code reuse and consistency.

## Purpose

These packages serve as the foundation for building services within the ecosystem. By centralizing common functionality, we:

- **Reduce code duplication** - Common patterns and utilities are implemented once
- **Ensure consistency** - All services use the same interfaces and implementations
- **Simplify maintenance** - Updates and fixes are applied in one place
- **Improve developer experience** - Clear, documented APIs for shared functionality

## Available Packages

### `db` - Weaviate ORM and Database Utilities

A Django-like ORM for Weaviate vector database with simplified configuration and query building.

**Key Features:**
- Django-style model definitions with field validation
- Simplified client configuration with environment-based setup
- Comprehensive query building with filter chaining
- Batch operations with error reporting
- Collection management utilities

For detailed documentation, usage examples, and API reference, see: [packages/db/README.md](./db/README.md)

### `shared` - Common Types and Models

Shared enumerations, data models, and types used across multiple services.

**Key Features:**
- Common enumerations (e.g., `ToolDiscoveryMode`)
- Shared data models (e.g., `McpTool` for vector search)
- Type definitions used by multiple services
- Centralized schema definitions

**Contents:**
- `enums.py` - Shared enumeration types
- `models.py` - Shared data model definitions
- Common type definitions and constants

This package provides a single source of truth for types and models that need to be consistent across different services.

## Usage

To use these packages in your service:

1. **Add dependency** - Include the package in your service's `pyproject.toml`
2. **Import modules** - Use standard Python imports to access functionality
3. **Follow patterns** - Adhere to the established patterns and conventions

Example import for `db` package:
```python
from packages.db import Model, TextField, init_weaviate, get_weaviate_client
from packages.db.search.filters import Q
```

Example import for `shared` package:
```python
from packages.shared.enums import ToolDiscoveryMode
from packages.shared.models import McpTool
```

## Development

When developing new packages or modifying existing ones:

1. **Maintain backward compatibility** - Avoid breaking changes when possible
2. **Add comprehensive tests** - Ensure reliability across all consuming services
3. **Update documentation** - Keep README files and docstrings current
4. **Consider service impact** - Changes may affect multiple services

## Adding New Packages

To add a new shared package:

1. Create a new subdirectory under `packages/`
2. Include a `pyproject.toml` with proper metadata
3. Add comprehensive documentation in a `README.md`
4. Implement the functionality with clear, reusable APIs
5. Add tests in the `packages/tests/` directory
