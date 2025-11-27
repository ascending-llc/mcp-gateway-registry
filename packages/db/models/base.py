from weaviate.classes.config import DataType, Property, Configure, VectorDistances, Tokenization
from typing import Any, Dict, List, Optional, Union, ClassVar
from dataclasses import dataclass, field


@dataclass
class FieldConfig:
    """Base class for field configuration"""
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
    """Base class for field"""

    def __init__(self,
                 data_type: DataType,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 required: bool = False,
                 index_filterable: bool = True,
                 index_searchable: bool = True,
                 tokenization: Optional[str] = None,
                 nested_properties: Optional[List[Property]] = None,
                 skip_vectorization: bool = False,
                 vectorize_property_name: bool = False):
        self.config = FieldConfig(
            data_type=data_type,
            name=name,
            description=description,
            required=required,
            index_filterable=index_filterable,
            index_searchable=index_searchable,
            tokenization=tokenization,
            nested_properties=nested_properties,
            skip_vectorization=skip_vectorization,
            vectorize_property_name=vectorize_property_name
        )
        self.attname = None  # Will be set during model initialization

    def contribute_to_class(self, cls, name):
        """Add field to model class"""
        self.attname = name
        self.model = cls

    def to_weaviate_property(self) -> Property:
        """Convert to Weaviate Property object"""
        # Handle tokenization configuration
        tokenization_config = None
        if self.config.tokenization:
            if self.config.tokenization == "word":
                tokenization_config = Tokenization.WORD
            elif self.config.tokenization == "field":
                tokenization_config = Tokenization.FIELD
            elif self.config.tokenization == "whitespace":
                tokenization_config = Tokenization.WHITESPACE
            elif self.config.tokenization == "lowercase":
                tokenization_config = Tokenization.LOWERCASE

        # Ensure field name is valid
        if not self.attname:
            raise ValueError(f"Field name is not set for field: {self}")

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
    """Text field"""

    def __init__(self,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 required: bool = False,
                 index_filterable: bool = True,
                 index_searchable: bool = True,
                 tokenization: str = "word",
                 skip_vectorization: bool = False,
                 vectorize_property_name: bool = False):
        super().__init__(
            data_type=DataType.TEXT,
            name=name,
            description=description,
            required=required,
            index_filterable=index_filterable,
            index_searchable=index_searchable,
            tokenization=tokenization,
            skip_vectorization=skip_vectorization,
            vectorize_property_name=vectorize_property_name
        )


class IntField(Field):
    """Integer field"""

    def __init__(self,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 required: bool = False,
                 index_filterable: bool = True):
        super().__init__(
            data_type=DataType.INT,
            name=name,
            description=description,
            required=required,
            index_filterable=index_filterable,
            index_searchable=False,  # Integers are typically not searchable
            skip_vectorization=True
        )


class FloatField(Field):
    """Float field"""

    def __init__(self,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 required: bool = False,
                 index_filterable: bool = True):
        super().__init__(
            data_type=DataType.NUMBER,
            name=name,
            description=description,
            required=required,
            index_filterable=index_filterable,
            index_searchable=False,  # Floats are typically not searchable
            skip_vectorization=True
        )


class BooleanField(Field):
    """Boolean field"""

    def __init__(self,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 required: bool = False,
                 index_filterable: bool = True):
        super().__init__(
            data_type=DataType.BOOL,
            name=name,
            description=description,
            required=required,
            index_filterable=index_filterable,
            index_searchable=False,  # Booleans are typically not searchable
            skip_vectorization=True
        )


class DateTimeField(Field):
    """Date time field"""

    def __init__(self,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 required: bool = False,
                 index_filterable: bool = True):
        super().__init__(
            data_type=DataType.DATE,
            name=name,
            description=description,
            required=required,
            index_filterable=index_filterable,
            index_searchable=False,  # Dates are typically not searchable
            skip_vectorization=True
        )


class UUIDField(Field):
    """UUID field"""

    def __init__(self,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 required: bool = False,
                 index_filterable: bool = True):
        super().__init__(
            data_type=DataType.UUID,
            name=name,
            description=description,
            required=required,
            index_filterable=index_filterable,
            index_searchable=False,  # UUIDs are typically not searchable
            skip_vectorization=True
        )


class TextArrayField(Field):
    """Text array field"""

    def __init__(self,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 required: bool = False,
                 index_filterable: bool = True,
                 index_searchable: bool = True,
                 tokenization: str = "word",
                 skip_vectorization: bool = False,
                 vectorize_property_name: bool = False):
        super().__init__(
            data_type=DataType.TEXT_ARRAY,
            name=name,
            description=description,
            required=required,
            index_filterable=index_filterable,
            index_searchable=index_searchable,
            tokenization=tokenization,
            skip_vectorization=skip_vectorization,
            vectorize_property_name=vectorize_property_name
        )


class IntArrayField(Field):
    """Integer array field"""

    def __init__(self,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 required: bool = False,
                 index_filterable: bool = True):
        super().__init__(
            data_type=DataType.INT_ARRAY,
            name=name,
            description=description,
            required=required,
            index_filterable=index_filterable,
            index_searchable=False,  # Integer arrays are typically not searchable
            skip_vectorization=True
        )


class ModelMeta(type):
    """Model metaclass for collecting field definitions"""

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
        
        # We'll initialize the object manager lazily when first accessed
        # to avoid circular imports and client initialization issues
        new_class._objects_initialized = False

        return new_class

    def __getattribute__(cls, name):
        """Lazily initialize object manager when first accessed"""
        if name == 'objects' and not cls._objects_initialized:
            from ..managers import ObjectManager
            from ..core.registry import get_weaviate_client
            try:
                client = get_weaviate_client()
                cls.objects = ObjectManager(cls, client)
                cls._objects_initialized = True
            except RuntimeError:
                # Client not initialized yet, will be initialized when needed
                pass
        return super().__getattribute__(name)
