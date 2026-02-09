"""
Vector Database Exceptions

Custom exceptions for vector database operations.
"""


class VectorDatabaseError(Exception):
    """Base exception for vector database operations."""

    pass


class RepositoryError(VectorDatabaseError):
    """Exception raised by Repository operations."""

    pass


class AdapterError(VectorDatabaseError):
    """Exception raised by VectorStoreAdapter operations."""

    pass


class ConfigurationError(VectorDatabaseError):
    """Exception raised for configuration errors."""

    pass


class ValidationError(VectorDatabaseError):
    """Exception raised for validation errors."""

    pass
