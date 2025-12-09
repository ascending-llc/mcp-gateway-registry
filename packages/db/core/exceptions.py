"""
Exception hierarchy for the Weaviate ORM framework.

Provides a comprehensive set of exceptions with context information
for better error handling and debugging.
"""

from typing import Any, Dict, Optional


# ============================================================================
# Base Exception
# ============================================================================

class WeaviateORMException(Exception):
    """Base exception for all ORM-related errors."""
    pass


# ============================================================================
# Connection Exceptions
# ============================================================================

class ConnectionException(WeaviateORMException):
    """Base exception for connection-related errors."""
    pass


class ConnectionTimeout(ConnectionException):
    """Raised when connection to Weaviate times out."""
    
    def __init__(self, host: str, port: int, timeout: float):
        self.host = host
        self.port = port
        self.timeout = timeout
        super().__init__(
            f"Connection to {host}:{port} timed out after {timeout}s"
        )


class ConnectionFailed(ConnectionException):
    """Raised when connection to Weaviate fails."""
    
    def __init__(self, host: str, port: int, reason: str):
        self.host = host
        self.port = port
        self.reason = reason
        super().__init__(
            f"Failed to connect to {host}:{port}: {reason}"
        )


# ============================================================================
# Configuration Exceptions
# ============================================================================

class ConfigurationException(WeaviateORMException):
    """Base exception for configuration-related errors."""
    pass


class InvalidProvider(ConfigurationException):
    """Raised when an invalid embeddings provider is specified."""
    
    def __init__(self, provider: str, available: list):
        self.provider = provider
        self.available = available
        super().__init__(
            f"Invalid provider '{provider}'. Available: {', '.join(available)}"
        )


class MissingCredentials(ConfigurationException):
    """Raised when required credentials are missing."""
    
    def __init__(self, provider: str, missing_keys: list):
        self.provider = provider
        self.missing_keys = missing_keys
        super().__init__(
            f"Missing credentials for {provider}: {', '.join(missing_keys)}"
        )


class InvalidConfiguration(ConfigurationException):
    """Raised when configuration is invalid."""
    
    def __init__(self, message: str):
        super().__init__(f"Invalid configuration: {message}")


# ============================================================================
# Query Exceptions
# ============================================================================

class QueryException(WeaviateORMException):
    """Base exception for query-related errors."""
    pass


class DoesNotExist(QueryException):
    """Raised when an object matching the query does not exist."""
    
    def __init__(self, model_name: str, filters: Optional[Dict] = None):
        self.model_name = model_name
        self.filters = filters or {}
        
        if filters:
            filter_str = ", ".join(f"{k}={v}" for k, v in filters.items())
            message = f"{model_name} matching ({filter_str}) does not exist"
        else:
            message = f"{model_name} does not exist"
        
        super().__init__(message)


class MultipleObjectsReturned(QueryException):
    """Raised when multiple objects are returned but only one was expected."""
    
    def __init__(self, model_name: str, count: int, filters: Optional[Dict] = None):
        self.model_name = model_name
        self.count = count
        self.filters = filters or {}
        
        filter_info = f" with filters {filters}" if filters else ""
        super().__init__(
            f"Expected 1 {model_name}{filter_info}, got {count} objects"
        )


class InvalidQuery(QueryException):
    """Raised when a query is malformed or invalid."""
    
    def __init__(self, reason: str):
        super().__init__(f"Invalid query: {reason}")


# ============================================================================
# Validation Exceptions
# ============================================================================

class ValidationException(WeaviateORMException):
    """Base exception for validation errors."""
    pass


class FieldValidationError(ValidationException):
    """Raised when field validation fails."""
    
    def __init__(self, field_name: str, value: Any, reason: str):
        self.field_name = field_name
        self.value = value
        self.reason = reason
        super().__init__(
            f"Validation failed for field '{field_name}': {reason}"
        )


class RequiredFieldMissing(ValidationException):
    """Raised when a required field is missing."""
    
    def __init__(self, field_name: str, model_name: str):
        self.field_name = field_name
        self.model_name = model_name
        super().__init__(
            f"Required field '{field_name}' missing in {model_name}"
        )


class ModelValidationError(ValidationException):
    """Raised when model-level validation fails."""
    
    def __init__(self, model_name: str, errors: Dict[str, str]):
        self.model_name = model_name
        self.errors = errors
        error_details = ", ".join(f"{k}: {v}" for k, v in errors.items())
        super().__init__(
            f"Validation failed for {model_name}: {error_details}"
        )


# ============================================================================
# Collection Exceptions
# ============================================================================

class CollectionException(WeaviateORMException):
    """Base exception for collection-related errors."""
    pass


class CollectionNotFound(CollectionException):
    """Raised when a collection does not exist."""
    
    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        super().__init__(f"Collection '{collection_name}' not found")


class CollectionAlreadyExists(CollectionException):
    """Raised when trying to create a collection that already exists."""
    
    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        super().__init__(f"Collection '{collection_name}' already exists")


class CollectionCreationFailed(CollectionException):
    """Raised when collection creation fails."""
    
    def __init__(self, collection_name: str, reason: str):
        self.collection_name = collection_name
        self.reason = reason
        super().__init__(
            f"Failed to create collection '{collection_name}': {reason}"
        )


# ============================================================================
# Data Operation Exceptions
# ============================================================================

class DataOperationException(WeaviateORMException):
    """Base exception for data operation errors."""
    pass


class InsertFailed(DataOperationException):
    """Raised when data insertion fails."""
    
    def __init__(self, collection_name: str, reason: str):
        self.collection_name = collection_name
        self.reason = reason
        super().__init__(
            f"Failed to insert into '{collection_name}': {reason}"
        )


class UpdateFailed(DataOperationException):
    """Raised when data update fails."""
    
    def __init__(self, collection_name: str, object_id: str, reason: str):
        self.collection_name = collection_name
        self.object_id = object_id
        self.reason = reason
        super().__init__(
            f"Failed to update {collection_name}/{object_id}: {reason}"
        )


class DeleteFailed(DataOperationException):
    """Raised when data deletion fails."""
    
    def __init__(self, collection_name: str, object_id: str, reason: str):
        self.collection_name = collection_name
        self.object_id = object_id
        self.reason = reason
        super().__init__(
            f"Failed to delete {collection_name}/{object_id}: {reason}"
        )
