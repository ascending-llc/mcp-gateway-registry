"""
Search Target Adapters

Provides adapter pattern to unify model-based and collection-based searches.
This eliminates code duplication between the two search approaches.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar

T = TypeVar('T')


class SearchTarget(ABC):
    """
    Abstract adapter for search targets.
    
    Provides a unified interface for both model-based and collection-based searches.
    This allows the same search logic to work with either models or raw collections.
    """
    
    @abstractmethod
    def get_collection_name(self) -> str:
        """
        Get the Weaviate collection name.
        
        Returns:
            Collection name string
        """
        pass
    
    @abstractmethod
    def to_instance(self, data: Dict[str, Any]) -> Any:
        """
        Convert raw data dictionary to the appropriate type.
        
        For models: converts to model instance
        For collections: returns dict as-is
        
        Args:
            data: Raw data dictionary from Weaviate
            
        Returns:
            Converted instance (model or dict)
        """
        pass
    
    @abstractmethod
    def to_dict(self, instance: Any) -> Dict[str, Any]:
        """
        Convert instance to dictionary for Weaviate operations.
        
        Args:
            instance: Model instance or dictionary
            
        Returns:
            Dictionary suitable for Weaviate
        """
        pass


class ModelTarget(SearchTarget):
    """
    Adapter for model-based searches.
    
    Wraps a model class and provides type-safe conversion between
    model instances and Weaviate data dictionaries.
    """
    
    def __init__(self, model_class: Type[T]):
        """
        Initialize with a model class.
        
        Args:
            model_class: The model class (must have Meta.collection_name or __name__)
        """
        self.model_class = model_class
        self._collection_name = None
    
    def get_collection_name(self) -> str:
        """Get collection name from model class."""
        if self._collection_name is None:
            if hasattr(self.model_class, 'get_collection_name'):
                self._collection_name = self.model_class.get_collection_name()
            elif hasattr(self.model_class, '_meta') and hasattr(self.model_class._meta, 'collection_name'):
                self._collection_name = self.model_class._meta.collection_name
            else:
                self._collection_name = self.model_class.__name__
        
        return self._collection_name
    
    def to_instance(self, data: Dict[str, Any]) -> T:
        """
        Convert data dictionary to model instance.
        
        Args:
            data: Raw data from Weaviate
            
        Returns:
            Model instance with fields populated
        """
        instance = self.model_class()
        
        # Set ID if present
        if 'id' in data:
            instance.id = data['id']
        
        # Set field values
        if hasattr(self.model_class, '_fields'):
            for field_name in self.model_class._fields.keys():
                if field_name in data:
                    setattr(instance, field_name, data[field_name])
        else:
            # Fallback: set all non-metadata fields
            for key, value in data.items():
                if not key.startswith('_'):
                    setattr(instance, key, value)
        
        # Set metadata (fields starting with _)
        for key, value in data.items():
            if key.startswith('_') and not hasattr(instance, key):
                setattr(instance, key, value)
        
        return instance
    
    def to_dict(self, instance: T) -> Dict[str, Any]:
        """
        Convert model instance to dictionary.
        
        Args:
            instance: Model instance
            
        Returns:
            Dictionary for Weaviate
        """
        if hasattr(instance, 'to_dict'):
            return instance.to_dict()
        
        # Fallback: extract all non-private attributes
        data = {}
        for attr in dir(instance):
            if not attr.startswith('_') and not callable(getattr(instance, attr)):
                value = getattr(instance, attr)
                if value is not None:
                    data[attr] = value
        
        return data
    
    def __str__(self) -> str:
        return f"ModelTarget({self.model_class.__name__})"
    
    def __repr__(self) -> str:
        return self.__str__()


class CollectionTarget(SearchTarget):
    """
    Adapter for collection-based searches.
    
    Works directly with collection names and returns raw dictionaries.
    No model conversion is performed.
    """
    
    def __init__(self, collection_name: str):
        """
        Initialize with a collection name.
        
        Args:
            collection_name: Name of the Weaviate collection
        """
        self._collection_name = collection_name
    
    def get_collection_name(self) -> str:
        """Return the collection name."""
        return self._collection_name
    
    def to_instance(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return data as-is (no conversion needed).
        
        Args:
            data: Raw data from Weaviate
            
        Returns:
            Same dictionary
        """
        return data
    
    def to_dict(self, instance: Any) -> Dict[str, Any]:
        """
        Convert instance to dictionary.
        
        Args:
            instance: Dictionary or dict-like object
            
        Returns:
            Dictionary for Weaviate
        """
        if isinstance(instance, dict):
            return instance
        
        # Try to convert to dict
        if hasattr(instance, 'to_dict'):
            return instance.to_dict()
        elif hasattr(instance, '__dict__'):
            return instance.__dict__
        else:
            raise TypeError(f"Cannot convert {type(instance)} to dictionary")
    
    def __str__(self) -> str:
        return f"CollectionTarget({self._collection_name})"
    
    def __repr__(self) -> str:
        return self.__str__()


def create_target(target: Any) -> SearchTarget:
    """
    Factory function to create the appropriate SearchTarget.
    
    Args:
        target: Model class, collection name, or SearchTarget
        
    Returns:
        Appropriate SearchTarget instance
        
    Example:
        # From model class
        target = create_target(Article)
        
        # From collection name
        target = create_target("Articles")
        
        # Already a target
        target = create_target(ModelTarget(Article))
    """
    if isinstance(target, SearchTarget):
        return target
    elif isinstance(target, str):
        return CollectionTarget(target)
    elif isinstance(target, type):
        # Assume it's a model class
        return ModelTarget(target)
    else:
        raise TypeError(
            f"Invalid target type: {type(target)}. "
            "Expected model class, collection name, or SearchTarget."
        )

