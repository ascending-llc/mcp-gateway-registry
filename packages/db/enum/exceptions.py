from langchain_core.exceptions import LangChainException


class DependencyMissingError(LangChainException):
    """
    Raised when a required dependency package is missing.
    
    This exception provides clear guidance on which package to install.
    """

    def __init__(self, package_name: str, message: str = None):
        if message is None:
            message = f"Required package '{package_name}' is not installed. " \
                      f"Please install it with: pip install {package_name}"
        super().__init__(message)
        self.package_name = package_name


class UnsupportedBackendError(LangChainException):
    """
    Raised when an unsupported database backend is requested.
    
    This exception provides information about supported backends.
    """

    def __init__(self, backend_name: str, supported_backends: list = None):
        if supported_backends is None:
            from .enums import VectorStoreType
            supported_backends = [e.value for e in VectorStoreType]

        message = f"Unsupported database backend: '{backend_name}'. " \
                  f"Supported backends: {', '.join(supported_backends)}"
        super().__init__(message)
        self.backend_name = backend_name
        self.supported_backends = supported_backends


class ConfigurationError(LangChainException):
    """
    Raised when there is a configuration error.
    
    This exception indicates issues with the global or model configuration.
    """

    def __init__(self, message: str):
        super().__init__(f"Configuration error: {message}")


# Reuse existing exceptions from the current codebase
# These exceptions are already defined and used in the existing code

class DoesNotExist(Exception):
    """
    Raised when an object does not exist in the database.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, model_name: str, lookup_params: dict):
        self.model_name = model_name
        self.lookup_params = lookup_params
        message = f"{model_name} matching query does not exist. Lookup: {lookup_params}"
        super().__init__(message)


class MultipleObjectsReturned(Exception):
    """
    Raised when multiple objects are returned but only one was expected.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, model_name: str, count: int, lookup_params: dict):
        self.model_name = model_name
        self.count = count
        self.lookup_params = lookup_params
        message = f"Multiple ({count}) {model_name} objects returned. Lookup: {lookup_params}"
        super().__init__(message)


class InsertFailed(Exception):
    """
    Raised when an insert operation fails.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, collection_name: str, error_message: str):
        self.collection_name = collection_name
        self.error_message = error_message
        message = f"Failed to insert into collection '{collection_name}': {error_message}"
        super().__init__(message)


class ConnectionException(Exception):
    """
    Raised when a database connection fails.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, host: str, port: int, error_message: str):
        self.host = host
        self.port = port
        self.error_message = error_message
        message = f"Connection to {host}:{port} failed: {error_message}"
        super().__init__(message)


class WeaviateORMException(Exception):
    """
    Base exception for Weaviate ORM errors.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, message: str):
        super().__init__(message)


class ConfigurationException(Exception):
    """
    Raised when there is a configuration error.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, message: str):
        super().__init__(f"Configuration error: {message}")


class QueryException(Exception):
    """
    Raised when a query operation fails.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, message: str):
        super().__init__(f"Query error: {message}")


class ValidationException(Exception):
    """
    Raised when data validation fails.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, message: str):
        super().__init__(f"Validation error: {message}")


class FieldValidationError(Exception):
    """
    Raised when a specific field validation fails.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, field_name: str, error_message: str):
        self.field_name = field_name
        self.error_message = error_message
        message = f"Field '{field_name}' validation failed: {error_message}"
        super().__init__(message)


class CollectionException(Exception):
    """
    Raised when a collection operation fails.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, message: str):
        super().__init__(f"Collection error: {message}")


class CollectionNotFound(Exception):
    """
    Raised when a collection is not found.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        message = f"Collection '{collection_name}' not found"
        super().__init__(message)


class DataOperationException(Exception):
    """
    Raised when a data operation fails.
    
    This exception is kept for backward compatibility with existing code.
    """

    def __init__(self, message: str):
        super().__init__(f"Data operation error: {message}")
