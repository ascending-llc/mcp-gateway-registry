"""
Vector Database Exceptions

Custom exceptions for vector database operations.
"""

class VectorDatabaseError(Exception):
    """Base exception for vector database operations."""


class RepositoryError(VectorDatabaseError):
    """Exception raised by Repository operations."""


class AdapterError(VectorDatabaseError):
    """Exception raised by VectorStoreAdapter operations."""


class ConfigurationError(VectorDatabaseError):
    """Exception raised for configuration errors."""


class ValidationError(VectorDatabaseError):
    """Exception raised for validation errors."""
