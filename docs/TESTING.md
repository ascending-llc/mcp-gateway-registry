# 🧪 Testing Guide for MCP Registry

## Overview

This document provides comprehensive guidance on testing the MCP Registry application. Our testing infrastructure supports multiple test types, comprehensive coverage reporting, and domain-specific testing.

## 🏗️ Test Architecture

### Test Types

- **Unit Tests** (`tests/unit/`) - Test individual components in isolation
- **Integration Tests** (`tests/integration/`) - Test component interactions
- **End-to-End Tests** (`tests/e2e/`) - Test complete user workflows

### Domain-Based Organization

Tests are organized by domain to match our application architecture:

```
tests/
├── unit/
│   ├── auth/          # Authentication domain tests
│   ├── servers/       # Server management tests  
│   ├── search/        # Search & AI tests
│   ├── health/        # Health monitoring tests
│   └── core/          # Core infrastructure tests
├── integration/       # Cross-domain integration tests
├── e2e/              # End-to-end workflow tests
├── fixtures/         # Test data factories and utilities
└── conftest.py       # Shared pytest configuration
```

## 🚀 Quick Start

### Installation

```bash
# Install development dependencies
make install-dev

# Or manually
pip install -e .[dev]
```

### Running Tests

```bash
# Run all tests with coverage
make test

# Run specific test types
make test-unit           # Unit tests only
make test-integration    # Integration tests only
make test-e2e           # End-to-end tests only
make test-fast          # Fast tests (exclude slow)

# Run domain-specific tests
make test-auth          # Authentication tests
make test-servers       # Server management tests
make test-search        # Search domain tests
make test-health        # Health monitoring tests
make test-core          # Core infrastructure tests
```

### Coverage Reports

```bash
# Generate coverage reports
make test-coverage

# View HTML report
open htmlcov/index.html
```

## 📊 Coverage Targets

We maintain **80% minimum coverage** across all domains:

| Domain | Target Coverage | Focus Areas |
|--------|----------------|-------------|
| **auth/** | 85%+ | Session management, OAuth2 flows |
| **servers/** | 90%+ | CRUD operations, state management |
| **search/** | 75%+ | FAISS operations, embeddings |
| **health/** | 85%+ | WebSocket management, monitoring |
| **core/** | 95%+ | Configuration, schemas |

## 🔧 Test Configuration

### Pytest Configuration

Our pytest setup (`pyproject.toml`) includes:

- **Automatic coverage reporting** with HTML and XML output
- **Strict markers** to prevent typos
- **Asyncio support** for testing async code
- **Parallel execution** capability
- **Multiple output formats** (HTML, JSON, XML)

### Test Markers

Use markers to categorize and run specific test groups:

```python
@pytest.mark.unit          # Unit test
@pytest.mark.integration   # Integration test
@pytest.mark.e2e          # End-to-end test
@pytest.mark.auth          # Authentication domain
@pytest.mark.servers       # Server management domain
@pytest.mark.search        # Search domain
@pytest.mark.health        # Health monitoring domain
@pytest.mark.core          # Core infrastructure
@pytest.mark.slow          # Slow-running test
```

### Running Specific Tests

```bash
# Run by marker
pytest -m "unit and auth"           # Unit tests for auth domain
pytest -m "integration and servers" # Integration tests for servers
pytest -m "not slow"               # Exclude slow tests

# Run by path
pytest tests/unit/servers/         # All server unit tests
pytest tests/integration/          # All integration tests

# Run specific test file
pytest tests/unit/servers/test_server_service.py

# Run specific test method
pytest tests/unit/servers/test_server_service.py::TestServerService::test_register_server_success
```

## 🏭 Test Fixtures and Factories

### Factory Classes

We use `factory-boy` for generating test data:

```python
from tests.fixtures.factories import (
    ServerInfoFactory,
    ToolInfoFactory,
    UserFactory,
    create_server_with_tools,
    create_multiple_servers
)

# Create a single server
server = ServerInfoFactory()

# Create a server with tools
server = create_server_with_tools(num_tools=5)

# Create multiple servers
servers = create_multiple_servers(count=10)
```

### Shared Fixtures

Common fixtures available in all tests:

```python
def test_example(
    test_client,           # FastAPI test client
    mock_authenticated_user,  # Authenticated user mock
    sample_server,         # Sample server data
    temp_dir,             # Temporary directory
    mock_settings,        # Mocked settings
):
    # Your test code here
    pass
```

## 🎯 Writing Effective Tests

### Unit Test Best Practices

```python
import pytest
from unittest.mock import patch, Mock, AsyncMock

@pytest.mark.unit
@pytest.mark.servers
class TestServerService:
    """Unit tests for ServerService."""
    
    def test_register_server_success(self, server_service, sample_server):
        """Test successful server registration."""
        # Arrange
        with patch.object(server_service, 'save_server_to_file', return_value=True):
            
            # Act
            result = server_service.register_server(sample_server)
            
            # Assert
            assert result is True
            assert sample_server["path"] in server_service.registered_servers
```

### Integration Test Best Practices

```python
@pytest.mark.integration
@pytest.mark.servers
def test_server_registration_flow(test_client, mock_authenticated_user):
    """Test complete server registration workflow."""
    # Test the full request/response cycle
    response = test_client.post("/register", data={
        "name": "Test Server",
        "path": "/test",
        "proxy_pass_url": "http://localhost:8000"
    })
    
    assert response.status_code == 201
    assert response.json()["message"] == "Service registered successfully"
```

### Async Test Best Practices

```python
@pytest.mark.asyncio
async def test_async_function(health_service):
    """Test async functionality."""
    result = await health_service.initialize()
    assert result is None  # Or whatever is expected
```

### Mock Best Practices

```python
# Mock external dependencies
with patch('registry.search.service.faiss_service') as mock_faiss:
    mock_faiss.add_or_update_service = AsyncMock()
    
    # Your test code
    await some_function()
    
    # Verify interactions
    mock_faiss.add_or_update_service.assert_called_once()
```

## 🔄 Continuous Integration

### GitHub Actions

Our CI pipeline runs:

1. **Dependency Check** - Verify all test deps are installed
2. **Unit Tests** - Fast, isolated component tests
3. **Integration Tests** - Cross-component interaction tests
4. **Domain Tests** - Parallel testing of each domain
5. **Coverage Reporting** - Ensure coverage targets are met
6. **Security Scanning** - Bandit security analysis

### Local CI Simulation

```bash
# Run the same checks as CI
make ci-test
```

## 📈 Performance Testing

### Slow Tests

Mark performance-intensive tests:

```python
@pytest.mark.slow
def test_large_dataset_processing():
    """Test processing large datasets - this is slow."""
    # Performance test code
    pass
```

### Running Without Slow Tests

```bash
# Skip slow tests for faster feedback
make test-fast
pytest -m "not slow"
```

## 🐛 Debugging Tests

### Verbose Output

```bash
# More detailed output
pytest -v

# Even more detailed
pytest -vv

# Show local variables on failure
pytest -l
```

### Debugging Specific Failures

```bash
# Stop on first failure
pytest -x

# Enter debugger on failure
pytest --pdb

# Show longer tracebacks
pytest --tb=long
```

### Log Output

```bash
# Show all log output
pytest -s

# Show logs for failed tests only
pytest --log-cli-level=INFO
```

## 📊 Coverage Analysis

### Viewing Coverage Reports

```bash
# Terminal report
coverage report

# HTML report (recommended)
coverage html
open htmlcov/index.html

# XML report (for CI)
coverage xml
```

### Coverage Exclusions

Add coverage pragmas for untestable code:

```python
def debug_only_function():  # pragma: no cover
    """This function is only used in debug mode."""
    pass

if __name__ == "__main__":  # pragma: no cover
    # Script entry point
    main()
```

## 🔧 Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure you're in the project root
   cd /path/to/mcp-gateway-registry
   
   # Install in development mode
   pip install -e .[dev]
   ```

2. **Async Test Issues**
   ```python
   # Always mark async tests
   @pytest.mark.asyncio
   async def test_async_function():
       pass
   ```

3. **Fixture Not Found**
   ```python
   # Check fixture is in conftest.py or imported properly
   # Ensure correct scope (function, class, module, session)
   ```

4. **Coverage Not Working**
   ```bash
   # Ensure pytest-cov is installed
   pip install pytest-cov
   
   # Check coverage configuration in pyproject.toml
   ```

## 📚 Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Factory Boy Documentation](https://factoryboy.readthedocs.io/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)
- [FastAPI Testing Guide](https://fastapi.tiangolo.com/tutorial/testing/)

## 🎯 Testing Checklist

Before submitting code:

- [ ] All tests pass locally (`make test`)
- [ ] Coverage is above 80% (`make test-coverage`)
- [ ] New functionality has tests
- [ ] Tests are properly marked with domains
- [ ] No security issues (`make lint`)
- [ ] Fast feedback tests pass (`make test-fast`)

---

**Happy Testing! 🧪✨** 