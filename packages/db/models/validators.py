"""Field validators for model fields."""

import re
from abc import ABC, abstractmethod
from typing import Any, Optional


class FieldValidator(ABC):
    """Base class for field validators."""
    
    @abstractmethod
    def validate(self, value: Any) -> bool:
        pass
    
    @abstractmethod
    def get_error_message(self, value: Any) -> str:
        pass


class RequiredValidator(FieldValidator):
    """Validates that value is not None."""
    
    def validate(self, value: Any) -> bool:
        return value is not None
    
    def get_error_message(self, value: Any) -> str:
        return "This field is required"


class MaxLengthValidator(FieldValidator):
    """Validates maximum string length."""
    
    def __init__(self, max_length: int):
        self.max_length = max_length
    
    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        return len(str(value)) <= self.max_length
    
    def get_error_message(self, value: Any) -> str:
        actual_length = len(str(value)) if value is not None else 0
        return f"Value exceeds maximum length of {self.max_length} (got {actual_length})"


class MinLengthValidator(FieldValidator):
    """Validates minimum string length."""
    
    def __init__(self, min_length: int):
        self.min_length = min_length
    
    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        return len(str(value)) >= self.min_length
    
    def get_error_message(self, value: Any) -> str:
        actual_length = len(str(value)) if value is not None else 0
        return f"Value must be at least {self.min_length} characters (got {actual_length})"


class RangeValidator(FieldValidator):
    """Validates numeric value is within range."""
    
    def __init__(self, min_value: Optional[float] = None, max_value: Optional[float] = None):
        self.min_value = min_value
        self.max_value = max_value
    
    def validate(self, value: Any) -> bool:
        if value is None:
            return True
        
        try:
            num_value = float(value)
            if self.min_value is not None and num_value < self.min_value:
                return False
            if self.max_value is not None and num_value > self.max_value:
                return False
            return True
        except (TypeError, ValueError):
            return False
    
    def get_error_message(self, value: Any) -> str:
        if self.min_value is not None and self.max_value is not None:
            return f"Value must be between {self.min_value} and {self.max_value}"
        elif self.min_value is not None:
            return f"Value must be at least {self.min_value}"
        elif self.max_value is not None:
            return f"Value must be at most {self.max_value}"
        else:
            return "Invalid numeric value"
