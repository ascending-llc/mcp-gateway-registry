"""
Field converters for type conversion.

Handles conversion between Python types and Weaviate storage format.
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from enum import Enum


class FieldConverter(ABC):
    """
    Base class for field converters.
    
    Converters handle bidirectional conversion between Python types
    and Weaviate storage format.
    """
    
    @abstractmethod
    def to_python(self, value: Any) -> Any:
        """
        Convert from Weaviate format to Python type.
        
        Args:
            value: Value from Weaviate
        
        Returns:
            Python-typed value
        """
        pass
    
    @abstractmethod
    def to_weaviate(self, value: Any) -> Any:
        """
        Convert from Python type to Weaviate format.
        
        Args:
            value: Python value
        
        Returns:
            Weaviate-compatible value
        """
        pass


class DateTimeConverter(FieldConverter):
    """
    Converter for datetime fields.
    
    Converts between Python datetime and ISO 8601 string format.
    """
    
    def to_python(self, value: Any) -> Any:
        """Convert ISO string to datetime."""
        if value is None:
            return None
        
        if isinstance(value, datetime):
            return value
        
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                # Return as-is if not valid ISO format
                return value
        
        return value
    
    def to_weaviate(self, value: Any) -> Any:
        """
        Convert datetime to RFC3339 format string.
        
        Weaviate requires RFC3339 format (ISO 8601 with timezone).
        """
        if value is None:
            return None
        
        if isinstance(value, datetime):
            # Ensure RFC3339 format with timezone
            if value.tzinfo is None:
                # Add UTC timezone if naive datetime
                from datetime import timezone
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()
        
        return value


class JSONConverter(FieldConverter):
    """
    Converter for JSON fields.
    
    Converts between Python dict/list and JSON string.
    """
    
    def to_python(self, value: Any) -> Any:
        """Parse JSON string to Python object."""
        if value is None:
            return None
        
        if isinstance(value, (dict, list)):
            return value
        
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        
        return value
    
    def to_weaviate(self, value: Any) -> Any:
        """Convert Python object to JSON string."""
        if value is None:
            return None
        
        if isinstance(value, str):
            return value
        
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        
        return value


class EnumConverter(FieldConverter):
    """
    Converter for Enum fields.
    
    Converts between Python Enum and string value.
    """
    
    def __init__(self, enum_class: type):
        """
        Initialize converter.
        
        Args:
            enum_class: The Enum class to convert to/from
        """
        if not issubclass(enum_class, Enum):
            raise TypeError(f"{enum_class} is not an Enum")
        
        self.enum_class = enum_class
    
    def to_python(self, value: Any) -> Any:
        """Convert string to Enum."""
        if value is None:
            return None
        
        if isinstance(value, self.enum_class):
            return value
        
        if isinstance(value, str):
            try:
                return self.enum_class(value)
            except ValueError:
                # Try by name
                try:
                    return self.enum_class[value]
                except KeyError:
                    return value
        
        return value
    
    def to_weaviate(self, value: Any) -> Any:
        """Convert Enum to string."""
        if value is None:
            return None
        
        if isinstance(value, Enum):
            return value.value
        
        return value


class BoolConverter(FieldConverter):
    """
    Converter for boolean fields.
    
    Handles string representations like "true", "false", "1", "0".
    """
    
    def to_python(self, value: Any) -> Any:
        """Convert to boolean."""
        if value is None:
            return None
        
        if isinstance(value, bool):
            return value
        
        if isinstance(value, str):
            lower_value = value.lower()
            if lower_value in ('true', '1', 'yes', 'y'):
                return True
            if lower_value in ('false', '0', 'no', 'n'):
                return False
        
        return bool(value)
    
    def to_weaviate(self, value: Any) -> Any:
        """Convert to boolean."""
        if value is None:
            return None
        return bool(value)

