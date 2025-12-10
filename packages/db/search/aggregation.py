"""Basic aggregation support for Weaviate."""

import logging
from typing import Any, Dict, List, Optional, Union

from ..core.client import WeaviateClient
from .filters import Q

logger = logging.getLogger(__name__)


class AggregationBuilder:
    """Aggregation builder for Weaviate."""
    
    def __init__(self, target: Any, client: WeaviateClient):
        self.client = client
        self._metrics: List[Dict] = []
        self._group_by_field: Optional[str] = None
        self._filters: Optional[Q] = None
        self._limit: Optional[int] = None
        
        if isinstance(target, str):
            self._collection_name = target
        elif hasattr(target, 'get_collection_name'):
            self._collection_name = target.get_collection_name()
        else:
            raise ValueError(f"Invalid target type: {type(target)}")
    
    def group_by(self, field: str) -> 'AggregationBuilder':
        self._group_by_field = field
        return self
    
    def count(self, alias: str = "count") -> 'AggregationBuilder':
        self._metrics.append({'type': 'count', 'field': None, 'alias': alias})
        return self
    
    def sum(self, field: str, alias: Optional[str] = None) -> 'AggregationBuilder':
        self._metrics.append({'type': 'sum', 'field': field, 'alias': alias or f"sum_{field}"})
        return self
    
    def avg(self, field: str, alias: Optional[str] = None) -> 'AggregationBuilder':
        self._metrics.append({'type': 'mean', 'field': field, 'alias': alias or f"avg_{field}"})
        return self
    
    def min(self, field: str, alias: Optional[str] = None) -> 'AggregationBuilder':
        self._metrics.append({'type': 'minimum', 'field': field, 'alias': alias or f"min_{field}"})
        return self
    
    def max(self, field: str, alias: Optional[str] = None) -> 'AggregationBuilder':
        self._metrics.append({'type': 'maximum', 'field': field, 'alias': alias or f"max_{field}"})
        return self
    
    def filter(self, *args, **kwargs) -> 'AggregationBuilder':
        new_filter = Q(*args, **kwargs)
        if self._filters is None:
            self._filters = new_filter
        else:
            self._filters = self._filters & new_filter
        return self
    
    def limit(self, n: int) -> 'AggregationBuilder':
        """Set result limit."""
        self._limit = n
        return self
    
    def execute(self) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        if not self._metrics:
            logger.warning("No metrics defined for aggregation")
            return [] if self._group_by_field else {}
        
        try:
            with self.client.managed_connection() as conn:
                collection = conn.client.collections.get(self._collection_name)
                
                agg_params = {}
                if self._filters and not self._filters.is_empty():
                    weaviate_filter = self._filters.to_weaviate_filter()
                    if weaviate_filter:
                        agg_params['filters'] = weaviate_filter
                
                for metric in self._metrics:
                    if metric['type'] == 'count':
                        agg_params['total_count'] = True
                
                if self._group_by_field:
                    result = collection.aggregate.over_all(
                        group_by=self._group_by_field,
                        **agg_params
                    )
                else:
                    result = collection.aggregate.over_all(**agg_params)
                
                return self._parse_results(result)
                
        except Exception as e:
            logger.error(f"Aggregation failed: {e}")
            return [] if self._group_by_field else {}
    
    def _parse_results(self, result) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        if self._group_by_field:
            parsed_results = []
            if hasattr(result, 'groups'):
                for group in result.groups:
                    group_data = {}
                    # Add group value
                    if hasattr(group, 'grouped_by') and hasattr(group.grouped_by, 'value'):
                        group_data['group'] = group.grouped_by.value
                    # Add count
                    if hasattr(group, 'total_count'):
                        group_data['count'] = group.total_count
                    parsed_results.append(group_data)
            return parsed_results
        else:
            result_data = {}
            if hasattr(result, 'total_count'):
                result_data['count'] = result.total_count
            return result_data
    
    def __str__(self) -> str:
        parts = [f"collection={self._collection_name}"]
        if self._group_by_field:
            parts.append(f"group_by={self._group_by_field}")
        if self._metrics:
            metrics_str = ", ".join(f"{m['alias']}" for m in self._metrics)
            parts.append(f"metrics=[{metrics_str}]")
        return f"AggregationBuilder({', '.join(parts)})"
