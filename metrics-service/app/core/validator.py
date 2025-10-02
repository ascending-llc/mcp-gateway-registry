"""Data validation module for metrics service."""
import re
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone
from ..core.models import MetricType, Metric, MetricRequest

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom validation error with detailed messages."""
    
    def __init__(self, field: str, message: str, value: Any = None):
        self.field = field
        self.message = message
        self.value = value
        super().__init__(f"{field}: {message}")


class ValidationResult:
    """Result of validation with errors and warnings."""
    
    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[str] = []
        self.is_valid: bool = True
    
    def add_error(self, field: str, message: str, value: Any = None):
        """Add a validation error."""
        self.errors.append(ValidationError(field, message, value))
        self.is_valid = False
    
    def add_warning(self, message: str):
        """Add a validation warning."""
        self.warnings.append(message)
    
    def get_error_messages(self) -> List[str]:
        """Get list of error messages."""
        return [str(error) for error in self.errors]


class MetricsValidator:
    """Comprehensive validator for metrics data."""
    
    # Service name validation
    SERVICE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
    SERVICE_NAME_MAX_LENGTH = 100
    
    # Instance ID validation
    INSTANCE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_.-]+$')
    INSTANCE_ID_MAX_LENGTH = 100
    
    # Version validation
    VERSION_PATTERN = re.compile(r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$')
    
    # Dimension key/value validation
    DIMENSION_KEY_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
    DIMENSION_KEY_MAX_LENGTH = 50
    DIMENSION_VALUE_MAX_LENGTH = 200
    MAX_DIMENSIONS = 20
    
    # Metadata validation
    MAX_METADATA_FIELDS = 30
    METADATA_KEY_MAX_LENGTH = 50
    METADATA_VALUE_MAX_LENGTH = 1000
    
    # Value validation
    MIN_METRIC_VALUE = -1e12
    MAX_METRIC_VALUE = 1e12
    MIN_DURATION_MS = 0.0
    MAX_DURATION_MS = 86400000.0  # 24 hours in milliseconds
    
    def validate_metric_request(self, request: MetricRequest) -> ValidationResult:
        """Validate a complete metric request."""
        result = ValidationResult()
        
        # Validate service name
        self._validate_service_name(request.service, result)
        
        # Validate version (optional)
        if request.version:
            self._validate_version(request.version, result)
        
        # Validate instance ID (optional)
        if request.instance_id:
            self._validate_instance_id(request.instance_id, result)
        
        # Validate metrics array
        if not request.metrics:
            result.add_error("metrics", "At least one metric is required")
        elif len(request.metrics) > 100:
            result.add_error("metrics", f"Too many metrics in request: {len(request.metrics)}, max 100")
        else:
            for i, metric in enumerate(request.metrics):
                self._validate_metric(metric, f"metrics[{i}]", result)
        
        return result
    
    def _validate_service_name(self, service: str, result: ValidationResult):
        """Validate service name."""
        if not service:
            result.add_error("service", "Service name is required")
            return
        
        if not isinstance(service, str):
            result.add_error("service", f"Service name must be string, got {type(service).__name__}")
            return
        
        if len(service) > self.SERVICE_NAME_MAX_LENGTH:
            result.add_error("service", f"Service name too long: {len(service)} chars, max {self.SERVICE_NAME_MAX_LENGTH}")
            return
        
        if not self.SERVICE_NAME_PATTERN.match(service):
            result.add_error("service", "Service name must contain only alphanumeric characters, underscores, and hyphens")
    
    def _validate_version(self, version: str, result: ValidationResult):
        """Validate version string."""
        if not isinstance(version, str):
            result.add_error("version", f"Version must be string, got {type(version).__name__}")
            return
        
        if not self.VERSION_PATTERN.match(version):
            result.add_warning(f"Version '{version}' does not follow semantic versioning (x.y.z)")
    
    def _validate_instance_id(self, instance_id: str, result: ValidationResult):
        """Validate instance ID."""
        if not isinstance(instance_id, str):
            result.add_error("instance_id", f"Instance ID must be string, got {type(instance_id).__name__}")
            return
        
        if len(instance_id) > self.INSTANCE_ID_MAX_LENGTH:
            result.add_error("instance_id", f"Instance ID too long: {len(instance_id)} chars, max {self.INSTANCE_ID_MAX_LENGTH}")
            return
        
        if not self.INSTANCE_ID_PATTERN.match(instance_id):
            result.add_error("instance_id", "Instance ID must contain only alphanumeric characters, underscores, dots, and hyphens")
    
    def _validate_metric(self, metric: Metric, field_prefix: str, result: ValidationResult):
        """Validate a single metric."""
        # Validate metric type
        if not isinstance(metric.type, MetricType):
            result.add_error(f"{field_prefix}.type", f"Invalid metric type: {metric.type}")
        
        # Validate timestamp
        self._validate_timestamp(metric.timestamp, f"{field_prefix}.timestamp", result)
        
        # Validate value
        self._validate_metric_value(metric.value, f"{field_prefix}.value", result)
        
        # Validate duration (optional)
        if metric.duration_ms is not None:
            self._validate_duration(metric.duration_ms, f"{field_prefix}.duration_ms", result)
        
        # Validate dimensions
        if metric.dimensions:
            self._validate_dimensions(metric.dimensions, f"{field_prefix}.dimensions", result)
        
        # Validate metadata
        if metric.metadata:
            self._validate_metadata(metric.metadata, f"{field_prefix}.metadata", result)
    
    def _validate_timestamp(self, timestamp: datetime, field: str, result: ValidationResult):
        """Validate timestamp."""
        if not isinstance(timestamp, datetime):
            result.add_error(field, f"Timestamp must be datetime object, got {type(timestamp).__name__}")
            return
        
        # Check if timestamp is in the future (allow 5 minutes skew)
        now = datetime.now(timezone.utc)
        max_future = now.timestamp() + 300  # 5 minutes
        
        if timestamp.timestamp() > max_future:
            result.add_error(field, f"Timestamp is too far in the future: {timestamp.isoformat()}")
        
        # Check if timestamp is too old (more than 7 days)
        min_past = now.timestamp() - (7 * 24 * 3600)  # 7 days
        
        if timestamp.timestamp() < min_past:
            result.add_warning(f"Timestamp is very old: {timestamp.isoformat()}")
    
    def _validate_metric_value(self, value: float, field: str, result: ValidationResult):
        """Validate metric value."""
        if value is None:
            result.add_error(field, "Metric value is required")
            return
        
        if not isinstance(value, (int, float)):
            result.add_error(field, f"Metric value must be numeric, got {type(value).__name__}")
            return
        
        if not (self.MIN_METRIC_VALUE <= value <= self.MAX_METRIC_VALUE):
            result.add_error(field, f"Metric value out of range: {value}, must be between {self.MIN_METRIC_VALUE} and {self.MAX_METRIC_VALUE}")
        
        # Check for NaN or infinity
        if isinstance(value, float):
            import math
            if math.isnan(value):
                result.add_error(field, "Metric value cannot be NaN")
            elif math.isinf(value):
                result.add_error(field, "Metric value cannot be infinite")
    
    def _validate_duration(self, duration: float, field: str, result: ValidationResult):
        """Validate duration in milliseconds."""
        if not isinstance(duration, (int, float)):
            result.add_error(field, f"Duration must be numeric, got {type(duration).__name__}")
            return
        
        if duration < self.MIN_DURATION_MS:
            result.add_error(field, f"Duration cannot be negative: {duration}")
        
        if duration > self.MAX_DURATION_MS:
            result.add_error(field, f"Duration too large: {duration}ms, max {self.MAX_DURATION_MS}ms")
    
    def _validate_dimensions(self, dimensions: Dict[str, Any], field: str, result: ValidationResult):
        """Validate dimensions dictionary."""
        if not isinstance(dimensions, dict):
            result.add_error(field, f"Dimensions must be dictionary, got {type(dimensions).__name__}")
            return
        
        if len(dimensions) > self.MAX_DIMENSIONS:
            result.add_error(field, f"Too many dimensions: {len(dimensions)}, max {self.MAX_DIMENSIONS}")
        
        for key, value in dimensions.items():
            self._validate_dimension_key(key, f"{field}.{key}", result)
            self._validate_dimension_value(value, f"{field}.{key}", result)
    
    def _validate_dimension_key(self, key: str, field: str, result: ValidationResult):
        """Validate dimension key."""
        if not isinstance(key, str):
            result.add_error(field, f"Dimension key must be string, got {type(key).__name__}")
            return
        
        if len(key) > self.DIMENSION_KEY_MAX_LENGTH:
            result.add_error(field, f"Dimension key too long: {len(key)} chars, max {self.DIMENSION_KEY_MAX_LENGTH}")
            return
        
        if not self.DIMENSION_KEY_PATTERN.match(key):
            result.add_error(field, "Dimension key must start with letter/underscore and contain only alphanumeric/underscore characters")
    
    def _validate_dimension_value(self, value: Any, field: str, result: ValidationResult):
        """Validate dimension value."""
        if value is None:
            return  # None values are allowed
        
        # Convert to string for length validation
        str_value = str(value)
        
        if len(str_value) > self.DIMENSION_VALUE_MAX_LENGTH:
            result.add_error(field, f"Dimension value too long: {len(str_value)} chars, max {self.DIMENSION_VALUE_MAX_LENGTH}")
        
        # Warn about non-string values that will be converted
        if not isinstance(value, (str, int, float, bool)):
            result.add_warning(f"Dimension value at {field} will be converted to string: {type(value).__name__}")
    
    def _validate_metadata(self, metadata: Dict[str, Any], field: str, result: ValidationResult):
        """Validate metadata dictionary."""
        if not isinstance(metadata, dict):
            result.add_error(field, f"Metadata must be dictionary, got {type(metadata).__name__}")
            return
        
        if len(metadata) > self.MAX_METADATA_FIELDS:
            result.add_error(field, f"Too many metadata fields: {len(metadata)}, max {self.MAX_METADATA_FIELDS}")
        
        for key, value in metadata.items():
            self._validate_metadata_key(key, f"{field}.{key}", result)
            self._validate_metadata_value(value, f"{field}.{key}", result)
    
    def _validate_metadata_key(self, key: str, field: str, result: ValidationResult):
        """Validate metadata key."""
        if not isinstance(key, str):
            result.add_error(field, f"Metadata key must be string, got {type(key).__name__}")
            return
        
        if len(key) > self.METADATA_KEY_MAX_LENGTH:
            result.add_error(field, f"Metadata key too long: {len(key)} chars, max {self.METADATA_KEY_MAX_LENGTH}")
    
    def _validate_metadata_value(self, value: Any, field: str, result: ValidationResult):
        """Validate metadata value."""
        if value is None:
            return  # None values are allowed
        
        # Convert to string for length validation if not already serializable
        if isinstance(value, (dict, list)):
            try:
                import json
                str_value = json.dumps(value)
            except (TypeError, ValueError):
                result.add_error(field, f"Metadata value at {field} is not JSON serializable")
                return
        else:
            str_value = str(value)
        
        if len(str_value) > self.METADATA_VALUE_MAX_LENGTH:
            result.add_error(field, f"Metadata value too long: {len(str_value)} chars, max {self.METADATA_VALUE_MAX_LENGTH}")


# Global validator instance
validator = MetricsValidator()