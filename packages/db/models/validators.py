"""
Field validators for model fields.

Provides extensible validation system for field values.
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Optional


class FieldValidator(ABC):
    """
    Base class for field validators.
    
    Validators check if a value is valid according to specific rules.
    They can be chained and reused across different fields.
    """
    
    @abstractmethod
    def validate(self, value: Any) -> bool:
        """
        Validate the value.
        
        Args:
            value: Value to validate
        
        Returns:
            True if valid, False otherwise
        """
        pass
    
    @abstractmethod
    def get_error_message(self, value: Any) -> str:
        """
        Get error message for invalid value.
        
        Args:
            value: The invalid value
        
        Returns:
            Human-readable error message
        """
        pass


class RequiredValidator(FieldValidator):
    """Validates that value is not None."""
    
    def validate(self, value: Any) -> bool:
        """Check if value is not None."""
        return value is not None
    
    def get_error_message(self, value: Any) -> str:
        """Get error message."""
        return "This field is required and cannot be None"


class MaxLengthValidator(FieldValidator):
    """Validates maximum string length."""
    
    def __init__(self, max_length: int):
        """
        Initialize validator.
        
        Args:
            max_length: Maximum allowed length
        """
        self.max_length = max_length
    
    def validate(self, value: Any) -> bool:
        """Check if value length is within limit."""
        if value is None:
            return True  # None is valid (use RequiredValidator for non-null check)
        return len(str(value)) <= self.max_length
    
    def get_error_message(self, value: Any) -> str:
        """Get error message."""
        actual_length = len(str(value)) if value is not None else 0
        return f"Value exceeds maximum length of {self.max_length} (got {actual_length})"


class MinLengthValidator(FieldValidator):
    """Validates minimum string length."""
    
    def __init__(self, min_length: int):
        """
        Initialize validator.
        
        Args:
            min_length: Minimum required length
        """
        self.min_length = min_length
    
    def validate(self, value: Any) -> bool:
        """Check if value length meets minimum."""
        if value is None:
            return True
        return len(str(value)) >= self.min_length
    
    def get_error_message(self, value: Any) -> str:
        """Get error message."""
        actual_length = len(str(value)) if value is not None else 0
        return f"Value must be at least {self.min_length} characters (got {actual_length})"


class RangeValidator(FieldValidator):
    """Validates numeric value is within range."""
    
    def __init__(
        self,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None
    ):
        """
        Initialize validator.
        
        Args:
            min_value: Minimum allowed value (inclusive)
            max_value: Maximum allowed value (inclusive)
        """
        self.min_value = min_value
        self.max_value = max_value
    
    def validate(self, value: Any) -> bool:
        """Check if value is within range."""
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
        """Get error message."""
        if self.min_value is not None and self.max_value is not None:
            return f"Value must be between {self.min_value} and {self.max_value}"
        elif self.min_value is not None:
            return f"Value must be at least {self.min_value}"
        elif self.max_value is not None:
            return f"Value must be at most {self.max_value}"
        else:
            return "Invalid numeric value"


class PatternValidator(FieldValidator):
    """Validates value matches a regex pattern."""
    
    def __init__(self, pattern: str, flags: int = 0):
        """
        Initialize validator.
        
        Args:
            pattern: Regular expression pattern
            flags: Regex flags (e.g., re.IGNORECASE)
        """
        self.pattern = pattern
        self.regex = re.compile(pattern, flags)
    
    def validate(self, value: Any) -> bool:
        """Check if value matches pattern."""
        if value is None:
            return True
        return self.regex.match(str(value)) is not None
    
    def get_error_message(self, value: Any) -> str:
        """Get error message."""
        return f"Value does not match required pattern: {self.pattern}"


class ChoicesValidator(FieldValidator):
    """Validates value is one of allowed choices."""
    
    def __init__(self, choices: list):
        """
        Initialize validator.
        
        Args:
            choices: List of allowed values
        """
        self.choices = choices
    
    def validate(self, value: Any) -> bool:
        """Check if value is in choices."""
        if value is None:
            return True
        return value in self.choices
    
    def get_error_message(self, value: Any) -> str:
        """Get error message."""
        choices_str = ", ".join(str(c) for c in self.choices)
        return f"Value must be one of: {choices_str}"


class EmailValidator(FieldValidator):
    """Validates email address format."""
    
    # Simple email regex
    EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    def __init__(self):
        """Initialize validator."""
        self.regex = re.compile(self.EMAIL_REGEX)
    
    def validate(self, value: Any) -> bool:
        """Check if value is valid email."""
        if value is None:
            return True
        return self.regex.match(str(value)) is not None
    
    def get_error_message(self, value: Any) -> str:
        """Get error message."""
        return "Invalid email address format"


class URLValidator(FieldValidator):
    """Validates URL format."""
    
    # Simple URL regex
    URL_REGEX = r'^https?://[^\s<>"]+$'
    
    def __init__(self):
        """Initialize validator."""
        self.regex = re.compile(self.URL_REGEX)
    
    def validate(self, value: Any) -> bool:
        """Check if value is valid URL."""
        if value is None:
            return True
        return self.regex.match(str(value)) is not None
    
    def get_error_message(self, value: Any) -> str:
        """Get error message."""
        return "Invalid URL format"

