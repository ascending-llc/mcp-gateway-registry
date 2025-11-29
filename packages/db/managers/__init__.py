"""
Manager classes for CRUD operations and query building.
"""

from .batch import BatchResult
from .collection import CollectionManager
from .object import ObjectManager
from .data import DirectDataManager

__all__ = [
    'BatchResult',
    'CollectionManager',
    'ObjectManager',
    'DirectDataManager',
]

