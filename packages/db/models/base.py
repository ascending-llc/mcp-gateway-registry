from weaviate.classes.config import DataType, Property, Configure, VectorDistances, Tokenization
from typing import Any, Dict, List, Optional, Union, ClassVar
from dataclasses import dataclass, field

from .validators import FieldValidator, RequiredValidator
from .converters import FieldConverter
from ..core.exceptions import FieldValidationError


@dataclass
class FieldConfig:
    """Field configuration data class."""
    data_type: DataType
    name: Optional[str] = None
    description: Optional[str] = None
    required: bool = False
    index_filterable: bool = True
    index_searchable: bool = True
    tokenization: Optional[str] = None
    nested_properties: Optional[List['Property']] = None
    skip_vectorization: bool = False
    vectorize_property_name: bool = False


class Field:
    """
    Base field class with validation and conversion support.
    
    Provides:
    - Validation through pluggable validators
    - Type conversion through converters
    - Clean Weaviate property generation
    """

    def __init__(
        self,
                 data_type: DataType,
        required: bool = False,
        default: Any = None,
                 description: Optional[str] = None,
        validators: Optional[List[FieldValidator]] = None,
        converter: Optional[FieldConverter] = None,
        # Weaviate-specific options
                 index_filterable: bool = True,
                 index_searchable: bool = True,
                 tokenization: Optional[str] = None,
                 skip_vectorization: bool = False,
        vectorize_property_name: bool = False,
        nested_properties: Optional[List[Property]] = None
    ):
        """
        Initialize field.
        
        Args:
            data_type: Weaviate data type
            required: Whether field is required
            default: Default value
            description: Field description
            validators: List of validators to apply
            converter: Converter for type conversion
            index_filterable: Whether field is filterable
            index_searchable: Whether field is searchable
            tokenization: Tokenization strategy
            skip_vectorization: Skip vectorization for this field
            vectorize_property_name: Include field name in vectorization
            nested_properties: Nested properties (for object types)
        """
        self.config = FieldConfig(
            data_type=data_type,
            description=description,
            required=required,
            index_filterable=index_filterable,
            index_searchable=index_searchable,
            tokenization=tokenization,
            nested_properties=nested_properties,
            skip_vectorization=skip_vectorization,
            vectorize_property_name=vectorize_property_name
        )
        
        self.default = default
        self.validators = validators or []
        self.converter = converter
        self.attname = None  # Set during model initialization
        
        # Auto-add required validator if field is required
        if required and not any(isinstance(v, RequiredValidator) for v in self.validators):
            self.validators.insert(0, RequiredValidator())

    def contribute_to_class(self, cls, name):
        """Add field to model class."""
        self.attname = name
        self.model = cls

    def validate(self, value: Any) -> None:
        """
        Validate field value.
        
        Args:
            value: Value to validate
        
        Raises:
            FieldValidationError: If validation fails
        """
        for validator in self.validators:
            if not validator.validate(value):
                raise FieldValidationError(
                    self.attname,
                    value,
                    validator.get_error_message(value)
                )
    
    def to_python(self, value: Any) -> Any:
        """
        Convert from Weaviate format to Python type.
        
        Args:
            value: Value from Weaviate
        
        Returns:
            Converted Python value
        """
        if self.converter:
            return self.converter.to_python(value)
        return value
    
    def to_weaviate(self, value: Any) -> Any:
        """
        Convert from Python type to Weaviate format.
        
        Args:
            value: Python value
        
        Returns:
            Weaviate-compatible value
        """
        if self.converter:
            return self.converter.to_weaviate(value)
        return value

    def to_weaviate_property(self) -> Property:
        """Convert to Weaviate Property object."""
        # Handle tokenization configuration
        tokenization_config = None
        if self.config.tokenization:
            tokenization_map = {
                "word": Tokenization.WORD,
                "field": Tokenization.FIELD,
                "whitespace": Tokenization.WHITESPACE,
                "lowercase": Tokenization.LOWERCASE
            }
            tokenization_config = tokenization_map.get(self.config.tokenization)

        # Ensure field name is valid
        if not self.attname:
            raise ValueError(f"Field name not set for field")

        return Property(
            name=self.attname,
            data_type=self.config.data_type,
            description=self.config.description,
            index_filterable=self.config.index_filterable,
            index_searchable=self.config.index_searchable,
            tokenization=tokenization_config,
            nested_properties=self.config.nested_properties
        )


class TextField(Field):
    """
    Text field with optional validation.
    
    Args:
        required: Whether field is required
        max_length: Maximum string length
        min_length: Minimum string length
        description: Field description
        tokenization: Tokenization strategy (word, field, whitespace, lowercase)
        index_searchable: Whether field should be searchable (default: True)
        **kwargs: Additional Field arguments
    """

    def __init__(
        self,
        required: bool = False,
        max_length: Optional[int] = None,
        min_length: Optional[int] = None,
        description: Optional[str] = None,
        tokenization: str = "word",
        index_searchable: bool = True,
        **kwargs
    ):
        # Build validators
        validators = kwargs.pop('validators', [])
        
        if max_length:
            from .validators import MaxLengthValidator
            validators.append(MaxLengthValidator(max_length))
        
        if min_length:
            from .validators import MinLengthValidator
            validators.append(MinLengthValidator(min_length))
        
        super().__init__(
            data_type=DataType.TEXT,
            required=required,
            description=description,
            validators=validators,
            index_searchable=index_searchable,
            tokenization=tokenization,
            **kwargs
        )


class IntField(Field):
    """
    Integer field with optional range validation.
    
    Args:
        required: Whether field is required
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        description: Field description
        **kwargs: Additional Field arguments
    """

    def __init__(
        self,
        required: bool = False,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
                 description: Optional[str] = None,
        **kwargs
    ):
        validators = kwargs.pop('validators', [])
        
        if min_value is not None or max_value is not None:
            from .validators import RangeValidator
            validators.append(RangeValidator(min_value, max_value))
        
        super().__init__(
            data_type=DataType.INT,
            required=required,
            description=description,
            validators=validators,
            index_searchable=False,
            skip_vectorization=True,
            **kwargs
        )


class FloatField(Field):
    """
    Float field with optional range validation.
    
    Args:
        required: Whether field is required
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        description: Field description
        **kwargs: Additional Field arguments
    """

    def __init__(
        self,
        required: bool = False,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
                 description: Optional[str] = None,
        **kwargs
    ):
        validators = kwargs.pop('validators', [])
        
        if min_value is not None or max_value is not None:
            from .validators import RangeValidator
            validators.append(RangeValidator(min_value, max_value))
        
        super().__init__(
            data_type=DataType.NUMBER,
            required=required,
            description=description,
            validators=validators,
            index_searchable=False,
            skip_vectorization=True,
            **kwargs
        )


class BooleanField(Field):
    """
    Boolean field with automatic conversion.
    
    Handles string representations like "true", "false", "1", "0".
    """

    def __init__(
        self,
        required: bool = False,
                 description: Optional[str] = None,
        **kwargs
    ):
        from .converters import BoolConverter
        
        super().__init__(
            data_type=DataType.BOOL,
            required=required,
            description=description,
            converter=BoolConverter(),
            index_searchable=False,
            skip_vectorization=True,
            **kwargs
        )


class DateTimeField(Field):
    """
    DateTime field with automatic ISO format conversion.
    
    Converts between Python datetime and ISO 8601 string.
    """

    def __init__(
        self,
        required: bool = False,
                 description: Optional[str] = None,
        **kwargs
    ):
        from .converters import DateTimeConverter
        
        super().__init__(
            data_type=DataType.DATE,
            required=required,
            description=description,
            converter=DateTimeConverter(),
            index_searchable=False,
            skip_vectorization=True,
            **kwargs
        )


class UUIDField(Field):
    """UUID field."""

    def __init__(
        self,
        required: bool = False,
                 description: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            data_type=DataType.UUID,
            required=required,
            description=description,
            index_searchable=False,
            skip_vectorization=True,
            **kwargs
        )


class TextArrayField(Field):
    """Text array field."""

    def __init__(
        self,
        required: bool = False,
        description: Optional[str] = None,
        tokenization: str = "word",
        index_searchable: bool = True,
        **kwargs
    ):
        super().__init__(
            data_type=DataType.TEXT_ARRAY,
            required=required,
            description=description,
            index_searchable=index_searchable,
            tokenization=tokenization,
            **kwargs
        )


class IntArrayField(Field):
    """Integer array field."""

    def __init__(
        self,
        required: bool = False,
                 description: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            data_type=DataType.INT_ARRAY,
            required=required,
            description=description,
            index_searchable=False,
            skip_vectorization=True,
            **kwargs
        )


class ModelMeta(type):
    """
    Model metaclass for collecting field definitions.
    
    Performance optimized: Uses descriptor for objects manager instead of
    __getattribute__ to avoid overhead on every attribute access.
    """

    def __new__(cls, name, bases, attrs):
        # Skip the Model base class itself
        if name == 'Model':
            return super().__new__(cls, name, bases, attrs)

        # Collect fields
        fields = {}
        for attr_name, attr_value in list(attrs.items()):
            if isinstance(attr_value, Field):
                # Set the field's attribute name
                attr_value.contribute_to_class(None, attr_name)
                fields[attr_name] = attr_value
                # Remove field from class attributes, will be set in instances
                del attrs[attr_name]

        attrs['_fields'] = fields

        # Handle Meta class configuration
        meta = attrs.pop('Meta', None)
        attrs['_meta'] = meta

        # Create the new class
        new_class = super().__new__(cls, name, bases, attrs)
        
        # Use descriptor for lazy ObjectManager initialization
        # This avoids __getattribute__ overhead (10-50x performance improvement)
        from .descriptors import ObjectManagerDescriptor
        new_class.objects = ObjectManagerDescriptor(new_class)

        return new_class
