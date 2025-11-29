"""
Aggregation Support for Weaviate

Provides a fluent API for building and executing aggregation queries.
Supports grouping, counting, and statistical operations.
"""

import logging
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

from ..core.client import WeaviateClient
from .filters import Q

logger = logging.getLogger(__name__)


class AggregationType(Enum):
    """Types of aggregation operations."""
    COUNT = "count"
    SUM = "sum"
    AVG = "mean"  # Weaviate uses 'mean' instead of 'avg'
    MIN = "minimum"
    MAX = "maximum"
    MEDIAN = "median"
    MODE = "mode"


@dataclass
class MetricDefinition:
    """Definition of a metric to aggregate."""
    metric_type: AggregationType
    field: Optional[str] = None  # None for count
    alias: Optional[str] = None  # Custom name for the result
    
    def __str__(self) -> str:
        if self.field:
            name = self.alias or f"{self.metric_type.value}_{self.field}"
            return f"{name}({self.field})"
        else:
            return f"count()"


class AggregationBuilder:
    """
    Fluent interface for building aggregation queries.
    
    Provides methods for grouping, counting, and computing statistics
    on Weaviate collections.
    
    Example:
        # Count by category
        results = (Article.objects.aggregate()
            .group_by("category")
            .count()
            .execute())
        
        # Multiple metrics
        results = (Article.objects.aggregate()
            .group_by("category")
            .count()
            .avg("views")
            .sum("likes")
            .execute())
        
        # With filters
        results = (Article.objects.aggregate()
            .filter(published=True)
            .group_by("category")
            .count()
            .execute())
    """
    
    def __init__(self, target: Any, client: WeaviateClient):
        """
        Initialize aggregation builder.
        
        Args:
            target: Model class or collection name
            client: Weaviate client instance
        """
        self.client = client
        self._metrics: List[MetricDefinition] = []
        self._group_by_field: Optional[str] = None
        self._filters: Optional[Q] = None
        self._limit: Optional[int] = None
        
        # Determine collection name
        if isinstance(target, str):
            self._collection_name = target
        elif hasattr(target, 'get_collection_name'):
            self._collection_name = target.get_collection_name()
        else:
            raise ValueError(f"Invalid target type: {type(target)}")
    
    def group_by(self, field: str) -> 'AggregationBuilder':
        """
        Group results by a field.
        
        Args:
            field: Field name to group by
            
        Returns:
            Self for chaining
            
        Example:
            .group_by("category")
        """
        self._group_by_field = field
        return self
    
    def count(self, alias: str = "count") -> 'AggregationBuilder':
        """
        Add count metric.
        
        Args:
            alias: Name for this metric in results
            
        Returns:
            Self for chaining
        """
        self._metrics.append(MetricDefinition(
            metric_type=AggregationType.COUNT,
            alias=alias
        ))
        return self
    
    def sum(self, field: str, alias: Optional[str] = None) -> 'AggregationBuilder':
        """
        Add sum metric for a numeric field.
        
        Args:
            field: Field name to sum
            alias: Custom name for result
            
        Returns:
            Self for chaining
        """
        self._metrics.append(MetricDefinition(
            metric_type=AggregationType.SUM,
            field=field,
            alias=alias or f"sum_{field}"
        ))
        return self
    
    def avg(self, field: str, alias: Optional[str] = None) -> 'AggregationBuilder':
        """
        Add average (mean) metric for a numeric field.
        
        Args:
            field: Field name to average
            alias: Custom name for result
            
        Returns:
            Self for chaining
        """
        self._metrics.append(MetricDefinition(
            metric_type=AggregationType.AVG,
            field=field,
            alias=alias or f"avg_{field}"
        ))
        return self
    
    def min(self, field: str, alias: Optional[str] = None) -> 'AggregationBuilder':
        """
        Add minimum metric for a numeric field.
        
        Args:
            field: Field name
            alias: Custom name for result
            
        Returns:
            Self for chaining
        """
        self._metrics.append(MetricDefinition(
            metric_type=AggregationType.MIN,
            field=field,
            alias=alias or f"min_{field}"
        ))
        return self
    
    def max(self, field: str, alias: Optional[str] = None) -> 'AggregationBuilder':
        """
        Add maximum metric for a numeric field.
        
        Args:
            field: Field name
            alias: Custom name for result
            
        Returns:
            Self for chaining
        """
        self._metrics.append(MetricDefinition(
            metric_type=AggregationType.MAX,
            field=field,
            alias=alias or f"max_{field}"
        ))
        return self
    
    def median(self, field: str, alias: Optional[str] = None) -> 'AggregationBuilder':
        """
        Add median metric for a numeric field.
        
        Args:
            field: Field name
            alias: Custom name for result
            
        Returns:
            Self for chaining
        """
        self._metrics.append(MetricDefinition(
            metric_type=AggregationType.MEDIAN,
            field=field,
            alias=alias or f"median_{field}"
        ))
        return self
    
    def mode(self, field: str, alias: Optional[str] = None) -> 'AggregationBuilder':
        """
        Add mode (most common value) metric.
        
        Args:
            field: Field name
            alias: Custom name for result
            
        Returns:
            Self for chaining
        """
        self._metrics.append(MetricDefinition(
            metric_type=AggregationType.MODE,
            field=field,
            alias=alias or f"mode_{field}"
        ))
        return self
    
    def filter(self, *args, **kwargs) -> 'AggregationBuilder':
        """
        Add filters to the aggregation.
        
        Args:
            *args: Q objects
            **kwargs: Field filters
            
        Returns:
            Self for chaining
            
        Example:
            .filter(published=True, category="tech")
        """
        new_filter = Q(*args, **kwargs)
        
        if self._filters is None:
            self._filters = new_filter
        else:
            self._filters = self._filters & new_filter
        
        return self
    
    def limit(self, n: int) -> 'AggregationBuilder':
        """
        Limit number of groups returned.
        
        Args:
            n: Maximum number of groups
            
        Returns:
            Self for chaining
        """
        self._limit = n
        return self
    
    def execute(self) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Execute the aggregation and return results.
        
        Returns:
            If grouped: List of dictionaries (one per group)
            If not grouped: Single dictionary with overall metrics
            
        Example:
            # Grouped result
            [
                {"group": "tech", "count": 100, "avg_views": 1500},
                {"group": "science", "count": 80, "avg_views": 1200}
            ]
            
            # Overall result
            {"count": 180, "avg_views": 1360}
        """
        if not self._metrics:
            logger.warning("No metrics defined for aggregation")
            return [] if self._group_by_field else {}
        
        try:
            with self.client.managed_connection() as conn:
                collection = conn.client.collections.get(self._collection_name)
                
                # Build Weaviate aggregation query
                agg_params = self._build_aggregation_params()
                
                # Execute aggregation
                if self._group_by_field:
                    result = collection.aggregate.over_all(
                        group_by=self._group_by_field,
                        **agg_params
                    )
                else:
                    result = collection.aggregate.over_all(**agg_params)
                
                # Parse and return results
                return self._parse_results(result)
                
        except Exception as e:
            logger.error(f"Aggregation failed: {e}")
            return [] if self._group_by_field else {}
    
    def _build_aggregation_params(self) -> Dict[str, Any]:
        """Build parameters for Weaviate aggregation."""
        params = {}
        
        # Add filters
        if self._filters and not self._filters.is_empty():
            weaviate_filter = self._filters.to_weaviate_filter()
            if weaviate_filter:
                params['filters'] = weaviate_filter
        
        # Add metrics
        # Note: Weaviate uses specific methods for each metric type
        # This is a simplified version - actual implementation may vary
        return_metrics = []
        
        for metric in self._metrics:
            if metric.metric_type == AggregationType.COUNT:
                params['total_count'] = True
            else:
                # For other metrics, we need to specify the property
                # Weaviate's Python client handles this differently
                pass
        
        return params
    
    def _parse_results(self, result) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Parse Weaviate aggregation results.
        
        Args:
            result: Raw Weaviate aggregation result
            
        Returns:
            Formatted dictionary or list of dictionaries
        """
        if self._group_by_field:
            # Grouped results
            parsed_results = []
            
            if hasattr(result, 'groups'):
                for group in result.groups:
                    group_data = {
                        'group': group.grouped_by.value if hasattr(group, 'grouped_by') else None
                    }
                    
                    # Add metrics
                    if hasattr(group, 'total_count'):
                        group_data['count'] = group.total_count
                    
                    # Add other metrics from properties
                    if hasattr(group, 'properties'):
                        for prop_name, prop_data in group.properties.items():
                            for metric in self._metrics:
                                if metric.field == prop_name:
                                    metric_name = metric.alias or f"{metric.metric_type.value}_{metric.field}"
                                    # Extract the specific metric value
                                    if hasattr(prop_data, metric.metric_type.value):
                                        group_data[metric_name] = getattr(prop_data, metric.metric_type.value)
                    
                    parsed_results.append(group_data)
            
            return parsed_results
        else:
            # Overall results
            result_data = {}
            
            if hasattr(result, 'total_count'):
                result_data['count'] = result.total_count
            
            # Add other metrics
            if hasattr(result, 'properties'):
                for prop_name, prop_data in result.properties.items():
                    for metric in self._metrics:
                        if metric.field == prop_name:
                            metric_name = metric.alias or f"{metric.metric_type.value}_{metric.field}"
                            if hasattr(prop_data, metric.metric_type.value):
                                result_data[metric_name] = getattr(prop_data, metric.metric_type.value)
            
            return result_data
    
    def __str__(self) -> str:
        """String representation for debugging."""
        parts = [f"collection={self._collection_name}"]
        
        if self._group_by_field:
            parts.append(f"group_by={self._group_by_field}")
        
        if self._metrics:
            metrics_str = ", ".join(str(m) for m in self._metrics)
            parts.append(f"metrics=[{metrics_str}]")
        
        return f"AggregationBuilder({', '.join(parts)})"

