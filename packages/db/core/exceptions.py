"""Exception hierarchy for the Weaviate ORM framework."""

from typing import Any, Dict, Optional


class WeaviateORMException(Exception):
    """Base exception for all ORM-related errors."""
    pass


class ConnectionException(WeaviateORMException):
    """Connection-related errors."""
    
    def __init__(self, host: str, port: int, reason: str):
        self.host = host
        self.port = port
        self.reason = reason
        super().__init__(f"Connection to {host}:{port} failed: {reason}")


class ConfigurationException(WeaviateORMException):
    """Configuration-related errors."""
    
    def __init__(self, message: str):
        super().__init__(message)


class QueryException(WeaviateORMException):
    """Query-related errors."""
    pass


class DoesNotExist(QueryException):
    """Object matching the query does not exist."""
    
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
    """Multiple objects returned but only one was expected."""
    
    def __init__(self, model_name: str, count: int, filters: Optional[Dict] = None):
        self.model_name = model_name
        self.count = count
        self.filters = filters or {}
        
        filter_info = f" with filters {filters}" if filters else ""
        super().__init__(f"Expected 1 {model_name}{filter_info}, got {count} objects")


class ValidationException(WeaviateORMException):
    """Validation errors."""
    pass


class FieldValidationError(ValidationException):
    """Field validation failed."""
    
    def __init__(self, field_name: str, value: Any, reason: str):
        self.field_name = field_name
        self.value = value
        self.reason = reason
        super().__init__(f"Validation failed for field '{field_name}': {reason}")


class CollectionException(WeaviateORMException):
    """Collection-related errors."""
    pass


class CollectionNotFound(CollectionException):
    """Collection does not exist."""
    
    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        super().__init__(f"Collection '{collection_name}' not found")


class DataOperationException(WeaviateORMException):
    """Data operation errors."""
    pass


class InsertFailed(DataOperationException):
    """Data insertion failed."""
    
    def __init__(self, collection_name: str, reason: str):
        self.collection_name = collection_name
        self.reason = reason
        super().__init__(f"Failed to insert into '{collection_name}': {reason}")
