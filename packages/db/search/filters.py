"""Filter system for Weaviate search."""

import logging
from typing import Any, Dict, List, Optional, Union, cast
from weaviate.collections.classes.filters import Filter, _FilterByProperty, _FilterValue, _Filters

logger = logging.getLogger(__name__)


class Q:
    """Q object for building complex queries with logical operators."""
    
    def __init__(self, *args, **kwargs):
        self._filters: List[Union[Filter, _FilterByProperty, _FilterValue, _Filters, 'Q']] = []
        self._operator = "And"
        self._negated = False
        
        for arg in args:
            if isinstance(arg, (Q, Filter, _FilterByProperty, _FilterValue, _Filters)):
                self._filters.append(arg)
        
        if kwargs:
            self._parse_kwargs(kwargs)
    
    def _parse_kwargs(self, kwargs: Dict[str, Any]):
        for key, value in kwargs.items():
            if '__' in key:
                field, operator = key.rsplit('__', 1)
                if operator == "eq":
                    self._filters.append(Filter.by_property(field).equal(value))
                elif operator == "ne":
                    self._filters.append(Filter.by_property(field).not_equal(value))
                elif operator == "gt":
                    self._filters.append(Filter.by_property(field).greater_than(value))
                elif operator == "gte":
                    self._filters.append(Filter.by_property(field).greater_or_equal(value))
                elif operator == "lt":
                    self._filters.append(Filter.by_property(field).less_than(value))
                elif operator == "lte":
                    self._filters.append(Filter.by_property(field).less_or_equal(value))
                elif operator == "contains_any":
                    self._filters.append(Filter.by_property(field).contains_any(value))
                elif operator == "contains_all":
                    self._filters.append(Filter.by_property(field).contains_all(value))
                elif operator == "like":
                    self._filters.append(Filter.by_property(field).like(value))
                elif operator == "is_null":
                    self._filters.append(Filter.by_property(field).is_none(True))
                elif operator == "not_null":
                    self._filters.append(Filter.by_property(field).is_none(False))
                elif operator == "in":
                    if isinstance(value, list):
                        self._filters.append(Filter.by_property(field).contains_any(value))
                    else:
                        self._filters.append(Filter.by_property(field).equal(value))
                else:
                    raise ValueError(f"Unsupported operator: {operator}")
            else:
                self._filters.append(Filter.by_property(key).equal(value))
    
    def __or__(self, other: 'Q') -> 'Q':
        if not isinstance(other, Q):
            raise TypeError(f"unsupported operand type(s) for |: 'Q' and '{type(other).__name__}'")
        
        combined = Q()
        
        # Flatten if self is already an OR Q
        if self._operator == "Or" and not self._negated:
            combined._filters = self._filters.copy()
        else:
            combined._filters = [self]
        
        # Flatten if other is already an OR Q
        if other._operator == "Or" and not other._negated:
            combined._filters.extend(other._filters)
        else:
            combined._filters.append(other)
        
        combined._operator = "Or"
        return combined
    
    def __and__(self, other: 'Q') -> 'Q':
        if not isinstance(other, Q):
            raise TypeError(f"unsupported operand type(s) for &: 'Q' and '{type(other).__name__}'")
        
        combined = Q()
        
        # Flatten if self is already an AND Q
        if self._operator == "And" and not self._negated:
            combined._filters = self._filters.copy()
        else:
            combined._filters = [self]
        
        # Flatten if other is already an AND Q
        if other._operator == "And" and not other._negated:
            combined._filters.extend(other._filters)
        else:
            combined._filters.append(other)
        
        combined._operator = "And"
        return combined
    
    def __invert__(self) -> 'Q':
        negated = Q()
        negated._filters = [self]
        negated._operator = "Not"
        negated._negated = True
        return negated
    
    def to_weaviate_filter(self) -> Optional[_Filters]:
        if not self._filters:
            return None
        
        if len(self._filters) == 1:
            single_filter = self._filters[0]
            # Check if it's a Q object
            if hasattr(single_filter, 'to_weaviate_filter'):
                result = single_filter.to_weaviate_filter()
            else:
                # Assume it's a Weaviate filter object
                result = single_filter
            return ~result if self._negated else result
        
        weaviate_filters = []
        for f in self._filters:
            if hasattr(f, 'to_weaviate_filter'):
                converted = f.to_weaviate_filter()
                if converted:
                    weaviate_filters.append(converted)
            else:
                # Assume it's a Weaviate filter object
                weaviate_filters.append(f)
        
        if not weaviate_filters:
            return None
        
        if len(weaviate_filters) == 1:
            result = weaviate_filters[0]
        else:
            if self._operator == "And":
                result = weaviate_filters[0]
                for f in weaviate_filters[1:]:
                    result = result & f
            elif self._operator == "Or":
                result = weaviate_filters[0]
                for f in weaviate_filters[1:]:
                    result = result | f
            else:
                result = weaviate_filters[0]
                for f in weaviate_filters[1:]:
                    result = result & f
        
        if self._negated:
            result = ~result
            
        return result
    
    def is_empty(self) -> bool:
        return len(self._filters) == 0
    
    def __str__(self) -> str:
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


def and_(*q_objects: Q) -> Q:
    if not q_objects:
        return Q()
    
    result = q_objects[0]
    for q in q_objects[1:]:
        result = result & q
    return result


def or_(*q_objects: Q) -> Q:
    if not q_objects:
        return Q()
    
    result = q_objects[0]
    for q in q_objects[1:]:
        result = result | q
    return result


def not_(q_object: Q) -> Q:
    return ~q_object
