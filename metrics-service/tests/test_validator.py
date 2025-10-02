"""Tests for the data validation module."""
import pytest
import math
from datetime import datetime, timezone, timedelta

from app.core.validator import MetricsValidator, ValidationResult, ValidationError
from app.core.models import MetricType, Metric, MetricRequest


class TestValidationResult:
    """Test ValidationResult class."""
    
    def test_validation_result_initialization(self):
        """Test ValidationResult initializes correctly."""
        result = ValidationResult()
        assert result.errors == []
        assert result.warnings == []
        assert result.is_valid is True
    
    def test_add_error(self):
        """Test adding validation errors."""
        result = ValidationResult()
        result.add_error("field1", "error message", "bad_value")
        
        assert len(result.errors) == 1
        assert result.errors[0].field == "field1"
        assert result.errors[0].message == "error message"
        assert result.errors[0].value == "bad_value"
        assert result.is_valid is False
    
    def test_add_warning(self):
        """Test adding validation warnings."""
        result = ValidationResult()
        result.add_warning("warning message")
        
        assert len(result.warnings) == 1
        assert result.warnings[0] == "warning message"
        assert result.is_valid is True  # Warnings don't affect validity
    
    def test_get_error_messages(self):
        """Test getting error message strings."""
        result = ValidationResult()
        result.add_error("field1", "error1")
        result.add_error("field2", "error2")
        
        messages = result.get_error_messages()
        assert len(messages) == 2
        assert "field1: error1" in messages
        assert "field2: error2" in messages


class TestValidationError:
    """Test ValidationError class."""
    
    def test_validation_error_creation(self):
        """Test ValidationError creation and string representation."""
        error = ValidationError("test_field", "test message", "test_value")
        
        assert error.field == "test_field"
        assert error.message == "test message"
        assert error.value == "test_value"
        assert str(error) == "test_field: test message"


class TestServiceValidation:
    """Test service name validation."""
    
    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return MetricsValidator()
    
    def test_valid_service_names(self, validator):
        """Test valid service names."""
        result = ValidationResult()
        
        valid_names = [
            "auth-server",
            "metrics_service",
            "my-service-123",
            "ServiceName",
            "service123"
        ]
        
        for name in valid_names:
            validator._validate_service_name(name, result)
        
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_invalid_service_names(self, validator):
        """Test invalid service names."""
        invalid_cases = [
            ("", "Service name is required"),
            ("service with spaces", "must contain only alphanumeric"),
            ("service@domain", "must contain only alphanumeric"),
            ("service.name", "must contain only alphanumeric"),
            ("a" * 101, "Service name too long")
        ]
        
        for name, expected_error in invalid_cases:
            result = ValidationResult()
            validator._validate_service_name(name, result)
            
            assert not result.is_valid
            assert any(expected_error in error.message for error in result.errors)
    
    def test_non_string_service_name(self, validator):
        """Test non-string service name."""
        result = ValidationResult()
        validator._validate_service_name(123, result)
        
        assert not result.is_valid
        assert "must be string" in result.errors[0].message


class TestVersionValidation:
    """Test version validation."""
    
    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return MetricsValidator()
    
    def test_valid_versions(self, validator):
        """Test valid semantic versions."""
        result = ValidationResult()
        
        valid_versions = [
            "1.0.0",
            "10.20.30",
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-beta.2",
            "2.0.0-rc.1"
        ]
        
        for version in valid_versions:
            validator._validate_version(version, result)
        
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_invalid_versions(self, validator):
        """Test versions that generate warnings."""
        warning_cases = [
            "1.0",
            "v1.0.0",
            "latest",
            "1.0.0.0",
            "1.0-SNAPSHOT"
        ]
        
        for version in warning_cases:
            result = ValidationResult()
            validator._validate_version(version, result)
            
            assert result.is_valid  # Warnings don't make it invalid
            assert len(result.warnings) > 0
            assert "semantic versioning" in result.warnings[0]


class TestMetricValueValidation:
    """Test metric value validation."""
    
    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return MetricsValidator()
    
    def test_valid_metric_values(self, validator):
        """Test valid metric values."""
        result = ValidationResult()
        
        valid_values = [0, 1, -1, 0.5, -0.5, 1000, 1000.5, 1e6, -1e6]
        
        for value in valid_values:
            validator._validate_metric_value(value, "test_field", result)
        
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_invalid_metric_values(self, validator):
        """Test invalid metric values."""
        invalid_cases = [
            (None, "required"),
            ("not_a_number", "must be numeric"),
            (float('nan'), "cannot be NaN"),
            (float('inf'), "cannot be infinite"),
            (-float('inf'), "cannot be infinite"),
            (1e15, "out of range"),
            (-1e15, "out of range")
        ]
        
        for value, expected_error in invalid_cases:
            result = ValidationResult()
            validator._validate_metric_value(value, "test_field", result)
            
            assert not result.is_valid
            assert any(expected_error in error.message for error in result.errors)


class TestDimensionsValidation:
    """Test dimensions validation."""
    
    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return MetricsValidator()
    
    def test_valid_dimensions(self, validator):
        """Test valid dimensions."""
        result = ValidationResult()
        
        valid_dimensions = {
            "success": True,
            "method": "GET",
            "status_code": 200,
            "user_id": "user123",
            "_private": "value"
        }
        
        validator._validate_dimensions(valid_dimensions, "dimensions", result)
        
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_invalid_dimension_keys(self, validator):
        """Test invalid dimension keys."""
        invalid_cases = [
            ({"123key": "value"}, "must start with letter"),
            ({"key-name": "value"}, "must start with letter"),
            ({"key.name": "value"}, "must start with letter"),
            ({"a" * 51: "value"}, "too long")
        ]
        
        for dimensions, expected_error in invalid_cases:
            result = ValidationResult()
            validator._validate_dimensions(dimensions, "dimensions", result)
            
            assert not result.is_valid
            assert any(expected_error in error.message for error in result.errors)
    
    def test_too_many_dimensions(self, validator):
        """Test too many dimensions."""
        result = ValidationResult()
        
        # Create more than MAX_DIMENSIONS
        too_many_dims = {f"key_{i}": f"value_{i}" for i in range(25)}
        
        validator._validate_dimensions(too_many_dims, "dimensions", result)
        
        assert not result.is_valid
        assert "Too many dimensions" in result.errors[0].message
    
    def test_dimension_value_length(self, validator):
        """Test dimension value length validation."""
        result = ValidationResult()
        
        long_value = "x" * 201  # Exceeds DIMENSION_VALUE_MAX_LENGTH
        dimensions = {"key": long_value}
        
        validator._validate_dimensions(dimensions, "dimensions", result)
        
        assert not result.is_valid
        assert "too long" in result.errors[0].message


class TestTimestampValidation:
    """Test timestamp validation."""
    
    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return MetricsValidator()
    
    def test_valid_timestamps(self, validator):
        """Test valid timestamps."""
        result = ValidationResult()
        
        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)
        near_future = now + timedelta(minutes=2)
        
        for timestamp in [now, past, near_future]:
            validator._validate_timestamp(timestamp, "timestamp", result)
        
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_future_timestamp(self, validator):
        """Test timestamp too far in future."""
        result = ValidationResult()
        
        far_future = datetime.now(timezone.utc) + timedelta(hours=1)
        validator._validate_timestamp(far_future, "timestamp", result)
        
        assert not result.is_valid
        assert "too far in the future" in result.errors[0].message
    
    def test_old_timestamp(self, validator):
        """Test very old timestamp generates warning."""
        result = ValidationResult()
        
        old_timestamp = datetime.now(timezone.utc) - timedelta(days=8)
        validator._validate_timestamp(old_timestamp, "timestamp", result)
        
        assert result.is_valid  # Old timestamps are warnings, not errors
        assert len(result.warnings) > 0
        assert "very old" in result.warnings[0]


class TestFullRequestValidation:
    """Test complete request validation."""
    
    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return MetricsValidator()
    
    def test_valid_request(self, validator):
        """Test completely valid request."""
        request = MetricRequest(
            service="test-service",
            version="1.0.0",
            instance_id="instance-01",
            metrics=[
                Metric(
                    type=MetricType.AUTH_REQUEST,
                    value=1.0,
                    duration_ms=150.5,
                    dimensions={"success": True, "method": "oauth"},
                    metadata={"user_agent": "test-client"}
                )
            ]
        )
        
        result = validator.validate_metric_request(request)
        
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_empty_metrics_array(self, validator):
        """Test request with empty metrics array."""
        request = MetricRequest(
            service="test-service",
            metrics=[]
        )
        
        result = validator.validate_metric_request(request)
        
        assert not result.is_valid
        assert "At least one metric is required" in result.errors[0].message
    
    def test_too_many_metrics(self, validator):
        """Test request with too many metrics."""
        # Create 101 metrics (exceeds limit of 100)
        metrics = []
        for i in range(101):
            metrics.append(Metric(
                type=MetricType.AUTH_REQUEST,
                value=1.0
            ))
        
        request = MetricRequest(
            service="test-service",
            metrics=metrics
        )
        
        result = validator.validate_metric_request(request)
        
        assert not result.is_valid
        assert "Too many metrics" in result.errors[0].message
    
    def test_invalid_service_propagates(self, validator):
        """Test that invalid service name propagates to result."""
        request = MetricRequest(
            service="invalid service name",  # Contains space
            metrics=[
                Metric(type=MetricType.AUTH_REQUEST, value=1.0)
            ]
        )
        
        result = validator.validate_metric_request(request)
        
        assert not result.is_valid
        assert any("alphanumeric" in error.message for error in result.errors)
    
    def test_metric_validation_with_index(self, validator):
        """Test that metric validation includes array index in error messages."""
        # Create a mock metric with invalid dimensions to test indexing
        metric1 = Metric(type=MetricType.AUTH_REQUEST, value=1.0)  # Valid
        metric2 = Metric(
            type=MetricType.AUTH_REQUEST, 
            value=1.0,
            dimensions={"invalid-key": "value"}  # Invalid key format
        )
        
        request = MetricRequest(
            service="test-service",
            metrics=[metric1, metric2]
        )
        
        result = validator.validate_metric_request(request)
        
        assert not result.is_valid
        assert any("metrics[1]" in error.field for error in result.errors)