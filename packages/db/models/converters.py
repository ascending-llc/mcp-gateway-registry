"""Field converters for type conversion."""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class FieldConverter(ABC):
    """Base class for field converters."""
    
    @abstractmethod
    def to_python(self, value: Any) -> Any:
        pass
    
    @abstractmethod
    def to_weaviate(self, value: Any) -> Any:
        pass


class DateTimeConverter(FieldConverter):
    """Converter for datetime fields."""
    
    def to_python(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return value
        return value
    
    def to_weaviate(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                from datetime import timezone
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()
        return value


class BoolConverter(FieldConverter):
    """Converter for boolean fields."""
    
    def to_python(self, value: Any) -> Any:
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
        if value is None:
            return None
        return bool(value)
