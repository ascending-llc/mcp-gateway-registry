"""
Descriptors for model attributes.

Provides efficient lazy initialization without __getattribute__ overhead.
"""

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..managers import ObjectManager

logger = logging.getLogger(__name__)


class ObjectManagerDescriptor:
    """
    Descriptor for lazy ObjectManager initialization.
    
    Avoids __getattribute__ performance penalty by using descriptor protocol.
    Manager is initialized only once on first access.
    
    Performance: 
        - __getattribute__: Called on EVERY attribute access (~1000x overhead)
        - Descriptor __get__: Called only on first access, then direct attribute access
    """
    
    def __init__(self, model_class):
        """
        Initialize descriptor with model class.
        
        Args:
            model_class: The model class this manager belongs to
        """
        self.model_class = model_class
        self._manager: Optional['ObjectManager'] = None
        self._attr_name = 'objects'
    
    def __set_name__(self, owner, name):
        """Store attribute name when descriptor is assigned to class."""
        self._attr_name = name
    
    def __get__(self, instance, owner):
        """
        Get ObjectManager, initializing on first access.
        
        Args:
            instance: Model instance (None for class access)
            owner: Model class
        
        Returns:
            ObjectManager instance
            
        Raises:
            RuntimeError: If Weaviate client not initialized
        """
        # Lazy initialization
        if self._manager is None:
            from ..managers import ObjectManager
            from ..core.registry import get_weaviate_client
            
            try:
                client = get_weaviate_client()
                self._manager = ObjectManager(self.model_class, client)
                logger.debug(f"Initialized ObjectManager for {self.model_class.__name__}")
            except RuntimeError as e:
                raise RuntimeError(
                    f"Cannot access {self.model_class.__name__}.{self._attr_name} - "
                    f"Weaviate client not initialized. Call init_weaviate() first."
                ) from e
        
        return self._manager
    
    def __set__(self, instance, value):
        """Prevent overwriting the manager."""
        raise AttributeError(f"Cannot set '{self._attr_name}' attribute")

