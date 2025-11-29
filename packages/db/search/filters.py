"""
Advanced Filter System for Weaviate Search

Provides a streamlined and extensible filter system that supports complex query conditions
and logical operations. Directly maps to Weaviate's native Filter API for optimal performance.

Key Features:
- Q objects for complex logical operations (AND, OR, NOT)
- Extensible operator registry for custom filter operations
- Direct conversion to Weaviate Filter (no intermediate layers)
- Django-style field lookups (field__operator=value)
"""

import logging
from typing import Any, Dict, List, Optional, Union, Callable
from weaviate.classes.query import Filter

# Import internal Weaviate filter types for isinstance checks
try:
    from weaviate.collections.classes.filters import _FilterValue, _FilterAnd, _FilterOr
    # Base class for all Weaviate filters
    _WeaviateFilterTypes = (_FilterValue, _FilterAnd, _FilterOr)
except ImportError:
    # Fallback if internal API changes - create dummy types
    _FilterValue = type(Filter.by_property("dummy").equal("value"))
    _WeaviateFilterTypes = (_FilterValue,)

logger = logging.getLogger(__name__)


class FilterOperatorRegistry:
    """
    Registry for filter operators that allows dynamic registration of new operators.
    
    This provides extensibility - users can register custom filter operators
    without modifying the core code.
    
    Example:
        # Register a custom operator
        def custom_filter(field: str, value: Any) -> Filter:
            return Filter.by_property(field).custom_operation(value)
        
        FilterOperatorRegistry.register("custom", custom_filter)
        
        # Use it
        Q(field__custom=value)
    """
    
    _handlers: Dict[str, Callable[[str, Any], Filter]] = {}
    
    @classmethod
    def register(cls, operator: str, handler: Callable[[str, Any], Filter]):
        """
        Register a new filter operator.
        
        Args:
            operator: Operator name (e.g., "gt", "contains_any")
            handler: Function that takes (field, value) and returns a Weaviate Filter
        """
        cls._handlers[operator] = handler
        logger.debug(f"Registered filter operator: {operator}")
    
    @classmethod
    def get(cls, operator: str) -> Optional[Callable[[str, Any], Filter]]:
        """Get the handler for an operator."""
        return cls._handlers.get(operator)
    
    @classmethod
    def list_operators(cls) -> List[str]:
        """List all registered operators."""
        return list(cls._handlers.keys())
    
    @classmethod
    def unregister(cls, operator: str):
        """Unregister an operator."""
        if operator in cls._handlers:
            del cls._handlers[operator]


# Register built-in operators
FilterOperatorRegistry.register(
    "eq", 
    lambda field, value: Filter.by_property(field).equal(value)
)
FilterOperatorRegistry.register(
    "ne", 
    lambda field, value: Filter.by_property(field).not_equal(value)
)
FilterOperatorRegistry.register(
    "gt", 
    lambda field, value: Filter.by_property(field).greater_than(value)
)
FilterOperatorRegistry.register(
    "gte", 
    lambda field, value: Filter.by_property(field).greater_or_equal(value)
)
FilterOperatorRegistry.register(
    "lt", 
    lambda field, value: Filter.by_property(field).less_than(value)
)
FilterOperatorRegistry.register(
    "lte", 
    lambda field, value: Filter.by_property(field).less_or_equal(value)
)
FilterOperatorRegistry.register(
    "contains_any", 
    lambda field, value: Filter.by_property(field).contains_any(value)
)
FilterOperatorRegistry.register(
    "contains_all", 
    lambda field, value: Filter.by_property(field).contains_all(value)
)
FilterOperatorRegistry.register(
    "like", 
    lambda field, value: Filter.by_property(field).like(value)
)
FilterOperatorRegistry.register(
    "is_null", 
    lambda field, value: Filter.by_property(field).is_none(True)
)
FilterOperatorRegistry.register(
    "not_null", 
    lambda field, value: Filter.by_property(field).is_none(False)
)
# Alias for common patterns
FilterOperatorRegistry.register(
    "in", 
    lambda field, value: Filter.by_property(field).contains_any(value) if isinstance(value, list) else Filter.by_property(field).equal(value)
)


class Q:
    """
    Q object for building complex queries with logical operators.
    
    Provides a Django-like API for constructing filters with AND, OR, and NOT operations.
    Directly converts to Weaviate's native Filter objects without intermediate layers.
    
    Example:
        # Simple equality
        Q(category="tech")
        
        # Field lookups
        Q(views__gt=1000, published=True)
        
        # Logical operations
        Q(category="tech") | Q(category="science")
        Q(views__gt=100) & Q(published=True)
        ~Q(category="obsolete")
        
        # Complex nested conditions
        (Q(category="tech") | Q(category="science")) & Q(views__gt=1000)
    """
    
    def __init__(self, *args, **kwargs):
        """
        Initialize Q object with filters.
        
        Args:
            *args: Other Q objects or Filter objects
            **kwargs: Field filters using Django-style lookups
        """
        self._filters: List[Union[Filter, 'Q']] = []
        self._operator = "And"  # Default operator
        self._negated = False
        
        # Handle Q objects passed as args
        for arg in args:
            if isinstance(arg, (Q, Filter)):
                self._filters.append(arg)
        
        # Parse keyword arguments
        if kwargs:
            self._parse_kwargs(kwargs)
    
    def _parse_kwargs(self, kwargs: Dict[str, Any]):
        """
        Parse Django-style keyword arguments into Weaviate filters.
        
        Supports field lookups like:
        - field=value (equality)
        - field__gt=value (greater than)
        - field__contains_any=value (contains any)
        etc.
        """
        for key, value in kwargs.items():
            if '__' in key:
                # Field lookup: field__operator
                field, operator = key.rsplit('__', 1)
                handler = FilterOperatorRegistry.get(operator)
                
                if not handler:
                    raise ValueError(
                        f"Unsupported operator: {operator}. "
                        f"Available operators: {FilterOperatorRegistry.list_operators()}"
                    )
                
                self._filters.append(handler(field, value))
            else:
                # Simple equality
                self._filters.append(Filter.by_property(key).equal(value))
    
    def __or__(self, other: 'Q') -> 'Q':
        """
        OR operator (|).
        
        Flattens nested OR operations for better performance.
        """
        if not isinstance(other, Q):
            raise TypeError(f"unsupported operand type(s) for |: 'Q' and '{type(other).__name__}'")
        
        # Flatten OR operations
        if self._operator == "Or" and not self._negated and other._operator == "Or" and not other._negated:
            combined = Q()
            combined._filters = self._filters + other._filters
            combined._operator = "Or"
            return combined
        elif self._operator == "Or" and not self._negated:
            combined = Q()
            combined._filters = self._filters + [other]
            combined._operator = "Or"
            return combined
        elif other._operator == "Or" and not other._negated:
            combined = Q()
            combined._filters = [self] + other._filters
            combined._operator = "Or"
            return combined
        else:
            combined = Q()
            combined._filters = [self, other]
            combined._operator = "Or"
            return combined
    
    def __and__(self, other: 'Q') -> 'Q':
        """
        AND operator (&).
        
        Flattens nested AND operations for better performance.
        """
        if not isinstance(other, Q):
            raise TypeError(f"unsupported operand type(s) for &: 'Q' and '{type(other).__name__}'")
        
        # Flatten AND operations
        if self._operator == "And" and not self._negated and other._operator == "And" and not other._negated:
            combined = Q()
            combined._filters = self._filters + other._filters
            combined._operator = "And"
            return combined
        elif self._operator == "And" and not self._negated:
            combined = Q()
            combined._filters = self._filters + [other]
            combined._operator = "And"
            return combined
        elif other._operator == "And" and not other._negated:
            combined = Q()
            combined._filters = [self] + other._filters
            combined._operator = "And"
            return combined
        else:
            combined = Q()
            combined._filters = [self, other]
            combined._operator = "And"
            return combined
    
    def __invert__(self) -> 'Q':
        """
        NOT operator (~).
        
        Negates the entire Q object.
        """
        negated = Q()
        negated._filters = [self]
        negated._operator = "Not"
        negated._negated = True
        return negated
    
    def to_weaviate_filter(self) -> Optional[Filter]:
        """
        Convert Q object directly to Weaviate Filter.
        
        No intermediate layers - direct conversion for optimal performance.
        
        Returns:
            Weaviate Filter object or None if empty
        """
        if not self._filters:
            return None
        
        # Handle single filter
        if len(self._filters) == 1:
            single_filter = self._filters[0]
            
            # Check if it's already a Weaviate filter (any type)
            if isinstance(single_filter, _WeaviateFilterTypes):
                result = single_filter
            elif isinstance(single_filter, Q):
                result = single_filter.to_weaviate_filter()
            else:
                return None
            
            # Apply negation if needed
            return ~result if self._negated else result
        
        # Convert all filters to Weaviate Filter objects
        weaviate_filters = []
        for f in self._filters:
            if isinstance(f, _WeaviateFilterTypes):
                weaviate_filters.append(f)
            elif isinstance(f, Q):
                converted = f.to_weaviate_filter()
                if converted:
                    weaviate_filters.append(converted)
        
        if not weaviate_filters:
            return None
        
        # Combine with logical operator
        if len(weaviate_filters) == 1:
            result = weaviate_filters[0]
        else:
            if self._operator == "And":
                # Use Weaviate's native AND combination
                result = weaviate_filters[0]
                for f in weaviate_filters[1:]:
                    result = result & f
            elif self._operator == "Or":
                # Use Weaviate's native OR combination
                result = weaviate_filters[0]
                for f in weaviate_filters[1:]:
                    result = result | f
            else:
                # Default to AND
                result = weaviate_filters[0]
                for f in weaviate_filters[1:]:
                    result = result & f
        
        # Apply negation if needed
        if self._negated:
            result = ~result
            
        return result
    
    def is_empty(self) -> bool:
        """Check if this Q object has any filters."""
        return len(self._filters) == 0
    
    def __str__(self) -> str:
        """String representation for debugging."""
        if not self._filters:
            return "Q(empty)"
        
        if len(self._filters) == 1:
            s = str(self._filters[0])
        else:
            parts = [f"({f})" for f in self._filters]
            s = f" {self._operator} ".join(parts)
        
        return f"~({s})" if self._negated else s
    
    def __repr__(self) -> str:
        return f"Q({self})"


# Convenience functions
def and_(*q_objects: Q) -> Q:
    """
    Combine multiple Q objects with AND.
    
    Example:
        and_(Q(category="tech"), Q(published=True), Q(views__gt=100))
    """
    if not q_objects:
        return Q()
    
    result = q_objects[0]
    for q in q_objects[1:]:
        result = result & q
    return result


def or_(*q_objects: Q) -> Q:
    """
    Combine multiple Q objects with OR.
    
    Example:
        or_(Q(category="tech"), Q(category="science"), Q(category="ai"))
    """
    if not q_objects:
        return Q()
    
    result = q_objects[0]
    for q in q_objects[1:]:
        result = result | q
        return result


def not_(q_object: Q) -> Q:
    """
    Negate a Q object.
    
    Example:
        not_(Q(category="obsolete"))
    """
    return ~q_object
