"""
Model definitions and field types for ORM.
"""

from .base import (
    Field, TextField, IntField, FloatField, BooleanField,
    DateTimeField, UUIDField, TextArrayField, IntArrayField,
    FieldConfig, ModelMeta
)
from .model import Model
from .descriptors import ObjectManagerDescriptor
from .validators import (
    FieldValidator,
    RequiredValidator,
    MaxLengthValidator,
    MinLengthValidator,
    RangeValidator,
    PatternValidator,
    ChoicesValidator,
    EmailValidator,
    URLValidator
)
from .converters import (
    FieldConverter,
    DateTimeConverter,
    JSONConverter,
    EnumConverter,
    BoolConverter
)

__all__ = [
    # Model base class
    'Model',
    
    # Field types
    'Field',
    'TextField',
    'IntField',
    'FloatField',
    'BooleanField',
    'DateTimeField',
    'UUIDField',
    'TextArrayField',
    'IntArrayField',
    
    # Metaclass and config
    'FieldConfig',
    'ModelMeta',
    
    # Descriptors
    'ObjectManagerDescriptor',
    
    # Validators
    'FieldValidator',
    'RequiredValidator',
    'MaxLengthValidator',
    'MinLengthValidator',
    'RangeValidator',
    'PatternValidator',
    'ChoicesValidator',
    'EmailValidator',
    'URLValidator',
    
    # Converters
    'FieldConverter',
    'DateTimeConverter',
    'JSONConverter',
    'EnumConverter',
    'BoolConverter',
]

